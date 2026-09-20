"""Unit tests for the paired-end QC pipeline (no DB required)."""

import pytest

from app.pipeline.runner import compute_pair_status, run_pair_chains


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


@pytest.mark.asyncio
async def test_pair_good_vs_broken_keeps_good_side():
    """合格 + 损坏配对：坏侧 ParseActor 失败，好侧指标完整保留。"""
    results = await run_pair_chains(GOOD_FASTQ, BROKEN_FASTQ)

    r1, r2 = results["R1"], results["R2"]
    assert r1["ok"] is True
    assert r1["stages"]["ParseActor"]["status"] == "success"
    assert r1["stages"]["ReportActor"]["status"] == "success"
    assert r1["ctx"].metrics["reads"] == 2
    assert r1["ctx"].metrics["n_rate"] == 0.25

    assert r2["ok"] is False
    assert r2["stages"]["ParseActor"]["status"] == "failed"
    assert r2["stages"]["QualityHistActor"]["status"] == "skipped"
    assert r2["stages"]["ReportActor"]["status"] == "skipped"
    assert r2["ctx"].failed_actor == "ParseActor"
    assert r2["ctx"].error


@pytest.mark.asyncio
async def test_pair_broken_first_side_still_runs_second():
    """损坏放在 R1 侧时，R2 侧合格样本照常出结果（方向无关）。"""
    results = await run_pair_chains(BROKEN_FASTQ, GOOD_FASTQ)
    assert results["R1"]["ok"] is False
    assert results["R1"]["ctx"].failed_actor == "ParseActor"
    assert results["R2"]["ok"] is True
    assert results["R2"]["ctx"].metrics["mean_quality"] > 0


@pytest.mark.asyncio
async def test_pair_both_broken():
    results = await run_pair_chains(BROKEN_FASTQ, BROKEN_FASTQ)
    assert results["R1"]["ok"] is False
    assert results["R2"]["ok"] is False


@pytest.mark.asyncio
async def test_pair_both_good():
    results = await run_pair_chains(GOOD_FASTQ, GOOD_FASTQ)
    assert results["R1"]["ok"] is True
    assert results["R2"]["ok"] is True


@pytest.mark.parametrize(
    ("r1", "r2", "expected"),
    [
        ("success", "success", "success"),
        ("success", "failed", "partial"),
        ("failed", "success", "partial"),
        ("failed", "failed", "failed"),
    ],
)
def test_compute_pair_status(r1, r2, expected):
    assert compute_pair_status(r1, r2) == expected
