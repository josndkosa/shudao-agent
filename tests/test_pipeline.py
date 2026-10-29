import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["SD_LLM_MODE"] = "offline"

from server.agent import TripRequest, run_pipeline
from server.agent.events import EventBus


def _run(**kw):
    req = TripRequest(**kw)
    return run_pipeline(req, EventBus())


def test_pipeline_offline_basic():
    r = _run(days=3, budget=3000, tags=["美食", "文化"])
    assert r["mode"] == "offline"
    days = r["itinerary"]["days"]
    assert 1 <= len(days) <= 3
    assert r["budget"]["total"] <= 3000 + 600   # 预算约束（含超限修复余量）


def test_pipeline_emits_three_stages():
    r = _run(days=2, budget=4000, tags=["夜景"])
    stages = {e["stage"] for e in r["timeline"]}
    assert {"plan", "validate", "narrate", "system"} <= stages
    reasons = [e for e in r["timeline"] if e["reason"]]
    assert len(reasons) >= 5, "事件流必须携带 reason 才能支撑可倒带回放"


def test_pipeline_days_not_overloaded():
    r = _run(days=3, budget=5000, tags=["亲子"])
    for d in r["itinerary"]["days"]:
        pois = [it for it in d["items"] if it["type"] == "poi"]
        for it in pois:
            arr = int(it["arrival"][:2]) + int(it["arrival"][3:5]) / 60
            dep = int(it["departure"][:2]) + int(it["departure"][3:5]) / 60
            assert dep <= 22.0 + 1e-6, f"第{d['day']}天 {it['name']} 结束超 22:00"
            assert arr >= 8.5 - 1e-6
        if d.get("narrative"):
            assert len(d["narrative"]) > 20