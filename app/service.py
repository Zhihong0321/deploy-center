from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.models import Deployment, Project, ServiceConfig, GitHubSnapshot
from app.railway import RailwayClient
from app.github import GitHubClient


def _compute_sync_status(deployed_sha: Optional[str], github_sha: Optional[str], deploy_status: str) -> str:
    if deploy_status in ("FAILED", "CRASHED"):
        return "FAILED"
    if not deployed_sha or not github_sha:
        return "UNKNOWN"
    if deployed_sha.startswith(github_sha) or github_sha.startswith(deployed_sha):
        return "IN_SYNC"
    return "BEHIND"


async def sync_all(db: Session) -> Dict[str, Any]:
    railway = RailwayClient()
    github = GitHubClient()

    synced = 0
    errors = []

    # Load all service→repo mappings
    configs: Dict[str, ServiceConfig] = {
        c.service_id: c for c in db.query(ServiceConfig).all()
    }

    # Refresh GitHub snapshots for all mapped repos
    github_cache: Dict[str, Optional[Dict]] = {}
    for cfg in configs.values():
        repo_key = f"{cfg.github_repo}:{cfg.github_branch}"
        if repo_key not in github_cache:
            try:
                commit = await github.get_latest_commit(cfg.github_repo, cfg.github_branch)
                github_cache[repo_key] = commit
                if commit:
                    snap = db.query(GitHubSnapshot).filter(GitHubSnapshot.repo == cfg.github_repo).first()
                    if not snap:
                        snap = GitHubSnapshot(repo=cfg.github_repo)
                        db.add(snap)
                    snap.branch = cfg.github_branch
                    snap.sha = commit["sha"]
                    snap.short_sha = commit["short_sha"]
                    snap.message = commit["message"]
                    snap.author = commit["author"]
                    snap.committed_at = datetime.fromisoformat(commit["date"].replace("Z", "+00:00"))
                    snap.url = commit["url"]
                    snap.fetched_at = datetime.utcnow()
            except Exception as e:
                github_cache[repo_key] = None
                errors.append(f"GitHub {cfg.github_repo}: {str(e)}")

    projects_data = await railway.get_projects()

    for project_edge in projects_data:
        project = project_edge["node"]
        project_id = project["id"]
        project_name = project["name"]

        db_project = db.query(Project).filter(Project.id == project_id).first()
        if not db_project:
            db_project = Project(id=project_id, name=project_name)
            db.add(db_project)
        db_project.last_synced_at = datetime.utcnow()

        for service_edge in project.get("services", {}).get("edges", []):
            service = service_edge["node"]
            service_id = service["id"]
            service_name = service["name"]

            cfg = configs.get(service_id)
            github_commit = None
            if cfg:
                repo_key = f"{cfg.github_repo}:{cfg.github_branch}"
                github_commit = github_cache.get(repo_key)

            try:
                deployments = await railway.get_deployments(service_id, limit=5)
                for dep_edge in deployments:
                    dep = dep_edge["node"]
                    dep_id = dep["id"]
                    status = dep["status"]

                    db_dep = db.query(Deployment).filter(Deployment.id == dep_id).first()
                    if db_dep and db_dep.status == status and not github_commit:
                        continue  # No change

                    meta = dep.get("meta") or {}
                    commit_sha = meta.get("commitHash") or meta.get("commitSha")
                    commit_message = meta.get("commitMessage")
                    commit_author = meta.get("commitAuthor")

                    error_log = None
                    if status in ("FAILED", "CRASHED"):
                        error_log = await railway.get_deployment_logs(dep_id)

                    if not db_dep:
                        db_dep = Deployment(id=dep_id)
                        db.add(db_dep)

                    db_dep.service_id = service_id
                    db_dep.service_name = service_name
                    db_dep.project_id = project_id
                    db_dep.project_name = project_name
                    db_dep.environment = dep.get("environment", {}).get("name", "production")
                    db_dep.status = status
                    db_dep.created_at = datetime.fromisoformat(dep["createdAt"].replace("Z", "+00:00"))
                    db_dep.updated_at = datetime.fromisoformat(dep["updatedAt"].replace("Z", "+00:00"))
                    db_dep.commit_sha = commit_sha
                    db_dep.commit_message = commit_message
                    db_dep.commit_author = commit_author
                    db_dep.error_log = error_log
                    db_dep.fetched_at = datetime.utcnow()

                    synced += 1

            except Exception as e:
                errors.append(f"{service_name}: {str(e)}")

    db.commit()
    return {"synced": synced, "errors": errors}


def get_services_view(db: Session) -> List[Dict[str, Any]]:
    """Per-service summary: latest Railway deployment + latest GitHub commit + sync_status."""
    configs = db.query(ServiceConfig).all()
    snapshots = {s.repo: s for s in db.query(GitHubSnapshot).all()}

    # Get latest deployment per service
    from sqlalchemy import func
    subq = (
        db.query(Deployment.service_id, func.max(Deployment.created_at).label("max_created"))
        .group_by(Deployment.service_id)
        .subquery()
    )
    latest_deps = (
        db.query(Deployment)
        .join(subq, (Deployment.service_id == subq.c.service_id) & (Deployment.created_at == subq.c.max_created))
        .all()
    )
    dep_by_service = {d.service_id: d for d in latest_deps}

    # Build per-service rows — include all services we know about
    service_ids = set(dep_by_service.keys()) | {c.service_id for c in configs}
    cfg_by_service = {c.service_id: c for c in configs}

    rows = []
    for sid in service_ids:
        dep = dep_by_service.get(sid)
        cfg = cfg_by_service.get(sid)
        snap = snapshots.get(cfg.github_repo) if cfg else None

        github_sha = snap.sha if snap else None
        deployed_sha = dep.commit_sha if dep else None
        deploy_status = dep.status if dep else "UNKNOWN"

        sync_status = _compute_sync_status(deployed_sha, github_sha, deploy_status)

        rows.append({
            "service_id": sid,
            "service_name": dep.service_name if dep else (cfg.service_name if cfg else sid),
            "project_name": dep.project_name if dep else None,
            "github_repo": cfg.github_repo if cfg else None,
            "github_branch": cfg.github_branch if cfg else None,
            # Railway side
            "railway": {
                "status": deploy_status,
                "deployment_id": dep.id if dep else None,
                "commit_sha": deployed_sha,
                "commit_message": dep.commit_message if dep else None,
                "commit_author": dep.commit_author if dep else None,
                "deployed_at": dep.created_at.isoformat() if dep and dep.created_at else None,
            },
            # GitHub side
            "github": {
                "sha": snap.sha if snap else None,
                "short_sha": snap.short_sha if snap else None,
                "message": snap.message if snap else None,
                "author": snap.author if snap else None,
                "committed_at": snap.committed_at.isoformat() if snap and snap.committed_at else None,
                "url": snap.url if snap else None,
                "fetched_at": snap.fetched_at.isoformat() if snap and snap.fetched_at else None,
            },
            # Cross-reference
            "sync_status": sync_status,
        })

    rows.sort(key=lambda r: r["service_name"])
    return rows


def get_deployments(
    db: Session,
    limit: int = 50,
    status: Optional[str] = None,
    project_id: Optional[str] = None
) -> List[Deployment]:
    q = db.query(Deployment)
    if status:
        q = q.filter(Deployment.status == status)
    if project_id:
        q = q.filter(Deployment.project_id == project_id)
    return q.order_by(desc(Deployment.created_at)).limit(limit).all()


def get_deployment(db: Session, deployment_id: str) -> Optional[Deployment]:
    return db.query(Deployment).filter(Deployment.id == deployment_id).first()


def get_projects(db: Session) -> List[Project]:
    return db.query(Project).all()


def get_status_summary(db: Session) -> Dict[str, Any]:
    from sqlalchemy import func
    rows = db.query(Deployment.status, func.count(Deployment.id)).group_by(Deployment.status).all()
    counts = {row[0]: row[1] for row in rows}
    latest = db.query(Deployment).order_by(desc(Deployment.created_at)).first()
    return {
        "counts": counts,
        "latest": latest,
        "total": sum(counts.values())
    }


# --- ServiceConfig CRUD ---

def get_service_configs(db: Session) -> List[ServiceConfig]:
    return db.query(ServiceConfig).all()


def upsert_service_config(db: Session, service_id: str, service_name: str, github_repo: str, github_branch: str = "main") -> ServiceConfig:
    cfg = db.query(ServiceConfig).filter(ServiceConfig.service_id == service_id).first()
    if not cfg:
        cfg = ServiceConfig(service_id=service_id)
        db.add(cfg)
    cfg.service_name = service_name
    cfg.github_repo = github_repo
    cfg.github_branch = github_branch
    db.commit()
    db.refresh(cfg)
    return cfg


def delete_service_config(db: Session, service_id: str) -> bool:
    cfg = db.query(ServiceConfig).filter(ServiceConfig.service_id == service_id).first()
    if not cfg:
        return False
    db.delete(cfg)
    db.commit()
    return True


# --- Webhook processing ---

async def process_webhook(db: Session, payload: Dict[str, Any]) -> None:
    """Process Railway webhook payload and update deployment record instantly."""
    # Log the raw payload for debugging
    import json
    print(f"[WEBHOOK] Received payload: {json.dumps(payload, indent=2)}")

    # Railway webhook payload structure (actual structure TBD - logging above will show it)
    deployment_data = payload.get("deployment", {})
    service_data = payload.get("service", {})
    project_data = payload.get("project", {})
    environment_data = payload.get("environment", {})

    dep_id = deployment_data.get("id")
    if not dep_id:
        return

    service_id = service_data.get("id")
    service_name = service_data.get("name", "unknown")
    project_id = project_data.get("id")
    project_name = project_data.get("name", "unknown")
    status = deployment_data.get("status", "UNKNOWN")
    environment = environment_data.get("name", "production")

    meta = deployment_data.get("meta", {})
    commit_sha = meta.get("commitHash") or meta.get("commitSha")
    commit_message = meta.get("commitMessage")
    commit_author = meta.get("commitAuthor")

    created_at_str = deployment_data.get("createdAt")
    updated_at_str = deployment_data.get("updatedAt") or created_at_str

    # Upsert deployment
    db_dep = db.query(Deployment).filter(Deployment.id == dep_id).first()
    if not db_dep:
        db_dep = Deployment(id=dep_id)
        db.add(db_dep)

    db_dep.service_id = service_id
    db_dep.service_name = service_name
    db_dep.project_id = project_id
    db_dep.project_name = project_name
    db_dep.environment = environment
    db_dep.status = status
    db_dep.commit_sha = commit_sha
    db_dep.commit_message = commit_message
    db_dep.commit_author = commit_author

    if created_at_str:
        db_dep.created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
    if updated_at_str:
        db_dep.updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))

    db_dep.fetched_at = datetime.utcnow()

    # Fetch error logs if failed
    if status in ("FAILED", "CRASHED") and not db_dep.error_log:
        railway = RailwayClient()
        try:
            error_log = await railway.get_deployment_logs(dep_id)
            db_dep.error_log = error_log
        except Exception:
            pass

    db.commit()
