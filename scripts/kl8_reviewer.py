#!/usr/bin/env python3
"""快乐8复盘 —— 候选池 vs 实际开奖，统计命中数"""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data" / "kl8"
OUTPUT_DIR = BASE / "output" / "kl8"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CN_TZ = timezone(timedelta(hours=8))


def review(prediction: dict, actual: dict) -> dict:
    pool = set(prediction["candidate_pool"])
    drawn = set(actual["numbers"])
    hit = sorted(pool & drawn)

    return {
        "lottery": "kl8",
        "issue": actual["issue"],
        "date": actual["date"],
        "strategy": prediction.get("strategy", ""),
        "hit_count": len(hit),
        "hit_numbers": hit,
        "candidate_pool": prediction["candidate_pool"],
        "actual_numbers": actual["numbers"],
        "hit_rate": round(len(hit) / 20, 4),
        "zone_hit": {
            "01-20": sum(1 for n in hit if 1 <= n <= 20),
            "21-40": sum(1 for n in hit if 21 <= n <= 40),
            "41-60": sum(1 for n in hit if 41 <= n <= 60),
            "61-80": sum(1 for n in hit if 61 <= n <= 80),
        },
        "note": "命中数 = 候选池 ∩ 开奖号码。每期开20个，完全随机期望命中5个。",
        "reviewed_at": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
    }


def save_review(data: dict) -> Path:
    issue = data["issue"]
    p = OUTPUT_DIR / f"kl8_review_{issue}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "kl8_review_latest.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def append_review_history(data: dict) -> Path:
    p = OUTPUT_DIR / "kl8_review_history.csv"
    row = {
        "日期": data["date"],
        "期号": data["issue"],
        "策略": data["strategy"],
        "命中数": str(data["hit_count"]),
        "命中号码": " ".join(f"{n:02d}" for n in data["hit_numbers"]) or "-",
        "命中率": str(data["hit_rate"]),
        "复盘时间": data["reviewed_at"],
    }
    fieldnames = list(row.keys())
    existed = []
    if p.exists():
        with open(p, encoding="utf-8-sig", newline="") as f:
            existed = list(csv.DictReader(f))
    # 同策略同期号去重
    existed = [r for r in existed if not (r["期号"] == row["期号"] and r["策略"] == row["策略"])]
    existed.append(row)
    existed.sort(key=lambda r: r["期号"], reverse=True)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(existed)
    return p


def main():
    parser = argparse.ArgumentParser(description="快乐8复盘")
    parser.add_argument("--predict", help="预测JSON路径(默认latest)")
    parser.add_argument("--actual", help="开奖JSON路径(默认latest)")
    args = parser.parse_args()

    pred_path = Path(args.predict) if args.predict else OUTPUT_DIR / "kl8_predict_latest.json"
    actual_path = Path(args.actual) if args.actual else DATA_DIR / "kl8_latest.json"

    if not pred_path.exists():
        print(f"[ERROR] 预测文件不存在: {pred_path}", file=sys.stderr)
        sys.exit(1)
    if not actual_path.exists():
        print(f"[ERROR] 开奖文件不存在: {actual_path}", file=sys.stderr)
        sys.exit(1)

    pred = json.loads(pred_path.read_text(encoding="utf-8"))
    actual = json.loads(actual_path.read_text(encoding="utf-8"))

    data = review(pred, actual)
    rpath = save_review(data)
    hpath = append_review_history(data)

    hit = data["hit_numbers"]
    print(f"📊 快乐8 复盘  {data['issue']}")
    print(f"   命中: {data['hit_count']}/20 (期望~5)")
    print(f"   号码: {' '.join(f'{n:02d}' for n in hit) if hit else '无'}")
    print(f"   分区: 01-20:{data['zone_hit']['01-20']} "
          f"21-40:{data['zone_hit']['21-40']} "
          f"41-60:{data['zone_hit']['41-60']} "
          f"61-80:{data['zone_hit']['61-80']}")
    print(f"   保存: {rpath}")
    print(f"   历史: {hpath}")


if __name__ == "__main__":
    main()
