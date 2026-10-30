"""OBS 接入薄转发：实现已迁移至 server/cloud/obs.py（华为云独立成层，任务 E）。

保留此模块仅为不破坏既有 import（server/app.py 与 tests）。
"""
from ..cloud.obs import *  # noqa: F401,F403
