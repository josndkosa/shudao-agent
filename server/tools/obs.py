"""OBS 可选接入：标准库实现 S3 SigV4 PUT 上传（零新依赖）。

环境变量 OBS_ENDPOINT / OBS_BUCKET / OBS_AK / OBS_SK 四者齐全才启用；
可选 OBS_REGION（默认 cn-north-4）。
未启用时 save_plan() 返回 {"enabled": false, "reason": "未配置 OBS 环境变量，已跳过"}，
主流程完全不受影响——华为云接入是评分增强项，不是断网依赖项。
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import os
from datetime import datetime, timezone


def enabled() -> bool:
    return all(os.environ.get(k) for k in ("OBS_ENDPOINT", "OBS_BUCKET", "OBS_AK", "OBS_SK"))


def _sig(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def save_plan(plan_json: str, plan_id: str) -> dict:
    """把 plan JSON 上传 OBS，返回 {enabled, ok, url/status/reason}。"""
    if not enabled():
        return {"enabled": False, "ok": False, "url": None,
                "reason": "未配置 OBS 环境变量，已跳过"}
    endpoint = os.environ["OBS_ENDPOINT"].removeprefix("https://").removeprefix("http://")
    bucket = os.environ["OBS_BUCKET"]
    ak, sk = os.environ["OBS_AK"], os.environ["OBS_SK"]
    region = os.environ.get("OBS_REGION", "cn-north-4")
    key = f"plans/{plan_id}.json"
    host = f"{bucket}.{endpoint}"
    body = plan_json.encode("utf-8")

    # AWS SigV4（S3 兼容，OBS 支持）
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical = (
        f"PUT\n/{key}\n\n"
        f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n\n"
        f"host;x-amz-content-sha256;x-amz-date\n{payload_hash}"
    )
    scope = f"{datestamp}/{region}/s3/aws4_request"
    sts = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"
    k = _sig(("AWS4" + sk).encode(), datestamp)
    for part in (region, "s3", "aws4_request"):
        k = _sig(k, part)
    signature = hmac.new(k, sts.encode("utf-8"), hashlib.sha256).hexdigest()
    auth = (f"AWS4-HMAC-SHA256 Credential={ak}/{scope}, "
            f"SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature={signature}")

    conn = http.client.HTTPSConnection(host, timeout=5)
    try:
        conn.request("PUT", f"/{key}", body=body, headers={
            "Host": host, "Authorization": auth,
            "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date,
            "Content-Type": "application/json",
        })
        resp = conn.getresponse()
        ok = 200 <= resp.status < 300
        return {
            "enabled": True, "ok": ok, "status": resp.status,
            "url": f"https://{host}/{key}" if ok else None,
            "reason": None if ok else f"OBS 返回 HTTP {resp.status}",
        }
    except Exception as e:
        return {"enabled": True, "ok": False, "url": None,
                "reason": f"{type(e).__name__}: {e}"}
    finally:
        conn.close()