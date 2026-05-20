#!/bin/bash
# Lottery review push script - designed for hermes cron no_agent=true mode
# ALWAYS regenerates review before pushing — never cats a stale file.
# send_log.jsonl + file lock handle dedup across the 3 evening waves.
# push_state.json is only used by direct webhook mode, not --stdout deliver=origin.

set -e

cd /home/admin/bendi/lottery-analysis
VENV=".venv/bin/python"

FINAL_FLAG="--complete-only"
if [ "${1:-}" = "--final" ]; then
    FINAL_FLAG="--final-check"
fi

LOG_DIR="logs"
LOG_FILE="$LOG_DIR/review_push_$(date +%F).log"
mkdir -p "$LOG_DIR"

echo "[$$] $(date) 开始复盘推送 final=$([ "$FINAL_FLAG" = "--final-check" ] && echo yes || echo no)" >> "$LOG_FILE"

# Step 1: 始终重新跑复盘（拉取开奖 + 对比 + 摘要）
echo "[$$] Step 1/2: 执行 daily_review..." >> "$LOG_FILE"
$VENV scripts/daily_review.py >> "$LOG_FILE" 2>&1 || true

# Step 2: 生成复盘推送内容
#   --complete-only: 两彩种齐全才输出，未齐静默（21:35/22:05）
#   --final-check: 未齐则输出兜底通知（23:10）
echo "[$$] Step 2/2: 生成复盘推送内容..." >> "$LOG_FILE"
$VENV scripts/hermes_push.py --mode review --stdout $FINAL_FLAG 2>> "$LOG_FILE"

echo "[$$] $(date) 复盘推送流程完成" >> "$LOG_FILE"
exit 0
