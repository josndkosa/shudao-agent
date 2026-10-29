# 依赖清单（deps.md）

# 生成于 2026-10-28 23:40:00，命令：pip freeze + importlib.metadata 递归解析（/tmp/deps_collect.py，脚本全文见本目录 defects-repro.md 附录说明，无新增安装）

## 采集方式

- 直接依赖以 `requirements.txt` 为准，用 `importlib.metadata` 递归解析 `Requires-Dist` 得到间接依赖闭包
- 许可证逐包读 `importlib.metadata.metadata(pkg)["License"]`，缺失时回退 `Classifier: License ::`，均无则记「未在元数据中声明」
- 环境为全局 Anaconda（`pip freeze` 共 535 项，大部分与本项目无关，不在此罗列）

## 直接依赖（requirements.txt）

| 包名 | 版本 | 许可证 | 在本项目中的用途 |
|---|---|---|---|
| fastapi | 0.136.3 | 未在元数据中声明 | W2 后端 API 服务（SSE 事件推送），CLI 离线模式不依赖 |
| uvicorn | 0.49.0 | 未在元数据中声明 | FastAPI 的 ASGI 服务器（W2 启动用） |
| pydantic | 2.13.5 | 未在元数据中声明 | FastAPI 请求/响应模型校验 |
| openai | 2.38.0 | Apache-2.0 | 在线模式访问 DeepSeek（OpenAI 兼容 FC），CLI 离线模式不依赖 |
| pytest | 9.1.1 | 未在元数据中声明 | 单元测试（29 个用例） |

**注意：CLI（`python cli.py`）离线模式仅使用 Python 标准库**（json / itertools / dataclasses / argparse / math），以上依赖只在 W2 API 服务、在线 LLM 模式与测试时需要——这是「断网演示保命」设计的一部分。

## 间接依赖（闭包）

| 包名 | 版本 | 许可证 | 用途 |
|---|---|---|---|
| starlette | 1.2.1 | 未在元数据中声明 | fastapi 底层 ASGI 框架 |
| typing-extensions | 4.16.0 | 未在元数据中声明 | 类型标注兼容 |
| typing-inspection | 0.4.2 | 未在元数据中声明 | pydantic 运行时类型检查 |
| annotated-doc | 0.0.4 | 未在元数据中声明 | pydantic 注解文档 |
| click | 8.4.1 | 未在元数据中声明 | uvicorn 命令行接口 |
| h11 | 0.16.0 | MIT | uvicorn HTTP/1.1 实现 |
| pydantic-core | 2.46.5 | 未在元数据中声明 | pydantic Rust 核心 |
| annotated-types | 0.6.0 | MIT License | pydantic 注解类型 |
| anyio | 4.15.1 | 未在元数据中声明 | starlette 异步工具（依赖 sniffio/idna） |
| distro | 1.9.0 | Apache License, Version 2.0 | openai 系统信息探测 |
| httpx | 0.28.1 | BSD License | openai HTTP 客户端 |
| jiter | 0.15.0 | 未在元数据中声明 | openai JSON 高性能解析 |
| sniffio | 1.3.1 | MIT OR Apache-2.0 | anyio 异步检测 |
| tqdm | 4.67.1 | MPL-2.0 AND MIT | openai 进度条 |
| colorama | 0.4.6 | BSD License | Windows 终端着色 |
| iniconfig | 1.1.1 | MIT License | pytest 配置解析 |
| packaging | 25.0 | Apache Software License | pytest 版本解析 |
| pluggy | 1.5.0 | MIT | pytest 插件机制 |
| pygments | 2.19.1 | BSD-2-Clause | pytest 输出高亮 |
| tomli | 2.0.1 | MIT License | pytest TOML 配置读取 |
| idna | 3.20 | 未在元数据中声明 | httpx 国际化域名 |
| certifi | 2026.4.22 | MPL-2.0 | httpx CA 证书 |
| httpcore | 1.0.9 | BSD License | httpx 传输层 |

未安装的声明依赖：`exceptiongroup`（仅 Python<3.11 需要，本机 3.13 不适用，pytest 声明为条件依赖）。

## 本项目未使用的外部技术（郑重声明）

本项目**零外部前端资源**：

- 未使用任何前端框架（无 Vue / React / GSAP，当前为纯 CLI 阶段，W2 前端为原生 SVG + 原生 JS）
- 未使用任何构建工具（无 Node / npm / Vite / webpack）
- 未使用任何 CDN 外链（无外部字体、图标、脚本引用）
- 未使用任何外部地图服务（无高德/百度/Google Maps；`server/tools/geo.py` 自带经纬度→SVG 画布投影 `Projector`，`server/tools/weather.py` 为本地快照）
- 未使用任何外部数据库（数据为 `server/data/pois.json` 本地文件）

以上约束目的：答辩现场断网 100% 可演示。

## 文档工具依赖说明（不属于运行依赖）

`python-docx`（1.2.0，MIT）与 `python-pptx`（1.2.0，MIT）在全局环境中已安装，**但它们是 W3 阶段生成 Word/PPT 交付物（评分要求 ppt/）的工具，不属于本项目运行依赖，不得写入 `requirements.txt`**——运行时（FastAPI + CLI）完全不 import 它们。

## 附：运行时导入关系实测

```
python -c "import cli"           # 仅标准库 + server 包（离线模式零第三方依赖）
SD_LLM_MODE=online 时额外引入:   # openai（延迟导入，见 server/agent/llm.py chat()）
W2 启动时额外引入:               # fastapi / uvicorn / pydantic
```