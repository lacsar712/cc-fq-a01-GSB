from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.auth import authenticate_user, create_access_token, get_current_user, require_bioops
from app.database import SessionLocal, get_db
from app.models import Job, JobStage, PairJob, PairJobStage, Sample
from app.pipeline.runner import (
    create_job_stages,
    create_pair_job_stages,
    run_pair_pipeline_sync,
    run_pipeline_sync,
)
from app.schemas import (
    HealthOut,
    JobCreate,
    JobListItem,
    JobOut,
    LoginRequest,
    PairJobCreate,
    PairJobListItem,
    PairJobOut,
    PairSideCreate,
    PairStageOut,
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
        pair = db.query(PairJob).filter(PairJob.id == pair_id).first()
        if pair:
            run_pair_pipeline_sync(db, pair)
    finally:
        db.close()


def _resolve_side(side: PairSideCreate, side_label: str, db: Session):
    """Each mate may pick a seeded sample or paste raw FASTQ text (sample wins)."""
    fastq_text = (side.fastqText or "").strip() if side.fastqText else ""
    if side.sampleId is not None:
        sample = db.query(Sample).filter(Sample.id == side.sampleId).first()
        if not sample:
            raise HTTPException(status_code=404, detail=f"{side_label} 侧样例不存在")
        return sample, sample.fastq_content, sample.name
    if not fastq_text:
        raise HTTPException(status_code=400, detail=f"{side_label} 侧请提供 sampleId 或 fastqText")
    return None, fastq_text, "自定义输入"


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
    return db.query(Job).order_by(Job.id.desc()).all()


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


# ---------------------------------------------------------------------------
# 双端配对质控：运维可开跑，审计员只读
# ---------------------------------------------------------------------------


@router.post("/pairs", response_model=PairJobOut, status_code=status.HTTP_201_CREATED)
def create_pair_job(
    body: PairJobCreate,
    background: BackgroundTasks,
    user: dict = Depends(require_bioops),
    db: Session = Depends(get_db),
):
    r1_sample, r1_text, r1_name = _resolve_side(body.r1, "R1", db)
    r2_sample, r2_text, r2_name = _resolve_side(body.r2, "R2", db)

    pair = PairJob(
        status="pending",
        created_by=user["username"],
        r1_sample_id=r1_sample.id if r1_sample else None,
        r1_sample_name=r1_name,
        r1_fastq_snapshot=r1_text,
        r2_sample_id=r2_sample.id if r2_sample else None,
        r2_sample_name=r2_name,
        r2_fastq_snapshot=r2_text,
    )
    db.add(pair)
    db.commit()
    db.refresh(pair)
    create_pair_job_stages(db, pair.id)
    background.add_task(_run_pair_background, pair.id)

    return (
        db.query(PairJob)
        .options(joinedload(PairJob.stages))
        .filter(PairJob.id == pair.id)
        .first()
    )


@router.get("/pairs", response_model=list[PairJobListItem])
def list_pair_jobs(_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(PairJob).order_by(PairJob.id.desc()).all()


@router.get("/pairs/{pair_id}", response_model=PairJobOut)
def get_pair_job(pair_id: int, _user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    pair = (
        db.query(PairJob)
        .options(joinedload(PairJob.stages))
        .filter(PairJob.id == pair_id)
        .first()
    )
    if not pair:
        raise HTTPException(status_code=404, detail="配对作业不存在")
    return pair


@router.get("/pairs/{pair_id}/stages", response_model=list[PairStageOut])
def get_pair_job_stages(
    pair_id: int, _user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    pair = db.query(PairJob).filter(PairJob.id == pair_id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="配对作业不存在")
    return (
        db.query(PairJobStage)
        .filter(PairJobStage.pair_job_id == pair_id)
        .order_by(PairJobStage.stage_order)
        .all()
    )
