#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
彩票分析每日一键运行脚本
==========================
支持排列三 + 福彩3D 全流程：
  数据更新 → 特征工程 → 统计引擎 → 评分预测 → 可视化

用法：
    python run_daily.py              # 跑两个彩种
    python run_daily.py pls          # 只跑排列三
    python run_daily.py d3           # 只跑福彩3D
"""

import subprocess
import sys
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent


def run_cmd(cmd, desc, timeout=300):
    """执行命令并记录日志，返回是否成功"""
    logger.info(f"▶️  {desc}")
    logger.debug(f"   $ {cmd}")
    try:
        result = subprocess.run(
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, cwd=str(BASE),
        )
        if result.returncode == 0:
            logger.info(f"✅ {desc}")
            lines = [l for l in result.stdout.decode().split('\n') if l.strip()]
            if lines:
                for line in lines[-2:]:
                    logger.info(f"   {line.strip()}")
            return True
        else:
            logger.error(f"❌ {desc} 失败")
            for line in result.stderr.decode().strip().split('\n')[-5:]:
                logger.error(f"   {line}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"⏰ {desc} 超时 ({timeout}s)")
        return False
    except Exception as e:
        logger.error(f"💥 {desc} 异常: {e}")
        return False


def pipeline(lottery, label, skiprows=3):
    """单个彩种的完整流水线，任一步骤失败则停止"""
    raw_file = f"data/raw/{lottery}_raw.csv"
    feat_file = f"data/processed/{lottery}_feat.csv"

    # 1. 数据更新
    if not run_cmd(
        f"python scripts/data_fetcher.py --lottery {lottery}",
        f"{label} 数据更新",
        timeout=180,
    ):
        logger.warning(f"⚠️ {label} 数据更新失败，继续使用现有数据")

    # 2. 特征工程
    if lottery == 'pls':
        if not run_cmd(
            f"python scripts/feature_engine.py --input {raw_file} --output {feat_file} "
            f"--lottery {lottery} --skiprows {skiprows} --force",
            f"{label} 特征工程",
            timeout=300,
        ):
            return
    else:
        if not run_cmd(
            f"python scripts/feature_engine.py --input {raw_file} --output {feat_file} "
            f"--lottery {lottery} --force",
            f"{label} 特征工程",
            timeout=300,
        ):
            return

    # 3. 统计引擎
    if not run_cmd(
        f"python scripts/stats_engine.py --lottery {lottery}",
        f"{label} 统计引擎",
        timeout=120,
    ):
        return

    # 4. 评分预测
    if not run_cmd(
        f"python scripts/scoring_engine.py --lottery {lottery} --top-k 30",
        f"{label} 评分预测",
        timeout=120,
    ):
        return

    # 5. 可视化（可选依赖，失败不影响预测）
    charts_dir = BASE / 'output' / 'charts'
    charts_dir.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib  # noqa: F401
        run_cmd(
            f"python scripts/visualize.py --lottery {lottery} --chart trend --output-format html",
            f"{label} 可视化",
            timeout=120,
        )
    except ImportError:
        logger.info(f"   ℹ️ {label} 可视化跳过（matplotlib未安装）")


def main():
    args = sys.argv[1:] if len(sys.argv) > 1 else ['pls', 'd3']
    today = datetime.now().strftime('%Y-%m-%d %H:%M')
    logger.info(f"{'='*50}")
    logger.info(f"  彩票分析每日任务  {today}")
    logger.info(f"{'='*50}")

    lotteries = {
        'pls': ('排列三', 3),
        'd3': ('福彩3D', 0),
    }

    for key in args:
        if key in lotteries:
            label, skip = lotteries[key]
            logger.info(f"")
            logger.info(f"── {label} ──")
            pipeline(key, label, skip)

    logger.info(f"")
    logger.info(f"{'='*50}")
    logger.info(f"  ✅ 全部任务完成！")
    logger.info(f"  预测文件: {BASE / 'output' / 'predictions/'}")
    logger.info(f"{'='*50}")


if __name__ == '__main__':
    main()
