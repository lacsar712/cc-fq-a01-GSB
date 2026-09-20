"""Shared pytest setup: fall back to a local SQLite file when no DATABASE_URL
is provided, so API tests can run without a Postgres server."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./fastq_qc_test.db")
