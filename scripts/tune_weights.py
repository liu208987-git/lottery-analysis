#!/usr/bin/env python3
"""
权重自动调优（随机搜索）
=======================
用过去 N 期 walk-forward 回测，随机采样权重组合，按综合分排序。

用法：
    python scripts/tune_weights.py --lottery pls
    python scripts/tune_weights.py --lottery d3 --trials 50 --periods 80

前置条件：output/reviews/review_history.csv 至少积累 15 期复盘数据。
"""

import argparse
import json
import random
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY_PATH = BASE_DIR / 'output' / 'reviews' / 'review_history.csv'
MIN_REVIEW_ROWS = 15


# ── 搜索空间 ──────────────────────────────────────────

SEARCH_SPACE = {
    '和值':       (12, 22),
    '跨度':       (10, 20),
    '形态':       (8, 16),
    '冷热':       (5, 15),
    '多样性':     (5, 20),
    'cold_threshold':  (5, 9),
    'group_penalty':   (3, 12),
    'span_spread':     (5, 15),
    'overheat_high':   (40, 70),    # ×0.01
    'overheat_medium': (60, 90),    # ×0.01
}

FIXED = {'奇偶': 8, '大小': 8, '012路': 7, '遗漏': 7, '组三六偏向': 8}


# ── 权重采样 ──────────────────────────────────────────

def sample_weights():
    """从搜索空间随机采样一组权重"""
    w = {}
    for k, (lo, hi) in SEARCH_SPACE.items():
        if k.startswith('overheat'):
            w[k] = round(random.randint(lo, hi) / 100.0, 2)
        elif k.startswith('cold') or k.startswith('group') or k.startswith('span'):
            w[k] = random.randint(lo, hi)
        else:
            w[k] = random.randint(lo, hi)
    return w


def build_yaml(sample):
    """将采样结果写成 YAML 字符串"""
    return yaml.dump({
        'weights': {
            '和值': sample['和值'],
            '跨度': sample['跨度'],
            '形态': sample['形态'],
            '奇偶': FIXED['奇偶'],
            '大小': FIXED['大小'],
            '012路': FIXED['012路'],
            '冷热': sample['冷热'],
            '遗漏': FIXED['遗漏'],
            '组三六偏向': FIXED['组三六偏向'],
            '多样性': sample['多样性'],
        },
        'hot_cold': {
            'cold_threshold': sample['cold_threshold'],
            'hot_threshold': 3,
        },
        'diversity': {
            'group_penalty': sample['group_penalty'],
            'span_spread': sample['span_spread'],
        },
        'overheat_decay': {
            'high': sample['overheat_high'],
            'medium': sample['overheat_medium'],
        },
    }, allow_unicode=True, sort_keys=False)


# ── 评分 ──────────────────────────────────────────────

def composite_score(result: dict, periods: int) -> float:
    """综合分 = 直选命中率*30 + 组选命中率*20 - 最大连未*2 + ROI/5"""
    sr = result.get('动态评分', {})
    direct = float(sr.get('直选命中', 0)) / periods
    group = float(sr.get('组选命中', 0)) / periods
    max_miss = int(sr.get('最大连续未中', 0))

    roi_str = sr.get('ROI', '0%').replace('%', '')
    try:
        roi = float(roi_str)
    except (ValueError, TypeError):
        roi = 0.0

    return direct * 30 + group * 20 - max_miss * 2 + roi / 5


# ── 主流程 ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='权重自动调优（随机搜索）')
    parser.add_argument('--lottery', required=True, choices=['pls', 'd3'],
                        help='彩种')
    parser.add_argument('--trials', type=int, default=30,
                        help='随机采样次数（默认30）')
    parser.add_argument('--periods', type=int, default=50,
                        help='回测期数（默认50）')
    parser.add_argument('--top-k', type=int, default=30,
                        help='推荐注数（默认30）')
    parser.add_argument('--seed', type=int, default=42,
                        help='随机种子（默认42）')
    args = parser.parse_args()

    # ── 门槛守卫 ──
    if not HISTORY_PATH.exists():
        print(f"\n  ⛔ 复盘总表不存在: {HISTORY_PATH}")
        print(f"  请先积累复盘数据。开奖后运行:")
        print(f"    python scripts/compare_result.py --lottery {args.lottery}")
        return

    hist = pd.read_csv(HISTORY_PATH, dtype=str, encoding='utf-8-sig')
    n_rows = len(hist)
    if n_rows < MIN_REVIEW_ROWS:
        print(f"\n  ⏳ 复盘数据不足: {n_rows} 期 < {MIN_REVIEW_ROWS} 期")
        print(f"  需要至少 {MIN_REVIEW_ROWS} 期复盘数据才能启动调参，当前还需 {MIN_REVIEW_ROWS - n_rows} 期。")
        print(f"  继续运行每日流程即可自动积累。")
        return

    print(f"\n  ✅ 复盘数据达标: {n_rows} 期 >= {MIN_REVIEW_ROWS} 期，开始调参。")

    # ── 加载数据 ──
    lottery_name = '排列三' if args.lottery == 'pls' else '福彩3D'
    data_path = BASE_DIR / 'data' / 'processed' / f'{args.lottery}_feat.csv'
    if not data_path.exists():
        print(f"\n  [错误] 特征数据不存在: {data_path}")
        sys.exit(1)

    df = pd.read_csv(data_path, encoding='utf-8-sig')
    df = df.sort_values('期数', ascending=False).reset_index(drop=True)

    from stats_engine import generate_theoretical_distribution
    theory = generate_theoretical_distribution()

    # ── 随机搜索 ──
    random.seed(args.seed)
    np.random.seed(args.seed)

    print(f"\n{'='*60}")
    print(f"  🔧 {lottery_name} 权重调优")
    print(f"{'='*60}")
    print(f"  数据: {len(df)} 期 | 回测窗口: {args.periods} 期 | 采样: {args.trials} 次")
    print(f"  {'─'*60}")

    results = []
    best_score = -999
    best_sample = None

    for i in range(args.trials):
        sample = sample_weights()
        yaml_str = build_yaml(sample)

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.yaml', encoding='utf-8', delete=False
        ) as f:
            f.write(yaml_str)
            tmp_path = f.name

        try:
            from backtest import walk_forward
            bt = walk_forward(df, theory, top_k=args.top_k,
                              test_periods=args.periods, train_window=100,
                              lottery_code=args.lottery, weight_path=tmp_path)
            score = composite_score(bt, args.periods)
        except Exception as e:
            score = -999
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        results.append({'trial': i + 1, 'weights': sample, 'score': score, 'backtest': bt})

        if score > best_score:
            best_score = score
            best_sample = sample

        if (i + 1) % 10 == 0:
            print(f"  进度: {i+1}/{args.trials} | 当前最佳分: {best_score:.1f}")

    # ── 排序输出 ──
    results.sort(key=lambda x: x['score'], reverse=True)

    print(f"\n  {'─'*60}")
    print(f"  🏆 Top-5 权重组合")
    print(f"  {'─'*60}")

    for rank, r in enumerate(results[:5], 1):
        w = r['weights']
        bt = r['backtest']
        sr = bt.get('动态评分', {})
        print(f"\n  #{rank} 综合分: {r['score']:.1f}")
        print(f"     和值={w['和值']} 跨度={w['跨度']} 形态={w['形态']} "
              f"冷热={w['冷热']} 多样性={w['多样性']}")
        print(f"     冷阈值={w['cold_threshold']} 组惩罚={w['group_penalty']} "
              f"跨促进={w['span_spread']} 过热={w['overheat_high']}/{w['overheat_medium']}")
        print(f"     直选{sr.get('直选命中','?')}/{args.periods} | "
              f"组选{sr.get('组选命中','?')}/{args.periods} | "
              f"ROI={sr.get('ROI','?')} | 最长连未={sr.get('最大连续未中','?')}期")

    # ── 保存最佳 ──
    if best_sample:
        output_dir = BASE_DIR / 'rules'
        best_path = output_dir / f'scoring_weights_{args.lottery}_tuned.yaml'
        best_yaml = build_yaml(best_sample)
        best_path.write_text(best_yaml, encoding='utf-8')
        print(f"\n  💾 最佳权重已保存: {best_path}")

        # 保存完整搜索结果
        log_dir = BASE_DIR / 'output' / 'tuning'
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f'{args.lottery}_tuning_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
        serializable = []
        for r in results[:10]:
            serializable.append({
                'trial': r['trial'],
                'score': r['score'],
                'weights': {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in r['weights'].items()},
                'backtest_summary': {k: v for k, v in r['backtest'].get('动态评分', {}).items()},
            })
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        print(f"  💾 搜索记录: {log_path}")

    # ── 稳定性分析 ──
    if best_sample and len(df) >= args.periods * 2:
        print(f"\n  {'─'*60}")
        print(f"  🔍 参数稳定性分析")
        print(f"  {'─'*60}")

        best_yaml_str = build_yaml(best_sample)
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.yaml', encoding='utf-8', delete=False
        ) as f:
            f.write(best_yaml_str)
            tmp_path = f.name

        windows = [
            ('最近{}期'.format(args.periods), 0),
            ('往前{}-{}期'.format(args.periods + 1, args.periods * 2), args.periods),
        ]

        scores = []
        try:
            from backtest import walk_forward
            for wname, offset in windows:
                sub_df = df.iloc[offset:offset + args.periods].copy()
                if len(sub_df) < args.periods:
                    continue
                bt = walk_forward(sub_df, theory, top_k=args.top_k,
                                  test_periods=min(args.periods, len(sub_df) - 30),
                                  train_window=min(100, len(sub_df) // 2),
                                  lottery_code=args.lottery, weight_path=tmp_path)
                sc = composite_score(bt, min(args.periods, len(sub_df) - 30))
                scores.append((wname, sc, bt))
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        if len(scores) == 2:
            diff = abs(scores[0][1] - scores[1][1])
            avg = (scores[0][1] + scores[1][1]) / 2
            rel_change = diff / abs(avg) * 100 if abs(avg) > 0.01 else 0

            for wname, sc, _ in scores:
                print(f"  {wname}: 综合分 {sc:.1f}")

            if rel_change > 50:
                stability = '⚠️ 不稳定（差异 {:.0f}%）— 最佳权重可能过拟合'.format(rel_change)
            elif rel_change > 25:
                stability = '🟡 一般（差异 {:.0f}%）— 权重尚可但不够稳健'.format(rel_change)
            else:
                stability = '✅ 稳定（差异 {:.0f}%）— 权重跨时间段表现一致'.format(rel_change)

            print(f"  → {stability}")

    print(f"\n{'='*60}\n")


if __name__ == '__main__':
    main()
