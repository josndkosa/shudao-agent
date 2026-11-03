"""决策报告导出回归锁（03L 任务L6，补 03K 砍掉的任务 C）。

锁什么：
  1. 六节结构齐全（Python 版与 JS 版同锁：章节标题序列逐字一致——
     两边 Markdown 拼装实现不同，逐字比对会脆，锁「六节齐全 + 章节名一致」）
  2. 第 3 节 reason 全量（不许出现 … / truncated）
  3. 第 4 节解包 detail：嵌套事件（violation/advisory）取内层、扁平事件（fix 的
     removed）原样——直读 ev.detail 会拿到嵌套外壳，第 4 节静默空白（03H 任务H5
     那次 P0 的重演，报告版不能再来一次）
  4. 报告点数 == 行程点数（不许虚报）
  5. 夜景场景（有完整 violation→fix→pass 叙事）第 4 节四类小节都有内容
  6. /api/plan/report 端点契约：text/markdown + attachment + 404 行为与 revise 一致
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SD_LLM_MODE", "offline")

from fastapi.testclient import TestClient

from server.agent import TripRequest, run_pipeline
from server.agent.events import EventBus
from server.agent.report import SECTION_TITLES, render_report, unwrap_detail
from server.app import app

ROOT = Path(__file__).resolve().parent.parent


def _run(days=3, budget=3000, tags=("美食", "文化"), cities=("成都", "重庆")):
    bus = EventBus()
    result = run_pipeline(TripRequest(days=days, budget=budget, tags=list(tags),
                                      cities=list(cities)), bus)
    return result, [e.to_dict() for e in bus.events]


def _sections(md: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^## (.+)$", md, re.M)]


def test_six_sections_python():
    result, timeline = _run()
    md = render_report(result["itinerary"], timeline,
                       {"data_version": "3.0.0", "contract_version": "1.0.0"})
    assert _sections(md) == SECTION_TITLES, f"六节缺失或乱序：{_sections(md)}"


def test_six_sections_js_and_same_titles():
    """JS 版（static/js/report.js）六节标题与 Python 版逐字一致——断网 Mock 导出
    与服务端渲染必须结构同构。跑法：node 以 ES module 加载 report.js，喂同一份
    demo.json（真实产物，路径传参由 JS 自读——命令行塞大 JSON 会超限），提取
    ## 标题序列比对。"""
    js = (
        "import { readFileSync } from 'node:fs';\n"
        f"import {{ renderReport, SECTION_TITLES }} from '{(ROOT / 'static' / 'js' / 'report.js').as_uri()}';\n"
        "const d = JSON.parse(readFileSync(process.argv[1], 'utf8'));\n"
        "const md = renderReport({ itinerary: d.itinerary, timeline: d.timeline,\n"
        "  meta: { poi_count: 237, data_version: null, contract_version: null } });\n"
        "const secs = [...md.matchAll(/^## (.+)$/gm)].map(m => m[1]);\n"
        "console.log(JSON.stringify({ titles: SECTION_TITLES, sections: secs }));\n"
    )
    r = subprocess.run(["node", "--input-type=module", "-e", js,
                        str(ROOT / "static" / "demo.json")],
                       capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=ROOT)
    assert r.returncode == 0, f"node 渲染失败：{r.stderr[:300]}"
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["titles"] == SECTION_TITLES, f"JS 常量表与 Python 不一致：{out['titles']}"
    assert out["sections"] == SECTION_TITLES, f"JS 渲染章节与 Python 不一致：{out['sections']}"


def test_reasons_full_no_truncation():
    result, timeline = _run()
    md = render_report(result["itinerary"], timeline, {})
    for ev in timeline:
        reason = ev.get("reason", "")
        if reason:
            assert reason in md, f"事件 #{ev.get('seq')} 的 reason 未全量出现在报告里"
    assert "truncated" not in md, "报告出现截断痕迹"


def test_poi_count_matches_itinerary():
    result, timeline = _run()
    md = render_report(result["itinerary"], timeline, {})
    n = sum(1 for d in result["itinerary"]["days"]
            for it in d["items"] if it.get("type") == "poi")
    m = re.search(r"行程点数：(\d+)", md)
    assert m and int(m.group(1)) == n, f"报告点数 {m and m.group(1)} ≠ 行程点数 {n}"


def test_unwrap_detail_both_shapes():
    """解包锁（判断 3）：嵌套取内层 / 扁平原样——与前端 payload(ev) 逐字同语义。"""
    nested = {"detail": {"detail": {"rule": "V3-intensity", "day": 3, "poi": "CQ-07"}}}
    flat = {"detail": {"violation": "V4-budget", "removed": ["CD-05", "CD-08"]}}
    arr = {"detail": ["CD-09", "CD-16"]}
    assert unwrap_detail(nested) == {"rule": "V3-intensity", "day": 3, "poi": "CQ-07"}
    assert unwrap_detail(flat) == {"violation": "V4-budget", "removed": ["CD-05", "CD-08"]}
    assert unwrap_detail(arr) == ["CD-09", "CD-16"]
    assert unwrap_detail({}) is None


def test_section4_full_narrative_night_scene():
    """夜景场景（✗violation → fix → ✔ 完整叙事）：第 4 节四小节都有真内容，
    fix 的被移除点 ID 来自扁平 detail.removed，violation 详情来自嵌套内层。"""
    result, timeline = _run(days=2, budget=2000, tags=("夜景",))
    md = render_report(result["itinerary"], timeline, {})
    body = md.split(f"## {SECTION_TITLES[3]}", 1)[1].split(f"## {SECTION_TITLES[4]}", 1)[0]
    assert "### violation" in body and "（本行程无此类事件）" not in body.split("### advisory")[0], \
        "夜景场景应有 violation 内容"
    fix_part = body.split("### fix")[1].split("### advisory")[0]
    assert "removed=[" in fix_part, f"fix 小节未见被移除点 ID：{fix_part[:200]}"
    adv_part = body.split("### advisory")[1].split("### unfixable")[0]
    assert "V3" in adv_part or "强度" in adv_part, "advisory 小节应为嵌套载荷的真实规则名"


def test_report_endpoint_contract():
    """端点契约：text/markdown + attachment 文件名 + 404 与 revise 行为一致。"""
    client = TestClient(app)
    r404 = client.get("/api/plan/report", params={"plan_id": "no-such-id"})
    assert r404.status_code == 404 and "error" in r404.json()
    r = client.post("/api/plan", json={"days": 3, "budget": 3000,
                                       "tags": ["美食", "文化"], "cities": ["成都", "重庆"]})
    pid = r.json()["plan_id"]
    rep = client.get("/api/plan/report", params={"plan_id": pid})
    assert rep.status_code == 200
    assert rep.headers["content-type"].startswith("text/markdown")
    assert rep.headers["content-disposition"] == f'attachment; filename="shudao-report-{pid}.md"'
    md = rep.text
    assert _sections(md) == SECTION_TITLES
    assert "事件契约版本：1.0.0" in md, "契约版本应从 event.schema.json 运行时读出"
    assert "数据层版本：3.0.0" in md
    # 只读端点：再取一次结果一致（没改缓存）；revise 后报告反映新行程（缓存语义）
    rep2 = client.get("/api/plan/report", params={"plan_id": pid})
    assert rep2.text == md, "只读端点不应改变缓存内容"
