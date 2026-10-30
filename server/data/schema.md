# POI 数据快照字段规范（schema.md）

> `server/data/` = 分城快照（`chengdu.json` 22 点 / `chongqing.json` 18 点）+ `meta.json`（词表/枢纽/城际）。
> `load_pois()` 遍历合并——**新增城市只需新增数据文件，不用改代码**。
> 字段不是随便堆的：每一个都直接参与规划/校验的某个决策，删掉任何一个，对应能力就退化。

## POI 字段

| 字段 | 类型 | 取值范围 | 为什么需要（决策依据） |
|---|---|---|---|
| `id` | str | 城市缩写-序号（CD-01 / CQ-01） | 全局唯一键；fix 事件的 `removed` 字段、前端地图高亮都靠它联动 |
| `name` | str | — | 展示与模糊匹配（对话改行程的"换掉文殊院"） |
| `city` | str | 成都 / 重庆 | 城市分天、分城投影（geo 契约按城市分组） |
| `lat` / `lng` | float | 真实经纬度 | haversine 距离 → leg_time 交通耗时 → 装箱容量 |
| `tags` | list[str] | 受控词表（见 meta.json tag_aliases 的值域） | 偏好命中打分 ×3，reason 里的"标签命中[...]" |
| `ticket` | int | 0=免费；>0 为票价（元） | V4 预算校验与 budget 工具核算 |
| `visit_hours` | float | 0.5–3.5 | 装箱容量消费的主体；V1 内容时长的组成 |
| `open_hour` | [float, float] | [0, 24] 小数制（18.5=18:30） | **V2 开放窗口校验**：到离时间须落在区间内；夜间收尾判断（≥18） |
| `reserve` | int | 0–3（0=免预约，3=一票难求） | 打分惩罚 ×0.8；reason 提示"预约难度" |
| `crowd_peak` | [float, float] | 高峰时段 | 预留：错峰排班的决策依据（当前用于提示，未参与硬约束） |
| `crowd_level` | int | 0–5 | **V3 强度软规则**的组成（slope + crowd×0.4 ≤ 8.5）+ 打分惩罚 ×0.4 |
| `slope` | int | 0–3 | **爬坡强度（重庆立体地形核心字段）**：V3 强度主体；装箱的轻度强度惩罚 |
| `family` | int | 0–5 | **V5 亲子硬规则**（family<2 亲子模式剔除）+ 亲子打分加成 |
| `night_friendly` | bool | — | 日内排序强制排最后（压轴体验）；摘点保护（最后摘）；夜景收尾叙事 |
| `must_see` | bool | — | 打分 +5；强度惩罚豁免；摘点保护（最后摘）；修复时不可删 |
| `summary` | str | 一句话 | 叙事段模板文案与行程卡展示 |

## meta.json 字段

| 字段 | 用途 |
|---|---|
| `version` | 数据层版本（当前 2.0.0：分城快照） |
| `cities` | 城市列表（分天分配、geo 分组的遍历依据） |
| `city_hub` | **城市枢纽坐标**（每城一个出发点，leg 计算/装箱/时间线的锚点）——数据文件化后新增城市不用改 planner |
| `tag_aliases` | 口语偏好 → 受控标签词表（"遛娃"→["亲子","动物"]） |
| `intercity_rail` | 城际铁路参数（"成都-重庆"→hours/price）——V1 跨城容量扣减与 budget 核算共用 |

## 不变量（改数据前必读）

1. **两把尺子必须同口径**：规划器 `_content_hours` 与校验器 V1 的 `content_hours` 都是
   `Σ(leg_hours + visit_hours)`（相邻跳，leg 从 city_hub 起算）。数据字段改动会影响两端。
2. **V3 阈值 8.5** 是按 `slope + crowd_level×0.4` 的量纲标定的；若新增点的 slope 普遍偏高，
   会在默认场景触发更多软提醒（是设计行为，不是 bug）。
3. `id` 不可复用不可改名——`fix` 事件 `removed`、前端 `data-poi`、revise 的匹配都以它为键。