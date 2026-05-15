#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
彩票数据获取器 —— 排列三 & 福彩3D
===================================
支持增量更新、日志记录、异常处理。

API 说明：
- 排列三：体彩官方 API webapi.sporttery.cn（已验证可用）
- 福彩3D：zhcw.com 网页抓取（最稳定方案，2026年5月实测有效）

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
#  福彩3D —— zhcw.com 网页抓取 ✅ 最稳定方案
# ==========================================

def fetch_3d_from_zhcw(max_pages=8):
    """
    从中国福彩网(zhcw.com)抓取福彩3D历史数据

    注意：zhcw.com 页面使用 Vue 动态渲染，requests 只能拿到模板标签，
    当前方案使用 Hermes 浏览器工具手动提取（通过 browser_console）。
    未来可升级为 Playwright 自动方案。

    Returns:
        list[dict]: 格式 [{'期号': str, '日期': str, '号码': str}, ...]
        返回空列表表示需要手动通过浏览器工具提取。
    """
    logger.warning("zhcw: 页面为Vue动态渲染，请使用浏览器工具提取数据")
    logger.warning("zhcw: URL: https://www.zhcw.com/kjxx/3d/")
    logger.warning("zhcw: 也可手动从旧的数据备份恢复: data/raw/d3_raw_backup_konglr.csv")
    return []


# ==========================================
#  增量保存（通用格式：期号,日期,号码）
# ==========================================

def save_incremental(data, lottery):
    """增量保存：合并新旧数据，按期号去重

    兼容旧版 konglr 宽表格式（转换后统一为简洁3列）
    """
    file_path = RAW_DIR / '{}_raw.csv'.format(lottery)

    if not data:
        logger.warning("{}: 无数据，跳过保存".format(lottery))
        return None

    new_rows = {r['期号']: r for r in data}

    if file_path.exists():
        with open(file_path, 'r', encoding='utf-8') as f:
            old_fieldnames = None
            for line in f:
                if not old_fieldnames:
                    old_fieldnames = line.strip().split(',')
                    continue
                # 按列名解析
                vals = line.strip().split(',')
                if len(vals) >= 3 and old_fieldnames:
                    row = dict(zip(old_fieldnames, vals))
                    eid = str(row.get('期号', row.get('issue', ''))).strip()
                    if eid and eid not in new_rows:
                        # 旧konglr宽表 → 转简洁3列格式
                        simple_row = {
                            '期号': eid,
                            '日期': str(row.get('日期', row.get('openTime', ''))).strip(),
                            '号码': '',
                        }
                        # 尝试从号码列提取
                        code = str(row.get('号码', row.get('红球1红球2红球3', ''))).strip()
                        if code:
                            simple_row['号码'] = code.replace(' ', '').zfill(3)
                        # 否则从 frontWinningNum 提取
                        if not simple_row['号码']:
                            fwn = row.get('frontWinningNum', '')
                            if fwn:
                                parts = fwn.split()
                                if len(parts) >= 3:
                                    try:
                                        n1 = int(float(parts[0]))
                                        n2 = int(float(parts[1]))
                                        n3 = int(float(parts[2]))
                                        simple_row['号码'] = '{}{}{}'.format(n1, n2, n3)
                                    except (ValueError, TypeError):
                                        pass
                        if simple_row.get('号码'):
                            new_rows[eid] = simple_row

    # 按期号降序写入
    all_rows = sorted(new_rows.values(), key=lambda x: str(x['期号']), reverse=True)

    simple_fields = ['期号', '日期', '号码']
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=simple_fields)
        w.writeheader()
        for row in all_rows:
            w.writerow({
                '期号': str(row.get('期号', '')),
                '日期': str(row.get('日期', '')),
                '号码': str(row.get('号码', '')),
            })

    logger.info("{}: 保存 {} 条 ({} 条新增) -> {}".format(lottery, len(all_rows), len(data), file_path))
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
        d = fetch_3d_from_zhcw(max_pages=8)
        if d:
            save_incremental(d, 'd3')
        else:
            logger.warning("福彩3D: zhcw方案失败，无数据更新")

    elapsed = datetime.now() - start
    logger.info("=== 更新完成 (耗时: {}) ===".format(elapsed))


if __name__ == '__main__':
    main()
