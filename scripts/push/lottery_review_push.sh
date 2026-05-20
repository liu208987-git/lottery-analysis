#!/bin/bash
# Lottery review push script - designed for hermes cron no_agent=true mode
# This runs the full review pipeline (fetch actual numbers + compare + push)
# and outputs the review report to stdout for hermes cron to deliver verbatim.

cd /home/admin/bendi/lottery-analysis

# Step 1: Run daily review (data_fetcher -> feature_engine -> compare_result -> review_summary)
.venv/bin/python scripts/daily_review.py 2>/dev/null

# Step 2: Read existing review report if available
REVIEW_FILE="output/push/review_report.md"
if [ -f "$REVIEW_FILE" ]; then
    cat "$REVIEW_FILE"
    exit 0
fi

# Step 3: Fallback - generate review message directly via hermes_push.py
.venv/bin/python scripts/hermes_push.py --mode review --stdout 2>/dev/null

# If all failed, exit silently (no output = no delivery in no_agent mode)
exit 0
