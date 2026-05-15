#!/usr/bin/env python3
"""
动态评分引擎 v2（核心）
=====================
对000-999全部1000注号码进行多维度评分，输出Top-K候选。

改进（v2）：
  1. 权重从 YAML 加载，不再硬编码
  2. 组选多样性惩罚：同组选只保留最高分直选
  3. 跨度多样性促进：Top-K尽量覆盖多个跨度
  4. 冷号阈值下调：遗漏>6视为冷号
  5. 过热衰减更敏感

用法：
    python scoring_engine.py --lottery pls --top-k 30
    python scoring_engine.py --lottery d3 --weights rules/scoring_weights.yaml
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import yaml


MAX_SCORE = 100


# ==========================================
#  加载YAML权重
# ==========================================

def load_weights(weight_path=None):
    """从YAML加载评分权重"""
    base = Path(__file__).resolve().parent.parent

    if weight_path is None:
        weight_path = base / 'rules' / 'scoring_weights.yaml'
    else:
        weight_path = base / weight_path

    if weight_path.exists():
        with open(weight_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        w = cfg.get('weights', {})
        # 兼容旧键名（中文）
        weights = {
            '和值': w.get('和值', 18),
            '跨度': w.get('跨度', 15),
            '形态': w.get('形态', 12),
            '奇偶': w.get('奇偶', 8),
            '大小': w.get('大小', 8),
            '012路': w.get('012路', 7),
            '冷热': w.get('冷热', 10),
            '遗漏': w.get('遗漏', 7),
            '组三/六偏向': w.get('组三六偏向', 8),
            '多样性': w.get('多样性', 10),
        }
        params = {
            'cold_threshold': cfg.get('hot_cold', {}).get('cold_threshold', 6),
            'hot_threshold': cfg.get('hot_cold', {}).get('hot_threshold', 3),
            'group_penalty': cfg.get('diversity', {}).get('group_penalty', 5),
            'span_spread': cfg.get('diversity', {}).get('span_spread', 8),
            'overheat_high': cfg.get('overheat_decay', {}).get('high', 0.6),
            'overheat_medium': cfg.get('overheat_decay', {}).get('medium', 0.8),
        }
        return weights, params
    else:
        # 旧版默认权重（兼容）
        return {
            '和值': 20, '跨度': 18, '形态': 14, '奇偶': 10,
            '大小': 10, '012路': 8, '冷热': 5, '遗漏': 5,
            '组三/六偏向': 10, '多样性': 0,
        }, {}


# ==========================================
#  生成000-999全部号码
# ==========================================

def generate_all():
    """生成000-999共1000个号码"""
    nums = [(a, b, c) for a in range(10) for b in range(10) for c in range(10)]
    df = pd.DataFrame(nums, columns=['红球1', '红球2', '红球3'])
    df['number'] = df['红球1'].astype(str) + df['红球2'].astype(str) + df['红球3'].astype(str)

    # 基础特征
    df['和值'] = df['红球1'] + df['红球2'] + df['红球3']
    df['跨度'] = df[['红球1','红球2','红球3']].max(axis=1) - df[['红球1','红球2','红球3']].min(axis=1)
    df['奇数'] = ((df['红球1'] % 2 == 1).astype(int) +
                  (df['红球2'] % 2 == 1).astype(int) +
                  (df['红球3'] % 2 == 1).astype(int))
    df['偶数'] = 3 - df['奇数']
    df['大号'] = ((df['红球1'] >= 5).astype(int) +
                  (df['红球2'] >= 5).astype(int) +
                  (df['红球3'] >= 5).astype(int))
    df['小号'] = 3 - df['大号']

    r0 = (df['红球1'] % 3 == 0).astype(int) + (df['红球2'] % 3 == 0).astype(int) + (df['红球3'] % 3 == 0).astype(int)
    r1 = (df['红球1'] % 3 == 1).astype(int) + (df['红球2'] % 3 == 1).astype(int) + (df['红球3'] % 3 == 1).astype(int)
    r2 = (df['红球1'] % 3 == 2).astype(int) + (df['红球2'] % 3 == 2).astype(int) + (df['红球3'] % 3 == 2).astype(int)
    df['0路数'] = r0
    df['1路数'] = r1
    df['2路数'] = r2

    # 形态
    same_ab = (df['红球1'] == df['红球2'])
    same_bc = (df['红球2'] == df['红球3'])
    same_ac = (df['红球1'] == df['红球3'])
    total_same = same_ab.astype(int) + same_bc.astype(int) + same_ac.astype(int)
    df['形态'] = '组六'
    df.loc[total_same == 3, '形态'] = '豹子'
    df.loc[total_same == 1, '形态'] = '组三'

    # group_number - 用Python字符串拼接避免numpy类型问题
    sorted_nums = np.sort(df[['红球1','红球2','红球3']].values, axis=1)
    gn = [str(int(sorted_nums[i, 0])) + str(int(sorted_nums[i, 1])) + str(int(sorted_nums[i, 2])) for i in range(len(df))]
    df['group_number'] = gn

    return df


# ==========================================
#  评分函数
# ==========================================

def score_number(row, stats, theory, weights, params):
    """
    多维度评分，返回 {总分, 明细}
    """
    details = {}
    total = 0

    s_val = row['和值']
    span_val = row['跨度']
    morph = row['形态']
    window_30 = stats.get('窗口', {}).get('近30期', {})
    window_5 = stats.get('窗口', {}).get('近5期', {})

    W = weights
    P = params
    cold_th = P.get('cold_threshold', 6)
    hot_th = P.get('hot_threshold', 3)

    # ---- 1. 和值评分 ----
    theory_sum = {int(k): v for k, v in theory.get('和值', {}).items()}
    freq = theory_sum.get(s_val, 0)
    max_freq = max(theory_sum.values()) if theory_sum else 1
    theory_score = int(W['和值'] * freq / max_freq)

    sum_freq_30 = {int(k): v for k, v in window_30.get('和值频率', {}).items() if v}
    if sum_freq_30 and sum(sum_freq_30.values()) > 0:
        recent = sum_freq_30.get(s_val, 0) / sum(sum_freq_30.values())
        recent_score = int(W['和值'] * 0.8 * recent * 30)
    else:
        recent_score = 0
    recent_score = min(recent_score, int(W['和值'] * 0.8))

    # 过热衰减
    sum_freq_5 = {int(k): v for k, v in window_5.get('和值频率', {}).items() if v}
    decay = 1.0
    if sum_freq_5.get(s_val, 0) >= 3:
        decay = P['overheat_high']
    elif sum_freq_5.get(s_val, 0) >= 2:
        decay = P['overheat_medium']

    sum_score = int((theory_score * 0.5 + recent_score * 0.5) * decay)
    details['和值'] = (sum_score, f"和值={s_val}")
    total += sum_score

    # ---- 2. 跨度评分 ----
    theory_span = {int(k): v for k, v in theory.get('跨度', {}).items()}
    freq_s = theory_span.get(span_val, 0)
    max_s = max(theory_span.values()) if theory_span else 1
    theory_score_s = int(W['跨度'] * freq_s / max_s)

    span_freq_30 = {int(k): v for k, v in window_30.get('跨度频率', {}).items() if v}
    if span_freq_30 and sum(span_freq_30.values()) > 0:
        recent_s = span_freq_30.get(span_val, 0) / sum(span_freq_30.values())
        recent_score_s = int(W['跨度'] * 0.8 * recent_s * 30)
    else:
        recent_score_s = 0
    recent_score_s = min(recent_score_s, int(W['跨度'] * 0.8))

    span_freq_5 = {int(k): v for k, v in window_5.get('跨度频率', {}).items() if v}
    decay_s = 1.0
    if span_freq_5.get(span_val, 0) >= 3:
        decay_s = P['overheat_high']
    elif span_freq_5.get(span_val, 0) >= 2:
        decay_s = P['overheat_medium']

    span_score = int((theory_score_s * 0.5 + recent_score_s * 0.5) * decay_s)
    details['跨度'] = (span_score, f"跨度={span_val}")
    total += span_score

    # ---- 3. 形态评分 ----
    morph_ratio = {
        '组六': window_30.get('形态_组六_pct', 70),
        '组三': window_30.get('形态_组三_pct', 27),
        '豹子': window_30.get('形态_豹子_pct', 1),
    }
    if morph == '豹子':
        morph_score = 0
    elif morph == '组六':
        morph_score = int(W['形态'] * min(morph_ratio['组六'] / 70, 1.5))
    else:
        morph_score = int(W['形态'] * min(morph_ratio['组三'] / 27, 1.5))
    morph_score = min(morph_score, W['形态'])
    details['形态'] = (morph_score, f"形态={morph}")
    total += morph_score

    # ---- 4. 奇偶评分 ----
    odd = row['奇数']
    odd_score = W['奇偶'] if 1 <= odd <= 2 else 2
    details['奇偶'] = (odd_score, f"奇={odd}")
    total += odd_score

    # ---- 5. 大小评分 ----
    big = row['大号']
    big_score = W['大小'] if 1 <= big <= 2 else 2
    details['大小'] = (big_score, f"大={big}")
    total += big_score

    # ---- 6. 012路评分 ----
    r0, r1, r2 = row['0路数'], row['1路数'], row['2路数']
    n_unique = (r0 > 0) + (r1 > 0) + (r2 > 0)
    if n_unique == 3:
        route_score = W['012路']
    elif n_unique == 2:
        route_score = int(W['012路'] * 0.5)
    else:
        route_score = 1
    details['012路'] = (route_score, f"0路={r0},1路={r1},2路={r2}")
    total += route_score

    # ---- 7. 冷热评分（加强版） ----
    raw_missing = window_30.get('当前遗漏', {})
    latest_missing = {int(k): int(v) for k, v in raw_missing.items() if v is not None} if raw_missing else {}

    if latest_missing:
        cold_count = 0
        hot_count = 0
        for d in [row['红球1'], row['红球2'], row['红球3']]:
            m = latest_missing.get(d, 0)
            if m > cold_th:
                cold_count += 1
            elif m <= hot_th:
                hot_count += 1

        if cold_count == 0 and hot_count >= 1:
            hot_score = W['冷热']
        elif cold_count == 0:
            hot_score = int(W['冷热'] * 0.8)
        elif cold_count == 1:
            hot_score = int(W['冷热'] * 0.4)
        else:
            hot_score = 0  # 2-3个冷号直接0分
    else:
        hot_score = W['冷热'] // 2
    details['冷热'] = (hot_score, f"冷号={cold_count if latest_missing else '?'}")
    total += hot_score

    # ---- 8. 遗漏评分 ----
    avg_miss = window_30.get('平均遗漏', 5)
    if latest_missing:
        miss_scores = []
        for d in [row['红球1'], row['红球2'], row['红球3']]:
            m = latest_missing.get(d, 0)
            if m <= avg_miss * 0.5:
                miss_scores.append(2)
            elif m <= avg_miss * 1.5:
                miss_scores.append(1)
            else:
                miss_scores.append(0)
        miss_score = int(sum(miss_scores) / 3 * W['遗漏'])
    else:
        miss_score = W['遗漏'] // 2
    details['遗漏'] = (miss_score, f"均遗={avg_miss}")
    total += miss_score

    # ---- 总分限制 ----
    total = min(total, MAX_SCORE)

    return {'总分': total, '明细': details, '跨度值': span_val, '组选': row['group_number']}


# ==========================================
#  多样性惩罚
# ==========================================

def apply_diversity(scored, weights, params):
    """
    两轮多样性调整：
    1. 组选惩罚：同组选只保留最高分，其它降分
    2. 跨度促进：覆盖更多跨度值
    """
    W = weights
    P = params
    gp = P.get('group_penalty', 5)
    ss = P.get('span_spread', 8)

    # 组选惩罚
    best_per_group = {}
    for c in scored:
        g = c['组选']
        if g not in best_per_group or c['总分'] > best_per_group[g]['总分']:
            best_per_group[g] = c

    for c in scored:
        detail = c['评分明细']
        if best_per_group.get(c['组选']) is not c:
            c['总分'] -= gp
            if '多样性' not in detail:
                detail['多样性'] = (0, "")
            d = detail['多样性']
            detail['多样性'] = (d[0] - gp, f"组选重复-{gp}")
        else:
            if '多样性' not in detail:
                detail['多样性'] = (0, "")
            d = detail['多样性']
            detail['多样性'] = (d[0], "组选唯一")

    # 跨度促进：给Top-30中不常见的跨度加分
    top_30 = sorted(scored, key=lambda x: x['总分'], reverse=True)[:30]
    span_counts = {}
    for c in top_30:
        sv = c['跨度值']
        span_counts[sv] = span_counts.get(sv, 0) + 1

    for c in scored:
        sv = c['跨度值']
        count_in_top = span_counts.get(sv, 0)
        if 0 < count_in_top <= 2:
            bonus = int(ss * (1 - count_in_top / 3))
            c['总分'] = min(c['总分'] + bonus, MAX_SCORE)
            detail = c['评分明细']
            if '多样性' not in detail:
                detail['多样性'] = (0, "")
            d = detail['多样性']
            detail['多样性'] = (d[0] + bonus, f"跨度{sv}加{bonus}")

    return scored


# ==========================================
#  主流程
# ==========================================

def main():
    parser = argparse.ArgumentParser(description='动态评分引擎 v2')
    parser.add_argument('--lottery', required=True, choices=['pls', 'd3'],
                        help='彩种')
    parser.add_argument('--top-k', type=int, default=30,
                        help='推荐注数')
    parser.add_argument('--exclude-recent', type=int, default=5,
                        help='排除近N期已出号码')
    parser.add_argument('--weights',
                        help='评分权重YAML路径（相对项目根）')
    parser.add_argument('--detail', action='store_true',
                        help='打印每注评分明细')
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent.parent
    lottery_name = '排列三' if args.lottery == 'pls' else '福彩3D'

    # 加载权重
    weights, params = load_weights(args.weights)
    print(f"\n{'='*60}")
    print(f"  🎯 {lottery_name} 评分预测引擎 v2")
    print(f"{'='*60}")
    print(f"  Top-K: {args.top_k} | 排除近{args.exclude_recent}期")
    print(f"  权重: {json.dumps(weights, ensure_ascii=False)}")
    print(f"{'='*60}")

    # 加载统计
    stats_path = base_dir / 'data' / 'cache' / f'{args.lottery}_stats_latest.json'
    if not stats_path.exists():
        print(f"[错误] 统计数据不存在: {stats_path}")
        sys.exit(1)
    with open(stats_path, 'r', encoding='utf-8') as f:
        stats = json.load(f)
    theory = stats.get('理论分布', {})

    # 加载历史
    recent_df = pd.read_csv(base_dir / 'data' / 'processed' / f'{args.lottery}_feat.csv')

    # 生成所有号码
    all_df = generate_all()

    # 排除近N期
    exclude_set = set()
    if args.exclude_recent > 0:
        for i in range(min(args.exclude_recent, len(recent_df))):
            row = recent_df.iloc[i]
            exclude_set.add((int(row['红球1']), int(row['红球2']), int(row['红球3'])))

    # 评分
    scored = []
    for _, row in all_df.iterrows():
        nums = (int(row['红球1']), int(row['红球2']), int(row['红球3']))
        if nums in exclude_set:
            continue
        if row['形态'] == '豹子':
            continue

        result = score_number(row, stats, theory, weights, params)
        scored.append({
            '号码': row['number'],
            'group_number': row['group_number'],
            '和值': int(row['和值']),
            '跨度': int(row['跨度']),
            '形态': row['形态'],
            '总分': result['总分'],
            '评分明细': result['明细'],
            '跨度值': result['跨度值'],
            '组选': result['组选'],
        })

    # 多样性调整
    scored = apply_diversity(scored, weights, params)

    # 排序取Top
    scored.sort(key=lambda x: x['总分'], reverse=True)
    top_k = scored[:args.top_k]

    # 输出
    print(f"\n  {'排名':>4} {'号码':>6} {'组选':>6} {'和值':>4} {'跨度':>4} {'形态':>4} {'总分':>4}")
    print(f"  {'─'*60}")
    span_in_top = {}
    for i, c in enumerate(top_k):
        detail_str = ' '.join(f"{k}={v[0]}" for k, v in c['评分明细'].items())
        print(f"  {i+1:>4} {c['号码']:>6} {c['group_number']:>6} {c['和值']:>4} {c['跨度']:>4} {c['形态']:>4} {c['总分']:>4}")
        sv = c['跨度']
        span_in_top[sv] = span_in_top.get(sv, 0) + 1

    # 统计
    if top_k:
        avg = sum(c['总分'] for c in top_k) / len(top_k)
        print(f"\n  📊 统计:")
        print(f"    总分: {top_k[0]['总分']} ~ {top_k[-1]['总分']}")
        print(f"    平均分: {avg:.1f}")
        print(f"    跨度分布: {dict(sorted(span_in_top.items()))}")
        print(f"    组选数: {len(set(c['group_number'] for c in top_k))}")
        print(f"    高分组(≥60): {sum(1 for c in scored if c['总分'] >= 60)}注")
        print(f"    候选总数: {len(scored)}")

    # 风险提示
    print(f"\n  ⚠️  风险提示: 彩票开奖具有高度随机性，本评分仅基于历史统计和理论分布。")

    # 保存
    output_dir = base_dir / 'output' / 'predictions'
    output_dir.mkdir(parents=True, exist_ok=True)
    latest_issue = int(recent_df.iloc[0]['期数'])
    output_path = output_dir / f'{args.lottery}_predict_{latest_issue}.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            '彩种': lottery_name,
            '最新期号': latest_issue,
            '评分时间': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
            'top_k': args.top_k,
            '排除近N期': args.exclude_recent,
            '权重': weights,
            '参数': params,
            '高分阈值': 60,
            '高分组注数': sum(1 for c in scored if c['总分'] >= 60),
            '候选总数': len(scored),
            '推荐': [{'排名': i+1, **c} for i, c in enumerate(top_k)],
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 保存: {output_path}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
