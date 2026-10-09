#!/bin/bash
# ============================================================
#  返投招商 Skill —— 一键启动
#
#  用法：
#    终端    cd /Users/luka7/project/fantou-skill && ./start.sh
#    访达    双击「启动.command」
#
#  可选参数：
#    ./start.sh 9000        换端口
#    ./start.sh --no-browser 启动但不自动开浏览器
# ============================================================
cd "$(dirname "$0")" || exit 1

PORT=8848
OPEN_BROWSER=1
for arg in "$@"; do
  case "$arg" in
    --no-browser) OPEN_BROWSER=0 ;;
    [0-9]*)       PORT="$arg" ;;
  esac
done

MANAGED_PY="/Users/luka7/.workbuddy-ai/binaries/python/envs/default/bin/python3"

echo "=============================================="
echo "  返投招商 Skill"
echo "=============================================="

# 双击运行时才需要暂停等待用户按键
pause() {
  if [ "${SKILL_DOUBLE_CLICKED:-0}" = "1" ]; then
    echo
    read -r -p "按回车键关闭本窗口…"
  fi
}

# ---------- 1. 找可用的 Python ----------
PY=""
if [ -x "$MANAGED_PY" ] && "$MANAGED_PY" -c "import yaml" 2>/dev/null; then
  PY="$MANAGED_PY"
else
  for cand in "$MANAGED_PY" "$(command -v python3)" /usr/bin/python3; do
    if [ -n "$cand" ] && [ -x "$cand" ]; then
      if "$cand" -c "import yaml" 2>/dev/null; then PY="$cand"; break; fi
      [ -z "$PY" ] && PY="$cand"    # 记下第一个能用的，稍后装依赖
    fi
  done
fi

if [ -z "$PY" ]; then
  echo "❌ 找不到 python3。请先安装 Python 3 后重试。"
  echo "   下载地址：https://www.python.org/downloads/"
  pause
  exit 1
fi

# ---------- 2. 确保依赖 ----------
if ! "$PY" -c "import yaml" 2>/dev/null; then
  echo "📦 首次运行，正在安装依赖 pyyaml …"
  if ! "$PY" -m pip install -q pyyaml; then
    echo "❌ 依赖安装失败。请手动执行："
    echo "   $PY -m pip install pyyaml"
    pause
    exit 1
  fi
  echo "✅ 依赖安装完成"
fi

# ---------- 3. 端口已占用？ ----------
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ℹ️  服务已经在运行了（端口 $PORT）"
  echo "   地址：http://127.0.0.1:$PORT"
  [ "$OPEN_BROWSER" = "1" ] && open "http://127.0.0.1:$PORT" 2>/dev/null
  echo
  echo "   想重启：先运行 ./stop.sh，再运行 ./start.sh"
  pause
  exit 0
fi

# ---------- 4. 启动 ----------
echo "🚀 启动中… 服务地址：http://127.0.0.1:$PORT"
echo
echo "   提示：按 Control + C 可停止服务"
echo "=============================================="

# 等服务真正起来再开浏览器，避免打开空白页
(
  for _ in $(seq 1 30); do
    sleep 0.5
    if curl -s -o /dev/null -m 2 "http://127.0.0.1:$PORT/api/options" 2>/dev/null; then
      [ "$OPEN_BROWSER" = "1" ] && open "http://127.0.0.1:$PORT" 2>/dev/null
      break
    fi
  done
) &

exec "$PY" app.py "$PORT"
