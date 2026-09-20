"""Seed database with demo users' samples (accounts are in-memory)."""

import time
from pathlib import Path

from sqlalchemy.exc import OperationalError

from app.database import Base, SessionLocal, engine
from app.models import Sample


DATA_DIR = Path(__file__).resolve().parent / "data"

SEED_SAMPLES = [
    {
        "name": "demo-good-r1",
        "description": "合格小型 FASTQ 样例（含少量 N），可作 R1",
        "is_broken": False,
        "file": "good.fastq",
    },
    {
        "name": "demo-good-r2",
        "description": "合格小型 FASTQ 样例（含少量 N），可作 R2",
        "is_broken": False,
        "file": "good_r2.fastq",
    },
    {
        "name": "demo-broken-malformed",
        "description": "损坏样例：缺少 + 分隔行 / 长度不一致，ParseActor 应失败",
        "is_broken": True,
        "file": "broken.fastq",
    },
]


def wait_for_db(retries: int = 30, delay: float = 1.0) -> None:
    for i in range(retries):
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            return
        except OperationalError:
            print(f"waiting for db... ({i + 1}/{retries})")
            time.sleep(delay)
    raise RuntimeError("database not ready")


def seed() -> None:
    wait_for_db()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 按名称幂等：已存在的样例跳过，新增样例（如 demo-good-r2）在重复启动时也能补齐
        created = 0
        for spec in SEED_SAMPLES:
            exists = db.query(Sample).filter(Sample.name == spec["name"]).first()
            if exists:
                continue
            content = (DATA_DIR / spec["file"]).read_text(encoding="utf-8")
            db.add(
                Sample(
                    name=spec["name"],
                    description=spec["description"],
                    is_broken=spec["is_broken"],
                    fastq_content=content,
                )
            )
            created += 1
        db.commit()
        print(f"seeded {created} new samples")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
