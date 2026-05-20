#!/usr/bin/env python3
"""快乐8候选池预测 —— 热号+冷号混合策略，生成20码候选池"""
import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data" / "kl8"
OUTPUT_DIR = BASE / "output" / "kl8"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CN_TZ = timezone(timedelta(hours=8))


def load_history(n: int = 50) -> list[list[int]]:
    """加载最近N期历史开奖"""
    p = DATA_DIR / "kl8_history.csv"
    if not p.exists():
        return []
    draws = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            nums = [int(x) for x in row["numbers"].split()]
            if len(nums) == 20:
                draws.append(nums)
    return draws[:n]


def next_issue(latest_issue: str) -> str:
    """推算下一期号"""
    try:
        y = int(latest_issue[:4])
        n = int(latest_issue[4:])
        return f"{y}{n + 1:03d}"
    except (ValueError, IndexError):
        return "unknown"


def build_candidate_pool(draws: list[list[int]], pool_size: int = 20,
                         hot_ratio: float = 0.6) -> list[int]:
    """热号+冷号混合生成候选池"""
    if not draws:
        return list(range(1, pool_size + 1))

    recent = draws[:30] if len(draws) >= 30 else draws
    freq = Counter()
    for nums in recent:
        freq.update(nums)

    # 所有号码按出现频率和最近出现期数排序
    hot_count = max(1, int(pool_size * hot_ratio))  # 12
    cold_count = pool_size - hot_count               # 8

    # 热号：频率最高的
    hot = [num for num, _ in freq.most_common(hot_count)]

    # 冷号：频率最低的、但仍出现过的
    all_nums = {i: freq.get(i, 0) for i in range(1, 81)}
    cold = [num for num, _ in sorted(all_nums.items(), key=lambda x: x[1]) if num not in hot][:cold_count]

    pool = sorted(set(hot + cold))
    # 不足 pool_size 从热号补齐
    for num, _ in freq.most_common():
        if len(pool) >= pool_size:
            break
        if num not in pool:
            pool.append(num)

    return sorted(pool[:pool_size])


def predict(latest_issue: str) -> dict:
    draws = load_history()
    if not draws:
        print("[ERROR] 无历史数据，请先运行 kl8_fetcher.py", file=sys.stderr)
        sys.exit(1)

    pool = build_candidate_pool(draws)
    freq = Counter()
    for nums in draws[:30]:
        freq.update(nums)

    target = next_issue(latest_issue)
    return {
        "lottery": "kl8",
        "predicted_issue": target,
        "data_until_issue": latest_issue,
        "strategy": "hot12_cold8",
        "candidate_pool": pool,
        "hot_numbers": [n for n, _ in freq.most_common(20)],
        "cold_numbers": [n for n, _ in sorted(
            {i: freq.get(i, 0) for i in range(1, 81)}.items(),
            key=lambda x: x[1]) if n not in freq.most_common(12)][:20],
        "zone_distribution": {
            "01-20": sum(1 for n in pool if 1 <= n <= 20),
            "21-40": sum(1 for n in pool if 21 <= n <= 40),
            "41-60": sum(1 for n in pool if 41 <= n <= 60),
            "61-80": sum(1 for n in pool if 61 <= n <= 80),
        },
        "note": "基于最近30期热号12+冷号8混合策略，仅供统计观察。",
        "generated_at": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
    }


def save_prediction(data: dict) -> Path:
    issue = data["predicted_issue"]
    p = OUTPUT_DIR / f"kl8_predict_{issue}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = OUTPUT_DIR / "kl8_predict_latest.json"
    latest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def main():
    parser = argparse.ArgumentParser(description="快乐8候选池预测")
    parser.add_argument("--pool-size", type=int, default=20, help="候选池大小")
    parser.add_argument("--hot-ratio", type=float, default=0.6, help="热号比例")
    args = parser.parse_args()

    # 从latest json读取最新期号
    latest_path = DATA_DIR / "kl8_latest.json"
    if not latest_path.exists():
        print("[ERROR] 请先运行 kl8_fetcher.py", file=sys.stderr)
        sys.exit(1)
    latest_data = json.loads(latest_path.read_text(encoding="utf-8"))
    latest_issue = latest_data["issue"]

    data = predict(latest_issue)
    path = save_prediction(data)

    pool = data["candidate_pool"]
    print(f"✅ 快乐8 预测期号: {data['predicted_issue']}")
    print(f"   策略: {data['strategy']}")
    print(f"   候选20码: {' '.join(f'{n:02d}' for n in pool[:10])}")
    print(f"            {' '.join(f'{n:02d}' for n in pool[10:])}")
    print(f"   分区: 01-20:{data['zone_distribution']['01-20']} "
          f"21-40:{data['zone_distribution']['21-40']} "
          f"41-60:{data['zone_distribution']['41-60']} "
          f"61-80:{data['zone_distribution']['61-80']}")
    print(f"   保存: {path}")


if __name__ == "__main__":
    main()
