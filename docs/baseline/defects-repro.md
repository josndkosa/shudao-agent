# ⚠️ 基线重跑说明：2026-10-29 01C（夜景收尾恢复+摘点排序键修正）后，baseline-*.{txt,json} 已再次重新生成；本文件仍为历史证据，不再覆盖。
# ⚠️ 基线重跑说明：2026-10-29 00:05 软硬分级+收敛检测+口径统一修复后，baseline-*.{txt,json} 已全部重新生成；本文件内容为历史证据，不再覆盖。

# 缺陷复现记录（defects-repro.md）

# 生成于 2026-10-28 23:45:00，命令：见各缺陷条目（D3 复现脚本全文内嵌）

## ⚠️ 执行时序声明（必读）

本文件是 **Prompt 00**（基线测量）的产物，但 **Prompt 01（缺陷修复）已于 2026-10-28 更早执行完毕**（同会话上一轮）。因此：

- **当前代码 = 修复后版本**：`python -m pytest -q` → 29 passed（原 17 + 修复回归 12）
- D1 / D2 / D4(1)(3) 在当前代码上**已无法复现**——下文逐条实测并注明「与预期不符（已修复）」
- **修复前的"先红"证据**完整保存于 `codearts_proof/debug-log-2026-10-28.md`（Prompt 01 产出），本文引用其原始输出
- D3 的 validator KeyError 与 D4(2) 的 reset_bus 未被调用**在当前代码上仍可实测复现**——见下文
- 若需要严格意义的"带缺陷代码基线"，`baseline-*.{txt,json}` 反映的是**修复后**状态，before/after 对照请以 debug-log-2026-10-28.md 的红基线（9 failed / 3 passed）+ 本文引用的修复前 CLI 输出为 before 侧

## D1：V1 时长规则跨城日误报（第 3 天）

**复现命令**：`python cli.py --days 3 --budget 3000 --tags 美食,文化`

**当前代码实测输出片段**（baseline-cli-3d.txt，修复后）：

```
 #017 [validate] ✗ [V3-intensity] 第3天
      └ 因为 强度 12.2 超过 8.5
 #019 [plan    ] ↻ 第3天强度超标，保留原行程
 ...
 Day 3 · 重庆
    10:21 ─ 湖广会馆 ¥30（1.0h，车乘 0.06h）
    13:00 ─ 磁器口古镇（3.0h，车乘 0.67h）
    16:39 ─ 洪崖洞（2.0h，车乘 0.65h）
    19:00 ─ 南山一棵树观景台 ¥30（1.5h，车乘 0.18h）
```

→ 第 3 天**无 V1-duration 违规**，磁器口（13:00–16:39）与湖广会馆（10:21–11:21）**均在行程中**。**与预期不符（该缺陷已修复）**。

**修复前原始输出（Prompt 01 先红记录，引自 codearts_proof/debug-log-2026-10-28.md）**——缺陷在修复前**属实**：

```
 #017 [validate] ✗ [V1-duration] 第3天
      └ 因为 日占用 13.8h 超过容量 11.0h
 #020 [plan    ] ↻ 第3天移除 磁器口古镇
      └ 因为 触发V1-duration：日占用 13.8h 超过容量 11.0h
 #021 [plan    ] ↻ 第3天移除 湖广会馆
      └ 因为 触发V3-intensity：强度 12.2 超过 8.5
```

修复前红测试 `test_v1_crosscity_no_false_positive`（构造跨城日内容 8.8h ≤ 容量 9.2h、收班 20:30）实测 FAIL，确认根因：旧 V1 把城际 1.8h 加进 `span` 却未在 `cap` 预留，阈值被压到 20:13，双重扣减致误报误删。

**结论：D1 误报属实（修复前）；磁器口与湖广会馆确实被误删（修复前）。当前已修复。**

## D2：days=1 生成 2 天行程

**复现命令**：`python cli.py --days 1 --budget 2000`

**当前代码实测输出片段**（baseline-cli-1d.txt，修复后）：

```
 #008 [plan    ] ◆ 城市分天：成都1天
 Day 1 · 成都
```

→ 恰好 1 天。**与预期不符（该缺陷已修复）**。

**修复前证据**：红测试 `test_days1_exactly_one_day` / `test_allocate_days_single_day_single_city` 实测 FAIL（旧 `_allocate_days` 的 `days <= 1` 分支给每城各分 1 天 → 输出 2 天）。根因与预期描述一致。

## D3：在线模式 KeyError: 'load'

**当前代码分两半验证：**

### (a) validator.validate() 本体 —— 仍可复现（属实）

validator.py 第 64 行 `d["load"]["tickets"]` 在 Prompt 01 中**未改动**（修复选择在 planner 归一化 + pipeline 兜底两侧）。临时脚本（≤10 行，无 key 场景直接构造无 load 假计划）：

```python
import sys, os
sys.path.insert(0, ".")
os.environ["SD_LLM_MODE"] = "offline"
from server.agent import TripRequest
from server.agent.validator import validate
plan = {"days": [{"day": 1, "city": "成都", "items": [
    {"type": "poi", "poi_id": "CD-01", "name": "宽窄巷子", "arrival": "09:00",
     "departure": "11:30", "visit_hours": 2.5, "ticket": 0, "leg_hours": 0.2, "tags": []}]}]}
try:
    vs = validate(plan, TripRequest(days=1, budget=99999))
    print("no exception, violations =", vs)
except KeyError as e:
    print(f"KeyError: {e!r}  <- validator.py 读取 d['load']['tickets'] 时抛出")
```

**实际运行输出**：

```
KeyError: KeyError('load')  <- validator.py 读取 d['load']['tickets'] 时抛出
```

→ **与预期一致：validator 对无 load 字段的计划确实抛 KeyError。**

### (b) 端到端路径 —— 已修复，不再冒出 CLI

当前代码两处防护使 KeyError 无法到达用户：

1. `planner._normalize_llm_plan`：LLM 返回 JSON 先归一化（补 load/丢弃非法 POI/days 空则整体降级离线），红→绿测试 `test_normalize_llm_plan_adds_load` 验证
2. `pipeline.run_pipeline` 校验段 try/except：异常 → 发 `validate/fallback` 事件并继续叙事段，测试 `test_pipeline_survives_validate_crash`（mock 校验抛 RuntimeError）实测通过

**结论：D3 根因定位属实（validator 缺兜底）；端到端路径已修复，仅 validator 本体行为保持（对非归一化输入仍抛 KeyError，属内部契约：入参必须是归一化后的计划）。**

## D4：静态检查三项

### (1) `for ... else: pass` 死代码（pipeline.py）

**当前实测**：`grep -n "else" server/agent/pipeline.py` 仅命中第 48 行（if/else 正常分支）与第 77 行（三元表达式），**无 for-else 结构**。→ **与预期不符（已删除）**。

### (2) `reset_bus()` 从未被调用

**当前实测**：`grep -rn "reset_bus" --include="*.py" server/ tests/ cli.py` 仅命中定义处 `server/agent/events.py:61`，**无任何调用方**。→ **与预期一致：仍属实。**

补充事实（Prompt 01 改造后）：`reset_bus()` 现在只重置进程时间基准 `_t0`；事件序号已改为 EventBus 实例属性（实例化即从 1 重置），因此该函数当前**无副作用、无必要性**，属于可留在将来的 API 面上的死接口——严重性远低于预期描述（原描述隐含 seq 全局累加问题，该问题已由实例化重置解决，测试 `test_eventbus_seq_resets_per_instance` 验证）。

### (3) `_day_load()` 漏算首段 leg

**当前实测**：`server/agent/planner.py:148` 签名为 `_day_load(day_pois, city, has_intercity=False)`，`prev` 从 `CITY_HUB[city]` 起算，首段 leg 已计入。→ **与预期不符（已修复）**。修复前红测试 `test_day_load_includes_first_leg` 实测 FAIL（hours=8.93 vs 期望 7.16+首段leg，差值即漏算的 1.77h）。

## 总结对账表

| 编号 | 预期 | 当前代码实测 | 修复前证据 | 状态 |
|---|---|---|---|---|
| D1 | 跨城日 V1 误报 + 误删两点 | 无误报，两点保留 | debug-log 红基线 + 修复前 CLI 输出 | **属实（已修复）** |
| D2 | days=1 输出 2 天 | 恰 1 天 | 红测试 FAIL 记录 | **属实（已修复）** |
| D3 | KeyError 冒出 CLI | validator 本体仍抛 KeyError；端到端已兜底 | (a) 本次实测复现 | **根因属实（端到端已修复）** |
| D4-1 | for-else:pass 死代码 | 已不存在 | — | 已修复 |
| D4-2 | reset_bus 未被调用 | 仍未被调用（无害死接口） | 本次 grep 实测 | **属实（严重性降级）** |
| D4-3 | _day_load 漏首段 leg | 已计入 | 红测试 FAIL 记录 | 已修复 |

## 附：D3 复现脚本与依赖采集脚本的说明

- D3 脚本全文见上文 (a) 节内嵌代码块，存于 `/tmp/d3_repro.py`，运行命令 `python -X utf8 /tmp/d3_repro.py`
- deps.md 的依赖数据来自 `/tmp/deps_collect.py`（pip freeze + importlib.metadata 递归解析）
- 本轮**未修改任何业务代码**（server/ 与 cli.py 零改动），仅新增 docs/baseline/ 目录下文件，未安装任何新包