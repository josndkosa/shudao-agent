# 03 · 代码生成（前端可视化）

> 拍摄于 2026-11-01，华为云码道 CodeArts IDE（人工逐张截图留存）。

| 文件 | 内容 | 对应证明点 |
|---|---|---|
| `01-export脚本生成演示资产并确认结构.png` | `export_demo_assets.py` +78 行 → 运行 export 脚本生成演示资产 → 确认导出数据结构供前端消费（并发现 mock 的 `demo.json` 默认场景已无 violation/fix 事件，需另存 `demo-revised.json`） | 前端离线兜底数据是**真实运行产物**，且结构被显式核对 |
| `02-前端多城化-动态图幅与城市多选.png` | `map.js` +1 −1、`main.js` +38 −1、`index.html` +8 −14、`api.js` Mock 层解析 `_city_meta`、`style.css` 加 flex 栏 | 多城图幅由行程驱动动态渲染 |
| `03-前端直觉性优化-发现两个真bug.png` | 「优化一下前端页面使之更符合直觉效果」→ 码道加载 frontend-design skill 后自查，发现两个真问题：① `timeline.js:4` 前端硬编码 `LOAD_CAP_INTENSITY = 8.5` 与地形分档脱节 ② 勾选 4 城但只给 2 天时 `_allocate_days` 产生负天数 → 修 planner.py +5 → 补回归测试 | **"直觉性优化"变成了 bug 挖掘**，而不是单纯改样式 |

## 尚未覆盖（如实申报）

- 视觉重构三轮（03D 测绘图鉴 → 03F 瑞士网格）的原始对话未逐帧留存；
  其结果由 `git log`（commit `2c94ff9` / `115abc7`）与 `debug-log` 第七/八轮记录佐证。
- **方向性返工的完整对话未留存**：视觉方向两次被人工评审否决后重做（03D→03F），
  该事实记录在 `docs/开发历程.md` 与 `readme/README.md` §4.4。
