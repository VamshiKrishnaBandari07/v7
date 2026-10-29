"""Run metadata in SQLite. Sample scores live in JSON payloads."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import Field, Session, SQLModel, col, create_engine, select

from app.models.schemas import CandidateRecord, FailureRecord, Report


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunRow(SQLModel, table=True):
    __tablename__ = "runs"
    id: str = Field(primary_key=True)
    status: str
    domain: str
    config_json: str
    progress_json: str = "{}"
    report_json: str | None = None
    error: str | None = None
    cancel_requested: bool = False
    created_at: str
    updated_at: str


class CandidateRow(SQLModel, table=True):
    __tablename__ = "candidates"
    key: str = Field(primary_key=True)
    run_id: str = Field(index=True)
    seq: int
    payload_json: str


class FailureRow(SQLModel, table=True):
    __tablename__ = "failures"
    key: str = Field(primary_key=True)
    run_id: str = Field(index=True)
    seq: int
    payload_json: str


class Database:
    def __init__(self, url: str) -> None:
        if url.startswith("sqlite:///"):
            raw = url[len("sqlite:///") :]
            if raw and raw != ":memory:":
                Path(raw).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, connect_args={"check_same_thread": False})
        self._lock = threading.Lock()

    def init(self) -> None:
        SQLModel.metadata.create_all(self.engine)

    def create_run(self, run_id: str, domain: str, config: dict[str, Any]) -> None:
        now = _now()
        row = RunRow(
            id=run_id,
            status="PENDING",
            domain=domain,
            config_json=json.dumps(config),
            progress_json=json.dumps({"phase": "PENDING", "message": "Queued"}),
            created_at=now,
            updated_at=now,
        )
        with self._lock, Session(self.engine) as session:
            session.add(row)
            session.commit()

    def update_progress(self, run_id: str, progress: dict[str, Any]) -> None:
        with self._lock, Session(self.engine) as session:
            row = session.get(RunRow, run_id)
            if row is None or row.status in {"COMPLETE", "FAILED", "CANCELLED"}:
                return
            row.progress_json = json.dumps(progress)
            phase = str(progress.get("phase") or row.status)
            if phase in {"PLANNING", "SIMULATING", "EVOLVING", "VALIDATING"}:
                row.status = phase
            row.updated_at = _now()
            session.add(row)
            session.commit()

    def request_cancel(self, run_id: str) -> bool:
        with self._lock, Session(self.engine) as session:
            row = session.get(RunRow, run_id)
            if row is None:
                return False
            row.cancel_requested = True
            row.updated_at = _now()
            session.add(row)
            session.commit()
            return True

    def cancel_requested(self, run_id: str) -> bool:
        with self._lock, Session(self.engine) as session:
            row = session.get(RunRow, run_id)
            return bool(row and row.cancel_requested)

    def complete(
        self,
        run_id: str,
        report: Report,
        candidates: list[CandidateRecord],
        failures: list[FailureRecord],
    ) -> None:
        with self._lock, Session(self.engine) as session:
            row = session.get(RunRow, run_id)
            if row is None:
                return
            row.status = "COMPLETE"
            row.error = None
            row.report_json = report.model_dump_json()
            row.progress_json = json.dumps(
                {
                    "phase": "COMPLETE",
                    "message": "Experiment finished",
                    "simulator_calls": report.total_search_calls,
                    "budget": report.config.get("budget", {}).get("total_simulator_calls"),
                    "best_score": _best_fitness(report),
                    "best_success_rate": _best_success(report),
                }
            )
            row.updated_at = _now()
            session.add(row)
            for seq, candidate in enumerate(candidates):
                session.add(
                    CandidateRow(
                        key=f"{run_id}:{seq}:{candidate.id}",
                        run_id=run_id,
                        seq=seq,
                        payload_json=candidate.model_dump_json(),
                    )
                )
            for seq, failure in enumerate(failures):
                session.add(
                    FailureRow(
                        key=f"{run_id}:f:{seq}:{failure.id}",
                        run_id=run_id,
                        seq=seq,
                        payload_json=failure.model_dump_json(),
                    )
                )
            session.commit()

    def fail(self, run_id: str, message: str, status: str = "FAILED") -> None:
        with self._lock, Session(self.engine) as session:
            row = session.get(RunRow, run_id)
            if row is None:
                return
            row.status = status
            row.error = message[:500] if message else None
            row.updated_at = _now()
            session.add(row)
            session.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock, Session(self.engine) as session:
            row = session.get(RunRow, run_id)
            if row is None:
                return None
            return row.model_dump()

    def get_candidates(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock, Session(self.engine) as session:
            rows = session.exec(
                select(CandidateRow).where(CandidateRow.run_id == run_id).order_by(col(CandidateRow.seq))
            ).all()
            return [json.loads(row.payload_json) for row in rows]

    def get_failures(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock, Session(self.engine) as session:
            rows = session.exec(
                select(FailureRow).where(FailureRow.run_id == run_id).order_by(col(FailureRow.seq))
            ).all()
            return [json.loads(row.payload_json) for row in rows]


def _best_fitness(report: Report) -> float | None:
    values = [method.best.fitness for method in report.methods if method.best is not None]
    return max(values) if values else None


def _best_success(report: Report) -> float | None:
    values = [method.best.success_rate for method in report.methods if method.best is not None]
    return max(values) if values else None
