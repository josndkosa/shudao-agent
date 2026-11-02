"""测试环境约定：强制离线确定性管线 + 偏好画像路径隔离。

为什么：.env 配置 DEEPSEEK_API_KEY 后 SD_LLM_MODE=auto 会让 run_pipeline 走在线 LLM 规划——
LLM 计划非确定性（temperature 0.3）且可能超容（设计内由校验段回流修复），
「规划器自算内容时长与 validator 同口径→V1 零误报」等确定性断言只对离线规划器成立。
在线路径的验证走真实端口手动/冒烟（CHANGELOG 1.1.6 已记录），不进 pytest。

模块级设置（而非 autouse fixture）：resolve_mode 在 run_pipeline 内逐次读取环境变量，
进程启动时一次性锁定即可；setdefault 不覆盖外部显式注入（如在线专项调试时
SD_LLM_MODE=online python -m pytest 仍可跑）。

偏好隔离（03J）：强制 SD_PREFERENCES_PATH 指向不存在的临时路径——
① 本机 ~/.shudao/ 演示留下的真实偏好绝不泄进测试（否则全部回归测试被污染）；
② 测试默认跑在「无记忆」基线上（与改造前行为逐字一致的回归锁依赖这一点）。
需要画像的用例各自 monkeypatch 到 tmp_path，不用这个兜底路径。
"""
import os
import tempfile

os.environ.setdefault("SD_LLM_MODE", "offline")
os.environ["SD_PREFERENCES_PATH"] = os.path.join(
    tempfile.gettempdir(), "shudao-test-prefs-isolated-nonexistent.json")
