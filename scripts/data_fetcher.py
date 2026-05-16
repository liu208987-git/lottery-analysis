#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
彩票数据获取器 —— 排列三 & 福彩3D
===================================
支持增量更新、日志记录、异常处理。

API 说明：
- 排列三：体彩官方 API webapi.sporttery.cn（已验证可用）
- 福彩3D：zhcw.com 静态列表页（pd.read_html 解析，最稳定方案）

用法：
    python data_fetcher.py --all              # 获取所有彩种
    python data_fetcher.py --lottery pls      # 仅排列三
    python data_fetcher.py --lottery d3       # 仅福彩3D
    python data_fetcher.py --all --days 30    # 获取最近30期
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
import yaml

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
                  'Chrome/134.0.0.0 Safari/537.36',
}


def load_source_config():
    """从 rules/data_sources.yaml 加载数据源配置"""
    config_path = BASE_DIR / 'rules' / 'data_sources.yaml'
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def get_source_urls(lottery, role='primary'):
    """获取指定彩种的数据源 URL 列表"""
    cfg = load_source_config()
    sources = cfg.get(lottery, {}).get(role, [])
    return [s for s in sources if s.get('enabled', True)]


# ==========================================
#  排列三 —— 体彩官方 API ✅ 可用
# ==========================================

def fetch_pls(limit=30, max_retries=3):
    """从体彩官方API获取排列三最新数据，567限频自动退避重试"""
    url = (
        "https://webapi.sporttery.cn/gateway/lottery/"
        f"getHistoryPageListV1.qry?gameNo=350133&provinceId=0"
        f"&pageSize={min(limit, 50)}&is498=1"
    )
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 567:
                wait = 5 * (attempt + 1)
                logger.warning("排列三API返回567(限频)，{}秒后重试({}/{})".format(
                    wait, attempt + 1, max_retries))
                time.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            break
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            logger.error("排列三API请求失败: {}".format(e))
            return []
        except (ValueError, KeyError) as e:
            logger.error("排列三数据解析失败: {}".format(e))
            return []
    else:
        logger.error("排列三API: {}次重试后仍失败".format(max_retries))
        return []

    results = []
    for item in data.get('value', {}).get('list', []):
        nums = item['lotteryDrawResult'].split()
        if len(nums) < 3:
            logger.warning("排列三: 期号{} 号码格式异常: {}".format(item['lotteryDrawNum'], item['lotteryDrawResult']))
            continue
        results.append({
            '期号': item['lotteryDrawNum'],
            '日期': item['lotteryDrawTime'],
            '号码': ''.join(nums[:3]),
        })
    if results:
        logger.info("排列三: 获取到 {} 条 (最新: {})".format(len(results), results[0]['期号']))
    else:
        logger.warning("排列三: 无数据")
    return results


# ==========================================
#  福彩3D —— zhcw.com 静态列表页 ✅ 最稳定方案
# ==========================================

def fetch_3d_from_zhcw(max_pages=10):
    """
    从中国福彩网(zhcw.com)抓取福彩3D历史数据

    使用 pd.read_html 解析静态表格，第1页返回404（最新数据从第2页开始），
    每页约21条记录。

    Args:
        max_pages: 抓取页数（默认10页≈189条）

    Returns:
        pd.DataFrame | None: 列 [期号, 开奖日期, 开奖号码]
    """
    all_dfs = []
    logger.info("开始抓取福彩3D数据，最多 {} 页...".format(max_pages))

    for page in range(1, max_pages + 1):
        # zhcw HTTPS返回假200（内容实际为404页面），必须用HTTP
        url = "http://kaijiang.zhcw.com/zhcw/html/3d/list_{}.html".format(page)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.encoding = 'utf-8'

            if resp.status_code != 200:
                # 第1页通常是404（zhcw的列表页从第2页开始有效）
                continue

            dfs = pd.read_html(StringIO(resp.text))
            found = False
            for df in dfs:
                cols = df.columns
                # MultiIndex 列名，检查任一 level 含"期号"
                col_strs = []
                if hasattr(cols, 'levels'):
                    for level in cols.levels:
                        col_strs.extend(str(c) for c in level)
                else:
                    col_strs = [str(c) for c in cols]

                if any('期号' in s for s in col_strs):
                    # zhcw 表格结构：前3列 = 开奖日期, 期号, 中奖号码
                    df = df.iloc[:, :3].copy()
                    # MultiIndex → 普通列名
                    df.columns = ['开奖日期', '期号', '中奖号码']
                    # 号码去空格："4 8 2" → "482"
                    df['中奖号码'] = df['中奖号码'].astype(str).str.replace(' ', '').str.zfill(3)
                    # 过滤无效行（表头行会被pd.read_html误读为数据）
                    df = df[df['期号'].astype(str).str.match(r'^\d{6,7}$')]
                    if len(df) > 0:
                        all_dfs.append(df)
                        logger.info("第 {} 页抓取成功 -> {} 条".format(page, len(df)))
                    found = True
                    break

            if not found:
                logger.debug("第 {} 页: 未找到开奖表格".format(page))

        except (requests.exceptions.RequestException, ValueError) as e:
            logger.debug("第 {} 页失败: {}".format(page, e))

        time.sleep(1.5)

    if not all_dfs:
        logger.error("福彩3D: 所有页面抓取失败")
        return None

    final_df = pd.concat(all_dfs, ignore_index=True)
    final_df = final_df.drop_duplicates(subset=['期号']).sort_values(by='期号', ascending=False).reset_index(drop=True)

    logger.info("✅ 福彩3D 抓取完成，共 {} 条记录 ({} ~ {})".format(
        len(final_df), final_df['期号'].iloc[-1], final_df['期号'].iloc[0]))
    return final_df


# ==========================================
#  福彩3D —— 东方财富 (eastmoney.com) ✅ 备用源
# ==========================================

def fetch_3d_from_eastmoney(max_pages=1):
    """
    从东方财富彩票页抓取福彩3D历史数据。

    页面含 HTML 表格，每页约50条记录。号码通过 <span class='pellet'> 标签展示。

    Args:
        max_pages: 抓取页数（默认1页≈50条）

    Returns:
        pd.DataFrame | None: 列 [期号, 开奖日期, 中奖号码]
    """
    import re

    all_rows = []
    logger.info("开始抓取东方财富福彩3D数据...")

    for page in range(1, max_pages + 1):
        url = "https://caipiao.eastmoney.com/Result/History/fc3d?page={}".format(page)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.encoding = 'utf-8'
            if resp.status_code != 200:
                logger.warning("东方财富第 {} 页返回 {}".format(page, resp.status_code))
                continue

            html = resp.text
            before_count = len(all_rows)

            # 提取行：包含 pellet 的 tr 块
            rows = re.findall(r'<tr>\s*<td>.*?</tr>', html, re.DOTALL)
            if not rows:
                # fallback: 直接匹配 pellet 所在的行块
                blocks = re.findall(
                    r'<a[^>]*id=(\d{7})[^>]*>.*?'
                    r'(20\d{2}-\d{2}-\d{2}).*?'
                    r'<span class="pellet[^"]*"[^>]*>(\d)</span>\s*'
                    r'<span class="pellet[^"]*"[^>]*>(\d)</span>\s*'
                    r'<span class="pellet[^"]*"[^>]*>(\d)</span>',
                    html, re.DOTALL
                )
                for block in blocks:
                    issue, date, d1, d2, d3 = block
                    all_rows.append({
                        '期号': issue,
                        '开奖日期': date,
                        '中奖号码': d1 + d2 + d3,
                    })
            else:
                for row in rows:
                    issue_m = re.search(r'id=(\d{7})', row)
                    date_m = re.search(r'(20\d{2}-\d{2}-\d{2})', row)
                    digits = re.findall(r'<span class="pellet[^"]*"[^>]*>(\d)</span>', row)
                    if issue_m and len(digits) >= 3:
                        all_rows.append({
                            '期号': issue_m.group(1),
                            '开奖日期': date_m.group(1) if date_m else '',
                            '中奖号码': ''.join(digits[:3]),
                        })

            logger.info("东方财富第 {} 页抓取成功 -> {} 条".format(page, len(all_rows) - before_count))

        except (requests.exceptions.RequestException, ValueError) as e:
            logger.debug("东方财富第 {} 页失败: {}".format(page, e))

    if not all_rows:
        logger.error("东方财富: 所有页面抓取失败")
        return None

    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset=['期号']).sort_values(by='期号', ascending=False).reset_index(drop=True)

    logger.info("✅ 东方财富福彩3D 抓取完成，共 {} 条记录 ({} ~ {})".format(
        len(df), df['期号'].iloc[-1], df['期号'].iloc[0]))
    return df


# ==========================================
#  增量保存（通用格式：期号,日期,号码）
# ==========================================

def save_incremental(df, lottery_type):
    """
    通用增量保存：合并新旧数据，按期号去重

    Args:
        df: pd.DataFrame，需包含列 [期号, 开奖日期(或日期), 中奖号码(或号码)]
        lottery_type: 'pls' 或 'd3'
    """
    file_path = RAW_DIR / '{}_raw.csv'.format(lottery_type)

    # 空数据保护：不覆盖已有数据
    if df is None or len(df) == 0:
        logger.warning("⚠️ {} 新数据为空，保留旧数据，不覆盖 {}".format(lottery_type, file_path))
        return file_path if file_path.exists() else None

    # 统一列名为简洁3列
    rename_map = {
        '开奖日期': '日期',
        '中奖号码': '号码',
        '号码': '号码',
    }
    df_out = df.rename(columns=rename_map)
    df_out = df_out[['期号', '日期', '号码']].copy()
    df_out['期号'] = df_out['期号'].astype(str)
    # 清洗号码：去空格→去非数字→补零到3位
    df_out['号码'] = (
        df_out['号码'].astype(str)
        .str.replace(r'\s+', '', regex=True)
        .str.replace(r'\D', '', regex=True)
        .str.zfill(3)
        .str[:3]
    )

    if file_path.exists():
        old_df = pd.read_csv(file_path, dtype=str, encoding='utf-8-sig')
        combined = pd.concat([old_df, df_out], ignore_index=True)
        combined = combined.drop_duplicates(subset=['期号'], keep='last')
    else:
        combined = df_out

    combined = combined.sort_values(by='期号', ascending=False).reset_index(drop=True)
    combined.to_csv(file_path, index=False, encoding='utf-8-sig')
    logger.info("数据已更新 -> {} (总计 {} 条)".format(file_path, len(combined)))
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
    parser.add_argument('--max-pages', type=int, default=10,
                        help='福彩3D抓取页数（每页约21条，默认10页）')
    parser.add_argument('--source', choices=['zhcw', 'eastmoney', 'auto'], default='auto',
                        help='福彩3D数据源：zhcw/eastmoney/auto（默认auto=主源+备用校验）')
    args = parser.parse_args()

    if not args.all and not args.lottery:
        parser.print_help()
        sys.exit(1)

    start = datetime.now()
    logger.info("=== 开始数据更新 ===")

    if args.all or args.lottery == 'pls':
        d = fetch_pls(args.days)
        if d:
            save_incremental(pd.DataFrame(d), 'pls')

    if args.all or args.lottery == 'd3':
        if args.source == 'eastmoney':
            df_d3 = fetch_3d_from_eastmoney()
            if df_d3 is not None:
                save_incremental(df_d3, 'd3')
        elif args.source == 'zhcw':
            df_d3 = fetch_3d_from_zhcw(max_pages=args.max_pages)
            if df_d3 is not None:
                save_incremental(df_d3, 'd3')
        else:  # auto: 主源 + 双源校验 + fallback
            df_main = fetch_3d_from_zhcw(max_pages=args.max_pages)
            df_verify = None
            try:
                df_verify = fetch_3d_from_eastmoney()
            except Exception:
                logger.debug("东方财富校验源不可用")

            # 优先保存主源
            if df_main is not None:
                save_incremental(df_main, 'd3')
            elif df_verify is not None:
                logger.warning("⚠️ 主源(zhcw)失败，回退到东方财富")
                save_incremental(df_verify, 'd3')

            # 双源校验
            if df_main is not None and df_verify is not None \
                    and len(df_main) > 0 and len(df_verify) > 0:
                latest_main = df_main['期号'].iloc[0]
                latest_v = df_verify[df_verify['期号'] == latest_main]
                if len(latest_v) > 0:
                    num_main = df_main[df_main['期号'] == latest_main]['中奖号码'].iloc[0]
                    num_v = latest_v['中奖号码'].iloc[0]
                    if num_main == num_v:
                        logger.info("✅ 双源校验通过: 期号{} 号码{}一致".format(latest_main, num_main))
                    else:
                        logger.warning("⚠️ 双源校验不一致: 期号{} zhcw={} eastmoney={}".format(
                            latest_main, num_main, num_v))
                else:
                    logger.info("ℹ️ 东方财富尚无期号{}的数据，跳过校验".format(latest_main))

    elapsed = datetime.now() - start
    logger.info("=== 更新完成 (耗时: {}) ===".format(elapsed))


if __name__ == '__main__':
    main()
