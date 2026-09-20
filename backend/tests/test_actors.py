"""Unit tests for Actor pipeline (no DB required)."""

import asyncio

import pytest

from app.pipeline.actors import (
    ActorError,
    NContentActor,
    ParseActor,
    PipelineContext,
    QualityHistActor,
    QueueMessage,
    ReportActor,
)
from app.pipeline.runner import _derive_pair_status, _run_chain, _run_pair_chains


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
async def test_parse_actor_rejects_malformed():
    actor = ParseActor()
    in_q: asyncio.Queue = asyncio.Queue()
    out_q: asyncio.Queue = asyncio.Queue()
    await in_q.put(QueueMessage(ok=True, context=PipelineContext(fastq_text=BROKEN_FASTQ)))
    await actor.run(in_q, out_q)
    result = await out_q.get()
    assert result.ok is False
    assert "必须以 +" in (result.error or "")


@pytest.mark.asyncio
async def test_parse_actor_ok_and_quality_mean():
    ok, ctx, stages = await _run_chain(GOOD_FASTQ)
    assert ok is True
    assert stages["ParseActor"]["status"] == "success"
    assert stages["ReportActor"]["status"] == "success"
    assert ctx.metrics["reads"] == 2
    assert "mean_quality" in ctx.metrics
    assert ctx.metrics["mean_quality"] > 0
    assert ctx.metrics["n_rate"] == 0.25  # 4 N out of 16 bases


@pytest.mark.asyncio
async def test_broken_stops_pipeline():
    ok, ctx, stages = await _run_chain(BROKEN_FASTQ)
    assert ok is False
    assert stages["ParseActor"]["status"] == "failed"
    assert stages["QualityHistActor"]["status"] == "skipped"
    assert stages["NContentActor"]["status"] == "skipped"
    assert stages["ReportActor"]["status"] == "skipped"
    assert ctx.failed_actor == "ParseActor"


def test_parse_length_mismatch():
    actor = ParseActor()
    with pytest.raises(ActorError, match="长度不一致"):
        actor._parse("@A\nACGT\n+\nII\n")


@pytest.mark.asyncio
async def test_pair_chains_are_independent():
    """合格配损坏各一侧：损坏侧 ParseActor 失败，合格侧仍完整产出指标。"""
    (ok_r1, ctx_r1, st_r1), (ok_r2, ctx_r2, st_r2) = await _run_pair_chains(
        GOOD_FASTQ, BROKEN_FASTQ
    )

    # 合格侧保留完整结果
    assert ok_r1 is True
    assert st_r1["ParseActor"]["status"] == "success"
    assert st_r1["ReportActor"]["status"] == "success"
    assert ctx_r1.metrics["reads"] == 2
    assert ctx_r1.metrics["mean_quality"] > 0

    # 损坏侧照常失败、后续阶段跳过，且没有拖垮合格侧
    assert ok_r2 is False
    assert st_r2["ParseActor"]["status"] == "failed"
    assert st_r2["QualityHistActor"]["status"] == "skipped"
    assert st_r2["ReportActor"]["status"] == "skipped"
    assert ctx_r2.failed_actor == "ParseActor"


@pytest.mark.asyncio
async def test_pair_chains_reversed_sides():
    """损坏在 R1 一侧时同样可以区分成败。"""
    (ok_r1, _ctx_r1, st_r1), (ok_r2, ctx_r2, st_r2) = await _run_pair_chains(
        BROKEN_FASTQ, GOOD_FASTQ
    )
    assert ok_r1 is False
    assert st_r1["ParseActor"]["status"] == "failed"
    assert ok_r2 is True
    assert st_r2["ReportActor"]["status"] == "success"
    assert ctx_r2.metrics["n_rate"] == 0.25


def test_derive_pair_status_cases():
    # 两侧皆成功
    assert _derive_pair_status(True, True, None, None) == ("success", None, None)

    # R2 损坏 -> partial，标明失败侧 r2，合格侧结果保留
    status, failed_side, err = _derive_pair_status(True, False, None, "解析炸了")
    assert status == "partial"
    assert failed_side == "r2"
    assert "R2" in err

    # R1 损坏
    status, failed_side, _ = _derive_pair_status(False, True, "bad", None)
    assert (status, failed_side) == ("partial", "r1")

    # 两侧皆损
    status, failed_side, _ = _derive_pair_status(False, False, "e1", "e2")
    assert status == "failed"
    assert failed_side == "both"
