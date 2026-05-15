#!/usr/bin/env python3
"""
动态评分引擎（核心）
====================
对000-999全部1000注号码进行多维度评分，输出Top-K候选。
替代原来的硬过滤逻辑。

评分思路：
  1. 每个号码从0分开始
  2. 和值在理论高频区间→加分（强权重）
  3. 跨度在理论高频区间→加分（强权重）
  4. 形态匹配近期趋势→加分（中权重）
  5. 奇偶/大小适中→加分（中权重）
  6. 012路均衡→加分（中权重）
  7. 冷热度评分（弱权重）
  8. 遗漏评分（弱权重）
  9. 按总分排序取Top-K

用法：
    python scoring_engine.py --lottery pls
    python scoring_engine.py --lottery d3 --top-k 50
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import numpy as np


# ==========================================
#  评分权重
# ==========================================

WEIGHTS = {
    '和值': 20,       # 强权重
    '跨度': 18,       # 强权重
    '形态': 14,       # 中强权重
    '奇偶': 10,       # 中权重
    '大小': 10,       # 中权重
    '012路': 8,       # 中权重
    '冷热': 5,        # 弱权重
    '遗漏': 5,        # 弱权重
    '组三/六偏向': 10, # 中权重
}

MAX_SCORE = sum(WEIGHTS.values())  # = 100


# ==========================================
#  生成000-999全部号码
# ==========================================

def generate_all() -> pd.DataFrame:
    """生成000-999共1000个号码"""
    nums = [(a, b, c) for a in range(10) for b in range(10) for c in range(10)]
    df = pd.DataFrame(nums, columns=['红球1', '红球2', '红球3'])
    df['number'] = df['红球1'].astype(str) + df['红球2'].astype(str) + df['红球3'].astype(str)
    
    # 计算基础特征
    df['和值'] = df['红球1'] + df['红球2'] + df['红球3']
    df['跨度'] = df[['红球1','红球2','红球3']].max(axis=1) - df[['红球1','红球2','红球3']].min(axis=1)
    df['奇数'] = ((df['红球1'] % 2 == 1).astype(int) + (df['红球2'] % 2 == 1).astype(int) + (df['红球3'] % 2 == 1).astype(int))
    df['偶数'] = 3 - df['奇数']
    df['大号'] = ((df['红球1'] >= 5).astype(int) + (df['红球2'] >= 5).astype(int) + (df['红球3'] >= 5).astype(int))
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
    
    # group_number
    sorted_nums = np.sort(df[['红球1','红球2','红球3']].values, axis=1)
    df['group_number'] = (sorted_nums[:, 0].astype(str) + 
                          sorted_nums[:, 1].astype(str) + 
                          sorted_nums[:, 2].astype(str))
    
    return df


# ==========================================
#  评分函数
# ==========================================

def score_number(row, stats: dict, theory: dict) -> dict:
    """
    对一个号码进行多维度评分
    
    返回: {
        '总分': N,
        '和值分': N, '跨度分': N, ...
        '明细': {...}
    }
    """
    details = {}
    total = 0
    
    # ---- 1. 和值评分（强权重 20分）—— 理论60% + 近期走势40% ----
    s_val = row['和值'] if isinstance(row, dict) else row['和值']
    # 理论分布分
    theory_sum = {int(k): v for k, v in theory.get('和值', {}).items()}
    freq = theory_sum.get(s_val, 0)
    freq_ratio = freq / max(theory_sum.values()) if max(theory_sum.values()) > 0 else 0
    theory_score = int(WEIGHTS['和值'] * freq_ratio)
    
    # 近期走势分（近30期实际频率）
    window_30 = stats.get('窗口', {}).get('近30期', {})
    sum_freq = window_30.get('和值频率', {})
    sum_freq = {int(k): v for k, v in sum_freq.items()} if sum_freq else {}
    if sum_freq and sum(sum_freq.values()) > 0:
        recent_ratio = sum_freq.get(s_val, 0) / sum(sum_freq.values())
        recent_score = int(WEIGHTS['和值'] * 0.8 * recent_ratio * 30)  # 放大近期差异
    else:
        recent_score = 0
    recent_score = min(recent_score, int(WEIGHTS['和值'] * 0.8))
    
    # 过热衰减：如果这个和值近5期出现≥3次，降低得分
    sum_freq_5 = stats.get('窗口', {}).get('近5期', {}).get('和值频率', {})
    sum_freq_5 = {int(k): v for k, v in sum_freq_5.items()} if sum_freq_5 else {}
    decay = 1.0
    if sum_freq_5.get(s_val, 0) >= 3:
        decay = 0.6
    elif sum_freq_5.get(s_val, 0) >= 2:
        decay = 0.8
    
    sum_score = int((theory_score * 0.6 + recent_score * 0.4) * decay)
    details['和值'] = (sum_score, f"和值={s_val}, 理论分={theory_score}, 近期分={recent_score}, 衰减={decay}")
    total += sum_score
    
    # ---- 2. 跨度评分（强权重 18分）—— 理论60% + 近期走势40% ----
    span_val = row['跨度']
    theory_span = {int(k): v for k, v in theory.get('跨度', {}).items()}
    freq_s = theory_span.get(span_val, 0)
    freq_ratio_s = freq_s / max(theory_span.values()) if max(theory_span.values()) > 0 else 0
    theory_score_s = int(WEIGHTS['跨度'] * freq_ratio_s)
    
    # 近期跨度走势
    span_freq = window_30.get('跨度频率', {})
    span_freq = {int(k): v for k, v in span_freq.items()} if span_freq else {}
    if span_freq and sum(span_freq.values()) > 0:
        recent_ratio_s = span_freq.get(span_val, 0) / sum(span_freq.values())
        recent_score_s = int(WEIGHTS['跨度'] * 0.8 * recent_ratio_s * 30)
    else:
        recent_score_s = 0
    recent_score_s = min(recent_score_s, int(WEIGHTS['跨度'] * 0.8))
    
    # 过热衰减
    span_freq_5 = stats.get('窗口', {}).get('近5期', {}).get('跨度频率', {})
    span_freq_5 = {int(k): v for k, v in span_freq_5.items()} if span_freq_5 else {}
    decay_s = 1.0
    if span_freq_5.get(span_val, 0) >= 3:
        decay_s = 0.5
    elif span_freq_5.get(span_val, 0) >= 2:
        decay_s = 0.7
    
    span_score = int((theory_score_s * 0.6 + recent_score_s * 0.4) * decay_s)
    details['跨度'] = (span_score, f"跨度={span_val}, 理论分={theory_score_s}, 近期分={recent_score_s}, 衰减={decay_s}")
    total += span_score
    
    # ---- 3. 形态评分（中强权重 14分） ----
    morph = row['形态']
    window_30 = stats.get('窗口', {}).get('近30期', {})
    morph_ratio = {
        '组六': window_30.get('形态_组六_pct', 70),
        '组三': window_30.get('形态_组三_pct', 27),
        '豹子': window_30.get('形态_豹子_pct', 1),
    }
    
    if morph == '豹子':
        morph_score = 0  # 豹子几乎不出现
    elif morph == '组六':
        morph_score = int(WEIGHTS['形态'] * min(morph_ratio['组六'] / 70, 1.5))
    else:  # 组三
        morph_score = int(WEIGHTS['形态'] * min(morph_ratio['组三'] / 27, 1.5))
    morph_score = min(morph_score, WEIGHTS['形态'])
    details['形态'] = (morph_score, f"形态={morph}, 30期比例: 组六{morph_ratio['组六']}% 组三{morph_ratio['组三']}%")
    total += morph_score
    
    # ---- 4. 奇偶评分（中权重 10分） ----
    odd = row['奇数']
    if 1 <= odd <= 2:  # 1奇2偶或2奇1偶是最常见
        odd_score = WEIGHTS['奇偶']
    else:
        odd_score = 2  # 全奇全偶也给点保底分
    details['奇偶'] = (odd_score, f"奇数={odd}")
    total += odd_score
    
    # ---- 5. 大小评分（中权重 10分） ----
    big = row['大号']
    if 1 <= big <= 2:
        big_score = WEIGHTS['大小']
    else:
        big_score = 2
    details['大小'] = (big_score, f"大号={big}")
    total += big_score
    
    # ---- 6. 012路评分（中权重 8分） ----
    r0, r1, r2 = row['0路数'], row['1路数'], row['2路数']
    unique_routes = (r0 > 0) + (r1 > 0) + (r2 > 0)
    if unique_routes == 3:  # 三路各至少一个 - 最均衡
        route_score = WEIGHTS['012路']
    elif unique_routes == 2:
        route_score = int(WEIGHTS['012路'] * 0.5)
    else:
        route_score = 1
    details['012路'] = (route_score, f"0路={r0}, 1路={r1}, 2路={r2}")
    total += route_score
    
    # ---- 7. 冷热评分（弱权重 5分）—— 冷号惩罚加强 ----
    raw_missing = stats.get('窗口', {}).get('近30期', {}).get('当前遗漏', {})
    latest_missing = {int(k): int(v) for k, v in raw_missing.items()} if raw_missing else {}
    if latest_missing:
        cold_count = 0
        hot_count = 0
        for d in [row['红球1'], row['红球2'], row['红球3']]:
            m = latest_missing.get(d, 0)
            if m > 8:
                cold_count += 1
            elif m <= 3:
                hot_count += 1
        # 0冷号+有热号 = 满分；1冷号 = 部分分；≥2冷号 = 扣分
        if cold_count == 0 and hot_count >= 1:
            hot_score = WEIGHTS['冷热']
        elif cold_count == 0:
            hot_score = int(WEIGHTS['冷热'] * 0.8)
        elif cold_count == 1:
            hot_score = int(WEIGHTS['冷热'] * 0.4)
        else:
            hot_score = 0  # 2-3个冷号的号码直接0分
    else:
        hot_score = WEIGHTS['冷热'] // 2
    details['冷热'] = (hot_score, f"冷号数={cold_count if latest_missing else 'N/A'}")
    total += hot_score
    
    # ---- 8. 遗漏评分（弱权重 5分） ----
    avg_miss = stats.get('窗口', {}).get('近30期', {}).get('平均遗漏', 5)
    if latest_missing:
        miss_scores = []
        for d in [row['红球1'], row['红球2'], row['红球3']]:
            m = latest_missing.get(str(d), 0)
            if m <= avg_miss * 0.5:
                miss_scores.append(2)
            elif m <= avg_miss * 1.5:
                miss_scores.append(1)
            else:
                miss_scores.append(0)
        miss_score = int(sum(miss_scores) / 3 * WEIGHTS['遗漏'])
    else:
        miss_score = WEIGHTS['遗漏'] // 2
    details['遗漏'] = (miss_score, f"平均遗漏={avg_miss}")
    total += miss_score
    
    # ---- 总分归一化到100 ----
    total = min(total, MAX_SCORE)
    
    return {
        '总分': total,
        '明细': details,
    }


# ==========================================
#  主流程
# ==========================================

def main():
    parser = argparse.ArgumentParser(description='动态评分引擎')
    parser.add_argument('--lottery', required=True, choices=['pls', 'd3'],
                        help='彩种')
    parser.add_argument('--top-k', type=int, default=30,
                        help='推荐注数（默认30，可选10/30/50）')
    parser.add_argument('--exclude-recent', type=int, default=5,
                        help='排除近N期已出号码（0为不排除）')
    parser.add_argument('--exclude-baozi', action='store_true',
                        help='排除豹子号码')
    parser.add_argument('--detail', action='store_true',
                        help='打印每注评分明细')
    args = parser.parse_args()
    
    base_dir = Path(__file__).resolve().parent.parent
    lottery_name = '排列三' if args.lottery == 'pls' else '福彩3D'
    
    # 加载统计数据
    stats_path = base_dir / 'data' / 'cache' / f'{args.lottery}_stats_latest.json'
    if not stats_path.exists():
        print(f"[错误] 统计数据不存在，请先运行 stats_engine.py: {stats_path}")
        sys.exit(1)
    with open(stats_path, 'r', encoding='utf-8') as f:
        stats = json.load(f)
    
    theory = stats.get('理论分布', {})
    
    # 加载最近历史数据（用于排除已出号码）
    recent_df = pd.read_csv(base_dir / 'data' / 'processed' / f'{args.lottery}_feat.csv')
    
    print(f"\n{'='*60}")
    print(f"  🎯 {lottery_name} 评分预测引擎")
    print(f"{'='*60}")
    print(f"  总候选: 1000注 | Top-K: {args.top_k} | 排除近{args.exclude_recent}期")
    print(f"  {'='*60}")
    
    # 生成所有号码
    all_df = generate_all()
    
    # 排除近N期已出号码（可选轻过滤）
    exclude_set = set()
    if args.exclude_recent > 0:
        for i in range(min(args.exclude_recent, len(recent_df))):
            row = recent_df.iloc[i]
            exclude_set.add((int(row['红球1']), int(row['红球2']), int(row['红球3'])))
    
    # 对每个号码评分
    scored = []
    for _, row in all_df.iterrows():
        nums = (int(row['红球1']), int(row['红球2']), int(row['红球3']))
        if nums in exclude_set:
            continue
        if args.exclude_baozi and row['形态'] == '豹子':
            continue
        
        result = score_number(row, stats, theory)
        scored.append({
            '号码': row['number'],
            'group_number': row['group_number'],
            '和值': int(row['和值']),
            '跨度': int(row['跨度']),
            '形态': row['形态'],
            '总分': result['总分'],
            '评分明细': result['明细'],
        })
    
    # 按总分排序
    scored.sort(key=lambda x: x['总分'], reverse=True)
    top_k = scored[:args.top_k]
    
    # 输出
    print(f"\n  {'排名':>4} {'号码':>6} {'和值':>4} {'跨度':>4} {'形态':>4} {'总分':>4}  {'散列'}")
    print(f"  {'─'*55}")
    for i, c in enumerate(top_k):
        detail_str = ' '.join(f"{k}={v[0]}" for k, v in c['评分明细'].items())
        print(f"  {i+1:>4} {c['号码']:>6} {c['和值']:>4} {c['跨度']:>4} {c['形态']:>4} {c['总分']:>4}  {detail_str}")
    
    # 统计概况
    avg_score = sum(c['总分'] for c in top_k) / len(top_k) if top_k else 0
    print(f"\n  📊 统计概况:")
    print(f"    总分分布: {top_k[0]['总分'] if top_k else 0} ~ {top_k[-1]['总分'] if top_k else 0}")
    print(f"    平均分: {avg_score:.1f}")
    print(f"    候选总数: {len(scored)}（含低分）")
    
    # 高分组
    high_score = [c for c in scored if c['总分'] >= 60]
    print(f"    高分组(≥60分): {len(high_score)}注")
    
    # 风险提示
    print(f"\n  {'─'*55}")
    print(f"  ⚠️  风险提示")
    print(f"  {'─'*55}")
    print(f"  彩票开奖结果具有高度随机性。")
    print(f"  本评分仅基于历史数据统计和理论分布，不代表未来开奖结果。")
    print(f"  请理性看待，不建议将分析结果作为实际投注依据。")
    print(f"{'='*60}\n")
    
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
            '权重': WEIGHTS,
            '高分阈值': 60,
            '高分组注数': len(high_score),
            '候选总数': len(scored),
            '推荐': [{'排名': i+1, **c} for i, c in enumerate(top_k)],
        }, f, ensure_ascii=False, indent=2)
    print(f"  💾 结果已保存: {output_path}")


if __name__ == '__main__':
    main()
