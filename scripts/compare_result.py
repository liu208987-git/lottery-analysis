#!/usr/bin/env python3
"""
预测 vs 开奖对比脚本
====================
读取最新预测 JSON，对比最新期开奖结果，生成差异报告。

用法：
    python scripts/compare_result.py --lottery pls
    python scripts/compare_result.py --lottery d3
    python scripts/compare_result.py --lottery pls --prediction output/predictions/pls_predict_26125.json
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent


def load_prediction(lottery, prediction_path=None):
    """加载预测 JSON"""
    if prediction_path:
        p = Path(prediction_path)
        path = p if p.is_absolute() else BASE_DIR / p
    else:
        path = BASE_DIR / 'output' / 'predictions' / f'latest_{lottery}.json'

    if not path.exists():
        print(f"[错误] 预测文件不存在: {path}")
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_latest_draw(lottery):
    """从特征 CSV 读取最新一期开奖"""
    path = BASE_DIR / 'data' / 'processed' / f'{lottery}_feat.csv'
    if not path.exists():
        print(f"[错误] 特征数据不存在: {path}")
        print(f"  请先运行: python run_daily.py {lottery}")
        sys.exit(1)

    df = pd.read_csv(path, encoding='utf-8-sig')
    latest = df.iloc[0]
    a, b, c = int(latest['红球1']), int(latest['红球2']), int(latest['红球3'])
    number = f"{a}{b}{c}"
    group = ''.join(sorted(number))
    return {
        '期号': int(latest['期数']),
        '开奖号码': number,
        '组选': group,
        '红球1': a, '红球2': b, '红球3': c,
        '和值': int(latest['和值']),
        '跨度': int(latest['跨度']),
        '形态': latest['形态'],
    }


def compare(predictions, actual):
    """逐注对比预测与开奖"""
    actual_num = actual['开奖号码']
    actual_group = actual['组选']
    actual_sum = actual['和值']
    actual_span = actual['跨度']
    actual_morph = actual['形态']

    rows = []
    for pred in predictions:
        num = pred['号码']
        group = pred.get('group_number', ''.join(sorted(num)))
        pred_sum = pred['和值']
        pred_span = pred['跨度']
        pred_morph = pred['形态']

        rows.append({
            '排名': pred['排名'],
            '预测号码': num,
            '直选命中': num == actual_num,
            '组选命中': group == actual_group,
            '和值差': abs(pred_sum - actual_sum),
            '跨度差': abs(pred_span - actual_span),
            '形态一致': pred_morph == actual_morph,
            '预测和值': pred_sum,
            '预测跨度': pred_span,
            '预测形态': pred_morph,
        })

    return rows


def build_report(pred_json, actual, rows):
    """生成对比报告"""
    direct_hit = any(r['直选命中'] for r in rows)
    group_hit = any(r['组选命中'] for r in rows)

    best_direct = next((r for r in rows if r['直选命中']), None)
    best_group = next((r for r in rows if r['组选命中']), None)
    min_sum_diff = min(rows, key=lambda r: r['和值差'])
    min_span_diff = min(rows, key=lambda r: r['跨度差'])
    morph_matches = [r for r in rows if r['形态一致']]

    # 一句话摘要（供 cron/Hermes 直接读取）
    if direct_hit:
        one_line = f"开奖 {actual['开奖号码']} | 直选命中第{best_direct['排名']}名 | 和值{actual['和值']} 跨度{actual['跨度']}"
    elif group_hit:
        one_line = f"开奖 {actual['开奖号码']} | 组选命中第{best_group['排名']}名 | 和值{actual['和值']} 跨度{actual['跨度']}"
    else:
        one_line = f"开奖 {actual['开奖号码']} | 未命中 最近和差{min_sum_diff['和值差']}跨差{min_span_diff['跨度差']} | 形态一致{morph_matches.__len__()}/{rows.__len__()}注"

    return {
        '一句话摘要': one_line,
        '对比时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '彩种': pred_json.get('彩种', ''),
        '预测期号': pred_json.get('预测期号', ''),
        '实际期号': actual['期号'],
        '预测期号匹配': pred_json.get('预测期号') == actual['期号'],
        '开奖号码': actual['开奖号码'],
        '开奖详情': {
            '号码': actual['开奖号码'],
            '组选': actual['组选'],
            '和值': actual['和值'],
            '跨度': actual['跨度'],
            '形态': actual['形态'],
        },
        '命中情况': {
            '直选命中': direct_hit,
            '组选命中': group_hit,
            '直选最佳排名': best_direct['排名'] if best_direct else None,
            '组选最佳排名': best_group['排名'] if best_group else None,
        },
        '最佳逼近': {
            '最小和值差': min_sum_diff['和值差'],
            '最小和值差排名': min_sum_diff['排名'],
            '最小和值差号码': min_sum_diff['预测号码'],
            '最小跨度差': min_span_diff['跨度差'],
            '最小跨度差排名': min_span_diff['排名'],
            '最小跨度差号码': min_span_diff['预测号码'],
            '形态一致数': len(morph_matches),
            '形态一致排名': [r['排名'] for r in morph_matches[:5]],
        },
        '逐注对比': rows,
    }


def print_report(report):
    """终端打印对比摘要"""
    actual = report['开奖详情']
    hit = report['命中情况']
    best = report['最佳逼近']

    number = actual['号码']

    # 顶部醒目的开奖号码
    print(f"\n{'='*55}")
    print(f"  🎰 今日开奖号码")
    print(f"{'='*55}")
    print(f"")
    print(f"         {number[0]}    {number[1]}    {number[2]}")
    print(f"        {'━'*13}")
    print(f"          {actual['形态']}  |  和值 {actual['和值']}  |  跨度 {actual['跨度']}")
    print(f"")

    # 预测对比
    print(f"  📋 {report['彩种']} 预测对比 (预测期号 {report['预测期号']})")

    if hit['直选命中']:
        print(f"  🎯 直选命中！排名第 {hit['直选最佳排名']} 位")
    elif hit['组选命中']:
        print(f"  🏅 组选命中！排名第 {hit['组选最佳排名']} 位（直选未中）")
    else:
        print(f"  ❌ 未命中 — 最佳逼近: 和值差{best['最小和值差']} | 跨度差{best['最小跨度差']}"
              f" | 形态一致 {best['形态一致数']}/{len(report['逐注对比'])} 注")

    print(f"  {'─'*55}")
    print(f"  {'排名':>4} {'预测':>6} {'直选':>4} {'组选':>4} {'和差':>4} {'跨差':>4} {'形态':>4}")
    for r in report['逐注对比'][:10]:
        print(f"  {r['排名']:>4} {r['预测号码']:>6} "
              f"{'✅' if r['直选命中'] else '  ' :>4} "
              f"{'✅' if r['组选命中'] else '  ' :>4} "
              f"{r['和值差']:>4} {r['跨度差']:>4} "
              f"{'✅' if r['形态一致'] else '  ' :>4}")
    print(f"{'='*55}\n")


def main():
    parser = argparse.ArgumentParser(description='预测 vs 开奖对比')
    parser.add_argument('--lottery', required=True, choices=['pls', 'd3'],
                        help='彩种')
    parser.add_argument('--prediction', help='预测JSON路径（默认 latest）')
    args = parser.parse_args()

    pred_json = load_prediction(args.lottery, args.prediction)
    actual = load_latest_draw(args.lottery)
    rows = compare(pred_json.get('推荐', []), actual)
    report = build_report(pred_json, actual, rows)

    print_report(report)

    # 保存报告
    output_dir = BASE_DIR / 'output' / 'reports'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'{args.lottery}_compare_latest.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  💾 对比报告: {output_path}")


if __name__ == '__main__':
    main()
