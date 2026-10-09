#!/bin/bash
# 双击本文件即可启动「返投招商 Skill」。
# 逻辑复用同目录的 start.sh，避免两份代码各改一遍。
cd "$(dirname "$0")" || exit 1
export SKILL_DOUBLE_CLICKED=1
exec ./start.sh "$@"
