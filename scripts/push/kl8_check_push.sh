#!/bin/bash
# KL8 health check script - designed for hermes cron no_agent=true mode
# Runs the full KL8 health check and reports status.
# Outputs to stdout for delivery; on failure, exit code != 0 alerts cron.

set -euo pipefail

cd /home/admin/bendi/lottery-analysis
VENV=".venv/bin/python"

echo "[$$] KL8 Step 1/1: 执行全链路健康检查..." >&2

# check.py exits 0 on healthy, non-zero on issues
$VENV scripts/kl8/check.py

echo "[$$] KL8 健康检查完成" >&2
exit 0
