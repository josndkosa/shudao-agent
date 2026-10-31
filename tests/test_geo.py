import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.tools import Projector, haversine, load_pois


def test_haversine_chengdu_chongqing():
    d = haversine(30.5728, 104.0665, 29.5647, 106.5507)
    assert 250 < d < 300


def test_projector_in_canvas():
    pois = load_pois()
    pr = Projector(pois)
    for p in pois:
        x, y = pr.project(p["lat"], p["lng"])
        assert 0 <= x <= 1000 and 0 <= y <= 700


def test_pois_snapshot_shape():
    """批次1 后覆盖 6 城共 101 点（prompt 03E 允许的唯一断言修改：40 → 多城覆盖）。"""
    pois = load_pois()
    assert {p["city"] for p in pois} >= {"成都", "重庆", "昆明", "大理", "贵阳", "桂林"}
    assert len(pois) >= 100
    for p in pois:
        for f in ("open_hour", "reserve", "crowd_peak", "crowd_level", "slope", "family", "visit_hours", "ticket"):
            assert f in p, f"{p['id']} 缺字段 {f}"
        assert 0 <= p["reserve"] <= 3 and 0 <= p["slope"] <= 3 and 0 <= p["family"] <= 5
