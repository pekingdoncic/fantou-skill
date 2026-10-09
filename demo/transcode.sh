#!/bin/bash
# ============================================================
# 返投招商 Skill —— 演示视频后期
#
# CLIENT=0（默认）→ 内部版：加速等待段 + 烧字幕
# CLIENT=1        → 对外版：同上 + 追加「难度说明」片尾卡 + 水印
#
# 对外版为什么要加片尾卡：这版视频最大的风险不是「被抄代码」，
# 而是「看起来太简单」——86 秒流畅跑通会让人低估工程量。
# 片尾把踩过的坑摊开，是比遮蔽更有效的保护。
# ============================================================
set -eu
DIR=/Users/luka7/project/fantou-skill
DEMO=$DIR/demo
ASS=$DEMO/subs.ass
CARD=$DEMO/closing-card.png
MARK=$DEMO/watermark.ass
SPEED=8
CARD_SEC=9
PY=/Users/luka7/.workbuddy-ai/binaries/python/envs/default/bin/python3
FF=/Users/luka7/.workbuddy-ai/bin/ffmpeg

CLIENT=${CLIENT:-0}
if [ "$CLIENT" = "1" ]; then
  RAW=$DEMO/raw/client-raw.webm
  TS=$DEMO/raw/timestamps-client.txt
  OUT=$DEMO/返投招商Skill演示_对外版.mp4
else
  RAW=$DEMO/raw/demo-raw.webm
  TS=$DEMO/raw/timestamps.txt
  OUT=$DEMO/返投招商Skill演示.mp4
fi
cd "$DIR"

[ -f "$RAW" ] || { echo "✗ 找不到原始录像 $RAW，请先跑 record.sh"; exit 1; }
[ -f "$TS" ]  || { echo "✗ 找不到时间戳 $TS"; exit 1; }
[ -x "$FF" ]  || { echo "✗ 找不到 ffmpeg"; exit 1; }
if [ "$CLIENT" = "1" ]; then
  [ -f "$CARD" ] || { echo "✗ 找不到片尾卡 $CARD"; exit 1; }
  [ -f "$MARK" ] || { echo "✗ 找不到水印 $MARK"; exit 1; }
fi

T0=$(awk -F= '/^T0_record_start/{print $2}' "$TS")
T1=$(awk -F= '/^T1_click_run/{print $2}'   "$TS")
T2=$(awk -F= '/^T2_fetch_done/{print $2}'  "$TS")
A=$("$PY" -c "print(round($T1-$T0,2))")
B=$("$PY" -c "print(round($T2-$T0,2))")
DUR=$("$PY" -c "print(round($B-$A,2))")
SHORT=$("$PY" -c "print(round($DUR/$SPEED,1))")

echo "版本：$([ "$CLIENT" = "1" ] && echo '对外版（遮蔽 + 片尾卡 + 水印）' || echo '内部版')"
echo "时间轴：加速段 ${A}s → ${B}s（共 ${DUR}s，快放 ${SPEED}x → ${SHORT}s）"

if [ "$CLIENT" = "1" ]; then
  # 两路输入：主录像 + 片尾卡（静帧循环成 CARD_SEC 秒）
  "$FF" -y -hide_banner -loglevel error \
    -i "$RAW" \
    -loop 1 -framerate 30 -t "$CARD_SEC" -i "$CARD" \
    -filter_complex "\
[0:v]trim=start=0:end=${A},setpts=PTS-STARTPTS[v0];\
[0:v]trim=start=${A}:end=${B},setpts=(PTS-STARTPTS)/${SPEED}[v1];\
[0:v]trim=start=${B},setpts=PTS-STARTPTS[v2];\
[v0][v1][v2]concat=n=3:v=1:a=0[cat];\
[cat]ass=filename=${ASS}:fontsdir=/System/Library/Fonts[vmain];\
[1:v]scale=1600:900,setsar=1,format=yuv420p[card];\
[vmain][card]concat=n=2:v=1:a=0[all];\
[all]ass=filename=${MARK}:fontsdir=/System/Library/Fonts[vout]" \
    -map "[vout]" \
    -c:v libx264 -pix_fmt yuv420p -crf 19 -preset medium -r 30 \
    -movflags +faststart -an \
    "$OUT"
else
  "$FF" -y -hide_banner -loglevel error -i "$RAW" \
    -filter_complex "\
[0:v]trim=start=0:end=${A},setpts=PTS-STARTPTS[v0];\
[0:v]trim=start=${A}:end=${B},setpts=(PTS-STARTPTS)/${SPEED}[v1];\
[0:v]trim=start=${B},setpts=PTS-STARTPTS[v2];\
[v0][v1][v2]concat=n=3:v=1:a=0[cat];\
[cat]ass=filename=${ASS}:fontsdir=/System/Library/Fonts[vout]" \
    -map "[vout]" \
    -c:v libx264 -pix_fmt yuv420p -crf 19 -preset medium -r 30 \
    -movflags +faststart -an \
    "$OUT"
fi

echo
echo "✅ 输出：$OUT"
"$FF" -i "$OUT" 2>&1 | grep -E "Duration|Stream #0:0" | sed 's/^/   /'
ls -lh "$OUT" | awk '{print "   大小:", $5}'
