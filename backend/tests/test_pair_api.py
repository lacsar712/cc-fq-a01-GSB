"""API-level tests for the paired-end QC endpoints (SQLite-backed).

验收口令：合格配损坏各一侧后能区分成败。
"""

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app

Base.metadata.create_all(bind=engine)
client = TestClient(app)

GOOD_FASTQ = """@SEQ1
ACGTACGT
+
IIIIHHHH
@SEQ2
NNNNACGT
+
IIIIIIII
"""

BROKEN_FASTQ = """@SEQ1
ACGT
NOTPLUS
IIII
"""


def _auth(username: str, password: str) -> dict:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _stage(stages: list[dict], side: str, actor: str) -> dict:
    return next(s for s in stages if s["side"] == side and s["actor_name"] == actor)


def test_pair_api_good_vs_broken_distinguishes_sides():
    """R1 合格 + R2 损坏 → 整体 partial，R1 指标保留，R2 标明失败阶段。"""
    headers = _auth("bioops", "fastq123456")
    res = client.post(
        "/api/pairs",
        json={"r1": {"fastqText": GOOD_FASTQ}, "r2": {"fastqText": BROKEN_FASTQ}},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    pair_id = res.json()["id"]

    detail = client.get(f"/api/pairs/{pair_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()

    # 整体可区分：一成功一失败 → partial
    assert body["status"] == "partial"
    # 成功侧结果保留
    assert body["r1_status"] == "success"
    assert body["r1_metrics"]["reads"] == 2
    assert body["r1_metrics"]["n_rate"] == 0.25
    assert body["r1_error"] is None
    # 失败侧标明失败与失败阶段
    assert body["r2_status"] == "failed"
    assert body["r2_error"]
    assert _stage(body["stages"], "R2", "ParseActor")["status"] == "failed"
    assert _stage(body["stages"], "R2", "ReportActor")["status"] == "skipped"
    assert _stage(body["stages"], "R1", "ParseActor")["status"] == "success"

    stages_res = client.get(f"/api/pairs/{pair_id}/stages", headers=headers)
    assert stages_res.status_code == 200
    assert len(stages_res.json()) == 8  # 双侧 × 4 个 Actor


def test_pair_api_both_good_success():
    headers = _auth("bioops", "fastq123456")
    res = client.post(
        "/api/pairs",
        json={"r1": {"fastqText": GOOD_FASTQ}, "r2": {"fastqText": GOOD_FASTQ}},
        headers=headers,
    )
    assert res.status_code == 201
    body = client.get(f"/api/pairs/{res.json()['id']}", headers=headers).json()
    assert body["status"] == "success"
    assert body["r1_status"] == "success"
    assert body["r2_status"] == "success"


def test_pair_api_auditor_is_readonly():
    auditor = _auth("auditor", "audit123456")
    res = client.post(
        "/api/pairs",
        json={"r1": {"fastqText": GOOD_FASTQ}, "r2": {"fastqText": GOOD_FASTQ}},
        headers=auditor,
    )
    assert res.status_code == 403
    # 只读接口可用
    assert client.get("/api/pairs", headers=auditor).status_code == 200


def test_pair_api_requires_login():
    res = client.post(
        "/api/pairs",
        json={"r1": {"fastqText": GOOD_FASTQ}, "r2": {"fastqText": GOOD_FASTQ}},
    )
    assert res.status_code == 401
    assert client.get("/api/pairs").status_code == 401


def test_pair_api_requires_both_sides():
    headers = _auth("bioops", "fastq123456")
    res = client.post(
        "/api/pairs",
        json={"r1": {"fastqText": GOOD_FASTQ}, "r2": {}},
        headers=headers,
    )
    assert res.status_code == 400
    assert "R2" in res.json()["detail"]
