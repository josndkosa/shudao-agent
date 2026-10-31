# POI 数据快照字段规范（schema.md）

> 数据层 v3（03E 批次1）：**西南 15 城总表**（`meta.json` city_info）+ 批次1 落地 6 城快照
> （`chengdu.json` 22 / `chongqing.json` 18 / `kunming.json` 15 / `dali.json` 15 / `guiyang.json` 15 / `guilin.json` 16，共 101 点）。
> `load_pois()` 遍历合并——**新增城市只需新增数据文件，不用改代码**；15 城总表先行配齐（含地形分档/天气/枢纽），
> 广度层 9 城 POI 随批次2/3 补充。
> 字段不是随便堆的：每一个都直接参与规划/校验的某个决策，删掉任何一个，对应能力就退化。

## POI 字段

| 字段 | 类型 | 取值范围 | 为什么需要（决策依据） |
|---|---|---|---|
| `id` | str | 城市缩写-序号（CD-01 / CQ-01 / KM-01 / DL-01 / GY-01 / GL-01） | 全局唯一键；fix 事件的 `removed` 字段、前端地图高亮都靠它联动 |
| `name` | str | — | 展示与模糊匹配（对话改行程的"换掉文殊院"） |
| `city` | str | meta.json cities 值域 | 城市分天、分城投影（geo 契约按城市分组） |
| `lat` / `lng` | float | 真实经纬度 | haversine 距离 → leg_time 交通耗时 → 装箱容量；城际自动生成的输入 |
| `tags` | list[str] | 受控词表（见 meta.json tag_aliases 的值域，含西南扩展：山水/喀斯特/湖泊/海滨/民族/雪山/梯田/溶洞/夜市/佛教/摄影/骑行） | 偏好命中打分 ×3，reason 里的"标签命中[...]" |
| `ticket` | int | 0=免费；>0 为票价（元） | V4 预算校验与 budget 工具核算 |
| `visit_hours` | float | 0.5–3.5 | 装箱容量消费的主体；V1 内容时长的组成 |
| `open_hour` | [float, float] | [0, 24] 小数制（18.5=18:30） | **V2 开放窗口校验**：到离时间须落在区间内；夜间收尾判断（≥18） |
| `reserve` | int | 0–3（0=免预约，3=一票难求） | 打分惩罚 ×0.8；reason 提示"预约难度" |
| `crowd_peak` | [float, float] | 高峰时段 | 预留：错峰排班的决策依据（当前用于提示，未参与硬约束） |
| `crowd_level` | int | 0–5 | **V3 强度软规则**的组成（slope + crowd×0.4 ≤ 城市地形 cap）+ 打分惩罚 ×0.4 |
| `slope` | int | 0–3 | **爬坡强度（西南立体地形核心字段）**：V3 强度主体；装箱的轻度强度惩罚 |
| `family` | int | 0–5 | **V5 亲子硬规则**（family<2 亲子模式剔除）+ 亲子打分加成 |
| `night_friendly` | bool | — | 日内排序强制排最后（压轴体验）；摘点保护（最后摘）；夜景收尾叙事 |
| `must_see` | bool | — | 打分 +5；强度惩罚豁免；摘点保护（最后摘）；修复时不可删 |
| `summary` | str | 一句话 | 叙事段模板文案与行程卡展示 |

## meta.json 字段

| 字段 | 用途 |
|---|---|
| `version` | 数据层版本（当前 3.0.0：西南 15 城总表） |
| `cities` | 城市列表（深度层 6 城在前；geo 分组与自动选城的顺序依据） |
| `city_info` | **城市总表**：slug / province / priority / note / line（图幅注记行）/ weather（11 月快照）/ **terrain** |
| `city_info[].terrain` | **地形分档**：type（plain/basin/hill/karst/plateau/alpine/tropical）+ intensity_cap + alt_m——V3 阈值按此取 |
| `city_hub` | **城市枢纽坐标**（每城一个出发点，leg 计算/装箱/时间线的锚点；城际自动生成的距离输入） |
| `tag_aliases` | 口语偏好 → 受控标签词表（含西南扩展：山水/看海/民族/雪山/梯田/溶洞/夜市/寺庙 等） |
| `intercity_rail` | 城际铁路**人工覆盖表**（"成都-重庆"→hours/price/km/label）——优先于自动生成 |

## 地形分档（03E 核心产出）

同样的"强度 8.5"，在成都盆地只是多走路，在昆明 1891m 高原与拉萨 3650m 高原完全是另一回事：

| terrain | 典型城市 | intensity_cap | 依据 |
|---|---|---|---|
| basin | 成都、阆中 | 8.5 | 盆地平原，基准 |
| plain | 北海 | 8.5 | 平原 |
| hill | 重庆、大理、乐山 | 8.0 | 丘陵/山城坡度偏高 |
| karst | 贵阳、桂林、安顺、西江千户苗寨 | 7.5 | 喀斯特连续爬升 |
| plateau | 昆明、丽江 | 7.0 | 高原氧耗与体感负担更高 |
| alpine | 拉萨 | 6.0 | 极高海拔（3650m） |
| tropical | 三亚、西双版纳 | 8.0 | 湿热体力消耗快 |

**设计取舍（哪些参数化、哪些不）**：V1 时长 / V2 开放窗口 / V4 预算 / V5 亲子**不随地形变化**
（时刻表与钱包不分海拔）；只有 V3 强度按地形分档——这是"按地形自适应"的规则参数化落地，
`validator._TERRAIN_CAP` 从 meta 读取，无配置城市回落默认 8.5（旧行为兜底）。

## 城际交通（自动生成 + 人工覆盖）

`route.intercity(city_a, city_b)`：
1. **人工覆盖表优先**（`intercity_rail`，如 成都-重庆 1.8h / ¥154 / 成渝高铁——与历史基线逐字一致）
2. 其余 105 对按**两城枢纽球面距离**自动生成：
   - `hours = clamp(1.2 + d×绕行系数/250, 1.2, 14.0)`，进藏城对绕行系数 2.0（直线 ~1250km、铁路实际 ~2500km），跨省进桂/琼/藏再 ×1.25
   - `price = round(clamp(d×0.48, 60, 2200) / 10) × 10`（按直线距离，贴近真实票价档）
   - 自动生成的 label 为 `"{A}→{B} 列车"`

## 不变量（改数据前必读）

1. **两把尺子必须同口径**：规划器 `_content_hours` 与校验器 V1 的 `content_hours` 都是
   `Σ(leg_hours + visit_hours)`（相邻跳，leg 从 city_hub 起算）。数据字段改动会影响两端。
2. **V3 阈值按城市地形分档**（`terrain.intensity_cap`），量纲仍是 `slope + crowd_level×0.4`；
   若新增点的 slope 普遍偏高，会在该城 cap 下触发更多软提醒（是设计行为，不是 bug）。
3. `id` 不可复用不可改名——`fix` 事件 `removed`、前端 `data-poi`、revise 的匹配都以它为键。
4. **跨城日容量扣减用实际城际时长**（planner `_ic_leg` / validator `_ic_hours` 从行程的 intercity
   条目推导），不再假设 1.8h；成都-重庆 经覆盖表仍为 1.8h，双城行为与历史一致。
5. **城际票价按行程序列累计**（`route.intercity_cost`）：相邻异城各计一段，多城多段如实入账。