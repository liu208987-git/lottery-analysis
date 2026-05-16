# GPT 代码审查：数据源修复后的遗留问题

> 审查时间：2026-05-17
> 审查对象：v2.7.1 数据源可靠性修复（js-lottery主源 + 熔断 + 校验 + 隔离）
> GPT 总体评价：数据源可靠性 5→8/10，防错误数据 4→8/10

---

## 🔴 P0 — Bug，需修复

### 1. review_history 去重缺少策略字段

**位置**: [scripts/compare_result.py:222](scripts/compare_result.py#L222)

**问题**:
```python
merged = merged.drop_duplicates(subset=['彩种', '期号'], keep='last')
```
三套策略(default/conservative/diversity)复盘同一期号时，只保留最后一条，前两条被覆盖。

**后果**: review_history 里所有记录 strategy 都是 `diversity`（字母序最后），default 和 conservative 的复盘数据全部丢失。后续无法统计"最近30期哪套策略命中率最高"。

**修复**: 改为 `subset=['彩种', '期号', '策略']`

**影响范围**: `review_summary.py` 读取 review_history 做统计，当前统计数据因缺少策略维度而偏低。

---

## 🟡 P1 — 应实施

### 2. 熔断冷却时间应指数递增

**位置**: `scripts/data_fetcher.py` CircuitBreaker 类

**问题**: 当前所有源失败 N 次后的冷却时间是固定的（sporttery 120min, zhcw 60min）。但 sporttery 实际已连续 35+ 小时 567，2 小时冷却不够。

**建议**: 冷却时间随失败轮次递增：
```
第1轮(连续2次失败) → 冷却 2h
第2轮(再次连续2次) → 冷却 6h
第3轮(再次连续2次) → 冷却 12h
第4轮+             → 冷却 24h
```
实现方式：在 `source_status.json` 中增加 `cooldown_round` 字段，`record_failure` 时检测上一轮冷却是否到期后再次失败，若是则 round+1。

**影响**: 减少对长期不可用源（如被 WAF 屏蔽的 sporttery）的无效请求。

---

### 3. 缺少数据源健康报告脚本

**位置**: 新建 `scripts/source_health.py`

**问题**: 当前需要手动 `cat data/cache/source_status.json` 才能看熔断状态。没有一个一目了然的健康报告。

**建议输出格式**:
```
【数据源健康状态】

PLS:
  ✅ js_lottery      正常，最新 26126=835
  🔒 sporttery_api   熔断中，HTTP 567，冷却至 02:30

D3:
  ✅ eastmoney       正常，最新 2026126=846
  ✅ zhcw            正常，双源校验一致

Quarantine:
  最近 24h 坏数据：0 条
```

**价值**: 适合加进 Hermes cron 推送，无需翻日志。

---

### 4. quarantine 应改为结构化 JSON

**位置**: `scripts/data_fetcher.py` `_quarantine_bad_data()`

**问题**: 当前隔离数据存为 CSV，缺少冲突上下文。当双源号码不一致时，CSV 无法清晰记录 primary 说什么、verify 说什么。

**建议格式**:
```json
{
  "lottery": "d3",
  "issue": "2026126",
  "expected_date": "2026-05-16",
  "primary": {"source": "eastmoney", "number": "846", "date": "2026-05-16"},
  "verify":  {"source": "zhcw",      "number": "954", "date": "2026-05-15"},
  "reason": "source_mismatch",
  "action": "not_written_to_raw",
  "created_at": "2026-05-17 00:35:00"
}
```

**价值**: 排查数据冲突时一目了然。

---

## 🟢 P2 — 可暂缓

### 5. data_sources.yaml 缺少 trust_level/priority 字段

**位置**: `rules/data_sources.yaml`

**问题**: 当前只有 `enabled`/`type`/`url`/`circuit_breaker`，缺少描述源可信度的元数据。

**建议新增**:
```yaml
pls:
  sources:
    - name: js_lottery
      role: primary
      priority: 1
      trust_level: high
    - name: sporttery_api
      role: backup
      priority: 2
      trust_level: official_but_limited
```

**价值**: 未来数据源多了以后便于排序和决策，当前仅 2 个源暂时不紧急。

---

### 6. run_daily.py 应拆分 predict / review 模式

**问题**: 当前 `run_daily.py` 把预测（抓数据→特征→评分）和复盘杂糅。Cron 需要两个独立命令。

**建议**:
```bash
python run_daily.py --mode predict --strategy all    # 17:30
python run_daily.py --mode review                     # 22:00
```

**价值**: 架构更清晰，但当前 Hermes cron 已经用两个独立命令（`run_daily.py` + `daily_review.py`），功能上已满足。

---

### 7. review_summary 应按策略分别统计

**问题**: 当前 `review_summary.py` 输出的是所有策略混合的统计。在修复 Bug #1 后，review_history 将正确包含策略字段，届时可以按策略维度输出。

**建议输出**:
```
【排列三 最近30期】
default:       组选命中 3/30 (10%), 平均和值差 2.1
conservative:  组选命中 5/30 (17%), 平均和值差 1.8
diversity:     组选命中 2/30 ( 7%), 平均和值差 2.5
最佳策略: conservative
```

**前置依赖**: 必须先修复 Bug #1，且需积累 ≥15 期复盘数据。

---

### 8. CircuitBreaker key 命名规范

**问题**: 当前 key 用 `pls_js_lottery`（下划线分隔），建议改为 `pls:js_lottery`（冒号分隔），避免 source name 本身含下划线时歧义。

**价值**: 命名规范，不影响功能，可随下次重构一并调整。

---

### 9. 每日边界期号测试

**问题**: `issue_utils.py` 已有自测，但未覆盖每年年初 `001` 期号的边界情况。

**建议补充**:
```python
assert parse_issue("26001") == {"year": 2026, "seq": 1, "seq3": "001"}
assert parse_issue("2026001") == {"year": 2026, "seq": 1, "seq3": "001"}
assert same_draw_day("26001", "2026001") is True
assert same_draw_day("26126", "2026125") is False
```

**价值**: 防止年初跨年时 parse 错误。当前 parse_issue 逻辑上能正确处理，但缺测试覆盖。

---

## 不需要改动（GPT 建议但已实现）

| GPT 建议 | 现状 |
|------|------|
| PLS 抓最近 N 期而非单期 | ✅ `--days 30`，每次抓30期 |
| D3 按期号精确匹配而非 iloc[0] | ✅ `df['期号'] == expected_issue` |
| PLS 号码保留前导 0 | ✅ `zfill(3)` 全程 |
| 空数据不覆盖旧文件 | ✅ `save_incremental` 有保护 |
| 旧 PLS 格式自动迁移 | ✅ `_migrate_old_format()` |
| 坏数据隔离到 quarantine | ✅ `_quarantine_bad_data()` |
| 熔断状态持久化 | ✅ `source_status.json` |
| 双源校验 | ✅ eastmoney vs zhcw |

---

## 小结

| 优先级 | 数量 | 预计总工作量 |
|------|------|------|
| P0 Bug | 1 | 1 行改动 |
| P1 应实施 | 3 | ~70 行 |
| P2 可暂缓 | 5 | ~150 行 |

当前数据源架构已从"单源裸奔"升级为"多源容错管道"，最严重的两个隐患（PLS 567断流、D3 zhcw错号）已解决。上述遗留问题不影响主流程运行，可在后续迭代中逐步修复。
