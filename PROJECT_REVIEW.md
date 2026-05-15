# 项目审查总览

> 最后更新：2026-05-15 | 版本：v2.3

## 审查结论

| 维度 | 状态 | 备注 |
|:-----|:----:|:-----|
| 代码质量 | 🟢 良好 | 模块化，函数职责清晰 |
| 评分引擎 | 🟢 v2 | YAML权重+多样性惩罚+冷补偿 |
| 回测 | 🟢 v2 | Walk-forward + 三策略 + 奖金区分组三/组六 |
| 数据源 | 🟡 待完善 | 排列三API可用，福彩3D需补全 |
| 依赖管理 | 🟢 有 | requirements.txt |
| 文档 | 🟢 完善 | README + SKILL.md + PROJECT_REVIEW.md |
| 可视化 | 🟢 有 | 三张基础图（走势/遗漏/热力图） |
| 工程化 | 🟢 有 | .gitattributes, .gitignore, .gitkeep |

## 已修复的问题清单

| 问题 | 发现来源 | 修复版本 | 说明 |
|:-----|:--------:|:--------:|:-----|
| Python文件被压缩显示 | GPT审查 | v2.2 | 实际是352/302/482行的正常文件，GitHub网页渲染问题 |
| README命令缺参数 | GPT审查 | v2.2 → v2.3 | 补充了 `--input`/`--output`/`--skiprows` |
| data_fetcher退出逻辑 | GPT审查 | v2.2 | 数据不通过且无 `--force` 时 exit(1) |
| stats_engine排序保护 | GPT审查 | v2.2 | 加 `sort_values('期数', ascending=False)` |
| backtest组选命中永远True | GPT审查 | v2.2 | 改为真正的组选匹配 |
| backtest权重引用过期 | GPT审查 | v2.2 | 改为 `load_weights()` |
| 评分权重硬编码 | 自行发现 | v2.0 | 迁移到 `rules/scoring_weights.yaml` |
| 跨度偏好固化 | 自行发现 | v2.0 | 加入多样性惩罚 |
| 评分0区分度 | 自行发现 | v2.0 | 加入冷补偿+多样性 |
| 回测奖金不区分组三/组六 | GPT审查 | v2.3 | 组三=346元，组六=173元 |
| strategy_dynamic重复评分逻辑 | GPT审查 | v2.3 | 改为复用 `generate_predictions()` |

## 已知待修复

| 问题 | 严重程度 | 影响 |
|:-----|:--------:|:-----|
| 福彩3D自动爬取未完善 | 🔴 高 | 数据需要手动更新 |
| 组三偏好回归惩罚未实现 | 🟡 中 | 形态评分可能被短期趋势带偏 |
| 可视化未集成主流程 | 🟢 低 | 需手动调用 |

## 架构变更记录

### v2.3（当前）
- `scoring_engine.py`: 新增 `generate_predictions()` 共用函数
- `backtest.py`: `strategy_dynamic_scoring` 复用 generate_predictions，删除35行重复代码
- `backtest.py`: 回测ROI奖金区分组三(346元)和组六(173元)
- 新增 `PROJECT_REVIEW.md`

### v2.2
- 修复GPT代码审查提出的3个P0 + 3个P1 + 3个P2问题
- 添加 `.gitkeep` 保留空目录
- 添加 `.gitattributes` 确保LF换行符
- README补全命令参数

### v2.0
- 评分引擎重大升级：YAML权重可配置
- 多样性惩罚（组选去重+跨度多样化）
- 冷号补偿（阈值6→冷号占比更大）
- data_fetcher 数据自动获取
- requirements.txt

## 文件清单

```
lottery-analysis/
├── scripts/
│   ├── feature_engine.py     # 113维特征工程 + 数据检查
│   ├── stats_engine.py       # 多窗口统计 + 理论分布
│   ├── scoring_engine.py     # 评分引擎v2 + generate_predictions()
│   ├── backtest.py           # Walk-forward回测v2
│   ├── data_fetcher.py       # 自动拉取数据
│   ├── filter_engine.py      # 轻量预过滤
│   └── visualize.py          # 走势/遗漏/热力图
├── rules/
│   ├── scoring_weights.yaml  # 评分权重（可配置）
│   ├── pls_default.yaml      # 排列三过滤规则
│   └── d3_default.yaml       # 福彩3D过滤规则
├── data/  (raw/processed/cache)
├── output/  (predictions/backtests/charts/reports)
├── logs/
├── README.md
├── requirements.txt
├── PROJECT_REVIEW.md
└── .gitattributes / .gitignore
```
