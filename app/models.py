from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(String, primary_key=True)  # Railway deployment ID
    service_id = Column(String, nullable=False, index=True)
    service_name = Column(String, nullable=False)
    project_id = Column(String, nullable=False)
    project_name = Column(String, nullable=False)
    environment = Column(String, nullable=False, default="production")
    status = Column(String, nullable=False)  # SUCCESS, FAILED, DEPLOYING, CRASHED, etc.
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    # Railway deployed commit
    commit_sha = Column(String, nullable=True)
    commit_message = Column(String, nullable=True)
    commit_author = Column(String, nullable=True)
    commit_url = Column(String, nullable=True)
    # Error log (only populated on failure)
    error_log = Column(Text, nullable=True)
    # Meta
    fetched_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    github_repo = Column(String, nullable=True)  # owner/repo
    last_synced_at = Column(DateTime, nullable=True)


class ServiceConfig(Base):
    """Manual mapping: Railway service_id → GitHub owner/repo"""
    __tablename__ = "service_configs"

    service_id = Column(String, primary_key=True)
    service_name = Column(String, nullable=False)
    github_repo = Column(String, nullable=False)  # owner/repo
    github_branch = Column(String, nullable=False, default="main")


class GitHubSnapshot(Base):
    """Latest GitHub commit per repo, refreshed on every sync"""
    __tablename__ = "github_snapshots"

    repo = Column(String, primary_key=True)  # owner/repo
    branch = Column(String, nullable=False, default="main")
    sha = Column(String, nullable=False)
    short_sha = Column(String, nullable=False)
    message = Column(String, nullable=True)
    author = Column(String, nullable=True)
    committed_at = Column(DateTime, nullable=True)
    url = Column(String, nullable=True)
    fetched_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
