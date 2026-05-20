#!/bin/bash
# Lottery predict push script - designed for hermes cron no_agent=true mode
# ALWAYS regenerates predictions before pushing, even if old data exists.
# This ensures data is fresh and no cron approval is needed.

set -e

cd /home/admin/bendi/lottery-analysis

VENV=".venv/bin/python"

echo "[$$] 开始预测推送流程..." >&2

# Step 1: 始终重新生成预测（确保数据是最新的）
echo "[$$] Step 1/3: 生成今日预测..." >&2
$VENV run_daily.py --strategy all --top-k 30 2>/dev/null

# Step 2: 生成数据源健康报告
echo "[$$] Step 2/3: 生成数据源健康报告..." >&2
$VENV scripts/source_health.py --json --output output/reports/source_health.json 2>/dev/null || true

# Step 3: 生成并输出推送内容（加 --force 避免当天去重击中后无输出）
echo "[$$] Step 3/3: 生成推送内容..." >&2
$VENV scripts/hermes_push.py --mode predict --stdout --force 2>/dev/null

echo "[$$] 预测推送流程完成" >&2
exit 0
