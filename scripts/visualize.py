#!/usr/bin/env python3
"""
可视化工具（可选）
=================
生成走势图、遗漏图、热力图，不参与核心决策。

用法：
    python visualize.py --lottery pls
    python visualize.py --lottery d3 --chart heatmap
"""

import argparse
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot_trend(df: pd.DataFrame, lottery_name: str, output_dir: Path, periods: int = 50):
    """和值/跨度走势图"""
    df = df.head(periods).sort_values('期数', ascending=True)
    
    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    
    # 和值走势
    axes[0].plot(df['期数'].astype(str), df['和值'], 'b-o', markersize=3, linewidth=1)
    axes[0].axhline(y=df['和值'].mean(), color='r', linestyle='--', alpha=0.5, label=f"均值={df['和值'].mean():.1f}")
    axes[0].set_ylabel('和值')
    axes[0].set_title(f'{lottery_name} 和值走势 (近{periods}期)')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # 跨度走势
    axes[1].plot(df['期数'].astype(str), df['跨度'], 'g-s', markersize=3, linewidth=1)
    axes[1].axhline(y=df['跨度'].mean(), color='r', linestyle='--', alpha=0.5, label=f"均值={df['跨度'].mean():.1f}")
    axes[1].set_ylabel('跨度')
    axes[1].set_title('跨度走势')
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    
    # 形态分布
    morph_colors = {'组六': 'blue', '组三': 'orange', '豹子': 'red'}
    morph_series = df['形态'].map(morph_colors)
    axes[2].scatter(range(len(df)), [1]*len(df), c=morph_series, s=30, alpha=0.6)
    axes[2].set_yticks([])
    axes[2].set_ylabel('形态')
    axes[2].set_title('形态分布 (蓝=组六, 橙=组三, 红=豹子)')
    axes[2].set_xlabel('期号')
    
    plt.xticks(rotation=45, fontsize=8)
    plt.tight_layout()
    
    path = output_dir / f'{lottery_name}_trend.png'
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  ✅ 走势图: {path}")


def plot_missing(df: pd.DataFrame, lottery_name: str, output_dir: Path):
    """遗漏柱状图"""
    latest = df.iloc[0]
    digits = list(range(10))
    miss_values = [int(latest[f'遗漏_{d}']) for d in digits]
    
    colors = ['#4CAF50' if v <= 3 else '#FFC107' if v <= 8 else '#F44336' for v in miss_values]
    
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(digits, miss_values, color=colors, edgecolor='white', linewidth=1.2)
    
    for bar, v in zip(bars, miss_values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                str(v), ha='center', va='bottom', fontsize=11)
    
    ax.axhline(y=sum(miss_values)/10, color='gray', linestyle='--', alpha=0.7, label=f"平均={sum(miss_values)/10:.1f}")
    ax.set_xlabel('数字')
    ax.set_ylabel('遗漏期数')
    ax.set_title(f'{lottery_name} 当前遗漏 (绿=热, 黄=温, 红=冷)')
    ax.set_xticks(digits)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    path = output_dir / f'{lottery_name}_missing.png'
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  ✅ 遗漏图: {path}")


def plot_heatmap(df: pd.DataFrame, lottery_name: str, output_dir: Path, periods: int = 100):
    """分位热力图"""
    df_window = df.head(periods)
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    for idx, (pos, col) in enumerate([('百位', '红球1'), ('十位', '红球2'), ('个位', '红球3')]):
        freq = df_window[col].value_counts().reindex(range(10), fill_value=0)
        freq_pct = freq / len(df_window) * 100
        
        ax = axes[idx]
        bars = ax.bar(range(10), freq_pct.values, color='steelblue', edgecolor='white')
        
        for bar, v in zip(bars, freq_pct.values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                    f'{v:.1f}%', ha='center', va='bottom', fontsize=8)
        
        ax.axhline(y=10, color='r', linestyle='--', alpha=0.5, label='理论值(10%)')
        ax.set_xlabel('数字')
        ax.set_ylabel('出现频率 (%)')
        ax.set_title(f'{pos} (近{periods}期)')
        ax.set_xticks(range(10))
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')
    
    plt.suptitle(f'{lottery_name} 分位数字频率', fontsize=14)
    plt.tight_layout()
    path = output_dir / f'{lottery_name}_heatmap.png'
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  ✅ 热力图: {path}")


def main():
    parser = argparse.ArgumentParser(description='可视化工具')
    parser.add_argument('--lottery', required=True, choices=['pls', 'd3'])
    parser.add_argument('--chart', choices=['trend', 'missing', 'heatmap', 'all'], default='all',
                        help='图表类型')
    parser.add_argument('--periods', type=int, default=50,
                        help='趋势图显示期数')
    args = parser.parse_args()
    
    base_dir = Path(__file__).resolve().parent.parent
    lottery_name = '排列三' if args.lottery == 'pls' else '福彩3D'
    
    data_path = base_dir / 'data' / 'processed' / f'{args.lottery}_feat.csv'
    df = pd.read_csv(data_path)
    
    output_dir = base_dir / 'output' / 'charts'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*50}")
    print(f"  可视化 - {lottery_name}")
    print(f"{'='*50}")
    
    if args.chart in ('trend', 'all'):
        plot_trend(df, lottery_name, output_dir, args.periods)
    
    if args.chart in ('missing', 'all'):
        plot_missing(df, lottery_name, output_dir)
    
    if args.chart in ('heatmap', 'all'):
        plot_heatmap(df, lottery_name, output_dir)


if __name__ == '__main__':
    main()
