from fastapi import APIRouter, Depends, BackgroundTasks, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
import httpx

from app.database import get_db, engine
from app import service
from app.config import settings

router = APIRouter()


class ServiceConfigIn(BaseModel):
    service_id: str
    service_name: str
    github_repo: str
    github_branch: str = "main"


@router.get("/status")
async def get_status(db: Session = Depends(get_db)):
    return service.get_status_summary(db)


@router.get("/health")
async def health_check():
    """Check connectivity to PostgreSQL, Railway API, and GitHub API."""
    health = {
        "postgres": {"ok": False, "error": None},
        "railway": {"ok": False, "error": None},
        "github": {"ok": False, "error": None}
    }

    # Test PostgreSQL
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health["postgres"]["ok"] = True
    except Exception as e:
        health["postgres"]["error"] = str(e)

    # Test Railway API
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://backboard.railway.app/graphql/v2",
                json={"query": "query { me { id } }"},
                headers={
                    "Authorization": f"Bearer {settings.railway_token}",
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            if resp.status_code == 200:
                data = resp.json()
                if "errors" in data:
                    health["railway"]["error"] = data["errors"][0]["message"]
                else:
                    health["railway"]["ok"] = True
            else:
                health["railway"]["error"] = f"HTTP {resp.status_code}"
    except Exception as e:
        health["railway"]["error"] = str(e)

    # Test GitHub API
    try:
        async with httpx.AsyncClient() as client:
            headers = {"Accept": "application/vnd.github+json"}
            if settings.github_token:
                headers["Authorization"] = f"Bearer {settings.github_token}"
            resp = await client.get(
                "https://api.github.com/user",
                headers=headers,
                timeout=10.0
            )
            if resp.status_code == 200:
                health["github"]["ok"] = True
            elif resp.status_code == 401:
                health["github"]["error"] = "Invalid token"
            else:
                health["github"]["error"] = f"HTTP {resp.status_code}"
    except Exception as e:
        health["github"]["error"] = str(e)

    all_ok = all(h["ok"] for h in health.values())
    return {"ok": all_ok, "checks": health}


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


@router.get("/railway/services")
async def list_railway_services():
    """All Railway services across all projects — for dropdown."""
    from app.railway import RailwayClient
    client = RailwayClient()
    try:
        return await client.list_all_services()
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})


@router.get("/railway/debug")
async def railway_debug():
    """Raw Railway API response for debugging."""
    from app.railway import RailwayClient
    client = RailwayClient()
    result = await client.query("query { projects { edges { node { id name } } } }")
    return result


@router.get("/github/repos")
async def list_github_repos():
    """All GitHub repos the token can access — for dropdown."""
    from app.github import GitHubClient
    client = GitHubClient()
    try:
        return await client.list_repos()
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})


@router.post("/webhook/railway")
async def railway_webhook(request: Request, db: Session = Depends(get_db)):
    """Receives Railway deployment status webhooks for instant updates."""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    await service.process_webhook(db, payload)
    return {"ok": True}


@router.delete("/webhook/logs")
async def clear_webhook_logs(db: Session = Depends(get_db)):
    """Clear all webhook logs."""
    from app.models import WebhookLog
    db.query(WebhookLog).delete()
    db.commit()
    return {"ok": True}


@router.get("/webhook/logs")
async def webhook_logs(db: Session = Depends(get_db)):
    logs = service.get_webhook_logs(db, limit=50)
    return [
        {
            "id": l.id,
            "received_at": _dt(l.received_at),
            "project_name": l.project_name,
            "service_name": l.service_name,
            "status": l.status,
            "deployment_id": l.deployment_id,
            "raw_payload": l.raw_payload
        }
        for l in logs
    ]


@router.post("/webhook/register")
async def register_webhooks():
    """Auto-register the webhook URL on all Railway projects."""
    from app.railway import RailwayClient
    client = RailwayClient()
    webhook_url = f"{settings.app_url}/api/webhook/railway"
    results = await client.register_webhook_all_projects(webhook_url)
    return results


def _dt(dt):
    if not dt:
        return None
    s = dt.isoformat()
    if not s.endswith('Z') and '+' not in s:
        s += 'Z'
    return s


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
