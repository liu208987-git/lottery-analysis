# 变更日志

> 集中式变更日志，按版本从新到旧排列。单日详细记录见 `changelog/` 目录。

## v2.10.2 (2026-05-20)

- **推送自闭环**：`lottery_predict_push.sh` 内部自动执行 run_daily → source_health → hermes_push 全流程
- **预测推送加 `--force`**：避免当天去重命中后无输出，每次 14:40 到点强制推送
- **推送脚本纳入版本控制**：`scripts/push/lottery_predict_push.sh`、`scripts/push/lottery_review_push.sh`
- **14:30/14:35 降级为辅助任务**：即使失败也不影响 14:40 推送
- **文档同步**：README / CLAUDE.md / HERMES_CONFIG.md / PROJECT_REVIEW.md 全部同步 no_agent 审批说明

## v2.10.1 (2026-05-19)

- **推送链路加固**：Tirith glibc 兼容问题导致 cron 审批中断，4 个推送任务全部改为 no_agent=true
- **脚本化推送**：新建 `~/.hermes/scripts/lottery_predict_push.sh` / `lottery_review_push.sh`
- **不消耗 API token**：no_agent 模式无大模型调用，脚本直接运行并 stdout 交付飞书
- **crontab 方案讨论并否决**：详见 `changelog/2026-05-19-fix-tirith-cron-push.md`

## v2.10.0 (2026-05-19)

- **两段式推送**：hermes_push 新增 predict(预测)/review(复盘)两种模式，下午推预测、晚间推复盘
- **compare_result 期号分类**：pred>actual → waiting_actual(exit 0，写 `*_waiting.json` 不覆盖 latest)；pred<actual 视为真错误(exit 1)
- **build_review_message 重写**：从"昨日复盘"改为"今日预测 vs 开奖直接对比"
- **HERMES_CONFIG 6 cron job**：结构化配置清单，含故障恢复章节
- **push_state.json**：每期推送状态记录，多轮 cron 不重复轰炸

## v2.7.1 (2026-05-16)

- **Hermes cron 适配**：新增 `daily_review.py` 一键复盘脚本
- **compare_result 多策略对比**：支持 `--strategy` 参数
- **review_history.csv 增加策略列**：支持按策略分组复盘
- **backtest ROI 拆分**：直选/组选独立计算
- **data_fetcher 空数据保护**：`save_incremental()` 处理空数据场景

## v2.7 (2026-05-16)

- **复盘闭环**：compare_result → review_history.csv 累加 → review_summary 表现摘要
- **多策略权重**：scoring_weights_conservative.yaml / diversity.yaml + `run_daily --strategy all`
- **权重自动调优**：tune_weights.py（随机搜索 + Optuna TPE 贝叶斯优化 + 参数稳定性分析）
- **数据源加固**：东方财富福彩3D 接入(50条/页) + 双源校验 + fallback
- **工具链**：CLAUDE.md 项目指令 + Makefile + data_sources.yaml 配置外部化

## v2.6.1 (2026-05-15)

- **组三回归惩罚**：形态评分改为双向惩罚（过热降分、过冷加分）
- **API 567 退避重试**：fetch_pls() 限频 5s/10s/15s 递增等待
- **回测命中累加**：从 any()/elif 改为 sum() 累加 + 参数验证
- **PNG 中文字体**：matplotlib 自动探测系统中文字体
- **号码清洗**：normalize_number() 去空格/补零/剔除非数字
- **compare_result 输出优化**：开奖号码大字展示 + JSON 一句话摘要

## v2.6 (2026-05-15)

- **第二轮代码审查修复**：shell=True→列表参数、skiprows=0、删除 dead code
- **scoring_engine**：`generate_all()` 复用 feature_engine.add_features()，消除~60行重复
- **compare_result.py 新增**：预测 vs 开奖对比脚本
- **run_daily.py CLI 参数化**：--top-k / --exclude-recent，`ensure_seed_data()` 自动初始化
- **种子数据归档**：data/archived/pls_history.csv + d3_history.csv

## v2.5.1 (2026-05-15)

- **run_daily.py 新增**：一键每日运行脚本
- **福彩3D 数据源升级**：zhcw.com pd.read_html
- **feature_engine 兼容简洁 3 列 CSV**

## v2.5 (2026-05-15)

- **scoring_engine JSON 结构升级**：过滤说明改 object、代码版本字段
- **README 模式 A/B 说明**：--skiprows 3/2
- **.gitignore 放行 predictions/*.json**

## v2.4.1 (2026-05-15)

- **numpy 2.x 兼容**：np.char.add 修复
- **遗漏特征向量化**：20x 加速

## v2.4 (2026-05-15)

- **Plotly 交互可视化**：走势图/热力图 HTML 双格式

## v2.3 (2026-05-15)

- **generate_predictions() 抽取共用**：backtest 复用，删除 35 行重复
- **回测奖金区分组三(346元)/组六(173元)**
- **data_fetcher 重写 v2**：增量保存、日志系统、--days 参数

## v2.2 (2026-05-15)

- **P0/P1/P2 代码审查修复**：README 参数补全、回测组选判断修复、数据检查退出保护等
- **工程化**：.gitkeep、.gitattributes(LF换行符)

## v2.0 (2026-05-15)

- **评分引擎重大升级**：YAML 权重可配置、多样性惩罚（组选去重+跨度多样化）
- **冷号补偿**：阈值 6→冷号占比更大
- **data_fetcher 数据自动获取**

## v1.0 (2026-05-14)

- **初始版本**：基础评分引擎、特征工程、回测
