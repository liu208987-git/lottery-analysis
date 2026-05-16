# Hermes 定时任务配置

> 此文件供 Hermes 读取并自动配置定时任务。修改此文件后，同步至 Hermes 平台生效。
> 最后更新：2026-05-17（v2.8 数据源修复 + 合并推送架构）

---

## 环境变量

Hermes 执行环境需配置以下变量：

| 变量名 | 必填 | 说明 | 示例 |
|------|:--:|------|------|
| `HERMES_WEBHOOK_URL` | 否 | 通用 Webhook 推送地址 | `https://your-webhook.example.com/send` |
| `WECOM_WEBHOOK_URL` | 否 | 企业微信群机器人 Webhook | `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx` |

> 二选一即可，都配置时优先使用 `WECOM_WEBHOOK_URL`（企业微信格式）。都不配置时推送内容仅打印到 stdout，不发送。

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
命令: cd /path/to/lottery-analysis && python scripts/hermes_push.py --mode daily
失败处理: 必须成功
说明: 读取复盘 + 预测 + 健康报告 → 拼接日报 → 落盘 → 推送
      推送失败时内容保存到 output/push/pending_daily_report.md
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
