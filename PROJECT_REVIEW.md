# 项目审查总览

> 最后更新：2026-05-15 | 版本：v2.3

## 审查结论

| 维度 | 状态 | 备注 |
|:-----|:----:|:-----|
| 代码质量 | 🟢 良好 | 模块化，函数职责清晰 |
| 评分引擎 | 🟢 v2 | YAML权重+多样性惩罚+冷补偿 |
| 回测 | 🟢 v2 | Walk-forward + 三策略 + 奖金区分组三/组六 |
| 数据源 | 🟡 待完善 | 排列三API(体彩官方,有限频567) ✅ 福彩3D API(福彩官网,有WAF 403) ❌ |
| 依赖管理 | 🟢 有 | requirements.txt（不锁版本号，不装无用库） |
| 文档 | 🟢 完善 | README + SKILL.md + PROJECT_REVIEW.md |
| 可视化 | 🟢 完善 | matplotlib + plotly 交互图（走势/遗漏/热力图/Top50分布） |
| 工程化 | 🟢 有 | .gitattributes, .gitignore, .gitkeep |

## 已修复的问题清单

| 问题 | 发现来源 | 修复版本 | 说明 |
|:-----|:--------:|:--------:|:-----|
| Python文件被压缩显示 | GPT审查 | v2.2 | 实际为正常多行文件，GitHub网页渲染问题。验证方法：`curl raw URL | wc -l` + `py_compile` |
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

## 已知待修复 & 不采纳的建议

### 待修复

| 问题 | 严重程度 | 影响 |
|:-----|:--------:|:-----|
| 福彩3D自动爬取未完善 | 🔴 高 | 数据需要手动更新 |
| 组三偏好回归惩罚未实现 | 🟡 中 | 形态评分可能被短期趋势带偏 |
| 可视化未集成主流程 | 🟢 低 | 需手动调用 |

### 不采纳的建议（附理由）

以下为外部审查提出的建议，经评估后决定暂不采纳：

| 建议 | 来源 | 不采纳理由 |
|:-----|:----:|:----------|
| requirements.txt 锁版本号 | Grok | 项目跑在 Hermes venv 下（pandas 3.0.3, numpy 2.4.4），不锁版本号 = 装最新兼容版。锁死了反而哪天依赖冲突装不上。 |
| 添加 plotly / seaborn / tqdm 依赖 | Grok | 当前代码未使用这三个库。`matplotlib` 已满足基础可视化需求。等真正需要交互图表或进度条时再加，避免装无用依赖。 |
| data_fetcher 统一用 cwl.gov.cn API | Grok | Grok提供的代码全用福彩官网API。实测该API在服务器上返回 **403（WAF防护）**，不可用。排列三体彩API(webapi.sporttery.cn)保持独立实现，已验证可用。 |
| feature_engine 替换为 Grok 简化版 | Grok | Grok版本删除了数据检查、分位遗漏、group_number、冷热分类等核心功能(~240行)，换来了有bug的遗漏向量化(applymap在pandas 3.x已移除)和滚动特征。只提取了滚动特征加入现有版本。 |
| scoring_engine 替换为 Grok 简化版 | Grok | Grok版本(~75行)严重简化了评分引擎：删除多样性惩罚、冷号补偿、generate_predictions()、apply_diversity()，不兼容现有backtest。评分从9维降至4维，精度大幅下降。仅提取了"推荐理由"字段加入现有v2版本。 |
| 添加 LSTM 预测模块 | GPT / Grok | **不采用**，理由：① 彩票开奖是独立同分布随机事件，无时间依赖，LSTM 对此类序列的预测能力等同于随机策略；② 服务器 2核CPU/3.5GB内存/无GPU，跑不了深度学习训练；③ 即便训出来 ROI 也趋近随机，不如把精力用在评分引擎和特征工程。ML 正确用途是特征工程辅助（聚类分析），而非直接预测号码。 |

## 架构变更记录

### v2.3（当前）
- `scoring_engine.py`: 新增 `generate_predictions()` 共用函数
- `backtest.py`: `strategy_dynamic_scoring` 复用 generate_predictions，删除35行重复代码
- `backtest.py`: 回测ROI奖金区分组三(346元)和组六(173元)
- `data_fetcher.py`: 重写v2 —— 增量保存、日志系统、`--days`参数、API状态标注
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
