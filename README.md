# 彩票数据分析与预测系统（排列三 / 福彩3D）

基于**多窗口统计 + 理论分布 + 动态评分引擎**的彩票评分预测系统。对 000-999 全部 1000 注号码多维度打分排序，输出 Top-K 候选。

> ⚠️ **重要声明**：彩票开奖完全随机，本项目仅供学习、研究和娱乐参考。所有分析仅基于历史数据统计和理论分布，不代表未来开奖结果。请理性对待，量力而行。不保证任何命中率。

## 快速开始

> 项目目录已预置 `.gitkeep` 占位文件。若从零克隆，可用 `mkdir -p data/raw data/processed data/cache output/predictions output/backtests output/charts output/reports logs` 创建完整目录结构。

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 更新数据
python scripts/data_fetcher.py --all
#     ⚠️ 福彩3D自动抓取可能因 cwl.gov.cn WAF 返回 403→空数据
#     如果 d3 未获取到数据，参考下方「福彩3D数据说明」

# 3. 完整预测流程（排列三）
python scripts/data_fetcher.py --lottery pls
python scripts/feature_engine.py \
  --input data/raw/pls_raw.csv \
  --output data/processed/pls_feat.csv \
  --lottery pls \
  --force
# feature_engine 自动识别格式：标准三列(期号,日期,号码) 或 旧KittenCN格式
# 旧格式需要 --skiprows 参数，新格式自动处理

python scripts/stats_engine.py --lottery pls
python scripts/scoring_engine.py --lottery pls --top-k 30

# 4. 完整预测流程（福彩3D）
# 数据已内置 seed（data/archived/d3_history.csv），首次运行自动复制
python scripts/feature_engine.py --input data/raw/d3_raw.csv --output data/processed/d3_feat.csv --lottery d3
python scripts/stats_engine.py --lottery d3
python scripts/scoring_engine.py --lottery d3 --top-k 30

# 5. 回测
python scripts/backtest.py --lottery pls --periods 100 --top-k 30
python scripts/backtest.py --lottery d3 --periods 100 --top-k 30
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
│   ├── compare_result.py     # 预测 vs 开奖对比 + review_history累加
│   ├── review_summary.py     # 最近N期复盘表现摘要
│   ├── daily_review.py       # 每日复盘一键脚本（Hermes cron调用）
│   ├── tune_weights.py       # 权重自动调优（随机搜索 + Optuna贝叶斯优化）
│   ├── filter_engine.py      # 轻量预过滤器
│   └── visualize.py          # 走势图/热力图（可选）
├── rules/
│   ├── scoring_weights.yaml              # 默认权重
│   ├── scoring_weights_conservative.yaml # 稳健策略
│   ├── scoring_weights_diversity.yaml    # 多样性策略
│   ├── data_sources.yaml                 # 数据源配置（URL外部化）
│   ├── pls_default.yaml                  # 排列三过滤规则
│   └── d3_default.yaml                   # 福彩3D过滤规则
├── data/
│   ├── raw/                  # 原始CSV（data_fetcher.py存放位置）
│   ├── processed/            # 特征工程输出（113维）
│   ├── archived/             # 种子数据（首次clone自动复制到raw/）
│   └── cache/                # 统计缓存
├── output/
│   ├── predictions/          # 预测结果JSON（支持多策略独立输出）
│   ├── reviews/              # 复盘总表（review_history.csv）
│   ├── backtests/            # 回测报告
│   ├── charts/               # 可视化图表
│   ├── reports/              # 数据检查+对比报告
│   └── tuning/               # 调参记录
├── CLAUDE.md                 # Claude Code 项目指令
├── Makefile                  # 一键命令入口
└── requirements.txt          # 依赖清单
```

## 评分引擎（核心）—— v2

### 权重配置（`rules/scoring_weights.yaml`）

| 维度 | 默认权重 | 评分方式 |
|------|:--------:|----------|
| 和值 | 18 | 理论组合比例×60% + 近30期频率比例×40% × 过热衰减 |
| 跨度 | 15 | 同上 |
| 形态 | 12 | 理论回归惩罚——实际频率偏离理论双向扣分（组三过热降分、过冷加分） |
| 奇偶 | 8 | 1-2个奇数=满分，全奇全偶=低分 |
| 大小 | 8 | 同上 |
| 012路 | 7 | 均衡=高分，一路集中=低分 |
| **冷热** | **10 ↑** | 0冷号+有热号=满分（冷号阈值由8→**6**） |
| **遗漏** | **7 ↑** | 三个号码在平均遗漏半值内=满分 |
| 组三六偏向 | 8 | 保留权重位，实际回归惩罚已由形态维度统一处理 |
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

## 后续计划

- [ ] 评分权重系统调优（等待 review_history.csv 积累 30 期数据后运行 tune_weights.py）
- [ ] 遗漏计算真正向量化（去除 Python for 循环，当前 7600 行性能足够）
- [ ] GitHub Actions 每日自动运行（可选）

> ❌ **不考虑 LSTM/ML 预测模块**，原因：
>
> 1. **理论不成立**：彩票开奖是独立同分布随机事件，每期之间无时间依赖关系，LSTM 对此类序列的预测能力等同于随机策略
> 2. **硬件不支持**：当前服务器为 2 核 CPU、3.5GB 内存、**无 NVIDIA GPU**（`nvidia-smi: 未安装`），无法运行深度学习训练
> 3. **投入产出比低**：即便训练出模型，其 ROI 在统计上也趋近于随机策略，不如把精力用在优化评分引擎和特征工程上
>
> ML 的正确用途：特征工程辅助（如聚类分析辅助生成规则），而非直接预测号码。

## 数据来源

| 彩种 | 源 | 方法 |
|------|-----|------|
| 排列三（体彩） | 体彩官方API | `data_fetcher.py` 自动拉取 JSON | ✅ 已验证可用 |
| 福彩3D | kaggle/konglr历史CSV | 需手动准备 | ❌ API有WAF 403 |

### 福彩3D手动数据准备

> ⚠️ **当前 `data_fetcher.py --lottery d3` 可能返回空数据**（cwl.gov.cn WAF 403）。

如果自动抓取失败，请手动准备 `data/raw/d3_raw.csv`：

```csv
期号,日期,号码
2025123,2025-05-01,583
2025122,2025-04-30,147
2025121,2025-04-29,902
```

- 字段：`期号`（数字）、`日期`（YYYY-MM-DD）、`号码`（3位数字连写）
- 可参考 [konglr/Lottery](https://github.com/konglr/Lottery) 获取历史数据
- 准备好后继续执行第4步的预测流程即可

### 开奖时间

| 彩种 | 官方开奖 | 建议拉取 |
|------|---------|---------|
| 排列三 | 每日 21:25 | 22:00 以后 |
| 福彩3D | 每日 21:15 | 22:00 以后 |

> 数据源（API/网页）通常在开奖后 15-30 分钟更新，过早拉取可能获取不到最新期。

### 排列三数据说明
当前 CSV 包含 3 行非数据头（列名 + 2 行中文说明），
`feature_engine.py` 需加 `--skiprows 3`。

如果使用其他来源的数据，先用 `head -10 data/raw/pls_raw.csv` 确认格式：
- 标准三列 CSV（`期号,日期,号码`）：不加 `--skiprows`
- 2 行中文说明：加 `--skiprows 2`
- 3 行非数据头（当前）：加 `--skiprows 3`

## 回测

```bash
python scripts/backtest.py --lottery pls --periods 100 --top-k 30
```

采用 **Walk-forward** 方式（避免未来函数），比较三种策略：
1. **随机基准**：纯随机选30注
2. **固定规则**：固定权重评分
3. **动态调整**：根据近期表现调权重

## 可视化

生成走势图、热力图（matplotlib PNG + plotly 交互 HTML）：

```bash
# 排列三全部图表（PNG + HTML 两种格式）
python scripts/visualize.py --lottery pls --chart all
# 福彩3D全部图表
python scripts/visualize.py --lottery d3 --chart all
# 仅生成走势图
python scripts/visualize.py --lottery pls --chart trend
# 仅生成交互HTML（不含PNG）
python scripts/visualize.py --lottery pls --chart all --output-format html
```

- **PNG 静态图**：走势图、遗漏图、热力图 → `output/charts/`
- **HTML 交互图**：走势图、热力图、Top50推荐分布（支持悬停/缩放）→ `output/charts/`
- plotly 为可选依赖，未安装则自动跳过 HTML 输出

## 预测 vs 开奖对比

开奖后比对预测结果与实际开奖：

```bash
python scripts/compare_result.py --lottery pls
python scripts/compare_result.py --lottery d3
```

输出：直选/组选命中、和值差、跨度差、形态一致性。报告保存至 `output/reports/{lottery}_compare_latest.json`。

## 自动化读取最新预测结果

预测结果同步保存为固定路径，方便脚本/Hermes/GPT自动读取：

```
output/predictions/latest_pls.json      # 排列三最新预测（固定入口）
output/predictions/latest_d3.json       # 福彩3D最新预测（固定入口）
output/predictions/pls_predict_26125.json   # 按期号命名的历史记录
output/predictions/d3_predict_2026125.json  # 同上
```

### GPT/Grok 直接读取 URL

```
https://raw.githubusercontent.com/liu208987-git/lottery-analysis/main/output/predictions/pls_predict_{期号}.json
https://raw.githubusercontent.com/liu208987-git/lottery-analysis/main/output/predictions/d3_predict_{期号}.json
```

## 每日推荐流程

### 一键每日运行（推荐）

```bash
python run_daily.py                     # 跑排列三 + 福彩3D（默认Top-30）
python run_daily.py pls                 # 只跑排列三
python run_daily.py d3                  # 只跑福彩3D
python run_daily.py --top-k 10          # 推荐10注
python run_daily.py pls --top-k 20 --exclude-recent 3
```

脚本自动执行：seed数据初始化 → 数据更新 → 特征工程 → 统计引擎 → 评分预测 → 可视化。
预测结果保存至 `output/predictions/{lottery}_predict_{期号}.json`。

### 手动流程

| 时间 | 操作 | 说明 |
|:---|:-----|:-----|
| 08:00 | `python run_daily.py` | 基于最新数据生成**当晚**预测 |
| 22:00 | `python scripts/data_fetcher.py --all` | 拉取今晚开奖结果（数据源通常 21:30-22:00 间更新） |
| 22:00 | `python scripts/compare_result.py --lottery pls` | 预测 vs 开奖对比，自动累加复盘记录 |
| 22:00 | `python run_daily.py` | 基于最新数据生成**明晚**预测 |
> ⚠️ 开奖后数据源更新有延迟，建议 22:00 后再拉取。福彩3D 双源自动切换，无需手动准备。

## 已知问题与限制

- 🟢 **福彩3D双源覆盖**：zhcw.com 主源 + eastmoney.com 备用校验，自动 fallback
- 🟡 **评分权重待调优**：tune_weights.py 已就绪（随机搜索 + Optuna 贝叶斯优化），等待复盘数据积累
- ⚠️ **彩票结果高度随机**：所有分析仅基于历史统计，不代表未来结果

## 风险提示

彩票开奖结果具有高度随机性。所有分析仅基于历史数据统计和理论分布，不代表未来开奖结果。请理性看待，不建议将分析结果作为实际投注依据。

## 更新日志

- **v2.7.1** (2026-05-16)：Hermes cron 适配——新增 `daily_review.py` 一键复盘脚本；`compare_result.py` 支持 `--strategy` 多策略对比；`review_history.csv` 增加策略列；回测 ROI 拆分直选/组选；`save_incremental` 空数据保护
- **v2.7** (2026-05-16)：复盘闭环 + 数据源加固 + 工具链完善——review_history.csv 长期复盘累加、review_summary.py 表现摘要、多策略权重(conservative/diversity)、tune_weights.py 随机搜索+Optuna贝叶斯优化+参数稳定性分析；东方财富福彩3D接入(50条/页)+双源校验+主源失败自动fallback；CLAUDE.md项目指令、Makefile一键命令、data_sources.yaml配置外部化
- **v2.6.1** (2026-05-15)：P1/P2集中修复——组三回归惩罚(形态评分双向扣分)、API 567退避重试、回测多注命中累加(sum替代any/elif)、回测参数验证、PNG中文字体自动探测；号码清洗加固(normalize_number去空格/补零/剔除非数字)；compare_result输出优化(开奖号码大字展示+一句话摘要)
- **v2.6** (2026-05-15)：第二轮代码审查修复——shell=True→列表参数、skiprows=0、删除openTime死代码、is_monotonic_increasing优化、generate_all()复用add_features()去重；新增 compare_result.py 预测vs开奖对比脚本；run_daily.py CLI参数化(--top-k/--exclude-recent)；seed数据归档(data/archived/)；Top30字段修复
- **v2.5.1** (2026-05-15)：新增 `run_daily.py` 一键每日运行脚本；福彩3D数据源升级为zhcw.com；feature_engine兼容简洁3列CSV格式
- **v2.5** (2026-05-15)：scoring_engine JSON结构升级——过滤说明改object、代码版本字段、展示理由字段；README模式A/B说明(--skiprows 3/2)；git兼容Python 3.6；.gitignore放行output/predictions/*.json
- **v2.4.1** (2026-05-15)：feature_engine.py numpy 2.x兼容修复(np.char.add)、遗漏特征向量化(20x加速)；scoring_engine新参数exclude-mode/include-baozi/target-issue；backtest同步
- **v2.4** (2026-05-15)：Plotly交互式可视化(HTML双格式)；README福彩3D入口优化；GPT/Grok建议评估
- **v2.3** (2026-05-15)：`generate_predictions()` 抽取共用、回测奖金区分组三(346元)/组六(173元)、新增 PROJECT_REVIEW.md
- **v2.2** (2026-05-15)：P0/P1/P2 代码审查修复（README参数补全、回测组选判断修复、数据检查退出保护等）
- **v2.0** (2026-05-15)：评分引擎重大升级——YAML权重配置、多样性惩罚、冷号补偿、data_fetcher 数据自动获取
- **v1.0** (2026-05-14)：初始版本——基础评分引擎、特征工程、回测
