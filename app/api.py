from fastapi import APIRouter, Depends, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app import service

router = APIRouter()


class ServiceConfigIn(BaseModel):
    service_id: str
    service_name: str
    github_repo: str
    github_branch: str = "main"


@router.get("/status")
async def get_status(db: Session = Depends(get_db)):
    return service.get_status_summary(db)


@router.get("/services")
async def list_services(db: Session = Depends(get_db)):
    """Full picture: Railway + GitHub side by side per service."""
    return service.get_services_view(db)


@router.get("/deployments")
async def list_deployments(
    limit: int = Query(50, le=200),
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    deployments = service.get_deployments(db, limit=limit, status=status, project_id=project_id)
    return [_serialize(d) for d in deployments]


@router.get("/deployments/{deployment_id}")
async def get_deployment(deployment_id: str, db: Session = Depends(get_db)):
    dep = service.get_deployment(db, deployment_id)
    if not dep:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return _serialize(dep, include_logs=True)


@router.get("/projects")
async def list_projects(db: Session = Depends(get_db)):
    projects = service.get_projects(db)
    return [{"id": p.id, "name": p.name, "github_repo": p.github_repo, "last_synced_at": _dt(p.last_synced_at)} for p in projects]


@router.post("/refresh")
async def refresh(db: Session = Depends(get_db)):
    result = await service.sync_all(db)
    return {"ok": True, "synced": result["synced"], "errors": result["errors"]}


# --- Service config (repo mappings) ---

@router.get("/configs")
async def list_configs(db: Session = Depends(get_db)):
    configs = service.get_service_configs(db)
    return [{"service_id": c.service_id, "service_name": c.service_name, "github_repo": c.github_repo, "github_branch": c.github_branch} for c in configs]


@router.post("/configs")
async def upsert_config(body: ServiceConfigIn, db: Session = Depends(get_db)):
    cfg = service.upsert_service_config(db, body.service_id, body.service_name, body.github_repo, body.github_branch)
    return {"ok": True, "service_id": cfg.service_id}


@router.delete("/configs/{service_id}")
async def delete_config(service_id: str, db: Session = Depends(get_db)):
    deleted = service.delete_service_config(db, service_id)
    if not deleted:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return {"ok": True}


def _dt(dt):
    return dt.isoformat() if dt else None


def _serialize(d, include_logs=False):
    out = {
        "id": d.id,
        "service_id": d.service_id,
        "service_name": d.service_name,
        "project_id": d.project_id,
        "project_name": d.project_name,
        "environment": d.environment,
        "status": d.status,
        "created_at": _dt(d.created_at),
        "updated_at": _dt(d.updated_at),
        "fetched_at": _dt(d.fetched_at),
        "commit_sha": d.commit_sha,
        "commit_message": d.commit_message,
        "commit_author": d.commit_author,
        "commit_url": d.commit_url,
    }
    if include_logs:
        out["error_log"] = d.error_log
    return out
