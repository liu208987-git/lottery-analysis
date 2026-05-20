#!/usr/bin/env python3
"""快乐8数据抓取 —— 拉取历史开奖 + 标准化校验"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data" / "kl8"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CN_TZ = timezone(timedelta(hours=8))


def fetch_official(page_size: int = 30, max_pages: int = 10) -> list[dict]:
    """从官方API拉取快乐8开奖数据"""
    url = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.cwl.gov.cn/"}
    all_rows = []

    for page in range(max_pages):
        params = {
            "name": "kl8",
            "issueCount": "",
            "issueStart": "",
            "issueEnd": "",
            "dayStart": "",
            "dayEnd": "",
            "pageNo": page + 1,
            "pageSize": page_size,
            "week": "",
            "systemType": "PC",
        }
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            items = data.get("result", [])
            if not items:
                break
            for item in items:
                code = item.get("code", "")
                red = item.get("red", "")
                date_raw = item.get("date", "")
                if not code or not red:
                    continue
                nums = [int(x) for x in red.split(",")]
                if len(nums) != 20:
                    continue
                # date format: "2026-05-19(二)" → "2026-05-19"
                date_clean = date_raw.split("(")[0] if "(" in date_raw else date_raw
                all_rows.append({
                    "issue": code,
                    "date": date_clean,
                    "numbers": sorted(nums),
                })
            if len(items) < page_size:
                break
        except Exception as e:
            print(f"[WARN] 抓取第{page+1}页失败: {e}", file=sys.stderr)
            break

    return all_rows


def normalize(issue: str, date: str, numbers: list[int]) -> dict:
    nums = sorted(int(n) for n in numbers)
    if len(nums) != 20:
        raise ValueError(f"应为20个号码，实际{len(nums)}")
    if min(nums) < 1 or max(nums) > 80:
        raise ValueError(f"号码范围1-80，实际{nums}")
    if len(set(nums)) != 20:
        raise ValueError(f"号码有重复: {nums}")
    return {"issue": issue, "date": date, "numbers": nums}


def save_history(rows: list[dict]) -> Path:
    p = DATA_DIR / "kl8_history.csv"
    existed = {}
    if p.exists():
        with open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                existed[r["issue"]] = r
    for r in rows:
        existed[r["issue"]] = {"issue": r["issue"], "date": r["date"],
                               "numbers": " ".join(f"{n:02d}" for n in r["numbers"])}
    sorted_rows = sorted(existed.values(), key=lambda x: x["issue"], reverse=True)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["issue", "date", "numbers"])
        w.writeheader()
        w.writerows(sorted_rows)
    return p


def save_latest(row: dict) -> Path:
    p = DATA_DIR / "kl8_latest.json"
    data = {
        "lottery": "kl8",
        "issue": row["issue"],
        "date": row["date"],
        "numbers": row["numbers"],
        "fetched_at": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
    }
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def main():
    parser = argparse.ArgumentParser(description="快乐8数据抓取")
    parser.add_argument("--pages", type=int, default=3, help="抓取页数(每页30期)")
    parser.add_argument("--test", action="store_true", help="使用测试数据")
    args = parser.parse_args()

    if args.test:
        rows = [normalize(f"2026{120+i:03d}", "2026-05-19",
                          sorted([1, 5, 8, 12, 16, 20, 23, 28, 31, 35,
                                  39, 42, 46, 50, 55, 61, 66, 70, 73, 80]))
                for i in range(3)]
    else:
        rows = fetch_official(page_size=30, max_pages=args.pages)
        if not rows:
            print("[ERROR] 未抓取到任何数据，尝试 --test", file=sys.stderr)
            sys.exit(1)

    cleaned = []
    for r in rows:
        try:
            cleaned.append(normalize(r["issue"], r["date"], r["numbers"]))
        except ValueError as e:
            print(f"[WARN] 跳过异常数据 {r.get('issue','?')}: {e}", file=sys.stderr)

    hpath = save_history(cleaned)
    lpath = save_latest(cleaned[0])
    print(f"✅ 快乐8: {len(cleaned)} 期")
    print(f"   最新: {cleaned[0]['issue']} | 号码: {' '.join(f'{n:02d}' for n in cleaned[0]['numbers'][:5])}...")
    print(f"   历史: {hpath}")
    print(f"   latest: {lpath}")


if __name__ == "__main__":
    main()
