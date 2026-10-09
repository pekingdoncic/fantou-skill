#!/bin/bash
# ============================================================
#  返投招商 Skill —— 停止服务
#  用法：终端执行 ./stop.sh   或在访达里双击「停止.command」
# ============================================================
PORT="${1:-8848}"

echo "=============================================="
echo "  返投招商 Skill —— 停止服务"
echo "=============================================="

PIDS="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null)"

if [ -z "$PIDS" ]; then
  echo "ℹ️  端口 $PORT 上没有运行中的服务，无需停止。"
else
  echo "$PIDS" | while read -r pid; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null && echo "✅ 已停止进程 PID $pid"
  done
  sleep 1
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "⚠️  进程未响应，强制结束…"
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | xargs kill -9 2>/dev/null
    echo "✅ 已强制停止"
  else
    echo "✅ 服务已停止，端口 $PORT 已释放。"
  fi
fi

echo
# 只有双击运行时才暂停（终端/后台运行不卡住）
if [ "${SKILL_DOUBLE_CLICKED:-0}" = "1" ]; then
  read -r -p "按回车键关闭本窗口…"
fi
