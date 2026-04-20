# Deploy Center

Railway deployment monitoring and control hub for AI agents.

## Features

- **Full picture view**: GitHub latest commit + Railway deployed commit side-by-side
- **Sync status detection**: IN_SYNC, BEHIND, FAILED states per service
- **Real-time deployment tracking** from Railway
- **Error log capture** on failed deployments
- **REST API** for AI agent access
- **Fast dashboard** with 3 tabs: Services, Deployments, Repo Mapping

## How It Works

```
Your code → git push → GitHub
                          ↓
                    Railway deploys
                          ↓
            Deploy-center polls both:
            - Railway API (deployment status, logs)
            - GitHub API (latest commit)
                          ↓
            Compares commit SHAs
                          ↓
            Shows sync status:
            - IN_SYNC: deployed == latest
            - BEHIND: new commits not deployed
            - FAILED: deployment failed
```

## Setup

### 1. Environment Variables

Create `.env` file:

```env
DATABASE_URL=postgresql://user:pass@host:port/dbname
RAILWAY_TOKEN=your_railway_api_token
GITHUB_TOKEN=your_github_token
POLL_INTERVAL_SECONDS=60
```

**Get Railway Token:**
1. Go to https://railway.app/account/tokens
2. Create new token
3. Copy and paste into `.env`

**Get GitHub Token:**
1. Go to https://github.com/settings/tokens
2. Generate new token (classic)
3. Select `repo` scope (read-only is fine)
4. Copy and paste into `.env`

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run Locally

```bash
python main.py
```

Visit http://localhost:8000

### 4. Configure Repo Mappings

Go to the **Repo Mapping** tab in the dashboard and add each Railway service:

- **Service ID**: Copy from Railway dashboard URL (e.g., `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
- **Service Name**: Display name (e.g., `my-api`)
- **GitHub Repo**: `owner/repo` format (e.g., `myorg/my-api`)
- **Branch**: Usually `main` or `master`

Click **Add / Update** to save.

### 5. Deploy to Railway

1. Push this repo to GitHub
2. Create new Railway project from GitHub repo → select `deploy-center`
3. Add PostgreSQL database (Railway auto-injects `DATABASE_URL`)
4. Add environment variables:
   - `RAILWAY_TOKEN`
   - `GITHUB_TOKEN`
5. Deploy

## API Endpoints

### `GET /api/status`
Summary stats (total, success, failed, deploying counts)

### `GET /api/services`
**Full picture per service** — GitHub latest + Railway deployed + sync status

Response:
```json
[
  {
    "service_id": "xxx",
    "service_name": "my-api",
    "project_name": "My Project",
    "github_repo": "myorg/my-api",
    "github_branch": "main",
    "railway": {
      "status": "SUCCESS",
      "deployment_id": "yyy",
      "commit_sha": "abc1234",
      "commit_message": "Fix bug",
      "deployed_at": "2026-04-20T10:30:00Z"
    },
    "github": {
      "sha": "def5678",
      "short_sha": "def5678",
      "message": "Add feature",
      "author": "John Doe",
      "committed_at": "2026-04-20T11:00:00Z",
      "url": "https://github.com/myorg/my-api/commit/def5678"
    },
    "sync_status": "BEHIND"
  }
]
```

### `GET /api/deployments`
List all deployments
- Query params: `limit`, `status`, `project_id`

### `GET /api/deployments/{id}`
Get single deployment with full error log

### `GET /api/projects`
List all Railway projects

### `POST /api/refresh`
Manually trigger sync from Railway + GitHub

### `GET /api/configs`
List all service→repo mappings

### `POST /api/configs`
Add or update a service→repo mapping

Body:
```json
{
  "service_id": "xxx",
  "service_name": "my-api",
  "github_repo": "myorg/my-api",
  "github_branch": "main"
}
```

### `DELETE /api/configs/{service_id}`
Remove a service→repo mapping

## AI Agent Usage

### Check sync status across all services

```python
import httpx

async with httpx.AsyncClient() as client:
    resp = await client.get("https://your-deploy-center.railway.app/api/services")
    services = resp.json()
    
    for svc in services:
        if svc["sync_status"] == "BEHIND":
            print(f"⚠️  {svc['service_name']} is behind")
            print(f"   GitHub latest: {svc['github']['short_sha']} - {svc['github']['message']}")
            print(f"   Railway deployed: {svc['railway']['commit_sha'][:7]}")
        
        elif svc["sync_status"] == "FAILED":
            print(f"❌ {svc['service_name']} deployment failed")
            # Fetch full error log
            dep_id = svc["railway"]["deployment_id"]
            resp = await client.get(f"https://your-deploy-center.railway.app/api/deployments/{dep_id}")
            detail = resp.json()
            print(f"   Error: {detail['error_log'][:200]}...")
```

### Auto-fix workflow (future skill)

After you set this up, we can create a skill that:
1. Monitors `/api/services` every 60s
2. Detects `FAILED` status
3. Fetches error log
4. Analyzes error
5. Fixes code
6. Pushes fix
7. Waits for Railway to redeploy
8. Verifies `IN_SYNC`

## Dashboard

**Services tab**: Full picture — GitHub vs Railway side-by-side with sync status badges

**Deployments tab**: Historical deployment log with error logs

**Repo Mapping tab**: Configure which GitHub repo belongs to which Railway service

Auto-refreshes every 60 seconds.

## Database Schema

**deployments** table:
- Railway deployment records with commit info and error logs

**projects** table:
- Railway projects

**service_configs** table:
- Manual mapping: Railway service_id → GitHub owner/repo + branch

**github_snapshots** table:
- Latest commit per repo, refreshed on every sync

## Sync Status Logic

| Status | Meaning |
|---|---|
| `IN_SYNC` | GitHub latest SHA == Railway deployed SHA |
| `BEHIND` | GitHub has newer commits not yet deployed |
| `FAILED` | Railway deployment failed (error log available) |
| `UNKNOWN` | No GitHub mapping or no deployment data |
