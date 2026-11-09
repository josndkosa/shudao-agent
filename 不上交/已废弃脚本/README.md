# 已废弃脚本（**不进 zip**）

> 这三个脚本是**清理出来的**，不是"忘了删"。保留在这里是为了**可回滚**——
> 确认不需要了，直接删掉整个目录即可，代码里已经没有任何引用。

## `ci.sh` / `ci.bat`（原 `scripts/`）

**为什么废弃**：职责被 `python scripts/ctl.py ci` **完全覆盖**，而且**比主力入口更弱**。

| | `ci.sh` / `ci.bat` | `python scripts/ctl.py ci`（唯一入口） |
|---|---|---|
| lint | `python -m ruff check . \|\| echo "（ruff 未安装则跳过）"` ——**`\|\|` 把 lint 失败也吞了**，ruff 真报出错误也照样通过 | 先 `probe.returncode` 判 ruff 是否安装，**装了但有 lint 错误就非零退出** |
| test | `python -m pytest -q` | 同（`-X utf8`） |
| smoke | `node scripts/smoke_frontend.mjs` | 同 |
| 跨平台 | 要 `.sh` + `.bat` 两份 | **一份跨平台**，Windows / macOS / Linux 同一句 |
| 失败语义 | lint 失败**不挡**（最关键的一条） | 任一步失败即非零退出 |

**保留旧入口的真实风险**：评委或码道在 Windows 上敲 `scripts\ci.bat`，
ruff 报出 3 个错误，脚本照样打印"✓ CI 全部通过"——这就是"虚假安全感"。
留着一个比主力弱的入口，等于给错误结论开口子。

**引用已同步**：`.github/workflows/ci.yml` 调的是 `ctl.py ci`；
`docs/华为云接入说明.md` 与 `server/cloud/README.md` 的 CI 说明已改为单一入口。

> 历史记录里提到这两个文件的地方**保持原样**——`codearts_proof/debug-log-2026-10-28.md`
> 和 `04_大项目化` 任务单原文记的是"当时创建了它们"，那是**事实**，不是待办清单。

## 三个不在本仓库里的散落脚本

移到了 `D:\项目代码\_废弃\`（**仓库外，本来就不进 zip**）：

| 原文件 | 为什么没用 |
|---|---|
| `_tmp_demo.bat` | 4 行的临时演示包装器，脚本自述「**临时演示脚本（用完即删）**」。 |
| `_整理截图.py` | **一次性**脚本，已执行完毕：把 `codearts_proof/` 根目录的散图按 `zip-layout.md` 的 6 个编号目录归类并改名，未入选的原图移到 `D:\项目代码\蜀道智行_截图原件_备份\`（**不删，原图都还在**）。效果已落盘，脚本本身不再需要。 |

> 备份目录 `D:\项目代码\蜀道智行_截图原件_备份\` **保留**——
> 补拍 `docs/images/` 的 6 张产品截图时可能要回查原始截图。

> ⚠️ **同目录下 `restructure_chapters.py` 与 `pelican-bike.html` 属于另一个项目（智学星球），不要动。**
> 这是 `04_大项目化` 任务单原文里的明确交代（`:160`）。
> （`restructure_chapters.py` 一度被误移进 `_废弃/`，**已原样放回** `D:\项目代码\`。）
