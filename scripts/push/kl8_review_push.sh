#!/bin/bash
# KL8 review push script - designed for hermes cron no_agent=true mode
# ALWAYS regenerates review before pushing — never cats a stale file.
# send_log.jsonl + file lock handle dedup.

set -euo pipefail

cd /home/admin/bendi/lottery-analysis
VENV=".venv/bin/python"

echo "[$$] KL8 Step 1/4: 拉取快乐8开奖数据..." >&2
$VENV scripts/kl8/fetcher.py --pages 3

echo "[$$] KL8 Step 2/4: 生成快乐8复盘..." >&2
$VENV scripts/kl8/reviewer.py

echo "[$$] KL8 Step 3/4: 生成快乐8累计表现..." >&2
$VENV scripts/kl8/metrics.py || true

echo "[$$] KL8 Step 4/4: 输出快乐8复盘推送..." >&2
$VENV scripts/hermes_push.py --mode review --lottery kl8 --stdout --force

echo "[$$] KL8 复盘推送流程完成" >&2
exit 0
