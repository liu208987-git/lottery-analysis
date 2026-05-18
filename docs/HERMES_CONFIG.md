# Hermes 定时任务配置

> 此文件供 Hermes 读取并自动配置定时任务。修改此文件后，同步至 Hermes 平台生效。
> 最后更新：2026-05-18（v2.10.0 两段式推送：predict + review 分离）

---

## ══════════════════════════════════════
## 👇 Hermes 配置清单（直接复制到 Hermes）
## ══════════════════════════════════════

### 一、环境变量

```
FEISHU_WEBHOOK_URL = （你的飞书机器人 webhook 地址）
```

> 飞书是主推送通道，不限频。不配则走 `--stdout` → Hermes `deliver=origin` 路径。

### 二、cron_mode

```
cron_mode = allow
```

### 三、定时任务（6 个，替换旧的 7 个）

> 所有任务 working_directory = 项目根目录
> cd 路径根据 Hermes 实际环境替换

```
# ── 下午预测链路（14:30 → 14:40）──

[task-predict-generate]
cron = 30 14 * * *
command = cd /path/to/lottery-analysis && python run_daily.py --strategy all --top-k 30
on_failure = stop
deliver = local
description = 生成今日预测（数据抓取→特征→统计→三策略评分）

[task-predict-health]
cron = 35 14 * * *
command = cd /path/to/lottery-analysis && python scripts/source_health.py --json --output output/reports/source_health.json
on_failure = continue
deliver = local
description = 生成数据源健康报告

[task-predict-push]
cron = 40 14 * * *
command = cd /path/to/lottery-analysis && python scripts/hermes_push.py --mode predict --stdout
on_failure = stop
deliver = origin
description = 推送今日预测到飞书

# ── 晚间复盘链路（21:35 / 22:05 / 23:10 三波补偿）──

[task-review-2135]
cron = 35 21 * * *
command = cd /path/to/lottery-analysis && python scripts/daily_review.py && python scripts/hermes_push.py --mode review --stdout
on_failure = continue
deliver = origin
description = 初次复盘+推送（开奖后35分钟）

[task-review-2205]
cron = 05 22 * * *
command = cd /path/to/lottery-analysis && python scripts/daily_review.py && python scripts/hermes_push.py --mode review --stdout
on_failure = continue
deliver = origin
description = 补偿复盘+推送（开奖后65分钟，push_state.json 自动防重）

[task-review-2310]
cron = 10 23 * * *
command = cd /path/to/lottery-analysis && python scripts/daily_review.py && python scripts/hermes_push.py --mode review --stdout
on_failure = continue
deliver = origin
description = 最后兜底复盘+推送（push_state.json 自动防重）
```

---

## ══════════════════════════════════════
## 👆 以上是需要配置的全部内容
## ══════════════════════════════════════

---

## 环境变量

Hermes 执行环境需配置以下变量：

| 变量名 | 必填 | 通道 | 说明 |
|------|:--:|------|------|
| `FEISHU_WEBHOOK_URL` | 推荐 | **飞书（主通道）** | 飞书机器人 Webhook，不限频，优先使用 |
| `WECOM_WEBHOOK_URL` | 可选 | 微信（辅助通道） | 企业微信群机器人，有限频保护（冷却5s + 退避30/60/120s） |
| `HERMES_WEBHOOK_URL` | 可选 | 通用（兜底通道） | 通用 Webhook 地址 |

> 三个通道独立隔离，任一失败不影响其他。飞书为主通道（不限频），微信为辅助（带限频保护）。
> 都不配置时走 `--stdout` 模式，由 Hermes `deliver=origin` 负责推送。

---

## 两段式推送设计

```
下午（14:30 ~ 14:40）：预测推送
  ├── 14:30 run_daily → 抓数据 + 特征 + 统计 + 三策略评分
  ├── 14:35 source_health → 健康报告
  └── 14:40 hermes_push --mode predict → 只含预测数据，不含复盘

晚上（21:35 / 22:05 / 23:10）：复盘推送
  ├── daily_review → 拉取开奖 + 特征 + compare_result
  └── hermes_push --mode review → 只含复盘数据，不含预测
      ├── 数据源未更新 → 自动跳过不推送
      ├── 复盘成功 + 未推送过 → 推送
      └── 已推送过 → 自动去重跳过
```

**核心改进：**

- 下午调早到 14:30，让你提前看到预测
- 预测和复盘分开推送，不再混在同一条消息里
- 期号不再出现 "预测 26128 复盘 26127" 的混淆
- 晚间三波复盘自带防重复（push_state.json），不会重复轰炸

---

## 定时任务清单

### 下午预测链路（14:30 → 14:40）

#### 任务 1 — 14:30 生成今日预测

```
时间: 14:30
命令: python run_daily.py --strategy all --top-k 30
失败处理: 必须成功，失败则停止后续任务
说明: 数据抓取 → 特征工程 → 统计 → 三策略评分
      生成 latest_*.json 和按期号归档的 *_predict_{issue}.json
```

#### 任务 2 — 14:35 健康报告

```
时间: 14:35
命令: python scripts/source_health.py --json --output output/reports/source_health.json
失败处理: 允许失败
说明: 预测推送可以不带健康状态，失败不阻塞
```

#### 任务 3 — 14:40 推送预测

```
时间: 14:40
命令: python scripts/hermes_push.py --mode predict --stdout
失败处理: 必须成功
deliver: origin  ← 关键！
说明: 只读取预测 JSON，生成"今日预测"推送。不读 review_history，不做期号比较。
```

---

### 晚间复盘链路（21:35 / 22:05 / 23:10）

> 三段式补偿：数据源通常在 21:00 开奖后 20-30 分钟更新，三波覆盖延迟场景。
> 每波都跑 `daily_review.py && hermes_push.py --mode review`。
> **防重复**：`push_state.json` 记录每期推送状态，同一期只推送一次。

#### 任务 4 — 21:35 初次复盘+推送

```
时间: 21:35
命令: python scripts/daily_review.py && python scripts/hermes_push.py --mode review --stdout
失败处理: 允许失败
deliver: origin
说明: 开奖后 35 分钟，大多数源已更新
      若数据源未更新 → compare_result 状态=waiting_actual → 跳过推送
      若复盘成功且该期未推送过 → 推送复盘
```

#### 任务 5 — 22:05 补偿复盘

```
时间: 22:05
命令: python scripts/daily_review.py && python scripts/hermes_push.py --mode review --stdout
失败处理: 允许失败
deliver: origin
说明: 距开奖 65 分钟，兜底延迟数据源
      若 21:35 已推送 → push_state.json 命中 → 自动跳过
```

#### 任务 6 — 23:10 最后兜底

```
时间: 23:10
命令: python scripts/daily_review.py && python scripts/hermes_push.py --mode review --stdout
失败处理: 允许失败
deliver: origin
说明: 最终补偿。若仍未更新，数据永久缺失（次日可回填）
```

---

## 手动命令参考

### 推送相关

```bash
# 推送预测
python scripts/hermes_push.py --mode predict

# 推送复盘
python scripts/hermes_push.py --mode review

# 强制补发（忽略去重）
python scripts/hermes_push.py --mode predict --force
python scripts/hermes_push.py --mode review --force

# 只生成不推送（检查内容）
python scripts/hermes_push.py --mode predict --write-only
python scripts/hermes_push.py --mode review --write-only

# 旧版混合日报（兼容）
python scripts/hermes_push.py --mode daily
```

### 复盘相关

```bash
# 手动复盘
python scripts/daily_review.py
python scripts/daily_review.py --lottery pls
python scripts/daily_review.py --lottery d3

# 单测 compare_result（按实际开奖期号查找对应预测）
python scripts/compare_result.py --lottery pls --strategy default
python scripts/compare_result.py --lottery d3 --strategy conservative
```

### 预测相关

```bash
python run_daily.py --strategy all --top-k 30
python run_daily.py pls --strategy all --top-k 30
```

### 数据源诊断

```bash
python scripts/source_health.py
python scripts/source_health.py --json --output output/reports/source_health.json
python scripts/data_fetcher.py --cb-status
```

---

## 文件依赖关系

### predict 模式读取

| 文件 | 来源 | 内容 |
|------|------|------|
| `output/predictions/latest_pls.json` | `run_daily.py` | 排列三默认策略预测 |
| `output/predictions/latest_pls_conservative.json` | `run_daily.py` | 排列三稳健策略预测 |
| `output/predictions/latest_pls_diversity.json` | `run_daily.py` | 排列三多样性策略预测 |
| `output/predictions/latest_d3.json` | `run_daily.py` | 福彩3D默认策略预测 |
| `output/predictions/latest_d3_conservative.json` | `run_daily.py` | 福彩3D稳健策略预测 |
| `output/predictions/latest_d3_diversity.json` | `run_daily.py` | 福彩3D多样性策略预测 |
| `output/reports/source_health.json` | `source_health.py` | 数据源健康报告 |
| `data/cache/{lottery}_stats_latest.json` | `stats_engine.py` | 统计缓存（冷热/和值/跨度） |

### review 模式读取

| 文件 | 来源 | 内容 |
|------|------|------|
| `output/reviews/review_history.csv` | `daily_review.py` | 复盘记录（含 strategy 字段） |
| `output/reports/{lottery}_compare_latest.json` | `compare_result.py` | 最新对比结果 |
| `output/reports/{lottery}_compare_waiting.json` | `compare_result.py` | 等待状态（pred > actual） |
| `output/reports/source_health.json` | `source_health.py` | 健康报告 |

### 推送脚本写入

| 文件 | 用途 |
|------|------|
| `output/push/predict_report.md` | 预测日报落盘 |
| `output/push/review_report.md` | 复盘日报落盘 |
| `output/push/daily_report.md` | 旧版混合日报落盘（兼容） |
| `output/push/pending_*_report.md` | 推送失败时待补发的内容 |
| `output/push/send_log.jsonl` | 发送记录（逐行 JSON，含 hash 去重） |
| `output/push/push_state.json` | 期号级防重状态（按 `日期_模式` 记录） |

---

## compare_result 期号不匹配分类

| 场景 | 返回状态 | exit code | 说明 |
|------|------|:--:|------|
| `pred > actual` | `waiting_actual` | 0 | 等待数据源更新，不算错误 |
| `pred < actual` | `错误` | 1 | 缺预测文件，真问题 |
| `pred == actual` | 正常复盘 | 0 | 写入 review_history |

> `waiting_actual` 时写入 `*_compare_waiting.json`，不覆盖 `*_compare_latest.json`。

---

## 关键设计原则

1. **两段式推送** — 预测单独推，复盘单独推，期号语义清晰无混淆
2. **预测按期号归档** — `*_predict_{issue}.json` 持久化，复盘按实开期号查找对应预测
3. **防重复推送** — `push_state.json` 记录每期推送状态，多轮 cron 不重复轰炸
4. **失败隔离** — 复盘失败不阻塞预测，健康报告失败不阻塞推送
5. **落盘优先** — 先写 `*_report.md` 再推送，推送失败内容不丢
6. **指数冷却** — sporttery API 连续失败后冷却 2h→6h→12h→24h
7. **stdout 隔离** — `--stdout` 模式只输出正文到 stdout，日志/警告全部走 stderr

---

## 故障恢复

### 预测推送失败

预测日报已落盘到 `output/push/predict_report.md`。手动补发：

```bash
python scripts/hermes_push.py --mode predict --force
```

### 复盘推送失败

复盘日报已落盘到 `output/push/review_report.md`。手动补发：

```bash
python scripts/hermes_push.py --mode review --force
```

### 晚间复盘自动跳过（预期行为）

若 compare_result JSON 状态为 `waiting_actual`，hermes_push --mode review 会自动跳过推送并输出日志：

```
[跳过] 全部等待开奖（pls 预测期号 > 实际开奖期号...）
```

这是正常行为，不需要任何操作。等数据源更新后下一波 cron 会自动补推。

### Gateway 关闭后恢复

1. 重启 Hermes gateway
2. 确认 `cron_mode = allow`
3. 手动补跑当天缺失的关键任务：
   ```bash
   # 如果下午预测没生成
   python run_daily.py --strategy all --top-k 30
   python scripts/hermes_push.py --mode predict --force
   
   # 如果晚间复盘没跑
   python scripts/daily_review.py
   python scripts/hermes_push.py --mode review --force
   ```

### 微信限频

`hermes_push.py` 已内置冷却和退避。如果仍然限频：
- 改用飞书作为主通道（配置 `FEISHU_WEBHOOK_URL`）
- 或只用 `--stdout` → `deliver=origin` 路径
