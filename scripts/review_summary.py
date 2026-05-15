#!/usr/bin/env python3
"""
复盘表现摘要
============
读取 review_history.csv，输出最近30/60/100期表现统计。

用法：
    python scripts/review_summary.py
    python scripts/review_summary.py --window 30
    python scripts/review_summary.py --lottery pls
"""

import argparse
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY_PATH = BASE_DIR / 'output' / 'reviews' / 'review_history.csv'

NAME_MAP = {'pls': '排列三', 'd3': '福彩3D'}


def pct(series):
    if len(series) == 0:
        return 0.0
    return series.astype(str).isin(['True', 'true', '1']).mean()


def summarize(df, lottery, window):
    sub = df[df['彩种'].apply(lambda x: NAME_MAP.get(lottery, lottery) in str(x))].copy()
    if sub.empty:
        return f"\n【{NAME_MAP.get(lottery, lottery)}】暂无复盘数据\n"

    sub = sub.tail(window)
    n = len(sub)

    direct_rate = pct(sub['直选命中Top30'])
    group_rate = pct(sub['组选命中Top30'])
    shape_rate = pct(sub['Top1形态一致'])

    sum_err = pd.to_numeric(sub['Top1和值误差'], errors='coerce').mean()
    span_err = pd.to_numeric(sub['Top1跨度误差'], errors='coerce').mean()

    lines = [
        f"",
        f"  {'─'*50}",
        f"  【{NAME_MAP.get(lottery, lottery)} 最近 {n} 期表现】",
        f"  {'─'*50}",
        f"  Top30 直选命中 : {sub['直选命中Top30'].astype(str).isin(['True','true','1']).sum():>3} 次 / {n} 期 = {direct_rate:.1%}",
        f"  Top30 组选命中 : {sub['组选命中Top30'].astype(str).isin(['True','true','1']).sum():>3} 次 / {n} 期 = {group_rate:.1%}",
        f"  Top1 形态一致  : {sub['Top1形态一致'].astype(str).isin(['True','true','1']).sum():>3} 次 / {n} 期 = {shape_rate:.1%}",
        f"  Top1 平均和值差: {sum_err:.1f}",
        f"  Top1 平均跨度差: {span_err:.1f}",
    ]

    if n >= 10:
        recent_5 = sub.tail(5)
        r5_direct = pct(recent_5['直选命中Top30'])
        r5_group = pct(recent_5['组选命中Top30'])
        lines.append(f"  {'─'*50}")
        lines.append(f"  最近5期趋势: 直选{r5_direct:.1%} | 组选{r5_group:.1%}")

    lines.append(f"  {'─'*50}")
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='复盘表现摘要')
    parser.add_argument('--window', type=int, default=30,
                        help='统计窗口（默认30期）')
    parser.add_argument('--lottery', choices=['pls', 'd3'],
                        help='仅统计指定彩种')
    args = parser.parse_args()

    if not HISTORY_PATH.exists():
        print(f"\n  暂无复盘数据: {HISTORY_PATH}")
        print(f"  开奖后运行: python scripts/compare_result.py --lottery pls")
        return

    df = pd.read_csv(HISTORY_PATH, dtype=str, encoding='utf-8-sig')
    total = len(df)

    print(f"\n{'='*55}")
    print(f"  📊 复盘表现摘要")
    print(f"{'='*55}")
    print(f"  数据来源: {HISTORY_PATH}")
    print(f"  总复盘期数: {total}")
    print(f"  统计窗口: 最近 {args.window} 期")

    lotteries = [args.lottery] if args.lottery else ['pls', 'd3']
    for lt in lotteries:
        print(summarize(df, lt, args.window))

    print(f"\n{'='*55}\n")


if __name__ == '__main__':
    main()
