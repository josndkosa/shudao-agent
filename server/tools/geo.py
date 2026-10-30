import math

EARTH_R = 6371.0
SVG_W, SVG_H = 1000.0, 700.0


def haversine(lat1, lng1, lat2, lng2):
    r = math.radians
    dlat = r(lat2 - lat1)
    dlng = r(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


class Projector:
    """经纬度 -> SVG 画布坐标，成渝双城自绘路线图用。"""

    def __init__(self, points):
        lats = [p["lat"] for p in points]
        lngs = [p["lng"] for p in points]
        self.min_lat, self.max_lat = min(lats), max(lats)
        self.min_lng, self.max_lng = min(lngs), max(lngs)

    def project(self, lat, lng):
        span_lat = self.max_lat - self.min_lat or 1.0
        span_lng = self.max_lng - self.min_lng or 1.0
        pad = 60.0
        x = pad + (lng - self.min_lng) / span_lng * (SVG_W - 2 * pad)
        y = SVG_H - pad - (lat - self.min_lat) / span_lat * (SVG_H - 2 * pad)
        return round(x, 1), round(y, 1)
