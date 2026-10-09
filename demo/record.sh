#!/bin/bash
# ============================================================
# 返投招商 Skill —— 演示视频录制脚本
#
# 两个关键设计（都是踩坑换来的）：
#  1) CLI 的 click 在长会话里会静默失败（错误被重定向吞掉），
#     所以标签页切换一律用页面内 JS 触发，并在点击后**回读激活标签校验**。
#  2) 每个动作都打时间戳，字幕按打点生成，不靠人算，
#     否则命令开销累积会让字幕和画面错开一整页。
# ============================================================
set -u
AB=/Users/luka7/.workbuddy-ai/binaries/node/versions/22.22.2-2/bin/agent-browser
DIR=/Users/luka7/project/fantou-skill
DEMO=$DIR/demo
CLIENT=${CLIENT:-0}          # CLIENT=1 → 对外演示版（遮蔽检索词/产出统计/配置路径）
URL=http://127.0.0.1:8848
if [ "$CLIENT" = "1" ]; then
  URL="http://127.0.0.1:8848/?demo=1"   # 页面自带脱敏：左栏提示从第一帧起就不含配置文件路径
  RAW=$DEMO/raw/client-raw.webm
  TS=$DEMO/raw/timestamps-client.txt
  LOG=$DEMO/raw/actions-client.log
else
  RAW=$DEMO/raw/demo-raw.webm
  TS=$DEMO/raw/timestamps.txt
  LOG=$DEMO/raw/actions.log
fi
mkdir -p "$DEMO/raw"
cd "$DIR" || exit 1

# --- ffmpeg 检测：agent-browser 的 record 靠外部 ffmpeg 编码 -----------------
if ! command -v ffmpeg >/dev/null 2>&1; then
  PYFF=/Users/luka7/.workbuddy-ai/binaries/python/envs/default/bin/python3
  if [ -x "$PYFF" ]; then
    SRC=$("$PYFF" -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())" 2>/dev/null)
    if [ -n "${SRC:-}" ] && [ -x "$SRC" ]; then
      mkdir -p /Users/luka7/.workbuddy-ai/bin
      ln -sf "$SRC" /Users/luka7/.workbuddy-ai/bin/ffmpeg
      export PATH="/Users/luka7/.workbuddy-ai/bin:$PATH"
    fi
  fi
fi
command -v ffmpeg >/dev/null 2>&1 || { echo "✗ 未找到 ffmpeg，请先 brew install ffmpeg"; exit 1; }

INJECT=$(base64 -i "$DEMO/cursor-inject.js" | tr -d '\n')
: > "$TS"
: > "$LOG"

# 注入本地 JS 文件 —— 必须走 TextDecoder
# atob() 只解出 Latin-1 字节串，源码里的中文会全变乱码，
# 导致所有基于中文关键词的判断（'检索词'/'接入条件'）静默失效。
inject_file() {
  local b64
  b64=$(base64 -i "$1" | tr -d '\n')
  $AB eval "eval(new TextDecoder().decode(Uint8Array.from(atob('$b64'), function(c){return c.charCodeAt(0);}))); 'ok'" >/dev/null 2>&1
}
cur() { $AB eval "window.__curEl('$1'${2:+,$2}); 'ok'" >/dev/null 2>&1; }
rip() { $AB eval "window.__curRipple(); 'ok'" >/dev/null 2>&1; }
js()  { $AB eval "$1" >/dev/null 2>&1; }
active() { $AB eval "(document.querySelector('#tabs .tab.on')||{}).textContent" 2>/dev/null | tail -1 | tr -d '"'; }

# 带超时的 eval —— 防止「页面卡住 → 回读永不返回 → 整个录制静默挂死」。
# 2026-10-08 实测：脱敏脚本里若挂 MutationObserver，抓取期间页面始终存在
# pending timer，eval 被拖到超时，录制卡在等待循环里 11 分钟没有任何输出。
to() { perl -e 'alarm shift; exec @ARGV' "$1" "$AB" eval "$2" 2>/dev/null | tail -1; }

cleanup() { $AB record stop >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "[1/4] 准备干净环境…"
$AB close --all >/dev/null 2>&1 || true
$AB set viewport 1600 900 >/dev/null 2>&1
$AB open "$URL" >/dev/null 2>&1
js "localStorage.clear(); sessionStorage.clear(); 'ok'"
$AB open "$URL" >/dev/null 2>&1
sleep 1

echo "[2/4] 开始录制…"
$AB record start "$RAW" "$URL" >/dev/null 2>&1
T0=$(date +%s.%N)
# 遮蔽脚本放在第一条注入（record start 会重载页面，注入只能在其之后）
if [ "$CLIENT" = "1" ]; then
  inject_file "$DEMO/mask-client.js"
  # 注入是静默的（stderr 被吞），必须回读确认，否则会录出一版「以为遮了其实没遮」的成片
  MASKED=$($AB eval "typeof window.__maskClient" 2>/dev/null | tail -1 | tr -d '"')
  echo "  · 遮蔽脚本 __maskClient = $MASKED"
  if [ "$MASKED" != "function" ]; then
    echo "  ✗ 遮蔽脚本注入失败，中止录制（避免录出未遮蔽的对外版）"
    exit 1
  fi
fi
sleep 0.5
js "eval(atob('$INJECT')); 'ok'"
js "window.__curHide(); 'ok'"
sleep 1.2

# ---------- 开场 ----------
echo "  · 开场"
js "window.__curShow(); window.__curTo(820, 120); 'ok'"
sleep 1.6
js "window.__curTo(760, 300); 'ok'"
sleep 1.4

# ---------- 选城市 ----------
echo "  · 选择城市"
cur '#city'
sleep 1.0
rip
echo "op_city=$(date +%s.%N)" >> "$TS"
$AB select "#city" "深圳" >/dev/null 2>&1
sleep 2.0

# ---------- 检索深度 ----------
echo "  · 调整检索深度"
js "var e=document.querySelector('#depth').getBoundingClientRect(); window.__curTo(e.left+e.width*0.98, e.top+e.height/2); 'ok'"
sleep 1.0
rip
echo "op_depth=$(date +%s.%N)" >> "$TS"
js "var d=document.querySelector('#depth'); d.value=3; d.dispatchEvent(new Event('input',{bubbles:true})); d.dispatchEvent(new Event('change',{bubbles:true})); 'ok'"
sleep 2.0

# ---------- 勾选实时抓取 ----------
echo "  · 勾选实时抓取"
cur '#live'
sleep 1.0
rip
echo "op_live=$(date +%s.%N)" >> "$TS"
js "var c=document.querySelector('#live'); if(!c.checked){c.click();} 'ok'"
sleep 1.8

# ---------- 运行 ----------
echo "  · 点击运行"
cur '#runBtn'
sleep 1.0
rip
T1=$(date +%s.%N)
echo "op_run=$T1" >> "$TS"
js "document.querySelector('#runBtn').click(); 'ok'"
sleep 0.6

echo "  · 等待抓取（真实抓取，约 40 秒）"
for i in $(seq 1 24); do
  sleep 2.5
  S=$(to 8 "document.querySelector('#status').textContent")
  case "$S" in
    *完成*) echo "    抓取完成"; break;;
    *失败*|*错误*) echo "    ⚠ 抓取异常: $S"; break;;
  esac
done
T2=$(date +%s.%N)
echo "T2_fetch_done=$T2" >> "$TS"
# 左栏「配置来源」在运行后才渲染，这里补一次遮蔽（去掉 config 文件路径）
if [ "$CLIENT" = "1" ]; then js "window.__maskClient(); 'ok'"; fi
sleep 2.2

# ---------- 结果页浏览 ----------
tab() {  # tab <data-t> <停顿秒> [滚动目标]
  local name="$1" pause="$2" scrollto="${3:-}"
  js "window.__curEl('#tabs button[data-t=$name]'); 'ok'"
  sleep 0.8
  rip
  local ST
  ST=$(date +%s.%N)
  js "document.querySelector('#tabs button[data-t=$name]').click(); 'ok'"
  sleep 0.7
  if [ "$CLIENT" = "1" ]; then js "window.__maskClient(); 'ok'"; fi
  local ACT
  ACT=$(active)
  echo "tab_$name=$ST" >> "$TS"
  echo "    [$name] 点击后激活标签 = $ACT" | tee -a "$LOG"
  sleep 1.2
  if [ -n "$scrollto" ]; then
    js "window.__scrollTo('$scrollto'); 'ok'"
    sleep 1.5
    js "window.__curTo(700, 620); 'ok'"
    sleep 1.3
  fi
  sleep "$pause"
}

echo "  · 产业链分析"
tab chain 2.2 '#out table'

echo "  · 企业筛选"
tab screen 2.6 '#out table tr:nth-child(6)'

echo "  · 线索卡"
tab leads 2.8 '#out .card:nth-child(2)'

echo "  · 实时信号"
tab signals 3.0 '#out table tr:nth-child(5)'

echo "  · 数据源"
tab sources 2.4

echo "  · 城市政策"
tab city 2.6

echo "  · 运行报告"
tab report 2.8 '#out table'

echo "  · 收尾"
js "document.querySelector('#out').scrollIntoView({block:'start'}); 'ok'"
sleep 1.0
js "window.__curTo(300, 300); 'ok'"
sleep 2.0

echo "[3/4] 停止录制…"
$AB record stop >/dev/null 2>&1
T3=$(date +%s.%N)

{
  echo "T0_record_start=$T0"
  echo "T1_click_run=$T1"
  echo "T3_record_stop=$T3"
} >> "$TS"

echo "[4/4] 完成"
ls -lh "$RAW" 2>/dev/null | awk '{print "  原始视频:", $5}'
echo "  打点文件: $TS"
