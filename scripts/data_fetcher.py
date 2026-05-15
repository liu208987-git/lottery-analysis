#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
彩票数据获取器 —— 排列三 & 福彩3D
===================================
支持增量更新、日志记录、异常处理。

API 说明：
- 排列三：体彩官方 API webapi.sporttery.cn（已验证可用）
- 福彩3D：福彩官网 API cwl.gov.cn（有 WAF 防护，当前 403）

用法：
    python data_fetcher.py --all              # 获取所有彩种
    python data_fetcher.py --lottery pls      # 仅排列三
    python data_fetcher.py --lottery d3       # 仅福彩3D
    python data_fetcher.py --all --days 30    # 获取最近30期
"""

import argparse
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import requests

# ==========================================
#  日志
# ==========================================

LOG_DIR = Path(__file__).resolve().parent.parent / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(LOG_DIR / 'data_fetcher.log'), encoding='utf-8'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ==========================================
#  路径
# ==========================================

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / 'data' / 'raw'
RAW_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/124.0.0.0 Safari/537.36',
}


# ==========================================
#  排列三 —— 体彩官方 API ✅ 可用
# ==========================================

def fetch_pls(limit=30):
    """从体彩官方API获取排列三最新数据"""
    url = (
        "https://webapi.sporttery.cn/gateway/lottery/"
        f"getHistoryPageListV1.qry?gameNo=350133&provinceId=0"
        f"&pageSize={min(limit, 50)}&is498=1"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.error(f"排列三API请求失败: {e}")
        return []

    results = []
    for item in data.get('value', {}).get('list', []):
        nums = item['lotteryDrawResult'].split()
        results.append({
            '期号': item['lotteryDrawNum'],
            '日期': item['lotteryDrawTime'],
            '号码': ''.join(nums[:3]),
        })
    logger.info(f"排列三: 获取到 {len(results)} 条 (最新: {results[0]['期号']})" if results else "排列三: 无数据")
    return results


# ==========================================
#  福彩3D —— 福彩官网 API ⚠️ 有WAF防护
# ==========================================

def fetch_fc3d(limit=30):
    """从福彩官网API获取福彩3D最新数据（存在WAF防护，可能返回403）"""
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
        if r.status_code == 403:
            logger.warning("福彩3D: API被WAF拦截(403)，需通过浏览器/Playwright替代")
            return []
        r.raise_for_status()
        data = r.json()
    except requests.JSONDecodeError:
        logger.warning("福彩3D: API返回非JSON（可能被重定向或拦截）")
        return []
    except Exception as e:
        logger.error(f"福彩3D API请求失败: {e}")
        return []

    results = []
    for item in data.get('result', []):
        red = item.get('red', '')
        results.append({
            '期号': item.get('code', ''),
            '日期': item.get('date', ''),
            '号码': red.replace(',', ''),
        })
    if results:
        logger.info(f"福彩3D: 获取到 {len(results)} 条 (最新: {results[0]['期号']})")
    else:
        logger.warning("福彩3D: API返回为空")
    return results


# ==========================================
#  增量保存（避免重复期号）
# ==========================================

def save_incremental(data, lottery):
    """增量保存：合并新旧数据，按期号去重"""
    file_path = RAW_DIR / f'{lottery}_raw.csv'

    if not data:
        logger.warning(f"{lottery}: 无数据，跳过保存")
        return None

    # 新数据转 dict 便于合并
    fieldnames = list(data[0].keys())
    new_rows = {r['期号']: r for r in data}

    if file_path.exists():
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['期号'] not in new_rows:
                    new_rows[row['期号']] = row

    # 按期号降序写入
    all_rows = sorted(new_rows.values(), key=lambda x: x['期号'], reverse=True)

    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    logger.info(f"{lottery}: 保存 {len(all_rows)} 条 ({len(data)} 条新增) → {file_path}")
    return file_path


# ==========================================
#  主流程
# ==========================================

def main():
    parser = argparse.ArgumentParser(description='彩票开奖数据获取器')
    parser.add_argument('--lottery', choices=['pls', 'd3'], help='彩种')
    parser.add_argument('--all', action='store_true', help='获取所有彩种')
    parser.add_argument('--days', type=int, default=30,
                        help='获取最近多少期（默认30）')
    args = parser.parse_args()

    if not args.all and not args.lottery:
        parser.print_help()
        sys.exit(1)

    start = datetime.now()
    logger.info("=== 开始数据更新 ===")

    if args.all or args.lottery == 'pls':
        d = fetch_pls(args.days)
        if d:
            save_incremental(d, 'pls')

    if args.all or args.lottery == 'd3':
        d = fetch_fc3d(args.days)
        if d:
            save_incremental(d, 'd3')

    elapsed = datetime.now() - start
    logger.info(f"=== 更新完成 (耗时: {elapsed}) ===")


if __name__ == '__main__':
    main()
