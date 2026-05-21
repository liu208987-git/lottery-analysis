#!/bin/bash
# KL8 review push script - designed for hermes cron no_agent=true mode
# ALWAYS regenerates review before pushing — never cats a stale file.
# send_log.jsonl + file lock handle dedup.
# Reviewer exits 0 when waiting for data; we skip push in that case.

set -euo pipefail

cd /home/admin/bendi/lottery-analysis
VENV=".venv/bin/python"

echo "[$$] KL8 Step 1/4: 拉取快乐8开奖数据..." >&2
$VENV scripts/kl8/fetcher.py --pages 3

echo "[$$] KL8 Step 2/4: 生成快乐8复盘..." >&2
$VENV scripts/kl8/reviewer.py

# reviewer 在等待开奖时不写 review_latest.json；检测是否真正写入了
REVIEW_FILE="output/kl8/kl8_review_latest.json"
if [ ! -f "$REVIEW_FILE" ]; then
    echo "[$$] KL8 复盘未生成（可能开奖数据未就绪），本轮不推送" >&2
    exit 0
fi

echo "[$$] KL8 Step 3/4: 生成快乐8累计表现..." >&2
$VENV scripts/kl8/metrics.py || true

echo "[$$] KL8 Step 4/4: 输出快乐8复盘推送..." >&2
$VENV scripts/hermes_push.py --mode review --lottery kl8 --stdout

echo "[$$] KL8 复盘推送流程完成" >&2
exit 0
