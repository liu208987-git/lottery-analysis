## 2026-05-19 修复：Hermes Tirith 安全扫描器与 glibc 不兼容导致 cron 推送中断

### 问题

彩票 cron 预测推送（14:40）和复盘推送（21:35/22:05/23:10）全部失败，飞书收不到消息。

**根因：** `~/.hermes/bin/tirith` 安全扫描二进制需要 GLIBC_2.33/2.34，但 Alibaba Cloud Linux 8 服务器只有 glibc 2.32。Tirith 启动即崩溃，导致终端命令被安全审批系统拦截（"Security scan: security issue detected. Asking the user for approval."）。

cron 环境无用户在线审批，agent 尝试了所有变通方法（直接路径、环境变量、cat 读取等）均被拦截，最终输出 `[SILENT]` 跳过交付。

### 解决方案

将所有推送类 cron 任务改为 **`no_agent=true`** 模式——绕过整个 agent 审批链，脚本直接运行并输出到 stdout，Hermes cron 原样交付到飞书（通过 WebSocket 网关）。

变更内容：

1. **`~/.hermes/scripts/lottery_predict_push.sh`** — 新建，14:40 预测推送脚本
   - 运行 `hermes_push.py --mode predict --stdout`，输出预测内容
   - 落盘到 `output/push/predict_report.md` 供审计

2. **`~/.hermes/scripts/lottery_review_push.sh`** — 新建，复盘推送脚本（三波共用）
   - 先运行 `daily_review.py` 拉取开奖数据并对比
   - 再通过 `hermes_push.py --mode review --stdout` 输出复盘内容
   - 无数据时静默退出（无输出 = 不投递）

3. **Cron 任务配置变更：**

   | Job ID | 任务 | 旧模式 | 新模式 |
   |--------|------|:------:|:------:|
   | 04ad3b8a687c | 14:40 推送预测 | agent | **no_agent** |
   | 32f78be4c2b4 | 21:35 复盘+推送 | agent | **no_agent** |
   | 7e0692b3c25b | 22:05 补偿复盘 | agent | **no_agent** |
   | 16e85cd5f89c | 23:10 兜底复盘 | agent | **no_agent** |

### 优点

- ✅ 完全绕过 Tirith glibc 兼容性问题
- ✅ 不消耗 API token（无大模型调用）
- ✅ 链路最短：脚本 → stdout → 飞书
- ✅ 原有去重、落盘逻辑不变（在 hermes_push.py 内部）
- ✅ 无需升级系统 glibc（风险高）

### 关于 Linux crontab 替代方案的讨论

GPT 建议将 cron 任务从 Hermes  cron 改为 Linux crontab 直接执行：
```
0 15 * * * cd /path && python run_daily.py && python scripts/hermes_push.py --mode predict >> logs/predict_push.log 2>&1
30 22 * * * cd /path && python scripts/daily_review.py && python scripts/hermes_push.py --mode review >> logs/review_push.log 2>&1
```

**决定：不采纳。理由如下：**

1. **Hermes cron no_agent 已等效绕过审批链** — no_agent 模式让脚本直接运行并输出 stdout，由 Hermes cron 原样交付到飞书，完全没有安全审批拦截问题，与 crontab 的链路一样短。
2. **Hermes cron 的优势无法替代**：
   - 交付路由到飞书 WebSocket 网关（无需配置 webhook URL）
   - 内建去重和三波补偿策略（21:35/22:05/23:10）
   - 统一管理界面（`cronjob list/run/pause/resume`）
   - 不消耗 API token（无大模型调用）
3. **crontab 方案额外维护成本**：需要自己维护日志轮转、失败告警、去重状态。
4. `push_to_all_channels()` 的 `return results` 缩进正确（第 887 行，与 `save_push_state` 同级在 for 循环外），GPT 的缩进 bug 报告经实码确认属于误判。

综上，保持 Hermes cron no_agent 方案为最终方案。

### 同期仍为 agent 模式的任务

- 14:30 生成预测（`run_daily.py`）— 需要 agent 推理判断，正常执行
- 14:35 数据源健康（`source_health.py`）— 允许失败，不影响主链路
