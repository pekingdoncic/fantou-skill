#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
返投招商 Skill —— 核心引擎

输入：城市 + 产业目标（+ 基金代号）
输出：五件套（产业链分析 / 企业筛选 / 线索卡 / 沙龙方案 / 跟进清单）

设计原则：
1. 配置驱动 —— 城市政策与返投口径全部外置到 YAML，换城市不改代码
2. 证据守卫 —— 所有企业信息强制带证据等级，D 级拦截，低置信度打标
3. 口径前置 —— 返投口径未确认时，不输出线索优先级排序
"""
import os
import re
import json
import copy
import datetime

try:
    import yaml
except ImportError:
    raise SystemExit("缺少依赖 pyyaml，请先安装：pip install pyyaml")

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE, "config")
KB_DIR = os.path.join(BASE, "kb")

EVIDENCE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1}

# industries.yaml 里的非产业节点 —— 必须统一过滤，避免「沙龙默认」被当成可选产业暴露给用户
INDUSTRY_META_KEYS = ("证据等级", "置信度规则", "沙龙默认")


# ----------------------------------------------------------------- 配置加载
def _norm(o):
    """YAML 会把 2026-04-28 之类解析成 date 对象，统一转成字符串，保证可 JSON 序列化"""
    if isinstance(o, dict):
        return {k: _norm(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_norm(v) for v in o]
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    return o


def _load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return _norm(yaml.safe_load(f))


def load_all_config():
    return {
        "cities": _load_yaml(os.path.join(CONFIG_DIR, "cities.yaml")),
        "funds": _load_yaml(os.path.join(CONFIG_DIR, "fantou_rules.yaml")),
        "industries": _load_yaml(os.path.join(CONFIG_DIR, "industries.yaml")),
        "companies": _load_yaml(os.path.join(KB_DIR, "companies.yaml"))["companies"],
    }


def industry_keys(industries_cfg):
    """industries.yaml 里真正的产业节点（排除证据等级/置信度规则/沙龙默认等元数据节点）"""
    return [k for k, v in industries_cfg.items()
            if isinstance(v, dict) and k not in INDUSTRY_META_KEYS]


def match_industry(industries_cfg, industry_name):
    """按别名匹配产业链框架；匹配不到返回 None（不脑补）"""
    for key in industry_keys(industries_cfg):
        val = industries_cfg[key]
        if key == industry_name or industry_name in key:
            return key, val
        for alias in val.get("别名", []) or []:
            if alias in industry_name or industry_name in alias:
                return key, val
    return None, None


# ------------------------------------------------------------- EvidenceGuard
class EvidenceGuard:
    """
    证据守卫：只做拦截，不生成内容。

    规则：
      R1 每条企业记录必须有 证据等级
      R2 证据等级 D 或 置信度 低 → 标记「禁止对外」
      R3 沙龙方案的评价指标不得含 参会人数/曝光量/名片 类考核项
      R4 跟进清单「证据链接」为空的记录不得输出
      R5 返投口径未确认 → 禁止输出优先级排序
    """

    def __init__(self):
        self.blocked = []
        self.warned = []
        self.checked = 0

    def check_companies(self, companies):
        out = []
        for c in companies:
            self.checked += 1
            lvl = (c.get("证据等级") or "").strip().upper()
            conf = c.get("置信度") or ""
            if lvl not in EVIDENCE_ORDER:
                self.blocked.append(f"R1 缺少证据等级：{c.get('名称')}")
                c["_禁止对外"] = True
                c["_拦截原因"] = "缺少证据等级"
            elif lvl == "D" or conf == "低":
                self.warned.append(f"R2 低置信度打标：{c.get('名称')}（等级 {lvl}）")
                c["_禁止对外"] = True
                c["_拦截原因"] = f"证据等级 {lvl} / 置信度 {conf} —— 未经核实，禁止对外"
            else:
                c["_禁止对外"] = False
            out.append(c)
        return out

    def check_salon(self, salon):
        banned = ["参会人数", "曝光量", "名片"]
        for m in salon.get("评价指标", []):
            if any(b in m for b in banned):
                self.blocked.append(f"R3 沙龙评价指标含被禁项：{m}")
        return salon

    def check_followup(self, rows):
        kept = []
        for r in rows:
            if not (r.get("证据链接") or "").strip():
                self.warned.append(f"R4 证据链接为空，已标记待补：{r.get('线索编号')}")
                r["证据链接"] = "待补充"
            kept.append(r)
        return kept

    def gate_priority(self, fund):
        """R5：口径未确认时禁止优先级排序"""
        if not fund:
            return False, "未指定基金，无法判定返投口径 —— 不输出优先级排序"
        if fund.get("确认状态") != "已确认":
            return False, f"返投口径「{fund.get('基金名称')}」确认状态为「{fund.get('确认状态')}」—— 不输出优先级排序"
        return True, ""

    def summary(self):
        return {
            "检查条数": self.checked,
            "拦截": self.blocked,
            "打标": self.warned,
            "拦截数": len(self.blocked),
            "打标数": len(self.warned),
        }


# ------------------------------------------------------------------- 五段流水线
def stage1_chain(city_cfg, industry_key, industry_cfg, city_name, industry):
    """S1 产业链分析"""
    chain = {
        "标题": f"{city_name} · {industry} 产业链分析",
        "框架": "强链 / 固链 / 延链 / 补链",
        "层级": [],
        "补链优先级": [],
        "结论": "",
        "数据来源": city_cfg.get("来源汇总", []),
    }
    layer_map = [
        ("上游 · 核心零部件", "上游核心零部件", "强链"),
        ("中游 · 本体与集成", "中游本体与集成", "固链"),
        ("下游 · 应用场景", "下游应用场景", "延链"),
    ]
    for title, key, tag in layer_map:
        segs = industry_cfg.get(key, []) if industry_cfg else []
        chain["层级"].append({
            "层级": title,
            "环节": segs,
            "判断": tag,
            "本地代表企业": city_cfg.get("本地代表企业", []) if "上游" in title or "中游" in title else [],
            "本地条件": "；".join(city_cfg.get("稀缺筹码", [])[:3]) if "下游" in title else "",
        })

    for name, spec in (industry_cfg or {}).get("补链优先级", {}).items():
        chain["补链优先级"].append({
            "环节": name,
            "优先级": spec.get("优先级"),
            "理由": spec.get("理由"),
        })
    chain["补链优先级"].sort(key=lambda x: x["优先级"])

    chips = city_cfg.get("稀缺筹码", [])
    chain["结论"] = (
        f"{city_name}的筹码类型为「{city_cfg.get('筹码类型')}」，"
        f"核心筹码：{'；'.join(chips[:2]) if chips else '待补充'}。"
        f"招商的边际价值集中在补链环节（{'、'.join([p['环节'] for p in chain['补链优先级'] if p['优先级'] == 'P0']) or '待定'}），"
        f"而非重复引入已有环节的厂商。"
    )
    return chain


def stage2_screen(city_cfg, city_name, industry, companies, guard, allow_priority=True):
    """
    S2 企业筛选

    注意：`allow_priority=False` 时（返投口径未确认）**不打分、不排序**，
    只按环节分组平铺 —— 这是 R5 门控的实质要求，不能只挡线索卡。
    """
    EVIDENCE_SCORE = {"A": 30, "B": 25, "C": 15, "D": 5}
    CONF_SCORE = {"中高": 20, "中": 15, "低": 0}
    local_kw = city_cfg.get("名称", "")

    scored = []
    for c in companies:
        score = 0
        reasons = []

        p = c.get("优先级")
        if p == "P0":
            score += 40; reasons.append("P0 补链环节 +40")
        elif p == "P1":
            score += 25; reasons.append("P1 补链环节 +25")

        lvl = c.get("证据等级", "D")
        add = EVIDENCE_SCORE.get(lvl, 0)
        score += add
        reasons.append(f"证据等级 {lvl} +{add}")

        conf = c.get("置信度", "")
        add = CONF_SCORE.get(conf, 0)
        score += add
        if conf:
            reasons.append(f"置信度「{conf}」 +{add}")

        if local_kw and local_kw[:2] in (c.get("所在地") or ""):
            reasons.append("已在本地（异地招商边际价值较低）")
        else:
            score += 10
            reasons.append("异地企业 +10")

        rec = {**c, "_匹配度": min(score, 100), "_打分理由": reasons}
        if not allow_priority:
            # 口径未确认 → 不给分、不给理由，避免任何形式的优先级暗示
            rec["_匹配度"] = None
            rec["_打分理由"] = []
        scored.append(rec)

    if allow_priority:
        scored.sort(key=lambda x: x["_匹配度"], reverse=True)
    else:
        # 未确认口径时按「环节 + 企业名」稳定排列，不做价值判断
        scored.sort(key=lambda x: (x.get("环节") or "zzz", x.get("名称") or ""))

    return {
        "标题": f"{city_name} · {industry} 目标企业筛选",
        "候选池": len(companies),
        "进入打分": len(scored),
        "推荐": len([s for s in scored if not s.get("_禁止对外")]),
        "已排序": allow_priority,
        "企业": scored,
    }


def stage3_lead_cards(screen, city_name, city_cfg, fund, allow_priority):
    """S3 线索卡"""
    cards = []
    idx = 0
    for c in screen["企业"]:
        idx += 1
        card = {
            "线索编号": f"LEAD-{datetime.date.today():%Y%m%d}-{idx:03d}",
            "企业": c.get("名称"),
            "环节": c.get("环节"),
            "触发信号": c.get("扩张信号"),
            "信号类型": c.get("信号类型"),
            "证据等级": c.get("证据等级"),
            "置信度": c.get("置信度"),
            "可能需求": c.get("关键问题") or c.get("关键发现") or "待补充",
            "匹配园区": city_cfg.get("名称"),
            "对接理由": (c.get("触达路径") or {}).get(city_name.split("（")[0], "") or city_cfg.get("邀约理由模板", ""),
            "风险": c.get("风险"),
            "责任人": "待指定（IR + 投资团队）",
            "跟进状态": "待验证" if c.get("_禁止对外") else "待交叉验证",
            "证据链接": "；".join(c.get("证据来源", [])) or "待补充",
            "下一步": c.get("下一步"),
            "禁止对外": c.get("_禁止对外", False),
            "拦截原因": c.get("_拦截原因", ""),
            "匹配度": c.get("_匹配度"),
        }
        cards.append(card)

    if allow_priority:
        cards.sort(key=lambda x: x["匹配度"], reverse=True)
    return {"标题": f"{city_name} · 线索卡", "卡片": cards, "已排序": allow_priority}


def stage4_salon(city_cfg, city_name, industry, industry_cfg, salon_default, leads):
    """S4 沙龙方案"""
    needs_side = [c["企业"] for c in leads["卡片"] if "整机" in (c.get("环节") or "")]
    targets = [c["企业"] for c in leads["卡片"] if "整机" not in (c.get("环节") or "")]
    return {
        "标题": f"{city_name} · {industry} 补链闭门沙龙方案",
        "主题": f"{city_name}具身智能「补链」闭门沙龙 —— 传感器与关节模组专场",
        "定位": "不做大型路演，做 20 人以内技术-产业-资本三方闭门对接",
        "规模上限": salon_default.get("规模上限", 20),
        "人群配比": salon_default.get("人群配比", {}),
        "时间地点": f"建议次季度，{city_cfg.get('名称')}重点园区",
        "议程": [
            {"时段": "14:00-14:20", "环节": "开场：本地产业政策与场景机会清单解读", "主讲": "地方产业主管部门"},
            {"时段": "14:20-15:00", "环节": "需求侧：本体厂商对核心零部件的真实技术要求与采购节奏",
             "主讲": " / ".join(needs_side) or "本地本体厂商"},
            {"时段": "15:00-15:40", "环节": "供给侧：核心零部件的技术路线与量产挑战",
             "主讲": " / ".join(targets) or "目标企业"},
            {"时段": "15:40-16:30", "环节": "一对一对接（预排 6 组，每组 8 分钟）", "主讲": "全体"},
            {"时段": "16:30-17:00", "环节": "返投口径与落地政策答疑（闭门）", "主讲": "基金 + 政府"},
        ],
        "邀约理由模板": city_cfg.get("邀约理由模板", ""),
        "评价指标": salon_default.get("评价指标", []),
        "明确不考核": salon_default.get("禁止考核", []),
    }


def _add_workdays(start, n):
    """从 start 往后推 n 个工作日（跳过周六周日）"""
    d = start
    added = 0
    while added < n:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def stage5_followup(leads, fund, allow_priority):
    """
    S5 跟进清单

    截止日不再留空 —— 按「有无可执行动作」自动给出期限：
      · 有明确下一步动作 → 5 个工作日内
      · 无下一步动作     → 留空并标记「待指定动作」，且阶段不得推进
    理由：跟进清单的价值在于「谁在什么时候做什么」，留空的截止日等于没有跟进。
    """
    rows = []
    today = datetime.date.today()

    for c in leads["卡片"]:
        has_action = bool((c.get("下一步") or "").strip())
        due = _add_workdays(today, 5).isoformat() if has_action else ""

        stage = c["跟进状态"]
        notes = [c.get("拦截原因") or ""]
        if not has_action:
            stage = "待指定动作"
            notes.append("缺下一步动作，阶段不得推进")
        if c["证据链接"] in ("", "待补充"):
            notes.append("证据链接待补充")

        rows.append({
            "线索编号": c["线索编号"],
            "企业": c["企业"],
            "环节": c["环节"],
            "阶段": stage,
            "责任人": c["责任人"],
            "下一步动作": c["下一步"] or "待指定",
            "截止日": due,
            "证据链接": "" if c["证据链接"] == "待补充" else c["证据链接"],
            "置信度": c["置信度"],
            "返投口径适配": (
                f"口径未确认（研发中心是否计入：{fund.get('是否含研发中心')}）"
                if fund else "未指定基金，待确认"
            ),
            "备注": "；".join(x for x in notes if x),
        })
    return {"标题": "跟进清单", "字段": list(rows[0].keys()) if rows else [], "行": rows}


# ------------------------------------------------------------------- 运行入口
def _industry_terms(industry_cfg):
    """
    取出用于在线检索的「具体环节词」。

    优先用配置里显式声明的 `在线检索词`（推荐，可控）；
    没有则从环节名自动派生（去括号、去斜杠、去「与」）。
    注意：必须用具体词，泛词（机器人）在巨潮接口会匹配到大量噪音。
    """
    explicit = (industry_cfg or {}).get("在线检索词")
    if explicit:
        return [t for t in explicit if len(t) >= 3][:10]

    terms = []
    for key in ("上游核心零部件", "中游本体与集成", "下游应用场景"):
        for seg in (industry_cfg or {}).get(key, []):
            for part in re.split(r"[（(/]", seg):
                part = part.strip().lstrip("与").strip()
                if len(part) >= 3 and part not in terms:
                    terms.append(part)
    return terms[:10]


# 检索深度 → 抓取范围。
# 之前 depth 只改报告里一个 token 预估数字，对结果零影响（是个假控件），现在真正生效。
DEPTH_SOURCES = {
    "light": ["巨潮资讯（上市公司公告）"],
    "standard": ["巨潮资讯（上市公司公告）", "东方财富（上市公司公告）"],
    "deep": None,   # None = 全部已接入的源（含媒体资讯）
}
DEPTH_DAYS = {"light": 365, "standard": 540, "deep": 730}
DEPTH_LABEL = {"light": "轻量（仅公告，最快）",
               "standard": "标准（公告 + 东财公告）",
               "deep": "重度（全部源，含媒体资讯，最全）"}


def _industry_words(industry_cfg):
    """
    取出用于**过滤跨行业噪音**的行业词表。

    东方财富是全文模糊检索：搜「减速器 扩产」会返回「胶原蛋白扩产竞速」，
    必须要求标题里出现本行业的词才保留。
    """
    explicit = (industry_cfg or {}).get("在线行业词")
    if explicit:
        return list(explicit)
    # 兜底：从环节名派生
    words = []
    for key in ("上游核心零部件", "中游本体与集成", "下游应用场景"):
        for seg in (industry_cfg or {}).get(key, []):
            for part in re.split(r"[（(/、]", seg):
                part = part.strip().lstrip("与").strip()
                if len(part) >= 2 and part not in words:
                    words.append(part)
    return words


def _infer_link(rec, industry_cfg):
    """
    从标题推断企业所属环节。

    在线抓来的新闻标题不含结构化环节字段，必须靠关键词推断。
    规则：**长词优先**（「无框力矩电机」优先于「电机」），推不出就留空，不硬塞。
    """
    title = " ".join(filter(None, [rec.get("扩张信号"), rec.get("关键发现")]))
    if not title:
        return ""

    kw_map = (industry_cfg or {}).get("环节关键词") or {}
    hits = []
    for link, kws in kw_map.items():
        for kw in kws:
            if kw in title:
                hits.append((len(kw), link))
    if hits:
        hits.sort(reverse=True)
        return hits[0][1]

    # 兜底：用补链优先级的键名直接匹配
    for name in ((industry_cfg or {}).get("补链优先级") or {}):
        for kw in re.split(r"[/（(、]", name):
            kw = kw.strip()
            if len(kw) >= 3 and kw in title:
                return name
    return ""


def _assign_priority(rec, industry_cfg):
    """给在线抓来的企业按环节匹配补链优先级"""
    prio_map = (industry_cfg or {}).get("补链优先级", {})

    # 先补环节（在线记录没有这个字段）
    if not rec.get("环节") or rec.get("环节") == "待归类":
        inferred = _infer_link(rec, industry_cfg)
        rec["环节"] = inferred or "待归类"

    env = rec.get("环节") or ""
    if not env or env == "待归类":
        rec.setdefault("优先级", "")
        return rec

    # 1) 整名互含
    for name, spec in prio_map.items():
        if name and (name in env or env in name):
            rec["优先级"] = spec.get("优先级", "")
            return rec

    # 2) 分词后双向匹配（'减速器' ↔ '谐波减速器'）
    for name, spec in prio_map.items():
        for kw in re.split(r"[/（(、]", name):
            kw = kw.strip()
            if len(kw) >= 2 and (kw in env or env in kw):
                rec["优先级"] = spec.get("优先级", "")
                return rec

    rec.setdefault("优先级", "")
    return rec


def run(city_name, industry, fund_name=None, depth="standard", live=False,
        live_days=None, live_limit=60, live_records=None):
    """
    :param depth:        检索深度 light|standard|deep —— 真正控制抓取范围（源与回溯天数）
    :param live_records: 预先抓好的 (records, log)，用于复用同一次抓取跑多个城市组合，
                         避免为每个组合重复请求外部源。传了它就不需要 live=True。
    """
    import time as _time
    _t0 = _time.time()

    if depth not in DEPTH_SOURCES:
        depth = "standard"
    if live_days is None:
        live_days = DEPTH_DAYS[depth]

    cfg = load_all_config()

    city_cfg = cfg["cities"].get(city_name)
    if not city_cfg:
        raise ValueError(f"未找到城市配置「{city_name}」。可选：{list(cfg['cities'].keys())}")

    fund = cfg["funds"].get(fund_name) if fund_name else None

    industry_key, industry_cfg = match_industry(cfg["industries"], industry)
    if not industry_cfg:
        raise ValueError(
            f"未找到产业「{industry}」的产业链框架。可选：{industry_keys(cfg['industries'])}"
        )

    # ---- 在线数据抓取（可选）----
    companies = list(cfg["companies"])
    live_log, live_terms, raw_signals = [], [], []
    if live or live_records is not None:
        try:
            live_terms = _industry_terms(industry_cfg)
            if live_records is not None:
                # 复用预先抓好的结果（深拷贝，避免 _assign_priority 跨组合互相污染）
                _recs, live_log = live_records
                recs = copy.deepcopy(_recs)
            else:
                import datasources
                iwords = _industry_words(industry_cfg)
                srcs = datasources.sources_by_name(DEPTH_SOURCES.get(depth))
                recs, live_log = datasources.fetch_expansion_signals(
                    live_terms, days=live_days, limit=live_limit,
                    sources=srcs, industry_words=iwords)
            # 有企业名的 → 并入企业库
            # 无企业名的 → 进「原始信号流」原文展示，**不脑补企业名**
            by_name = {c.get("名称"): c for c in companies}
            for r in recs:
                if r.get("名称"):
                    r["_在线"] = True
                    by_name[r["名称"]] = _assign_priority(r, industry_cfg)
                else:
                    raw_signals.append(r)
            companies = list(by_name.values())
        except Exception as e:
            live_log = [{"数据源": "在线抓取", "证据等级": "-", "返回条数": 0,
                         "状态": f"失败：{type(e).__name__}: {e}"}]
    live_on = bool(live or live_records is not None)

    guard = EvidenceGuard()

    companies = guard.check_companies(companies)
    allow_priority, priority_note = guard.gate_priority(fund)

    chain = stage1_chain(city_cfg, industry_key, industry_cfg, city_name, industry)
    screen = stage2_screen(city_cfg, city_name, industry, companies, guard, allow_priority)
    leads = stage3_lead_cards(screen, city_name, city_cfg, fund, allow_priority)
    salon = stage4_salon(city_cfg, city_name, industry, industry_cfg,
                         cfg["industries"].get("沙龙默认", {}), leads)
    salon = guard.check_salon(salon)
    followup = stage5_followup(leads, fund, allow_priority)
    followup["行"] = guard.check_followup(followup["行"])

    elapsed = round(_time.time() - _t0, 1)

    # 运行报告
    est_in = {"light": 45000, "standard": 90300, "deep": 180600}[depth]
    report = {
        "运行时间": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "耗时秒": elapsed,
        "城市": city_name,
        "产业": industry,
        "基金": fund_name or "未指定",
        "运行模式": "在线抓取 + 内置库" if live_on else "离线模板模式（M1）",
        "检索深度": DEPTH_LABEL[depth],
        "证据守卫": guard.summary(),
        "优先级排序": {"允许": allow_priority, "说明": priority_note},
        "在线抓取": {
            "已启用": live_on,
            "检索词": live_terms,
            "回溯天数": live_days if live_on else None,
            "各源状态": live_log,
            "企业线索数": len([c for c in companies if c.get("_在线")]),
            "原始信号数": len(raw_signals),
        },
        "原始信号流": [
            {"标题": r.get("扩张信号"), "信号类型": r.get("信号类型"),
             "证据等级": r.get("证据等级"), "证据来源": r.get("证据来源", [])}
            for r in raw_signals
        ],
        "LLM模式预估token": {"输入": est_in, "输出": int(est_in * 0.187),
                          "说明": "离线模式不消耗 token，此为切换 LLM 模式时的预估"},
        "配置来源": {
            "城市政策": f"config/cities.yaml → {city_name}",
            "返投口径": f"config/fantou_rules.yaml → {fund_name}" if fund_name else "未指定",
            "产业框架": f"config/industries.yaml → {industry_key}",
            "企业库": "kb/companies.yaml" + (" + 在线抓取" if live_on else ""),
        },
    }

    return {
        "meta": {
            "skill": "返投招商Skill",
            "version": "1.0",
            "generated_at": report["运行时间"],
            "disclaimer": "本工具输出为线索池，非决策结论。所有企业信息须经投资团队交叉验证后方可对外。",
        },
        "cityCfg": city_cfg,
        "fundCfg": fund or {},
        "industryCfg": industry_cfg,
        "artifacts": {
            "chain": chain,
            "screen": screen,
            "leads": leads,
            "salon": salon,
            "followup": followup,
        },
        "report": report,
    }


def list_options():
    cfg = load_all_config()
    return {
        "cities": list(cfg["cities"].keys()),
        "funds": list(cfg["funds"].keys()),
        "industries": industry_keys(cfg["industries"]),
    }


if __name__ == "__main__":
    r = run("深圳", "具身智能机器人", "基金A")
    print(json.dumps(r["report"], ensure_ascii=False, indent=2))
