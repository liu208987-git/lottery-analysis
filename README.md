# 彩票数据分析与预测系统（排列三 / 福彩3D）

基于多窗口统计 + 理论分布 + 动态评分引擎的彩票评分预测系统。对 000-999 全部 1000 注号码多维度打分排序，输出 Top-K 候选。**随机开奖，统计参考，不保证命中。**

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 更新数据（自动从体彩/福彩API拉取）
python scripts/data_fetcher.py --all

# 3. 完整预测流程（排列三）
python scripts/feature_engine.py --input data/raw/pls_raw.csv --output data/processed/pls_feat.csv --lottery pls --skiprows 2
python scripts/stats_engine.py --lottery pls
python scripts/scoring_engine.py --lottery pls --top-k 30

# 4. 完整预测流程（福彩3D）
python scripts/feature_engine.py --input data/raw/d3_raw.csv --output data/processed/d3_feat.csv --lottery d3
python scripts/stats_engine.py --lottery d3
python scripts/scoring_engine.py --lottery d3 --top-k 30

# 5. 回测
python scripts/backtest.py --lottery pls --periods 100 --top-k 30
python scripts/backtest.py --lottery d3 --periods 100 --top-k 30

# 6. 每日自动更新（cron）
# 08:00 北京时间 → 最新数据+今晚预测
# 21:30 北京时间 → 拉取今晚结果+明晚预测
```

## 项目结构

```
lottery-analysis/
├── scripts/
│   ├── data_fetcher.py       # 自动拉取最新数据（体彩API+福彩页面）
│   ├── feature_engine.py     # 113维特征工程 + 数据质量检查
│   ├── stats_engine.py       # 多窗口统计 + 理论分布对比
│   ├── scoring_engine.py     # 评分引擎v2（YAML权重+多样性惩罚+冷补偿）
│   ├── backtest.py           # Walk-forward回测（三策略对比）
│   ├── filter_engine.py      # 轻量预过滤器
│   └── visualize.py          # 趋势图/热力图（可选）
├── rules/
│   ├── pls_default.yaml      # 排列三过滤规则
│   ├── d3_default.yaml       # 福彩3D过滤规则
│   └── scoring_weights.yaml  # 评分权重（可调，无需改代码）
├── data/
│   ├── raw/                  # 原始CSV（data_fetcher.py存放位置）
│   ├── processed/            # 特征工程输出（113维）
│   └── cache/                # 统计缓存
├── output/
│   ├── predictions/          # 预测结果JSON
│   ├── backtests/            # 回测报告
│   ├── charts/               # 可视化图表
│   └── reports/              # 数据检查报告
└── requirements.txt          # 依赖清单
```

## 评分引擎（核心）—— v2

### 权重配置（`rules/scoring_weights.yaml`）

| 维度 | 默认权重 | 评分方式 |
|------|:--------:|----------|
| 和值 | 18 | 理论组合比例×60% + 近30期频率比例×40% × 过热衰减 |
| 跨度 | 15 | 同上 |
| 形态 | 12 | 近30期实际比例评分（组六/组三），+理论回归惩罚 |
| 奇偶 | 8 | 1-2个奇数=满分，全奇全偶=低分 |
| 大小 | 8 | 同上 |
| 012路 | 7 | 均衡=高分，一路集中=低分 |
| **冷热** | **10 ↑** | 0冷号+有热号=满分（冷号阈值由8→**6**） |
| **遗漏** | **7 ↑** | 三个号码在平均遗漏半值内=满分 |
| 组三六偏向 | 8 | 短期趋势评分 + 回归惩罚 |
| **多样性** | **10 新增** | 组选重复扣分 + 跨度多样性加分 |

**v2 关键改进：**
- ✅ 所有权重从 YAML 加载，改策略不需改代码
- ✅ **组选多样性惩罚**：同组选号码只保留最高分直选
- ✅ **跨度多样性促进**：Top-K 尽量覆盖多个跨度
- ✅ **冷号阈值下调**：遗漏>6视为冷号（原8），给冷号更多机会
- ✅ **过热衰减更敏感**：近5期出现≥3次打6折
- ✅ **走势分计算修复**：从 `*30` 改为理论频率比

### 评分原则
- **不硬过滤**：1000注全部打分，按总分排序
- **理论+近期混合**：每条规则 = 理论分布分×60% + 近期走势分×40%
- **过热衰减**：近5期高频特征折扣
- **理论回归惩罚**：形态/跨度偏离理论分布越大扣分越多

## 数据来源

| 彩种 | 源 | 方法 |
|------|-----|------|
| 排列三（体彩） | 体彩官方API | `data_fetcher.py` 自动拉取 JSON |
| 福彩3D | kaggle/konglr历史CSV | 当前手动准备，后续自动 |

### 开奖时间

| 彩种 | 开奖时间 |
|------|---------|
| 排列三 | 每日 21:25 |
| 福彩3D | 每日 21:15 |

### 排列三数据说明
原始数据有2行表头，`feature_engine.py` 需加 `--skiprows 2`。

## 回测

```bash
python scripts/backtest.py --lottery pls --periods 100 --top-k 30
```

采用 **Walk-forward** 方式（避免未来函数），比较三种策略：
1. **随机基准**：纯随机选30注
2. **固定规则**：固定权重评分
3. **动态调整**：根据近期表现调权重

## 已知问题与限制

- 🟡 **数据源不完整**：福彩3D自动爬取尚未实现完整
- 🟡 **评分跨度偏好**：跨度5因理论组合数最多，容易主导评分（已加入多样性惩罚缓解）
- 🟡 **可视化未集成**：visualize.py 存在但未正式接入主流程
- ⚠️ **彩票结果高度随机**：所有分析仅基于历史统计，不代表未来结果

## 风险提示

彩票开奖结果具有高度随机性。所有分析仅基于历史数据统计和理论分布，不代表未来开奖结果。请理性看待，不建议将分析结果作为实际投注依据。

## 更新日志

- **v2.2** (2026-05-15)：P0/P1/P2 代码审查修复（README参数补全、回测组选判断修复、数据检查退出保护等）
- **v2.0** (2026-05-15)：评分引擎重大升级——YAML权重配置、多样性惩罚、冷号补偿、data_fetcher 数据自动获取
- **v1.0** (2026-05-14)：初始版本——基础评分引擎、特征工程、回测
