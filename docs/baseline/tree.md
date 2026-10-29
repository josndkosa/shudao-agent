# 生成于 2026-10-28 23:39:21，命令：python /tmp/tree_gen.py（Python os.walk 遍历，排除 __pycache__/.pytest_cache/.venv）
├── codearts_proof  # 码道留痕：AI 开发过程证据（debug-log 等），评分项 25 分素材
│   ├── prompts
│   │   ├── 00_基线自检与素材一次性产出.md
│   │   ├── 01_修复W1缺陷_P0.md
│   │   ├── 02_W2后端_FastAPI_SSE_对话改行程.md
│   │   ├── 03_W2前端_单页SVG路线图_可倒带时间轴.md
│   │   ├── 04_readme_一键安装_工程整理.md
│   │   └── 05_PPT与视频分镜_走码道Space模式.md
│   ├── .gitkeep
│   ├── ACCEPTANCE.md
│   ├── README.md
│   ├── debug-log-2026-10-28.md
│   ├── zip-layout.md
│   └── 回贴模板.md
├── docs  # 文档：基线测量与后续设计文档
│   └── baseline  # Prompt 00 基线产物（本目录）：修复后代码的真实运行基线
│       ├── baseline-cli-1d.txt
│       ├── baseline-cli-3d.txt
│       ├── baseline-cli-family.txt
│       ├── baseline-demo.json
│       └── baseline-tests.txt
├── server  # 后端包根
│   ├── agent  # 三段式管线：planner 规划 / validator 校验 / narrator 叙事 / pipeline 编排 / llm 客户端 / events 事件流
│   │   ├── __init__.py
│   │   ├── events.py
│   │   ├── llm.py
│   │   ├── narrator.py
│   │   ├── pipeline.py
│   │   ├── planner.py
│   │   └── validator.py
│   ├── data  # POI 本地快照（40 点厚字段，禁止改动）
│   │   └── pois.json
│   ├── tools  # 工具层：poi_search 检索打分 / route 交通 / weather 天气快照 / budget 预算 / geo 投影
│   │   ├── __init__.py
│   │   ├── budget.py
│   │   ├── geo.py
│   │   ├── poi_search.py
│   │   ├── route.py
│   │   └── weather.py
│   └── __init__.py
├── tests  # pytest 测试：geo / tools / validator / pipeline / fixes（缺陷回归）
│   ├── test_fixes.py
│   ├── test_geo.py
│   ├── test_pipeline.py
│   ├── test_tools.py
│   └── test_validator.py
├── .env.example
├── README.md
├── cli.py
└── requirements.txt
