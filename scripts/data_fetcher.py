#!/usr/bin/env python3
"""
数据自动获取脚本
================
从体彩/福彩官方渠道自动拉取最新开奖数据。

用法：
    python data_fetcher.py --lottery pls      # 排列三
    python data_fetcher.py --lottery d3       # 福彩3D  
    python data_fetcher.py --all              # 两个一起拉
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/124.0.0.0 Safari/537.36',
}

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / 'data' / 'raw'
RAW_DIR.mkdir(parents=True, exist_ok=True)


def fetch_pls(limit=30):
    """从体彩API获取排列三数据"""
    url = (
        "https://webapi.sporttery.cn/gateway/lottery/"
        f"getHistoryPageListV1.qry?gameNo=350133&provinceId=0"
        f"&pageSize={min(limit, 50)}&is498=1"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        data = r.json()
    except Exception:
        return []

    results = []
    for item in data.get('value', {}).get('list', []):
        nums = item['lotteryDrawResult'].split()
        results.append({
            '期号': item['lotteryDrawNum'],
            '日期': item['lotteryDrawTime'],
            '号码': ''.join(nums[:3]),
        })
    return results


def fetch_fc3d(limit=30):
    """从福彩官网API获取福彩3D数据"""
    url = (
        "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/"
        f"kjxx/findDrawNotice?name=3d&issueCount={limit}&systemType=PC"
    )
    try:
        r = requests.get(url, headers={
            **HEADERS,
            'Referer': 'https://www.cwl.gov.cn/ygkj/wqkjgg/fc3d/',
            'Cookie': 'wqkjgg=3d',
        }, timeout=15)
        data = r.json()
    except Exception:
        return []

    results = []
    for item in data.get('result', []):
        red = item.get('red', '')
        results.append({
            '期号': item.get('code', ''),
            '日期': item.get('date', ''),
            '号码': red.replace(',', ''),
        })
    return results


def save_csv(lottery, data):
    """保存数据"""
    now = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = RAW_DIR / f'{lottery}_raw_{now}.csv'
    if not data:
        print(f"[警告] 无数据可保存")
        return None
    fieldnames = list(data[0].keys())
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(data)
    print(f"[OK] {len(data)}条 -> {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description='彩票开奖数据获取')
    parser.add_argument('--lottery', choices=['pls', 'd3'])
    parser.add_argument('--all', action='store_true', help='获取所有彩种')
    args = parser.parse_args()

    if args.all:
        args.lottery = None
    elif not args.lottery:
        parser.print_help()
        sys.exit(1)

    if args.lottery in (None, 'pls'):
        print("\n  排列三 数据获取")
        d = fetch_pls()
        if d:
            save_csv('pls', d)
            print(f"  最新: {d[0]['期号']} {d[0]['号码']}")
        else:
            print("  ⚠️  获取失败")

    if args.lottery in (None, 'd3'):
        print("\n  福彩3D 数据获取")
        d = fetch_fc3d()
        if d:
            save_csv('d3', d)
            print(f"  最新: {d[0]['期号']} {d[0]['号码']}")
        else:
            print("  ⚠️  获取失败")

    print("\n✅ 完成")


if __name__ == '__main__':
    main()
