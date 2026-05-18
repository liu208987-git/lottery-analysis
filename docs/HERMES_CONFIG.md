# Hermes 定时任务配置

> 此文件供 Hermes 读取并自动配置定时任务。修改此文件后，同步至 Hermes 平台生效。
> 最后更新：2026-05-18（v2.9.6 推送通道拆分 + 微信限频保护）

---

## ══════════════════════════════════════
## 👇 Hermes 配置清单（直接复制到 Hermes）
## ══════════════════════════════════════

### 一、环境变量

```
FEISHU_WEBHOOK_URL = （你的飞书机器人 webhook 地址）
```

> 飞书是主推送通道，不限频。不配则走 `--stdout` → Hermes `deliver=origin` 路径。
> 微信 `WECOM_WEBHOOK_URL` 和通用 `HERMES_WEBHOOK_URL` 可选，配了就多通道同时推。

### 二、定时任务（7 个 cron job）

```
┌────────┬──────────────────────────────────────────────────────────────┬──────────────┐
│ 时间   │ 命令                                                         │ 失败处理     │
├────────┼──────────────────────────────────────────────────────────────┼──────────────┤
│ 17:20  │ python scripts/daily_review.py                               │ 允许失败     │
│ 17:25  │ python run_daily.py --strategy all --top-k 30                │ 必须成功     │
│ 17:28  │ python scripts/source_health.py --json                       │ 允许失败     │
│        │   --output output/reports/source_health.json                 │              │
│ 17:30  │ python scripts/hermes_push.py --mode daily --stdout          │ 必须成功     │
│        │   ⚠️ 这个任务 deliver = origin                                │              │
├────────┼──────────────────────────────────────────────────────────────┼──────────────┤
│ 21:35  │ python scripts/daily_review.py                               │ 允许失败     │
│ 22:05  │ python scripts/daily_review.py                               │ 允许失败     │
│ 23:10  │ python scripts/daily_review.py                               │ 允许失败     │
└────────┴──────────────────────────────────────────────────────────────┴──────────────┘

所有任务 working directory = lottery-analysis 项目根目录
前 6 个任务 deliver = local（静默不推送）
只有 17:30 任务 deliver = origin（推送日报到微信/飞书）
```

### 三、cron_mode

```
cron_mode = allow
```

> `deny` 会拦截所有 terminal 命令，必须设为 `allow`。

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

## 定时任务清单

### 下午主任务链（17:20 → 17:30）

> **执行顺序不能颠倒**：先复盘昨日（此时预测文件还是昨天的），再生成今日预测，最后合并推送。

#### 任务 1 — 17:20 补齐昨日复盘

```
时间: 17:20
命令: cd /path/to/lottery-analysis && python scripts/daily_review.py
失败处理: 允许失败，不阻塞后续任务（Hermes 配置为 continue-on-error）
说明: 拉取最新开奖数据 → 特征工程 → 对比三策略预测 → 写入 review_history.csv
      失败通常是数据源问题（sporttery 567 / zhcw 404），有熔断保护
```

#### 任务 2 — 17:25 生成今日预测

```
时间: 17:25
命令: cd /path/to/lottery-analysis && python run_daily.py --strategy all --top-k 30
失败处理: 必须成功，失败则停止后续任务（Hermes 配置为 stop-on-error）
说明: 数据抓取 → 特征工程 → 统计 → 三策略评分 → 写入 latest_*.json
      此步骤失败意味着今日预测无法生成，日报将缺少预测部分
```

#### 任务 3 — 17:28 生成数据源健康报告

```
时间: 17:28
命令: cd /path/to/lottery-analysis && python scripts/source_health.py --json --output output/reports/source_health.json
失败处理: 允许失败，不阻塞后续任务
说明: 生成 JSON 格式健康报告供推送脚本读取
      失败时 hermes_push.py 会 fallback 到 data/cache/source_status.json
```

#### 任务 4 — 17:30 合并推送日报

```
时间: 17:30
命令: cd /path/to/lottery-analysis && python scripts/hermes_push.py --mode daily --stdout
失败处理: 必须成功
deliver: origin  ← 关键！必须设 origin，Hermes 才会把 stdout 内容转发到微信
说明: 读取复盘+预测+健康→拼接日报→落盘→stdout 只输出日报正文
      前三个任务 deliver=local，只有这个任务 deliver=origin
```

---

### 晚间静默复盘链（21:35 / 22:05 / 23:10）

> 晚间只跑复盘，不推送。三波补偿确保即使数据源延迟也能抓到开奖数据。

#### 任务 5 — 21:35 初次复盘

```
时间: 21:35
命令: cd /path/to/lottery-analysis && python scripts/daily_review.py
失败处理: 允许失败
说明: 开奖后第一波抓取。21:35 距 21:00 开奖已过 35 分钟，大多数源已更新
```

#### 任务 6 — 22:05 补偿复盘

```
时间: 22:05
命令: cd /path/to/lottery-analysis && python scripts/daily_review.py
失败处理: 允许失败
说明: 第一波失败或数据源延迟时的补偿，距开奖 65 分钟
```

#### 任务 7 — 23:10 最后兜底

```
时间: 23:10
命令: cd /path/to/lottery-analysis && python scripts/daily_review.py
失败处理: 允许失败
说明: 最终补偿。此时仍未抓到则当日数据永久缺失（次日复盘可回填）
```

---

## 手动命令参考

### 推送相关

```bash
# 正常推送日报
python scripts/hermes_push.py --mode daily

# 强制补发（忽略今日去重）
python scripts/hermes_push.py --mode daily --force

# 只生成内容不推送（检查内容用）
python scripts/hermes_push.py --mode daily --write-only
```

### 复盘相关

```bash
# 手动跑复盘
python scripts/daily_review.py

# 仅复盘排列三
python scripts/daily_review.py --lottery pls

# 仅复盘福彩3D
python scripts/daily_review.py --lottery d3
```

### 预测相关

```bash
# 全策略预测
python run_daily.py --strategy all --top-k 30

# 单彩种
python run_daily.py pls --strategy all --top-k 30
```

### 数据源诊断

```bash
# 健康报告（终端）
python scripts/source_health.py

# 健康报告（JSON）
python scripts/source_health.py --json

# 健康报告（写入文件）
python scripts/source_health.py --json --output output/reports/source_health.json

# 熔断器状态（来源 status 文件）
python scripts/data_fetcher.py --cb-status
```

---

## 文件依赖关系（Hermes 需确保这些文件存在）

推送脚本 `hermes_push.py` 读取以下文件，任一缺失则该 section 显示"暂无"：

| 文件 | 来源 | 内容 |
|------|------|------|
| `output/reviews/review_history.csv` | `daily_review.py` | 复盘记录（含 strategy 字段） |
| `output/predictions/latest_pls.json` | `run_daily.py` / `scoring_engine.py` | 排列三预测 |
| `output/predictions/latest_d3.json` | `run_daily.py` / `scoring_engine.py` | 福彩3D预测 |
| `output/reports/source_health.json` | `source_health.py --output` | 数据源健康报告 |
| `data/cache/source_status.json` | `data_fetcher.py` | 熔断器状态（fallback） |

推送脚本写入：

| 文件 | 用途 |
|------|------|
| `output/push/daily_report.md` | 日报落盘（无论推送成功与否） |
| `output/push/pending_daily_report.md` | 推送失败时待补发的内容 |
| `output/push/send_log.jsonl` | 发送记录（逐行 JSON，含 hash 去重） |

---

## 关键设计原则

1. **任务分开执行，消息合并推送** — 复盘/预测/健康各自独立跑，hermes_push 只读不写
2. **失败隔离** — 复盘失败不阻塞预测，健康报告失败不阻塞推送
3. **落盘优先** — 先写 `daily_report.md` 再推送，推送失败内容不丢
4. **去重防轰炸** — 同一 hash 的日报同一天不会重复推送
5. **指数冷却** — sporttery API 连续失败后冷却 2h→6h→12h→24h
6. **stdout 隔离** — `--stdout` 模式只输出日报正文到 stdout，日志/警告全部走 stderr，确保 Hermes deliver=origin 推送内容干净

---

## 故障恢复

### 推送失败

推送失败时日报已落盘到 `output/push/daily_report.md`，不会丢失。手动补发：

```bash
python scripts/hermes_push.py --mode daily --force
```

### Gateway 关闭后恢复

1. 重启 Hermes gateway
2. 确认 `cron_mode = allow`
3. 手动补跑当天缺失的关键任务（优先补 17:25 预测 + 17:30 推送）
4. 不要连续补发多条微信，避免触发限频。间隔至少 5 秒

### 微信限频

`hermes_push.py` 已内置冷却和退避。如果仍然限频：
- 改用飞书作为主通道（配置 `FEISHU_WEBHOOK_URL`）
- 或只用 `--stdout` → `deliver=origin` 路径
