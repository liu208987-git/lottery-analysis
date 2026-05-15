# CLAUDE.md — 彩票分析项目指令

## 项目概述

排列三 + 福彩3D 彩票数据分析与评分预测系统。核心思路：基于多窗口统计 + 理论分布 + 动态评分引擎，对 000-999 全部 1000 注号码多维度打分排序，输出 Top-K 候选。

> 彩票开奖完全随机，本项目仅供学习研究。所有分析仅基于历史统计，不代表未来结果。

## 项目结构

```
lottery-analysis/
├── run_daily.py              # 一键每日运行入口
├── scripts/
│   ├── data_fetcher.py       # 数据抓取（体彩API + zhcw/东方财富）
│   ├── feature_engine.py     # 特征工程（113维）+ 数据质量检查
│   ├── stats_engine.py       # 多窗口统计 + 理论分布
│   ├── scoring_engine.py     # 评分引擎v2（YAML权重 + 回归惩罚 + 多样性）
│   ├── backtest.py           # Walk-forward 回测（三策略对比）
│   ├── compare_result.py     # 预测 vs 开奖对比 + review_history 累加
│   ├── review_summary.py     # 最近N期复盘表现摘要
│   ├── tune_weights.py       # 权重自动调优（随机搜索 + 稳定性分析）
│   ├── filter_engine.py      # 轻量预过滤（已降级）
│   └── visualize.py          # 走势图/热力图（matplotlib + plotly）
├── rules/
│   ├── scoring_weights.yaml              # 默认权重
│   ├── scoring_weights_conservative.yaml # 稳健策略
│   ├── scoring_weights_diversity.yaml    # 多样性策略
│   └── data_sources.yaml                 # 数据源配置
├── data/
│   ├── raw/         # 原始CSV（git忽略）
│   ├── processed/   # 特征工程输出（git忽略）
│   ├── archived/    # 种子数据（git追踪）
│   └── cache/       # 统计缓存（git忽略）
└── output/
    ├── predictions/ # 预测JSON
    ├── reviews/     # 复盘CSV
    ├── backtests/   # 回测报告
    ├── reports/     # 数据检查报告
    ├── charts/      # 可视化图表
    └── tuning/      # 调参记录
```

## 核心脚本与常用命令

### 每日一键运行

```bash
python run_daily.py                              # 跑两个彩种，默认策略Top-30
python run_daily.py pls --top-k 10               # 只跑排列三，10注
python run_daily.py --strategy conservative       # 稳健策略
python run_daily.py --strategy all                # 三套策略全跑
```

### 特征工程

```bash
python scripts/feature_engine.py --input data/raw/pls_raw.csv --output data/processed/pls_feat.csv --lottery pls --force
```

### 评分预测

```bash
python scripts/scoring_engine.py --lottery pls --top-k 30
python scripts/scoring_engine.py --lottery pls --weights rules/scoring_weights_conservative.yaml --output-name conservative
```

### 回测

```bash
python scripts/backtest.py --lottery pls --periods 100 --top-k 30
```

### 预测 vs 开奖对比

```bash
python scripts/compare_result.py --lottery pls
python scripts/compare_result.py --lottery d3
```

### 复盘摘要

```bash
python scripts/review_summary.py
python scripts/review_summary.py --window 60 --lottery pls
```

### 权重调优（需 review_history ≥ 15 期）

```bash
python scripts/tune_weights.py --lottery pls --trials 30 --periods 50
```

### 可视化

```bash
python scripts/visualize.py --lottery pls --chart all
python scripts/visualize.py --lottery pls --chart trend --output-format html
```

## 数据流

```
data_fetcher.py → data/raw/*.csv
    ↓
feature_engine.py → data/processed/*.csv（113维特征）
    ↓
stats_engine.py → data/cache/*_stats_latest.json
    ↓
scoring_engine.py → output/predictions/latest_*.json
    ↓
compare_result.py → output/reports/*_compare_latest.json + output/reviews/review_history.csv
    ↓
review_summary.py → 终端表现摘要
```

## 关键设计决策

1. **不硬过滤**：1000 注全部打分排序，不做硬规则排除（豹子除外）
2. **理论+近期混合**：每条规则 = 理论分布×60% + 近期走势×40%
3. **YAML 权重可配置**：改策略不改代码
4. **回归惩罚**：形态评分双向惩罚偏离理论值（过热降分、过冷加分）
5. **多样性惩罚**：同组选只保留最高分直选 + 跨度多样性促进
6. **不做 LSTM/ML 直接预测号码**：彩票无时间依赖，ML 不优于统计方法
7. **号码始终当字符串**：防止前导零丢失（040→40）

## 文件编码

所有 CSV/JSON/YAML 统一使用 UTF-8-sig（Windows 兼容）。Python open() 必须显式指定 encoding='utf-8' 或 'utf-8-sig'。
