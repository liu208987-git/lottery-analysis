#!/bin/bash
# KL8 predict push script - designed for hermes cron no_agent=true mode
# ALWAYS regenerates predictions before pushing — never cats a stale file.

set -euo pipefail

cd /home/admin/bendi/lottery-analysis
VENV=".venv/bin/python"

echo "[$$] KL8 Step 1/4: 拉取快乐8数据..." >&2
$VENV scripts/kl8/fetcher.py --pages 3

echo "[$$] KL8 Step 2/4: 生成快乐8预测..." >&2
$VENV scripts/kl8/predictor.py

echo "[$$] KL8 Step 3/4: 生成快乐8统计..." >&2
$VENV scripts/kl8/stats.py || true

echo "[$$] KL8 Step 4/4: 输出快乐8预测推送..." >&2
$VENV scripts/hermes_push.py --mode predict --lottery kl8 --stdout --force

echo "[$$] KL8 预测推送流程完成" >&2
exit 0
