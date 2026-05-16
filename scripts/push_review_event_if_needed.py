#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
晚间复盘事件推送
===============
仅在重要事件发生时推送：命中 / 数据异常 / 熔断 / 新隔离文件

用法:
    python scripts/push_review_event_if_needed.py
    python scripts/push_review_event_if_needed.py --force  # 强制推送（忽略事件判断）
"""

import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
REVIEW_HISTORY = BASE / "output" / "reviews" / "review_history.csv"
CACHE_DIR = BASE / "data" / "cache"
QUARANTINE_DIR = BASE / "data" / "quarantine"

CN_TZ = timezone(timedelta(hours=8))


def now() -> datetime:
    return datetime.now(CN_TZ)


def read_review_csv() -> list[dict]:
    if not REVIEW_HISTORY.exists():
        return []
    with REVIEW_HISTORY.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_events() -> list[str]:
    """检查重要事件，返回事件描述列表"""
    events = []

    # 1. 最新一期是否命中
    rows = read_review_csv()
    if rows:
        # 取最新一期
        latest_issue = {}
        for r in rows:
            lottery = r.get("彩种", "")
            issue = r.get("期号", "")
            key = f"{lottery}_{issue}"
            if key not in latest_issue:
                latest_issue[key] = []
            latest_issue[key].append(r)

        for key, items in latest_issue.items():
            for item in items:
                direct = str(item.get("直选命中Top30", "")).strip().lower()
                group = str(item.get("组选命中Top30", "")).strip().lower()
                st = item.get("策略", "?")
                actual = item.get("开奖号码", "?")
                if direct in ("true", "1", "yes"):
                    events.append(f"🎯 {key} {st}策略 直选命中！开奖{actual}")
                elif group in ("true", "1", "yes"):
                    events.append(f"✅ {key} {st}策略 组选命中！开奖{actual}")

    # 2. 数据源熔断
    status = read_json(CACHE_DIR / "source_status.json")
    for name, item in status.items():
        cd = item.get("cooldown_until", "")
        if cd:
            try:
                cd_dt = datetime.strptime(cd, "%Y-%m-%d %H:%M:%S")
                if cd_dt > now():
                    events.append(f"🔒 {name} 冷却中，至 {cd}")
            except ValueError:
                events.append(f"🔒 {name} 冷却中")

    # 3. 新隔离文件（最近 2 小时内）
    if QUARANTINE_DIR.exists():
        cutoff = now() - timedelta(hours=2)
        for f in QUARANTINE_DIR.glob("*"):
            if datetime.fromtimestamp(f.stat().st_mtime) > cutoff:
                events.append(f"⚠️  新隔离文件: {f.name}")
                break  # 只报一次

    return events


def send_push(text: str) -> bool:
    hermes_url = os.getenv("HERMES_WEBHOOK_URL", "")
    wecom_url = os.getenv("WECOM_WEBHOOK_URL", "")

    if not hermes_url and not wecom_url:
        print(text)
        return True

    url = wecom_url or hermes_url
    payload = (
        {"msgtype": "markdown", "markdown": {"content": text}}
        if wecom_url
        else {"text": text}
    )

    try:
        resp = requests.post(url, json=payload, timeout=20)
        return resp.status_code == 200
    except Exception as e:
        print(f"[ERROR] 推送失败: {e}")
        return False


def main():
    force = "--force" in sys.argv

    events = check_events()

    if not events and not force:
        print("📭 无重要事件，跳过推送")
        return

    if not events and force:
        events = ["ℹ️  手动触发（无自动检测事件）"]

    lines = [
        f"📌 彩票复盘事件｜{now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ] + events

    text = "\n".join(lines)
    print(text)

    ok = send_push(text)
    if not ok:
        print("[WARN] 推送可能失败")


if __name__ == "__main__":
    main()
