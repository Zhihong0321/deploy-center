# Deploy Center — AI Agent Guide

**Base URL:** `https://deploy-center-production.up.railway.app`

Deploy Center gives AI coding agents full visibility into Railway deployments: what's broken, what's behind GitHub, what's currently deploying, and complete error logs.

---

## Quick Start

### 1. Get the full picture in one call

```bash
GET /api/agent/overview
```

Returns:
- **summary**: counts (total services, failing, behind, deploying, in_sync)
- **failing[]**: services with FAILED/CRASHED status + error logs attached
- **behind[]**: services where GitHub has newer commits than Railway
- **deploying[]**: services currently building/deploying

**Use this at the start of every coding session** to know what's broken and what needs attention.

---

## Core Workflows

### Check if a service is broken

```bash
GET /api/services/failing
```

Returns only services with FAILED or CRASHED deploy status. Each includes the error log if available.

**Example response:**
```json
[
  {
    "service_id": "f856aa3e-3804-419b-9dbb-3b81bf0cfd46",
    "service_name": "ai-command-center",
    "project_name": "eternalgy-erp",
    "railway": {
      "status": "FAILED",
      "deployment_id": "7c2b6770-972b-4bf4-9d67-45bd0e6e2f6d",
      "commit_sha": "9bb083b8",
      "deployed_at": "2026-03-27T07:07:38.891000Z"
    },
    "sync_status": "FAILED",
    "error_log": "pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings..."
  }
]
```

---

### Check if a service needs deploying

```bash
GET /api/services/behind
```

Returns only services where GitHub has commits that Railway hasn't deployed yet.

**Example response:**
```json
[
  {
    "service_id": "23b89f64-9036-4780-a28e-4127db1c765b",
    "service_name": "Solar-Calculator",
    "railway": {
      "commit_sha": "a1689aef",
      "deployed_at": "2026-04-21T04:52:55.109000Z"
    },
    "github": {
      "sha": "46f64de3",
      "message": "Keep hybrid upgrade visible and disabled",
      "committed_at": "2026-04-14T16:29:44Z"
    },
    "sync_status": "BEHIND"
  }
]
```

---

### Get full status for one service

```bash
GET /api/services/{service_id}/status
```

Single call returns:
- Current deploy status
- Deployed commit vs GitHub latest commit
- Sync status (IN_SYNC / BEHIND / FAILED)
- Error log (if failed)
- Last 5 deployments

**Use this before touching a service** — you'll know exactly what state you're walking into.

---

### Trigger a deployment

```bash
POST /api/deploy/{service_id}
```

Kicks off a new Railway deployment. Returns:
```json
{
  "ok": true,
  "deployment_id": "abc123...",
  "status": "DEPLOYING"
}
```

**After pushing code:**
1. `POST /api/deploy/{service_id}` — trigger the deploy
2. Poll `GET /api/services/{service_id}/status` until `status != "DEPLOYING"`
3. Check `sync_status` — should be `IN_SYNC` if successful

---

### Force sync all services

```bash
POST /api/refresh
```

Pulls latest data from Railway and GitHub APIs. Use this if you suspect the dashboard is stale.

Returns:
```json
{
  "ok": true,
  "synced": 7,
  "errors": []
}
```

---

## Additional Endpoints

### Get latest deployment

```bash
GET /api/deployments/latest
GET /api/deployments/latest?service_id={service_id}
```

Returns the most recent deployment overall, or for a specific service.

---

### Get deployment history

```bash
GET /api/deployments?limit=50&status=FAILED
```

Query params:
- `limit` (max 200)
- `status` (SUCCESS, FAILED, CRASHED, DEPLOYING, BUILDING)
- `project_id`

---

### Get single deployment with full error log

```bash
GET /api/deployments/{deployment_id}
```

Includes the complete `error_log` field.

---

### Health check

```bash
GET /api/health
```

Verifies connectivity to PostgreSQL, Railway API, and GitHub API.

---

### API documentation

```bash
GET /api/agent/docs
```

Returns machine-readable JSON schema of all endpoints.

---

## Important Notes

### Sync Status

Services show `sync_status: UNKNOWN` until you map them to a GitHub repo. Go to the **Repo Mapping** tab in the UI and link each Railway service to its GitHub repo once. After that, the system automatically detects BEHIND/IN_SYNC by comparing commit SHAs.

### Error Logs

Error logs are fetched from Railway's deployment logs API. Logs older than ~30 days may return `null` because Railway expires them. Fresh failures always have logs.

### Timestamps

All timestamps are UTC with `Z` suffix. The browser/client handles local timezone conversion.

---

## Example: Full AI Agent Session

```bash
# 1. Start of session — what's broken?
curl https://deploy-center-production.up.railway.app/api/agent/overview

# Response shows 3 failing services, 1 behind

# 2. Check the failing service
curl https://deploy-center-production.up.railway.app/api/services/f856aa3e-3804-419b-9dbb-3b81bf0cfd46/status

# Error log shows: "ValidationError: 1 validation error for Settings"
# → Missing environment variable

# 3. Fix the code, push to GitHub

# 4. Trigger deploy
curl -X POST https://deploy-center-production.up.railway.app/api/deploy/f856aa3e-3804-419b-9dbb-3b81bf0cfd46

# 5. Poll until done
curl https://deploy-center-production.up.railway.app/api/services/f856aa3e-3804-419b-9dbb-3b81bf0cfd46/status
# Keep polling until railway.status != "DEPLOYING"

# 6. Verify success
# sync_status should be "IN_SYNC" and railway.status should be "SUCCESS"
```

---

## Summary

**For AI agents, this tool provides:**
- ✅ Single-call overview of all broken and behind services
- ✅ Full error logs on failures
- ✅ Commit-level sync detection (GitHub vs Railway)
- ✅ Programmatic deploy triggering
- ✅ Complete deployment history
- ✅ No manual dashboard clicking required

**Start every coding session with `/api/agent/overview` and you'll know exactly what needs attention.**
