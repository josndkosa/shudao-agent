"""华为云接入独立层（可选增强：OBS / FunctionGraph）。

全部接入线都是：未配置时静默降级，绝不影响主流程。详见本目录 README.md。
"""
from . import functiongraph, obs

__all__ = ["functiongraph", "obs"]
