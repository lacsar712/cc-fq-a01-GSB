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


class PairRun(Base):
    """一次双端配对质控：R1/R2 两条读段各自走一条 Actor 链。"""

    __tablename__ = "pair_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/success/partial/failed
    r1_name: Mapped[str] = mapped_column(String(128), default="自定义输入")
    r2_name: Mapped[str] = mapped_column(String(128), default="自定义输入")
    r1_sample_id: Mapped[int | None] = mapped_column(ForeignKey("samples.id"), nullable=True)
    r2_sample_id: Mapped[int | None] = mapped_column(ForeignKey("samples.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    failed_side: Mapped[str | None] = mapped_column(String(8), nullable=True)  # r1/r2/both
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    jobs: Mapped[list["Job"]] = relationship(
        "Job",
        back_populates="pair_run",
        cascade="all, delete-orphan",
        order_by="Job.pair_side_order",
    )


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
    # 配对子系统：该作业属于哪次配对、充当哪一侧（r1/r2）
    pair_id: Mapped[int | None] = mapped_column(ForeignKey("pair_runs.id"), nullable=True)
    pair_side: Mapped[str] = mapped_column(String(4), nullable=True)  # r1/r2
    pair_side_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    stages: Mapped[list["JobStage"]] = relationship(
        "JobStage", back_populates="job", cascade="all, delete-orphan", order_by="JobStage.stage_order"
    )
    sample: Mapped[Sample | None] = relationship(foreign_keys=[sample_id])
    pair_run: Mapped[PairRun | None] = relationship(back_populates="jobs")


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

    job: Mapped[Job] = relationship(back_populates="stages")
