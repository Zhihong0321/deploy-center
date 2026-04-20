import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.config import settings


class RailwayClient:
    BASE_URL = "https://backboard.railway.app/graphql/v2"

    def __init__(self):
        self.token = settings.railway_token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def query(self, query: str, variables: Dict[str, Any] = None) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.BASE_URL,
                json={"query": query, "variables": variables or {}},
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def get_projects(self) -> List[Dict[str, Any]]:
        query = """
        query {
            projects {
                edges {
                    node {
                        id
                        name
                        services {
                            edges {
                                node {
                                    id
                                    name
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        result = await self.query(query)
        return result.get("data", {}).get("projects", {}).get("edges", [])

    async def get_deployments(self, service_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        query = """
        query GetDeployments($serviceId: String!, $limit: Int!) {
            deployments(input: {serviceId: $serviceId}, first: $limit) {
                edges {
                    node {
                        id
                        status
                        createdAt
                        updatedAt
                        meta
                        staticUrl
                        url
                        environment {
                            name
                        }
                        service {
                            id
                            name
                            project {
                                id
                                name
                            }
                        }
                    }
                }
            }
        }
        """
        result = await self.query(query, {"serviceId": service_id, "limit": limit})
        return result.get("data", {}).get("deployments", {}).get("edges", [])

    async def get_deployment_logs(self, deployment_id: str, limit: int = 100) -> Optional[str]:
        query = """
        query GetLogs($deploymentId: String!, $limit: Int!) {
            deploymentLogs(deploymentId: $deploymentId, limit: $limit) {
                message
                timestamp
            }
        }
        """
        result = await self.query(query, {"deploymentId": deployment_id, "limit": limit})
        logs = result.get("data", {}).get("deploymentLogs", [])

        if not logs:
            return None

        # Filter for error logs
        error_logs = [
            f"[{log.get('timestamp')}] {log.get('message')}"
            for log in logs
            if any(keyword in log.get('message', '').lower()
                   for keyword in ['error', 'failed', 'exception', 'fatal'])
        ]

        return "\n".join(error_logs) if error_logs else None
