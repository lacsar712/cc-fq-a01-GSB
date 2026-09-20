from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Boolean, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Sample(Base):
    __tablename__ = "samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(512), default="")
    is_broken: Mapped[bool] = mapped_column(Boolean, default=False)
    fastq_content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sample_id: Mapped[int | None] = mapped_column(ForeignKey("samples.id"), nullable=True)
    sample_name: Mapped[str] = mapped_column(String(128), default="自定义输入")
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/success/failed
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fastq_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    stages: Mapped[list["JobStage"]] = relationship(
        "JobStage", back_populates="job", cascade="all, delete-orphan", order_by="JobStage.stage_order"
    )
    sample: Mapped[Sample | None] = relationship("Sample")


class JobStage(Base):
    __tablename__ = "job_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/success/failed/skipped
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[Job] = relationship("Job", back_populates="stages")


class PairJob(Base):
    """双端配对质控：R1/R2 两条读段各自独立跑 Actor 链，单侧失败不影响另一侧。"""

    __tablename__ = "pair_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/success/partial/failed
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # R1 侧
    r1_sample_id: Mapped[int | None] = mapped_column(ForeignKey("samples.id"), nullable=True)
    r1_sample_name: Mapped[str] = mapped_column(String(128), default="自定义输入")
    r1_fastq_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    r1_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/success/failed
    r1_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    r1_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # R2 侧
    r2_sample_id: Mapped[int | None] = mapped_column(ForeignKey("samples.id"), nullable=True)
    r2_sample_name: Mapped[str] = mapped_column(String(128), default="自定义输入")
    r2_fastq_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    r2_status: Mapped[str] = mapped_column(String(32), default="pending")
    r2_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    r2_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    stages: Mapped[list["PairJobStage"]] = relationship(
        "PairJobStage",
        back_populates="pair_job",
        cascade="all, delete-orphan",
        order_by="PairJobStage.stage_order",
    )
    r1_sample: Mapped[Sample | None] = relationship("Sample", foreign_keys=[r1_sample_id])
    r2_sample: Mapped[Sample | None] = relationship("Sample", foreign_keys=[r2_sample_id])


class PairJobStage(Base):
    __tablename__ = "pair_job_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pair_job_id: Mapped[int] = mapped_column(ForeignKey("pair_jobs.id"), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # R1 / R2
    actor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/success/failed/skipped
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    pair_job: Mapped[PairJob] = relationship("PairJob", back_populates="stages")
