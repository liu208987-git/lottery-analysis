# lottery-analysis 代码审查报告

> 审查时间：2026-05-15 | 审查范围：全部 10 个文件（~3000 行 Python）
> 修复已推送至分支：`code-review-fixes` | 第二轮(v2.6) / 第三轮(v2.6.1) 均已合入 main

---

## 一、发现与修复总结

| 优先级 | 数量 | 影响 |
|--------|:----:|------|
| P0 严重 | 4 | 回测结果失真、程序崩溃 |
| P1 高 | 8 | 标记失效、逻辑错误、静默数据损坏 |
| P2 中 | 8 | 性能、可维护性、代码整洁 |
| **合计** | **20** | |

---

## 二、P0 严重修复

### 2.1 回测未来信息泄露 — `scripts/backtest.py` L158-163

**问题**：Walk-forward 回测的排除集使用了目标期**之后**的期号数据。数据按期号降序排列（最新在前），原代码 `df.iloc[0:5]` 始终取全局最新的 5 期，其中包含了目标期之后才发生的数据。

**影响**：动态评分策略获得不公平优势，回测 ROI 虚高。

**修复**：
```diff
-        # 排除最近5期已出
+        # 排除目标期之前的最近5期（不是全局最新，避免未来信息泄露）
         exclude = set()
-        for j in range(min(5, i)):
-            if j < total:
-                prev = df.iloc[j]
+        for j in range(1, min(5, total - i - 1) + 1):
+            if i + j < total:
+                prev = df.iloc[i + j]
                 exclude.add((int(prev['红球1']), int(prev['红球2']), int(prev['红球3'])))
```

### 2.2 空 YAML 文件导致 AttributeError — `scripts/scoring_engine.py` L49

**问题**：`yaml.safe_load()` 在文件为空或仅含空白时返回 `None`，后续 `.get()` 调用触发 `AttributeError`。

**影响**：配置文件损坏时程序崩溃，无错误提示。

**修复**：
```diff
     if weight_path.exists():
         with open(weight_path, 'r', encoding='utf-8') as f:
-            cfg = yaml.safe_load(f)
+            cfg = yaml.safe_load(f) or {}
```

### 2.3 除零错误 — `scripts/scoring_engine.py` L153/L181

**问题**：理论分布字典中所有值均为零时，`max_freq` 为 0，触发 `ZeroDivisionError`。

**影响**：数据损坏时程序崩溃。

**修复** (两处: 和值评分 + 跨度评分)：
```diff
-    max_freq = max(theory_sum.values()) if theory_sum else 1
+    max_freq = max(theory_sum.values()) if theory_sum and max(theory_sum.values()) > 0 else 1

-    max_s = max(theory_span.values()) if theory_span else 1
+    max_s = max(theory_span.values()) if theory_span and max(theory_span.values()) > 0 else 1
```

### 2.4 流水线无错误传播 — `run_daily.py` L31-91

**问题**：`run_cmd` 无返回值，各步骤失败后继续执行后续步骤。若特征工程失败，统计引擎会使用过期数据运行。

**影响**：数据损坏时静默产生错误预测结果。

**修复**：
```diff
-def run_cmd(cmd, desc, timeout=300):
-    """执行 shell 命令并记录日志"""
+def run_cmd(cmd, desc, timeout=300):
+    """执行命令并记录日志，返回是否成功"""
     ...
         if result.returncode == 0:
             ...
+            return True
         else:
             ...
+            return False
     except subprocess.TimeoutExpired:
         ...
+        return False
     except Exception as e:
         ...
+        return False
```

各关键步骤增加 `if not run_cmd(...): return` 守卫。

---

## 三、P1 高优先级修复

### 3.1 `except Exception` 吞掉 KeyboardInterrupt — `scripts/data_fetcher.py` L76/L155

**问题**：`except Exception` 捕获了 `KeyboardInterrupt` 和 `SystemExit`，用户按 Ctrl+C 无法中断程序。

**影响**：程序无响应，只能强制杀进程。

**修复**：
```diff
-    except Exception as e:
+    except requests.exceptions.RequestException as e:
         logger.error("排列三API请求失败: {}".format(e))
         return []
+    except (ValueError, KeyError) as e:
+        logger.error("排列三数据解析失败: {}".format(e))
+        return []

-        except Exception as e:
+        except (requests.exceptions.RequestException, ValueError) as e:
```

### 3.2 HTTP 明文请求 — `scripts/data_fetcher.py` L116

**问题**：zhcw.com 使用 HTTP 明文协议。

**修复**：
```diff
-        url = "http://kaijiang.zhcw.com/zhcw/html/3d/list_{}.html".format(page)
+        url = "https://kaijiang.zhcw.com/zhcw/html/3d/list_{}.html".format(page)
```

### 3.3 空 `lotteryDrawResult` 产生假号码 `000` — `scripts/data_fetcher.py` L82-83

**问题**：API 返回空 `lotteryDrawResult` 时，`''.join([])` 得空字符串，经 `zfill(3)` 变为 `"000"` 存入数据。

**影响**：静默产生错误历史数据。

**修复**：
```diff
         nums = item['lotteryDrawResult'].split()
+        if len(nums) < 3:
+            logger.warning("排列三: 期号{} 号码格式异常: {}".format(
+                item['lotteryDrawNum'], item['lotteryDrawResult']))
+            continue
         results.append({...})
```

### 3.4 `--no-baozi`/`--no-extreme` 标记完全无效 — `scripts/filter_engine.py` L46-49

**问题**：`action='store_true'` 配合 `default=True`，无论用户是否指定标记，值永远为 `True`。无法关闭排除。

**修复**：
```diff
-    parser.add_argument('--no-baozi', action='store_true', default=True,
-                        help='排除豹子')
-    parser.add_argument('--no-extreme', action='store_true', default=True,
-                        help='排除极端和值')
+    parser.add_argument('--no-baozi', action='store_false', dest='exclude_baozi',
+                        help='包含豹子（默认排除）')
+    parser.add_argument('--no-extreme', action='store_false', dest='exclude_extreme',
+                        help='包含极端和值（默认排除）')
```

### 3.5 权重文件路径处理 — `scripts/scoring_engine.py` L45

**问题**：`base / weight_path` 在 `weight_path` 为绝对路径时产生错误结果（`Path('/a/b') / '/c/d'` = `/c/d`，会丢失 base）。

**修复**：
```diff
     else:
-        weight_path = base / weight_path
+        p = Path(weight_path)
+        weight_path = p if p.is_absolute() else base / p
```

### 3.6 断期检测误报 — `scripts/feature_engine.py` L55-64

**问题**：原代码用 `issues[i-1] % 1000 > 990` 判断年底，仅跳过最后 10 期。但期号格式为 YYDDD，年最大约 358 期。正常的跨年过渡 `25358→26001` 会被误报，因为 `25358 % 1000 = 358` 不 > 990。

**修复**：
```diff
-                # 处理跨年（如 26104 → 26105 正常，26135 → 27001 跨年）
-                if issues[i-1] % 1000 > 990:  # 接近年底
+                # 处理跨年（期号格式 YYDDD：如 25358→26001，差≫1）
+                if issues[i] - issues[i-1] > 100:
                     continue
```

同时移除了死代码 `expected_next`（两个分支逻辑相同，变量无用）。

### 3.7 可视化被静默跳过 — `run_daily.py` L101-107

**问题**：`charts_dir` 首次运行时不存在，但代码只在目录存在时才进入可视化分支。同时 `mkdir` 未执行。

**修复**：
```diff
     charts_dir = BASE / 'output' / 'charts'
-    if charts_dir.exists():
-        try:
-            import matplotlib
-            ...
-        except ImportError:
-            ...
+    charts_dir.mkdir(parents=True, exist_ok=True)
+    try:
+        import matplotlib
+        ...
+    except ImportError:
+        ...
```

---

## 四、P2 中等修复

### 4.1 权重总和注释错误 — `rules/scoring_weights.yaml` L2

```diff
-# 各维度权重总和 = 100
+# 各维度权重总和 = 103（非100，各维度独立评分）
```

### 4.2 奇偶/大小评分硬编码 — `scripts/scoring_engine.py` L222-229

**问题**：非均衡组合固定给 2 分，不受 YAML 权重控制。若用户将权重设为 0（意图禁用该维度），反而均衡组合得 0 分、非均衡得 2 分。

**修复**：
```diff
-    odd_score = W['奇偶'] if 1 <= odd <= 2 else 2
+    odd_score = W['奇偶'] if 1 <= odd <= 2 else max(1, W['奇偶'] // 4)

-    big_score = W['大小'] if 1 <= big <= 2 else 2
+    big_score = W['大小'] if 1 <= big <= 2 else max(1, W['大小'] // 4)
```

### 4.3 组选排除 O(n×m) 优化 — `scripts/scoring_engine.py` L392-394

**问题**：每次组选排除对 `exclude_set` 做遍历 + 排序，复杂度 O(1000×5×log3)。

**修复**：预计算 `group_exclude` 集合，O(1) 查找：
```diff
+    # 预计算组选排除集合（O(1) 查找）
+    group_exclude = set()
+    if exclude_mode == 'group':
+        for e in exclude_set:
+            group_exclude.add(''.join(str(d) for d in sorted(e)))
+
     ...
         elif exclude_mode == 'group':
-            gn = row['group_number']
-            if any(sorted(nums) == sorted(e) for e in exclude_set):
+            if row['group_number'] in group_exclude:
                 continue
```

### 4.4 移除未使用参数 — `scripts/scoring_engine.py` L419

```diff
-def _add_reason(rank, c, exclude_recent, exclude_mode, include_baozi):
+def _add_reason(rank, c):
```

### 4.5 移除未使用导入

- `scripts/stats_engine.py` L16：移除 `from itertools import product`
- `scripts/backtest.py` L26：移除 `score_number` 导入
- `scripts/backtest.py` L135：移除重复的 `import json as _json`

### 4.6 回测 off-by-one — `scripts/backtest.py` L106-107

```diff
-    if test_periods > total - train_window - 1:
-        test_periods = total - train_window - 1
+    if test_periods > total - train_window:
+        test_periods = max(0, total - train_window)
```

原码多减去 1 期，且 `total < train_window` 时会产生负值。

---

## 五、已知未修复项（v2.6.1 状态更新）

| 问题 | 说明 | 状态 |
|------|------|:----:|
| `feature_engine.py` 遗漏计算伪"向量化" | 实际为 Python for 循环，需完全重写为真正的向量化实现 | 待修 |
| `backtest.py` 缺少参数范围验证 | ~~`--top-k` 传入 0 或负数无警告~~ | ✅ v2.6.1 已修复 |
| `backtest.py` 多注中奖漏算 | ~~`if/elif` 结构在多个预测命中时不累加~~ | ✅ v2.6.1 已修复 |
| `stats_engine.py` 空 DataFrame 无防护 | `iloc[0]` 在 0 行数据时抛 IndexError | 待修 |
| `run_daily.py` `shell=True` | ~~使用字符串命令而非列表参数~~ | ✅ v2.6 已修复 |
| `data_fetcher.py` 竞态条件 | 文件读写之间无锁，并发执行可能丢数据 | 待修 |
| `scoring_engine.py` 形态回归惩罚缺失 | ~~组三过热时形态评分只奖不惩~~ | ✅ v2.6.1 已修复 |
| `data_fetcher.py` API 567 无重试 | ~~限频直接失败返回空~~ | ✅ v2.6.1 已修复 |
| `visualize.py` PNG 中文乱码 | ~~无中文字体配置~~ | ✅ v2.6.1 已修复 |

---

## 六、变更文件清单

| 文件 | 变更类型 |
|------|----------|
| `run_daily.py` | 流水线错误传播 + 可视化目录创建 |
| `scripts/backtest.py` | 未来信息泄露修复 + off-by-one + 清理导入 |
| `scripts/data_fetcher.py` | 异常处理精确化 + HTTPS + 空数据校验 |
| `scripts/feature_engine.py` | 跨年断期误报修复 + 死代码移除 |
| `scripts/filter_engine.py` | CLI 标记修复 |
| `scripts/scoring_engine.py` | YAML 崩溃修复 + 除零修复 + 路径修复 + 评分一致性 + 性能优化 + 清理 |
| `scripts/stats_engine.py` | 未使用导入移除 |
| `rules/scoring_weights.yaml` | 注释修正 |

---

> 推送分支: [`code-review-fixes`](https://github.com/liu208987-git/lottery-analysis/tree/code-review-fixes)
