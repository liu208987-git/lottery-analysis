# CLAUDE.md — 彩票分析项目指令

## 项目概述

排列三 + 福彩3D 彩票数据分析与评分预测系统。核心思路：基于多窗口统计 + 理论分布 + 动态评分引擎，对 000-999 全部 1000 注号码多维度打分排序，输出 Top-K 候选。

> 彩票开奖完全随机，本项目仅供学习研究。所有分析仅基于历史统计，不代表未来结果。

## Hermes cron 定时任务

项目通过 Hermes 定时执行，不依赖 GitHub Actions。

### 下午预测链路（14:30 → 14:40）

> 两段式推送：下午推送预测 + 晚间推送复盘，详见 [docs/HERMES_CONFIG.md](docs/HERMES_CONFIG.md)

| 时间 | 命令 | 说明 | 失败处理 |
|------|------|------|:--:|
| 14:30 | `python run_daily.py --strategy all --top-k 30` | 生成今日预测（数据抓取→特征→统计→三策略评分） | 必须成功 |
| 14:35 | `python scripts/source_health.py --json --output output/reports/source_health.json` | 生成数据源健康报告 | 允许失败 |
| 14:40 | `python scripts/hermes_push.py --mode predict --stdout` | 推送预测（只含预测，不含复盘） | 必须成功 / **deliver=origin** |

> `hermes_push.py --mode predict` 只读取预测 JSON，不读 review_history，不做期号比较。

### 晚间复盘链路（21:35 / 22:05 / 23:10 三波补偿）

> 每波执行 `daily_review.py && hermes_push.py --mode review`。`push_state.json` 防重复推送。

| 时间 | 命令 | 说明 |
|------|------|------|
| 21:35 | `python scripts/daily_review.py && python scripts/hermes_push.py --mode review --stdout` | 初次复盘+推送 |
| 22:05 | 同上 | 补偿复盘（自动去重） |
| 23:10 | 同上 | 最后兜底 |

> `daily_review.py` 内部依次执行：data_fetcher → feature_engine → compare_result(三策略) → review_summary。
> `hermes_push.py --mode review` 只读 review_history + compare JSON，不含预测。compare_result 返回 `waiting_actual` 时跳过推送不报错。
> 推送失败时内容落盘 `output/push/pending_*_report.md`，可手动 `--force` 补发。

## 项目结构

```
lottery-analysis/
├── run_daily.py              # 一键每日运行入口
├── scripts/
│   ├── data_fetcher.py       # 多源数据抓取（js-lottery/eastmoney主源 + sporttery/zhcw备用 + 熔断 + 校验）
│   ├── feature_engine.py     # 特征工程（113维）+ 数据质量检查
│   ├── stats_engine.py       # 多窗口统计 + 理论分布
│   ├── scoring_engine.py     # 评分引擎v2（YAML权重 + 回归惩罚 + 多样性）
│   ├── backtest.py           # Walk-forward 回测（三策略对比 + ROI拆分）
│   ├── compare_result.py     # 预测 vs 开奖对比 + review_history累加
│   ├── review_summary.py     # 最近N期复盘表现摘要
│   ├── daily_review.py       # 每日复盘一键脚本（Hermes cron调用）
│   ├── tune_weights.py       # 权重自动调优（随机搜索 + Optuna贝叶斯优化 + 稳定性分析）
│   ├── filter_engine.py      # 轻量预过滤（已降级）
│   ├── visualize.py          # 走势图/热力图（matplotlib + plotly）
│   ├── issue_utils.py         # 期号标准化（PLS/D3格式互转）
│   ├── source_health.py       # 数据源健康报告
│   └── hermes_push.py         # 两段式推送（predict模式=预测 / review模式=复盘+近期表现）
├── rules/
│   ├── scoring_weights.yaml              # 默认权重
│   ├── scoring_weights_conservative.yaml # 稳健策略
│   ├── scoring_weights_diversity.yaml    # 多样性策略
│   └── data_sources.yaml                 # 数据源配置
├── data/
│   ├── raw/         # 原始CSV（git忽略）
│   ├── processed/   # 特征工程输出（git忽略）
│   ├── archived/    # 种子数据（git追踪）
│   ├── cache/       # 统计缓存 + 熔断状态（git忽略）
│   └── quarantine/  # 坏数据隔离区（git忽略）
└── output/
    ├── predictions/ # 预测JSON
    ├── reviews/     # 复盘CSV
    ├── backtests/   # 回测报告
    ├── reports/     # 数据检查报告 + 健康报告
    ├── charts/      # 可视化图表
    ├── push/        # 推送日报 + 发送日志 + pending补发
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

### 每日复盘

```bash
python scripts/daily_review.py                    # 一键复盘（拉取→对比→摘要）
python scripts/daily_review.py --lottery pls      # 仅排列三
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
python scripts/compare_result.py --lottery pls --strategy conservative
```

### 复盘摘要

```bash
python scripts/review_summary.py
python scripts/review_summary.py --window 60 --lottery pls
```

### 数据源健康 & 推送

```bash
python scripts/source_health.py                          # 终端健康报告
python scripts/source_health.py --json                   # JSON 格式
python scripts/source_health.py --json --output output/reports/source_health.json  # 写文件
python scripts/data_fetcher.py --cb-status               # 熔断器状态
python scripts/hermes_push.py --mode predict             # 推送预测
python scripts/hermes_push.py --mode review              # 推送复盘
python scripts/hermes_push.py --mode predict --force     # 强制补发预测
python scripts/hermes_push.py --mode review --force      # 强制补发复盘
python scripts/hermes_push.py --mode predict --write-only  # 只生成不推送
python scripts/hermes_push.py --mode daily               # 旧版混合日报（兼容）
```

### 期号工具

```bash
python scripts/issue_utils.py                            # 自测
```

### 权重调优（需 review_history ≥ 15 期）

```bash
python scripts/tune_weights.py --lottery pls --trials 30 --periods 50
python scripts/tune_weights.py --lottery pls --method optuna --trials 30
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
6. **遗漏评分上限截断**：`miss_score = max(0, min(miss_score, W['遗漏']))`，防止三热号场景遗漏分超过配置权重2倍（14/7）
7. **期号不匹配分类处理**：`pred>actual` 标记 `waiting_actual`(exit 0)，写 `*_waiting.json` 不覆盖 latest；`pred<actual` 视为真错误(exit 1)
8. **不做 LSTM/ML 直接预测号码**：彩票无时间依赖，ML 不优于统计方法
9. **号码始终当字符串**：防止前导零丢失（040→40）

## 文件编码

所有 CSV/JSON/YAML 统一使用 UTF-8-sig（Windows 兼容）。Python open() 必须显式指定 encoding='utf-8' 或 'utf-8-sig'。
