# CLAUDE.md — 彩票分析项目指令

## 项目概述

排列三 + 福彩3D + 快乐8 彩票数据分析与评分预测系统。核心思路：基于多窗口统计 + 理论分布 + 动态评分引擎，对候选号码打分排序，输出 Top-K 候选。

> 彩票开奖完全随机，本项目仅供学习研究。所有分析仅基于历史统计，不代表未来结果。

## Hermes cron 定时任务

项目通过 Hermes 定时执行，不依赖 GitHub Actions。所有推送类任务（14:40 / 21:35 / 22:05 / 23:10）均为 **no_agent 模式**，绕过 Tirith 安全审批链，不消耗 API token。

### 下午预测链路（14:30 → 14:35 → 14:40）

> 两段式推送：下午推送预测 + 晚间推送复盘，详见 [docs/HERMES_CONFIG.md](docs/HERMES_CONFIG.md)
> 
> ⚠️ 14:30 和 14:35 为辅助预生成。即使失败，14:40 的 `lottery_predict_push.sh` 会自动补跑全流程再推送。

| 时间 | 命令 | 说明 | 模式 | 审批 |
|------|------|------|:----:|:----:|
| 14:30 | `python run_daily.py --strategy all --top-k 30` | 预生成预测（辅助） | agent | ⚠️ 有 |
| 14:35 | `python scripts/source_health.py --json --output output/reports/source_health.json` | 健康报告（辅助） | agent | ⚠️ 有 |
| 14:40 | `scripts/push/lottery_predict_push.sh`（自闭环） | **run_daily + source_health + hermes_push --force** | **no_agent** | **✅ 无** |

> `lottery_predict_push.sh` 内部依次执行：run_daily → source_health → hermes_push --mode predict --stdout --force。
> 加 `--force` 避免当天因去重命中后无输出。

### 晚间复盘链路（21:35 / 22:05 / 23:10 三波补偿）

> 每波执行 `lottery_review_push.sh`（内部：daily_review.py && hermes_push.py --mode review --stdout）。
> `push_state.json` 防重复推送。复盘推送**不加 --force**，避免多波补偿重复推送。

| 时间 | 命令 | 模式 | 审批 |
|------|------|:----:|:----:|
| 21:35 | `scripts/push/lottery_review_push.sh` | **no_agent** ✅ | **无** |
| 22:05 | 同上（push_state.json 自动去重） | **no_agent** ✅ | **无** |
| 23:10 | 同上（push_state.json 自动去重） | **no_agent** ✅ | **无** |

> `daily_review.py` 内部依次执行：data_fetcher → feature_engine → compare_result(三策略) → review_summary。
> `hermes_push.py --mode review` 只读 review_history + compare JSON，不含预测。compare_result 返回 `waiting_actual` 时跳过推送不报错。
> 推送失败时内容落盘 `output/push/pending_*_report.md`，可手动 `--force` 补发。

### 快乐8候选池链路（14:30 预测 / 21:35 复盘）

| 时间 | 命令 | 说明 |
|------|------|------|
| 14:30 | `python scripts/kl8_fetcher.py && python scripts/kl8_predictor.py` | 拉取历史开奖 → 生成20码候选池 |
| 14:40 | `python scripts/hermes_push.py --mode predict --lottery kl8 --stdout` | 推送快乐8预测 |
| 21:35 | `python scripts/kl8_fetcher.py && python scripts/kl8_reviewer.py` | 拉最新开奖 → 复盘命中数 |
| 21:35 | `python scripts/hermes_push.py --mode review --lottery kl8 --stdout` | 推送快乐8复盘 |

> 快乐8每期开20个号码(1-80)。策略：热号12+冷号8混合生成20码候选池。复盘计算候选池∩开奖号码的命中数，随机期望约5/20。

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
│   ├── hermes_push.py         # 两段式推送（支持 --lottery pls/d3/kl8）
│   ├── kl8_fetcher.py          # 快乐8官方API数据抓取（1-80选20）
│   ├── kl8_predictor.py        # 快乐8候选池预测（热12+冷8策略）
│   ├── kl8_reviewer.py         # 快乐8复盘（候选池∩开奖交集统计）
│   └── push/                   # Hermes cron no_agent 推送脚本
│       ├── lottery_predict_push.sh  # 预测推送（自闭环：run_daily→source_health→push）
│       └── lottery_review_push.sh   # 复盘推送（daily_review→push）
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
│   ├── kl8/         # 快乐8历史数据 + latest JSON
│   └── quarantine/  # 坏数据隔离区（git忽略）
└── output/
    ├── predictions/ # 预测JSON
    ├── reviews/     # 复盘CSV
    ├── backtests/   # 回测报告
    ├── reports/     # 数据检查报告 + 健康报告
    ├── charts/      # 可视化图表
    ├── kl8/         # 快乐8预测+复盘输出
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

### 快乐8

```bash
python scripts/kl8_fetcher.py                      # 拉取历史开奖（cwl.gov.cn官方API）
python scripts/kl8_fetcher.py --pages 5            # 拉取5页(150期)
python scripts/kl8_predictor.py                    # 热12+冷8策略生成20码候选池
python scripts/kl8_reviewer.py                     # 候选池 vs 开奖复盘
python scripts/hermes_push.py --mode predict --lottery kl8   # 推送快乐8预测
python scripts/hermes_push.py --mode review --lottery kl8    # 推送快乐8复盘
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
8. **复盘命中按范围分层**：review_history 记录 `命中范围(Top5/Top10/Top30)` + `命中号码` + `命中排名` + `Top5直选/组选`，hermes_push 复盘推送口径与预测一致，命中时展示具体号码和排名，Top5 标注为"参考"
9. **不做 LSTM/ML 直接预测号码**：彩票无时间依赖，ML 不优于统计方法
10. **快乐8候选池不参与主评分**：独立模块（kl8_fetcher/predictor/reviewer），热号+冷号混合策略，与排列三/福彩3D 互不干扰
11. **号码始终当字符串**：防止前导零丢失（040→40）

## 文件编码

所有 CSV/JSON/YAML 统一使用 UTF-8-sig（Windows 兼容）。Python open() 必须显式指定 encoding='utf-8' 或 'utf-8-sig'。
