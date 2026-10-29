# 最终提交包（zip）结构、命名与自检

> 赛题原文：
> 所有参赛作品需打包为 zip 压缩包提交，**命名规范：作品名称+队伍名称+版本号+联系方式**，压缩包内**必须包含**以下 5 部分内容：
> `ppt/` `project/` `video/` `codearts_proof/` `readme/`
> 提交次数：每支队伍**每天最多 1 次**提交机会，最终成绩取**最近的一次**提交版本。

---

## 一、zip 内部结构

```
蜀道智行_<队伍名>_v1.0_<姓名>_<手机号>.zip
├── ppt/                       ← 作品整体介绍 PPT 或 PDF
│   ├── 蜀道智行.pptx
│   ├── 蜀道智行.pdf              （若能导出则放，赛题允许 PPT 或 PDF，PDF 兜底更保险）
│   ├── 讲稿.md
│   └── 视频分镜.md
├── project/                   ← 可演示完整功能的 Demo
│   ├── README.md                （快速上手；完整文档在 readme/）
│   ├── cli.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── server/
│   │   ├── __init__.py
│   │   ├── agent/{pipeline,planner,validator,narrator,llm,events}.py
│   │   ├── tools/{poi_search,route,weather,budget,geo,obs}.py
│   │   └── data/pois.json
│   ├── static/
│   │   ├── index.html
│   │   ├── app.js  (或 js/*.js)
│   │   ├── style.css
│   │   └── demo.json             （真实运行产物的离线兜底）
│   ├── scripts/
│   │   ├── install.sh / install.bat
│   │   ├── start_server.sh / start_server.bat
│   │   └── demo_offline.sh / demo_offline.bat
│   ├── tests/
│   │   └── test_*.py
│   └── requirements-dev.txt      （python-pptx 等文档工具，不影响运行）
├── video/                     ← 功能演示视频，≤ 3 分钟
│   ├── 蜀道智行-演示视频.mp4
│   └── 视频分镜.md              （副本，便于评委对照）
├── codearts_proof/             ← 华为云码道使用证明材料
│   ├── prompts/                 ← ★ 码道交互的原始素材（25 分「Prompt 设计质量」的正面证据）
│   │   ├── 04_大项目化_工程正规化与文档体系.md
│   │   ├── 05_PPT与视频分镜_走码道Space模式.md
│   │   └── _已执行/             ← 已执行过的 prompt 原文，**必须一并提交**
│   │       ├── 00_基线自检与素材一次性产出.md
│   │       ├── 01_修复W1缺陷_P0.md
│   │       ├── 01B_收敛检测_规则软硬分级_leg口径统一.md
│   │       ├── 01C_恢复夜景收尾_修正摘点排序键.md
│   │       ├── 02_W2后端_FastAPI_SSE_对话改行程.md
│   │       ├── 03_W2前端_单页SVG路线图_可倒带时间轴.md
│   │       ├── 03B_前端改进_修复可视化补齐.md
│   │       ├── 03C_P0前端运行时ReferenceError修复.md
│   │       └── 03D_前端视觉升级_测绘图鉴风格.md
│   ├── debug-log-2026-10-28.md   ← ★ 完整调试排错过程记录（六轮，含"工程反思"）
│   ├── ACCEPTANCE.md
│   ├── 回贴模板.md
│   ├── README.md
│   ├── zip-layout.md
│   ├── 01-环境搭建与工程初始化/     ← 截图 + 说明
│   ├── 02-代码生成-三段式管线/       ← 对话与 prompt 截图
│   ├── 03-代码生成-前端可视化/       ← 对话与 prompt 截图
│   ├── 04-调试排错-跨城日时长规则误报/  ← ★ 真实排错过程记录
│   ├── 05-文档生成-PPT与readme/      ← Space 模式生成过程
│   └── 06-一键安装与部署验证/         ← 脚本运行输出截图
└── readme/                    ← 作品说明文档
    ├── README.md                （环境依赖+一键安装 / 部署步骤 / 开源组件 / 码道应用总结）
    ├── 团队分工.md               （空模板，由参赛者手填）
    └── CHANGELOG.md
```

### 关键映射

| 仓库位置 | zip 位置 |
|---|---|
| `D:\项目代码\shudao-agent\`（除 `codearts_proof/` 外全部） | `project/` |
| `D:\项目代码\shudao-agent\codearts_proof\` | `codearts_proof/` |
| `D:\项目代码\shudao-agent\readme\` | `readme/` |
| `D:\项目代码\shudao-agent\ppt\` | `ppt/` |
| `D:\项目代码\shudao-agent\video\` | `video/` |

**不要**把 `.venv/`、`__pycache__/`、`.pytest_cache/`、`.env`（含真实 key）打进包里。
**`.env.example` 要打进去，`.env` 绝对不要。**

---

## 二、命名

```
蜀道智行_<队伍名>_v1.0_<姓名>_<手机号>.zip
例：蜀道智行_成渝智行队_v1.0_张三_13800138000.zip
```

- 队伍名必须与**报名时填写的队伍名称完全一致**（报名后不可改）
- 每天提交一次时把版本号递增：`v1.0` → `v1.1` → `v1.2`…（同名重复上传可能覆盖，取最后一次）
- 联系方式填**能联系到你的手机号**

---

## 三、组装脚本

放在 `scripts/package.sh`（Windows 用 `package.bat`）：

```bash
#!/usr/bin/env bash
set -euo pipefail
# 1. 参数：队伍名 姓名 手机号 [版本号]（版本号默认 v1.0）
# 2. 在项目根建 staging/ 临时目录
# 3. 拷贝上述映射（rsync/cp，排除 __pycache__ .pytest_cache .venv .env *.pyc .git）
# 4. 打印 zip 内部树（tree 或 find）供人工核对
# 5. 生成 zip 文件名：蜀道智行_${TEAM}_${VER}_${NAME}_${PHONE}.zip
# 6. 打印 zip 大小与 sha256
# 7. 退出前自检：
#    - 五个必需目录都存在且非空
#    - video/ 里有一个 .mp4 且体积 < 200MB
#    - codearts_proof/ 里截图数量 >= 8
#    - grep 确认包里没有 .env、没有 __pycache__
#    任一不满足 → 非零退出，不产出 zip
```

**打包前必须手动确认：**
- [ ] `.env` 未进包（`unzip -l xxx.zip | grep -c "\.env$"` 应只匹配到 `.env.example`）
- [ ] `codearts_proof/` 截图数量足够（≥ 8 张，覆盖环境搭建/代码生成/调试排错/文档生成四类）
- [ ] `video/` 成片 ≤ 3 分钟且能正常播放（**在另一台机器上试播一次**）
- [ ] `ppt/` 能正常打开（字体不乱码）
- [ ] `project/` 在**全新机器**上按 `readme/` 步骤能跑起来

---

## 四、提交操作（每天最多 1 次）

1. 大赛官网作品提交入口 → 上传 zip → 查看提交状态
2. 每次提交前跑一遍上面的手动确认清单
3. 提交后**截图存档提交状态**（放进 `codearts_proof/07-提交记录/`）
4. 建议节奏：
   - 11/10 第一次提交（此时应有完整可演示版本）
   - 11/11–11/15 每天一次微调提交
   - **11/15 或 11/16 上午做最后一次**（不要压 11/16 当天，官网拥堵/上传失败无重试机会）

---

## 五、答辩（11/21–11/27）另行准备

赛题原文：「完善版作品安装包/**在线演示地址**，确保现场可稳定运行」「未上线答辩，视为放弃参赛资格」。

- 11/10 前完成云上部署（华为云 ECS / CodeArts 流水线 → 拉取 `project/` → venv → uvicorn → 安全组放行 8000）
- 同时保留本地一键启动方案作为备份
- 答辩 PPT 另存一份到本地与 U 盘
- 演示时**先跑本地 demo.json 兜底**，确认无误后再切真实服务
