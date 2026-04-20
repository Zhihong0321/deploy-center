import httpx
from typing import Optional, Dict, Any
from app.config import settings


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self):
        self.token = settings.github_token
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    async def get_latest_commit(self, repo: str, branch: str = "main") -> Optional[Dict[str, Any]]:
        """repo = 'owner/repo'"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/repos/{repo}/commits/{branch}",
                headers=self.headers,
                timeout=15.0
            )
            if response.status_code == 404:
                # Try master branch
                response = await client.get(
                    f"{self.BASE_URL}/repos/{repo}/commits/master",
                    headers=self.headers,
                    timeout=15.0
                )
            if response.status_code != 200:
                return None

            data = response.json()
            return {
                "sha": data["sha"],
                "short_sha": data["sha"][:7],
                "message": data["commit"]["message"].split("\n")[0],
                "author": data["commit"]["author"]["name"],
                "date": data["commit"]["author"]["date"],
                "url": data["html_url"]
            }
