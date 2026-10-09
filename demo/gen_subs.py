#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 record.sh 产出的时间戳生成 ASS 字幕。

为什么这么做：手算页面切换时间会因为命令开销累积几秒误差，
导致字幕说「企业筛选」而画面还在「产业链分析」。
改为录制时打点、后期按点生成，字幕就永远和画面对齐。

时间映射：抓取等待段 [op_run, fetch_done] 在成片里被快放 SPEED 倍。
"""
import os
import sys

DEMO = "/Users/luka7/project/fantou-skill/demo"
CLIENT = os.environ.get("CLIENT", "0") == "1"
TS = os.path.join(DEMO, "raw", "timestamps-client.txt" if CLIENT else "timestamps.txt")
OUT = os.path.join(DEMO, "subs.ass")
SPEED = 8

# ---------- 读时间戳 ----------
raw = {}
with open(TS, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        try:
            raw[k] = float(v)
        except ValueError:
            pass

if "T0_record_start" not in raw:
    sys.exit("✗ timestamps.txt 里没有 T0_record_start")

T0 = raw["T0_record_start"]
need = ["op_city", "op_depth", "op_live", "op_run", "T2_fetch_done",
        "tab_chain", "tab_screen", "tab_leads", "tab_signals",
        "tab_sources", "tab_city", "tab_report", "T3_record_stop"]
missing = [k for k in need if k not in raw]
if missing:
    sys.exit("✗ 缺少时间戳: %s" % ", ".join(missing))

# 全部转成「相对录制起点的秒数」
N = {k: v - T0 for k, v in raw.items()}

A = N["op_run"]        # 加速段起点
B = N["T2_fetch_done"]    # 加速段终点
print("原始时间轴：录制 %.1fs | 加速段 %.2fs→%.2fs (%.2fs) | 快放 %dx"
      % (N["T3_record_stop"], A, B, B - A, SPEED))


def m(t):
    """把原始时间映射到成片时间"""
    if t <= A:
        return t
    if t <= B:
        return A + (t - A) / SPEED
    return A + (B - A) / SPEED + (t - B)


# ---------- 字幕条目 ----------
# (起点表达式, 终点表达式, 文本)；表达式里可直接引用节点名
ITEMS = [
    ("0.3",              "4.2",                 "返投招商 Skill：输入「城市 + 产业目标」，自动生成招商线索池"),
    ("op_city-0.3",      "op_city+3.3",         "选择目标城市：深圳"),
    ("op_depth-0.3",     "op_depth+3.3",        "检索深度设为「重度」：覆盖全部数据源，回溯 730 天"),
    ("op_live-0.3",      "op_run-1.7",          "勾选「实时抓取在线数据」：从巨潮资讯、东方财富抓真实公告与媒体报道"),
    ("op_run-1.5",       "op_run-0.1",          "点击「运行 Skill」"),
    ("op_run+0.2",       "T2_fetch_done-0.1",   "正在抓取真实数据…（约 38 秒，此处快放）"),
    ("tab_chain+0.3",    "tab_screen-0.3",      "① 产业链分析：按「强链 / 固链 / 延链 / 补链」拆解产业"),
    ("tab_screen+0.3",   "tab_leads-0.3",       "② 企业筛选：逐条标注证据等级与置信度；口径未确认时不做优先级排序"),
    ("tab_leads+0.3",    "tab_signals-0.3",     "③ 线索卡：触发信号 · 证据链接 · 风险提示 · 下一步动作"),
    ("tab_signals+0.3",  "tab_sources-0.3",     "④ 实时信号：数据从哪来 —— 公开源的原文标题与链接"),
    ("tab_sources+0.3",  "tab_city-0.3",        "⑤ 数据源：3 个已接入，8 个规划中"),
    ("tab_city+0.3",     "tab_report-0.3",      "⑥ 城市政策：政策与返投口径独立配置，换城市不改代码"),
    ("tab_report+0.3",   "T3_record_stop-2.6",  "⑦ 运行报告：耗时 · 请求数 · 证据守卫记录，全程可审计"),
    ("T3_record_stop-2.4", "T3_record_stop-0.2", "输出为线索池，不是决策结论。所有信息可溯源、可交叉验证"),
]


def ev(expr):
    return m(float(eval(expr, {"__builtins__": {}}, dict(N))))


def ass_time(t):
    if t < 0:
        t = 0
    h = int(t // 3600)
    mi = int((t % 3600) // 60)
    s = t % 60
    return "%d:%02d:%05.2f" % (h, mi, s)


HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1600
PlayResY: 900
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Hiragino Sans GB,31,&H00FFFFFF,&H000000FF,&HA0000000,&H00000000,0,0,0,0,100,100,0.4,0,3,7,0,2,80,80,46,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

lines = []
for a, b, txt in ITEMS:
    st, en = ev(a), ev(b)
    if en <= st:
        print("  ⚠ 跳过（时间无效）: %s" % txt[:24])
        continue
    lines.append("Dialogue: 0,%s,%s,Default,,0,0,0,,%s" % (ass_time(st), ass_time(en), txt))
    print("  %7.2f → %7.2f  %s" % (st, en, txt[:40]))

with open(OUT, "w", encoding="utf-8") as f:
    f.write(HEAD + "\n".join(lines) + "\n")

print()
print("✅ 字幕已生成：%s（%d 条）" % (OUT, len(lines)))
