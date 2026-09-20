from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api import router
from app.database import Base, engine


# 轻量迁移：在旧版 jobs 表上补齐配对子系统新增列（开发环境无 Alembic）
_JOBS_ADDED_COLUMNS = {
    "pair_id": "INTEGER REFERENCES pair_runs(id)",
    "pair_side": "VARCHAR(4)",
    "pair_side_order": "INTEGER NOT NULL DEFAULT 0",
}


def _ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if "jobs" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("jobs")}
    with engine.begin() as conn:
        for name, ddl in _JOBS_ADDED_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _ensure_schema()
    yield


app = FastAPI(title="FASTQ QC Pipeline Console", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
