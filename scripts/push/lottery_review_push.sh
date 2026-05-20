#!/bin/bash
# Lottery review push script - designed for hermes cron no_agent=true mode
# ALWAYS regenerates review before pushing — never cats a stale file.
# push_state.json / send_log.jsonl handle dedup across the 3 evening waves.

set -e

cd /home/admin/bendi/lottery-analysis

VENV=".venv/bin/python"

echo "[$$] 开始复盘推送流程..." >&2

# Step 1: 始终重新跑复盘（拉取开奖 + 对比 + 摘要）
echo "[$$] Step 1/2: 执行 daily_review..." >&2
$VENV scripts/daily_review.py 2>/dev/null

# Step 2: 始终重新生成复盘推送内容（无 --force，依赖 hash 去重防三波重复推送）
echo "[$$] Step 2/2: 生成复盘推送内容..." >&2
$VENV scripts/hermes_push.py --mode review --stdout 2>/dev/null

echo "[$$] 复盘推送流程完成" >&2
exit 0
