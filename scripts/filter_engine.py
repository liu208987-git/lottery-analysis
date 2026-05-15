#!/usr/bin/env python3
"""
轻量预过滤（降级版）
====================
原来的 filter_engine.py 改为只做最基础的预过滤：
- 排除豹子（出现率<1%）
- 排除和值极端值（0-3 或 24-27）
- 其他所有过滤逻辑已移入 scoring_engine.py 的评分系统

用法：
    python filter_engine.py --lottery pls
"""

import argparse
import sys
from pathlib import Path
import json

import pandas as pd
import numpy as np


def generate_all() -> list:
    """生成000-999"""
    return [(a, b, c) for a in range(10) for b in range(10) for c in range(10)]


def light_filter(nums: list, exclude_baozi: bool = True, extreme_sum: bool = True) -> list:
    """轻量预过滤"""
    result = []
    for a, b, c in nums:
        s = a + b + c
        # 排除豹子
        if exclude_baozi and a == b == c:
            continue
        # 排除极端和值
        if extreme_sum and (s <= 3 or s >= 24):
            continue
        result.append((a, b, c))
    return result


def main():
    parser = argparse.ArgumentParser(description='轻量预过滤（降级版）')
    parser.add_argument('--lottery', required=True, choices=['pls', 'd3'])
    parser.add_argument('--no-baozi', action='store_true', default=True,
                        help='排除豹子')
    parser.add_argument('--no-extreme', action='store_true', default=True,
                        help='排除极端和值')
    args = parser.parse_args()
    
    all_nums = generate_all()
    filtered = light_filter(all_nums, args.no_baozi, args.no_extreme)
    
    print(f"\n{'='*50}")
    print(f"  轻量预过滤 - {'排列三' if args.lottery=='pls' else '福彩3D'}")
    print(f"{'='*50}")
    print(f"  原始: {len(all_nums)} 注")
    print(f"  排除豹子: {'是' if args.no_baozi else '否'}")
    print(f"  排除极端和值: {'是' if args.no_extreme else '否'}")
    print(f"  剩余: {len(filtered)} 注")
    print(f"  ⚠️  此模块已降级，主要过滤逻辑请使用 scoring_engine.py")
    print(f"{'='*50}")


if __name__ == '__main__':
    main()
