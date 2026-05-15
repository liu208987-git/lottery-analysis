# 彩票数据分析与预测系统

排列三和福彩3D的统计分析与评分预测系统，基于多窗口统计+理论分布+动态评分引擎。

## 快速使用

```bash
# 完整预测流程（排列三）
python scripts/feature_engine.py --input data/raw/pls_raw.csv --output data/processed/pls_feat.csv --lottery pls --skiprows 2
python scripts/stats_engine.py --lottery pls
python scripts/scoring_engine.py --lottery pls --top-k 30

# 完整预测流程（福彩3D）
python scripts/feature_engine.py --input data/raw/d3_raw.csv --output data/processed/d3_feat.csv --lottery d3
python scripts/stats_engine.py --lottery d3
python scripts/scoring_engine.py --lottery d3 --top-k 30

# 回测
python scripts/backtest.py --lottery pls --periods 100 --top-k 30

# 可视化（待实现）
python scripts/visualize.py --lottery pls
```

## 项目结构

```
lottery-analysis/
├── data/
│   ├── raw/          # 原始数据CSV
│   ├── processed/    # 特征工程输出
│   └── cache/        # 统计缓存
├── output/
│   ├── predictions/  # 评分预测JSON
│   ├── backtests/    # 回测结果
│   ├── charts/       # 可视化图表
│   └── reports/      # 数据检查报告
├── scripts/
│   ├── feature_engine.py   # 特征工程
│   ├── stats_engine.py     # 多窗口统计
│   ├── scoring_engine.py   # 评分预测引擎
│   ├── backtest.py         # Walk-forward回测
│   ├── visualize.py        # 趋势/热力图
│   └── filter_engine.py    # 轻量预过滤器
├── rules/            # 规则配置YAML
└── logs/             # 运行日志
```

## 评分权重

| 维度 | 权重 | 说明 |
|------|------|------|
| 和值 | 20分 | 理论分布打分 |
| 跨度 | 18分 | 跨度5组合最多 |
| 形态 | 14分 | 组三/组六倾向 |
| 奇偶 | 10分 | |
| 大小 | 10分 | |
| 012路 | 8分 | |
| 冷热 | 5分 | |
| 遗漏 | 5分 | |
| 组三/六偏向 | 10分 | |
