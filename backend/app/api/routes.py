"""Run endpoints. Long experiments return immediately and the client polls."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from app.core.config import ROOT
from app.models.schemas import Report, RunConfig, RunCreated, RunView
from app.orchestration.run import RunCancelled, execute_run
from app.sim.energy import ENERGY_VERSION
from app.sim.gripper import SIMULATOR_VERSION

logger = logging.getLogger("swarm.api")
router = APIRouter()


def _view(row: dict) -> RunView:
    report = None
    if row.get("report_json"):
        report = Report.model_validate_json(row["report_json"])
    progress = json.loads(row.get("progress_json") or "{}")
    return RunView(
        id=row["id"],
        status=row["status"],
        domain=row["domain"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        progress=progress,
        error=row.get("error"),
        report=report,
    )


def _execute_and_store(db, settings, run_id: str, config: RunConfig) -> None:
    try:
        report, candidates, failures = execute_run(
            config,
            settings,
            run_id,
            on_progress=lambda progress: db.update_progress(run_id, progress),
            should_cancel=lambda: db.cancel_requested(run_id),
        )
        db.complete(run_id, report, candidates, failures)
    except RunCancelled:
        db.fail(run_id, "Cancelled", status="CANCELLED")
    except Exception as exc:
        logger.exception("run %s failed", run_id)
        db.fail(run_id, str(exc))


@router.get("/health")
def health(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "simulator_version": SIMULATOR_VERSION,
        "energy_version": ENERGY_VERSION,
        "enable_meta": settings.enable_meta,
        "model": settings.meta_model,
    }


@router.post("/runs", response_model=RunCreated)
def create_run(body: RunConfig, request: Request) -> RunCreated:
    db = request.app.state.db
    settings = request.app.state.settings
    run_id = uuid4().hex
    db.create_run(run_id, body.domain, body.model_dump(mode="json"))
    if body.blocking:
        _execute_and_store(db, settings, run_id, body)
        row = db.get_run(run_id)
        return RunCreated(id=run_id, status=row["status"] if row else "FAILED")
    request.app.state.pool.submit(_execute_and_store, db, settings, run_id, body)
    return RunCreated(id=run_id, status="PENDING")


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, request: Request) -> dict:
    db = request.app.state.db
    row = db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    if row["status"] in {"COMPLETE", "FAILED", "CANCELLED"}:
        return {"id": run_id, "status": row["status"], "cancel_requested": False}
    db.request_cancel(run_id)
    return {"id": run_id, "status": row["status"], "cancel_requested": True}


@router.post("/runs/{run_id}/retry", response_model=RunCreated)
def retry_run(run_id: str, request: Request) -> RunCreated:
    db = request.app.state.db
    row = db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    config = RunConfig.model_validate_json(row["config_json"])
    config.blocking = False
    return create_run(config, request)


@router.get("/runs/{run_id}", response_model=RunView)
def get_run(run_id: str, request: Request) -> RunView:
    row = request.app.state.db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    return _view(row)


@router.get("/runs/{run_id}/candidates")
def get_candidates(run_id: str, request: Request) -> list:
    if request.app.state.db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    return request.app.state.db.get_candidates(run_id)


@router.get("/runs/{run_id}/failures")
def get_failures(run_id: str, request: Request) -> list:
    if request.app.state.db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    return request.app.state.db.get_failures(run_id)


@router.get("/runs/{run_id}/report", response_model=Report)
def get_report(run_id: str, request: Request) -> Report:
    row = request.app.state.db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    if not row.get("report_json"):
        raise HTTPException(status_code=409, detail="report is not ready")
    return Report.model_validate_json(row["report_json"])


@router.get("/demo/hero")
def demo_hero() -> dict:
    candidates = [
        ROOT / "experiments" / "hero_run.json",
        ROOT / "frontend" / "public" / "demo" / "hero.json",
    ]
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="hero run has not been exported")
