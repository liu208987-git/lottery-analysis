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

### 备注

- `hermes_push.py` 中 `push_to_all_channels()` 的 `return results` 缩进正确（在 for 循环外），GPT 的缩进 bug 报告为误判。
- 14:30 生成预测（`run_daily.py`）和 14:35 数据源健康（`source_health.py`）仍为 agent 模式——前者需要推理判断（正常执行），后者允许失败。
