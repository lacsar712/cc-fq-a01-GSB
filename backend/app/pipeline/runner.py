"""Orchestrate Actor chain with asyncio queues and persist stage status."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Job, JobStage, PairRun
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


def _persist_result(
    db: Session,
    job: Job,
    success: bool,
    ctx: PipelineContext,
    stage_status: dict[str, dict],
) -> None:
    """Write chain outcome (stages + metrics) onto one job."""
    stages = (
        db.query(JobStage)
        .filter(JobStage.job_id == job.id)
        .order_by(JobStage.stage_order)
        .all()
    )
    stage_by_name = {s.actor_name: s for s in stages}

    for name, info in stage_status.items():
        st = stage_by_name[name]
        st.status = info["status"]
        st.message = info["message"]
        if info["status"] in ("running", "success", "failed"):
            st.started_at = st.started_at or _utcnow()
        if info["status"] in ("success", "failed", "skipped"):
            st.finished_at = _utcnow()
            if info["status"] == "skipped" and st.started_at is None:
                st.started_at = st.finished_at

    if success:
        job.status = "success"
        job.metrics = ctx.metrics
        job.error_message = None
    else:
        job.status = "failed"
        job.metrics = ctx.metrics or None
        job.error_message = ctx.error or "流水线失败"
    job.finished_at = _utcnow()


async def _run_pair_chains(
    text_r1: str, text_r2: str
) -> tuple[
    tuple[bool, PipelineContext, dict[str, dict]],
    tuple[bool, PipelineContext, dict[str, dict]],
]:
    """两条 Actor 链在同一事件循环内并发执行，互不影响（一侧失败不打断另一侧）。"""
    return await asyncio.gather(_run_chain(text_r1), _run_chain(text_r2))


def run_pipeline_sync(db: Session, job: Job) -> Job:
    """Execute pipeline for a job and update DB stages/metrics."""
    job.status = "running"
    db.commit()

    success, ctx, stage_status = asyncio.run(_run_chain(job.fastq_snapshot))
    _persist_result(db, job, success, ctx, stage_status)
    db.commit()
    db.refresh(job)
    return job


def _derive_pair_status(
    ok_r1: bool,
    ok_r2: bool,
    err_r1: str | None,
    err_r2: str | None,
) -> tuple[str, str | None, str | None]:
    """根据两侧成败推导 (配对状态, 失败侧, 汇总错误)。

    success  两侧均成功
    partial  恰好一侧失败（保留成功侧指标，标明失败侧 r1/r2）
    failed   两侧均失败（failed_side=both）
    """
    failed_sides = [side for side, ok in (("r1", ok_r1), ("r2", ok_r2)) if not ok]
    errors: list[str] = []
    if not ok_r1:
        errors.append(f"R1：{err_r1 or '流水线失败'}")
    if not ok_r2:
        errors.append(f"R2：{err_r2 or '流水线失败'}")

    if not failed_sides:
        return "success", None, None
    if len(failed_sides) == 2:
        return "failed", "both", "；".join(errors)
    return "partial", failed_sides[0], "；".join(errors)


def run_pair_pipeline_sync(db: Session, pair: PairRun) -> PairRun:
    """并发执行 R1/R2 两条 Actor 链，并根据两侧成败推导配对状态。"""
    jobs = {j.pair_side: j for j in pair.jobs}
    if "r1" not in jobs or "r2" not in jobs:
        raise RuntimeError("配对记录缺少 R1/R2 作业")

    for job in jobs.values():
        job.status = "running"
    pair.status = "running"
    db.commit()

    (ok_r1, ctx_r1, st_r1), (ok_r2, ctx_r2, st_r2) = asyncio.run(
        _run_pair_chains(jobs["r1"].fastq_snapshot, jobs["r2"].fastq_snapshot)
    )

    # 两侧各自持久化：一侧解析失败不影响另一侧的指标与阶段结果
    _persist_result(db, jobs["r1"], ok_r1, ctx_r1, st_r1)
    _persist_result(db, jobs["r2"], ok_r2, ctx_r2, st_r2)

    pair.status, pair.failed_side, pair.error_message = _derive_pair_status(
        ok_r1, ok_r2, ctx_r1.error, ctx_r2.error
    )
    pair.finished_at = _utcnow()
    db.commit()
    db.refresh(pair)
    return pair


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
