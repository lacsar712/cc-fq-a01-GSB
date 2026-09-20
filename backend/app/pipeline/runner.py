"""Orchestrate Actor chain with asyncio queues and persist stage status."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Job, JobStage, PairJob, PairJobStage
from app.pipeline.actors import (
    ACTOR_CHAIN,
    NContentActor,
    ParseActor,
    PipelineContext,
    QualityHistActor,
    QueueMessage,
    ReportActor,
)


STAGE_NAMES = [cls.name for cls in ACTOR_CHAIN]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _apply_stage_info(stage, info: dict) -> None:
    """Write one actor's outcome onto a stage row (shared by single/pair runners)."""
    stage.status = info["status"]
    stage.message = info["message"]
    if info["status"] in ("running", "success", "failed"):
        stage.started_at = stage.started_at or _utcnow()
    if info["status"] in ("success", "failed", "skipped"):
        stage.finished_at = _utcnow()
        if info["status"] == "skipped" and stage.started_at is None:
            stage.started_at = stage.finished_at


async def _run_chain(fastq_text: str) -> tuple[bool, PipelineContext, dict[str, dict]]:
    """
    Run Parse → QualityHist → NContent → Report via asyncio queues.
    Returns (success, context, stage_status keyed by actor name).
    """
    actors = [ParseActor(), QualityHistActor(), NContentActor(), ReportActor()]
    queues: list[asyncio.Queue] = [asyncio.Queue() for _ in range(len(actors) + 1)]
    stage_status: dict[str, dict] = {
        a.name: {"status": "pending", "message": None} for a in actors
    }

    ctx = PipelineContext(fastq_text=fastq_text)
    await queues[0].put(QueueMessage(ok=True, context=ctx))

    final = QueueMessage(ok=False, context=ctx, error="流水线未执行")
    # Queue-driven chain: each actor consumes from queues[i] and produces to queues[i+1]
    for i, actor in enumerate(actors):
        stage_status[actor.name]["status"] = "running"
        await actor.run(queues[i], queues[i + 1])
        result: QueueMessage = await queues[i + 1].get()
        final = result
        if result.ok:
            stage_status[actor.name]["status"] = "success"
            stage_status[actor.name]["message"] = "完成"
            # Forward to next actor's input (same queue slot for the next hop)
            if i + 1 < len(actors):
                await queues[i + 1].put(result)
        else:
            stage_status[actor.name]["status"] = "failed"
            stage_status[actor.name]["message"] = result.error or "失败"
            for later in actors[i + 1 :]:
                stage_status[later.name]["status"] = "skipped"
                stage_status[later.name]["message"] = f"因 {actor.name} 失败而跳过"
            break

    return final.ok, final.context, stage_status


def run_pipeline_sync(db: Session, job: Job) -> Job:
    """Execute pipeline for a job and update DB stages/metrics."""
    stages = (
        db.query(JobStage)
        .filter(JobStage.job_id == job.id)
        .order_by(JobStage.stage_order)
        .all()
    )
    stage_by_name = {s.actor_name: s for s in stages}

    job.status = "running"
    db.commit()

    success, ctx, stage_status = asyncio.run(_run_chain(job.fastq_snapshot))

    for name, info in stage_status.items():
        _apply_stage_info(stage_by_name[name], info)

    if success:
        job.status = "success"
        job.metrics = ctx.metrics
        job.error_message = None
    else:
        job.status = "failed"
        job.metrics = ctx.metrics or None
        job.error_message = ctx.error or "流水线失败"
    job.finished_at = _utcnow()
    db.commit()
    db.refresh(job)
    return job


def create_job_stages(db: Session, job_id: int) -> list[JobStage]:
    stages = []
    for order, cls in enumerate(ACTOR_CHAIN):
        st = JobStage(
            job_id=job_id,
            actor_name=cls.name,
            stage_order=order,
            status="pending",
        )
        db.add(st)
        stages.append(st)
    db.commit()
    return stages


# ---------------------------------------------------------------------------
# 双端配对流水线：R1/R2 各自独立跑同一条 Actor 链，单侧失败不影响另一侧
# ---------------------------------------------------------------------------

PAIR_SIDES = ("R1", "R2")


async def run_pair_chains(r1_text: str, r2_text: str) -> dict[str, dict]:
    """
    Concurrently run the actor chain for both mates. Each side has its own
    queues/context, so a parse failure on one side can never abort the other.
    """
    (r1_ok, r1_ctx, r1_stages), (r2_ok, r2_ctx, r2_stages) = await asyncio.gather(
        _run_chain(r1_text),
        _run_chain(r2_text),
    )
    return {
        "R1": {"ok": r1_ok, "ctx": r1_ctx, "stages": r1_stages},
        "R2": {"ok": r2_ok, "ctx": r2_ctx, "stages": r2_stages},
    }


def compute_pair_status(r1_status: str, r2_status: str) -> str:
    """Overall pair status: both ok → success; both failed → failed; else partial."""
    if r1_status == "success" and r2_status == "success":
        return "success"
    if r1_status == "failed" and r2_status == "failed":
        return "failed"
    return "partial"


def create_pair_job_stages(db: Session, pair_job_id: int) -> list[PairJobStage]:
    stages = []
    for side_idx, side in enumerate(PAIR_SIDES):
        for order, cls in enumerate(ACTOR_CHAIN):
            st = PairJobStage(
                pair_job_id=pair_job_id,
                side=side,
                actor_name=cls.name,
                stage_order=side_idx * 10 + order,
                status="pending",
            )
            db.add(st)
            stages.append(st)
    db.commit()
    return stages


def run_pair_pipeline_sync(db: Session, pair: PairJob) -> PairJob:
    """Execute both mates' actor chains and persist per-side stages/metrics."""
    stages = (
        db.query(PairJobStage)
        .filter(PairJobStage.pair_job_id == pair.id)
        .order_by(PairJobStage.stage_order)
        .all()
    )
    stage_by_key = {(s.side, s.actor_name): s for s in stages}

    pair.status = "running"
    pair.r1_status = "running"
    pair.r2_status = "running"
    db.commit()

    results = asyncio.run(run_pair_chains(pair.r1_fastq_snapshot, pair.r2_fastq_snapshot))

    for side in PAIR_SIDES:
        res = results[side]
        for name, info in res["stages"].items():
            _apply_stage_info(stage_by_key[(side, name)], info)
        ctx: PipelineContext = res["ctx"]
        if res["ok"]:
            side_status, side_metrics, side_error = "success", ctx.metrics, None
        else:
            # 失败侧保留已算出的部分指标，并记录失败原因（含失败 Actor）
            side_status = "failed"
            side_metrics = ctx.metrics or None
            side_error = ctx.error or "流水线失败"
        setattr(pair, f"{side.lower()}_status", side_status)
        setattr(pair, f"{side.lower()}_metrics", side_metrics)
        setattr(pair, f"{side.lower()}_error", side_error)

    pair.status = compute_pair_status(pair.r1_status, pair.r2_status)
    pair.finished_at = _utcnow()
    db.commit()
    db.refresh(pair)
    return pair
