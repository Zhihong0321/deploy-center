from sqlalchemy import Column, String, DateTime, Text, Integer
from sqlalchemy.sql import func
from app.database import Base


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(String, primary_key=True)
    service_id = Column(String, nullable=False, index=True)
    service_name = Column(String, nullable=False)
    project_id = Column(String, nullable=False)
    project_name = Column(String, nullable=False)
    environment = Column(String, nullable=False, default="production")
    status = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    commit_sha = Column(String, nullable=True)
    commit_message = Column(String, nullable=True)
    commit_author = Column(String, nullable=True)
    commit_url = Column(String, nullable=True)
    error_log = Column(Text, nullable=True)
    fetched_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    github_repo = Column(String, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)


class ServiceConfig(Base):
    __tablename__ = "service_configs"

    service_id = Column(String, primary_key=True)
    service_name = Column(String, nullable=False)
    github_repo = Column(String, nullable=False)
    github_branch = Column(String, nullable=False, default="main")


class GitHubSnapshot(Base):
    __tablename__ = "github_snapshots"

    repo = Column(String, primary_key=True)
    branch = Column(String, nullable=False, default="main")
    sha = Column(String, nullable=False)
    short_sha = Column(String, nullable=False)
    message = Column(String, nullable=True)
    author = Column(String, nullable=True)
    committed_at = Column(DateTime, nullable=True)
    url = Column(String, nullable=True)
    fetched_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class WebhookLog(Base):
    """Every incoming Railway webhook call — last 200 kept."""
    __tablename__ = "webhook_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    received_at = Column(DateTime, server_default=func.now(), index=True)
    project_name = Column(String, nullable=True)
    service_name = Column(String, nullable=True)
    status = Column(String, nullable=True)
    deployment_id = Column(String, nullable=True)
    raw_payload = Column(Text, nullable=True)

