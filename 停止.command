#!/bin/bash
# 双击本文件即可停止「返投招商 Skill」。
# 逻辑复用同目录的 stop.sh。
cd "$(dirname "$0")" || exit 1
export SKILL_DOUBLE_CLICKED=1
exec ./stop.sh "$@"
