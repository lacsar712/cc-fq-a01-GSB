from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.auth import authenticate_user, create_access_token, get_current_user, require_bioops
from app.database import SessionLocal, get_db
from app.models import Job, JobStage, PairRun, Sample
from app.pipeline.runner import create_job_stages, run_pipeline_sync, run_pair_pipeline_sync
from app.schemas import (
    HealthOut,
    JobCreate,
    JobListItem,
    JobOut,
    LoginRequest,
    PairRunCreate,
    PairRunListItem,
    PairRunOut,
    PairSideInput,
    PairSideOut,
    SampleOut,
    StageOut,
    TokenResponse,
)


router = APIRouter(prefix="/api")


def _run_job_background(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            run_pipeline_sync(db, job)
    finally:
        db.close()


def _run_pair_background(pair_id: int) -> None:
    db = SessionLocal()
    try:
        pair = (
            db.query(PairRun)
            .options(joinedload(PairRun.jobs).joinedload(Job.stages))
            .filter(PairRun.id == pair_id)
            .first()
        )
        if pair:
            run_pair_pipeline_sync(db, pair)
    finally:
        db.close()


def _resolve_side(
    db: Session, side: PairSideInput, label: str
) -> tuple[str, Sample | None]:
    """Resolve one paired side to (fastq_text, sample). Raises 400/404 on bad input."""
    sample_id = side.sampleId
    fastq_text = (side.fastqText or "").strip() if side.fastqText else ""

    if sample_id is not None:
        sample = db.query(Sample).filter(Sample.id == sample_id).first()
        if not sample:
            raise HTTPException(status_code=404, detail=f"{label} 样例不存在")
        return sample.fastq_content, sample
    if not fastq_text:
        raise HTTPException(status_code=400, detail=f"{label} 请选择样例或粘贴 FASTQ 文本")
    return fastq_text, None


@router.get("/health", response_model=HealthOut)
def health():
    return HealthOut(status="ok", service="fastq-qc-pipeline")


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user = authenticate_user(body.username.strip(), body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_access_token(user["username"], user["role"])
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
    )


@router.get("/samples", response_model=list[SampleOut])
def list_samples(_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Sample).order_by(Sample.id).all()


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: JobCreate,
    background: BackgroundTasks,
    user: dict = Depends(require_bioops),
    db: Session = Depends(get_db),
):
    sample_id = body.sampleId
    fastq_text = (body.fastqText or "").strip() if body.fastqText else ""
    sample_name = "自定义输入"
    sample = None

    if sample_id is not None:
        sample = db.query(Sample).filter(Sample.id == sample_id).first()
        if not sample:
            raise HTTPException(status_code=404, detail="样例不存在")
        fastq_text = sample.fastq_content
        sample_name = sample.name
    elif not fastq_text:
        raise HTTPException(status_code=400, detail="请提供 sampleId 或 fastqText")

    job = Job(
        sample_id=sample.id if sample else None,
        sample_name=sample_name,
        status="pending",
        created_by=user["username"],
        fastq_snapshot=fastq_text,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    create_job_stages(db, job.id)
    background.add_task(_run_job_background, job.id)

    job = (
        db.query(Job)
        .options(joinedload(Job.stages))
        .filter(Job.id == job.id)
        .first()
    )
    return job


@router.get("/jobs", response_model=list[JobListItem])
def list_jobs(_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    # 配对产生的单侧作业在配对详情中展示，不混入单端历史
    return (
        db.query(Job)
        .filter(Job.pair_id.is_(None))
        .order_by(Job.id.desc())
        .all()
    )


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, _user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    job = (
        db.query(Job)
        .options(joinedload(Job.stages))
        .filter(Job.id == job_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="作业不存在")
    return job


@router.get("/jobs/{job_id}/stages", response_model=list[StageOut])
def get_job_stages(
    job_id: int, _user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="作业不存在")
    return (
        db.query(JobStage)
        .filter(JobStage.job_id == job_id)
        .order_by(JobStage.stage_order)
        .all()
    )


def _build_pair_out(pair: PairRun) -> PairRunOut:
    sides: dict[str, PairSideOut] = {}
    for job in pair.jobs:
        sides[job.pair_side] = PairSideOut(
            side=job.pair_side,
            sample_name=job.sample_name,
            sample_id=job.sample_id,
            status=job.status,
            metrics=job.metrics,
            error_message=job.error_message,
            stages=[StageOut.model_validate(s) for s in job.stages],
        )
    return PairRunOut(
        id=pair.id,
        status=pair.status,
        created_by=pair.created_by,
        failed_side=pair.failed_side,
        error_message=pair.error_message,
        created_at=pair.created_at,
        finished_at=pair.finished_at,
        r1=sides.get("r1"),
        r2=sides.get("r2"),
    )


@router.post("/pair-runs", response_model=PairRunOut, status_code=status.HTTP_201_CREATED)
def create_pair_run(
    body: PairRunCreate,
    background: BackgroundTasks,
    user: dict = Depends(require_bioops),
    db: Session = Depends(get_db),
):
    text_r1, sample_r1 = _resolve_side(db, body.r1, "R1")
    text_r2, sample_r2 = _resolve_side(db, body.r2, "R2")

    pair = PairRun(
        status="pending",
        r1_name=sample_r1.name if sample_r1 else "自定义输入",
        r2_name=sample_r2.name if sample_r2 else "自定义输入",
        r1_sample_id=sample_r1.id if sample_r1 else None,
        r2_sample_id=sample_r2.id if sample_r2 else None,
        created_by=user["username"],
    )
    db.add(pair)
    db.commit()
    db.refresh(pair)

    for side, text, sample, order in (
        ("r1", text_r1, sample_r1, 0),
        ("r2", text_r2, sample_r2, 1),
    ):
        job = Job(
            sample_id=sample.id if sample else None,
            sample_name=sample.name if sample else "自定义输入",
            status="pending",
            created_by=user["username"],
            fastq_snapshot=text,
            pair_id=pair.id,
            pair_side=side,
            pair_side_order=order,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        create_job_stages(db, job.id)

    background.add_task(_run_pair_background, pair.id)

    pair = (
        db.query(PairRun)
        .options(joinedload(PairRun.jobs).joinedload(Job.stages))
        .filter(PairRun.id == pair.id)
        .first()
    )
    return _build_pair_out(pair)


@router.get("/pair-runs", response_model=list[PairRunListItem])
def list_pair_runs(_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    pairs = (
        db.query(PairRun)
        .options(joinedload(PairRun.jobs))
        .order_by(PairRun.id.desc())
        .all()
    )
    items: list[PairRunListItem] = []
    for pair in pairs:
        side_status = {j.pair_side: j.status for j in pair.jobs}
        items.append(
            PairRunListItem(
                id=pair.id,
                status=pair.status,
                created_by=pair.created_by,
                failed_side=pair.failed_side,
                r1_name=pair.r1_name,
                r2_name=pair.r2_name,
                r1_status=side_status.get("r1"),
                r2_status=side_status.get("r2"),
                created_at=pair.created_at,
                finished_at=pair.finished_at,
            )
        )
    return items


@router.get("/pair-runs/{pair_id}", response_model=PairRunOut)
def get_pair_run(
    pair_id: int, _user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    pair = (
        db.query(PairRun)
        .options(joinedload(PairRun.jobs).joinedload(Job.stages))
        .filter(PairRun.id == pair_id)
        .first()
    )
    if not pair:
        raise HTTPException(status_code=404, detail="配对记录不存在")
    return _build_pair_out(pair)
