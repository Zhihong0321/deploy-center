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
        result = await self.query("""
        query {
            me {
                workspaces {
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
            }
        }
        """)
        workspaces = result.get("data", {}).get("me", {}).get("workspaces", [])
        all_projects = []
        for ws in workspaces:
            all_projects.extend(ws.get("projects", {}).get("edges", []))
        return all_projects

    async def list_all_services(self) -> List[Dict[str, Any]]:
        """Flat list of all services across all projects for dropdown."""
        projects = await self.get_projects()
        services = []
        for proj_edge in projects:
            proj = proj_edge["node"]
            for svc_edge in proj.get("services", {}).get("edges", []):
                svc = svc_edge["node"]
                services.append({
                    "service_id": svc["id"],
                    "service_name": svc["name"],
                    "project_id": proj["id"],
                    "project_name": proj["name"]
                })
        return services

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

    async def get_deployment_logs(self, deployment_id: str, limit: int = 150) -> Optional[str]:
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

        return "\n".join(
            f"[{log.get('timestamp')}] {log.get('message')}"
            for log in logs
        )

    async def trigger_deploy(self, service_id: str) -> Dict[str, Any]:
        """Trigger a new deployment for a service via Railway API."""
        mutation = """
        mutation TriggerDeploy($serviceId: String!) {
            serviceInstanceRedeploy(serviceId: $serviceId)
        }
        """
        result = await self.query(mutation, {"serviceId": service_id})
        if "errors" in result:
            raise Exception(result["errors"][0]["message"])
        return result.get("data", {})

    async def register_webhook_all_projects(self, webhook_url: str) -> List[Dict[str, Any]]:
        """Register webhook URL on every project the token can access."""
        projects = await self.get_projects()
        results = []
        for proj_edge in projects:
            proj = proj_edge["node"]
            project_id = proj["id"]
            project_name = proj["name"]
            try:
                mutation = """
                mutation CreateWebhook($projectId: String!, $url: String!) {
                    webhookCreate(input: { projectId: $projectId, url: $url }) {
                        id
                        url
                    }
                }
                """
                result = await self.query(mutation, {"projectId": project_id, "url": webhook_url})
                if "errors" in result:
                    results.append({"project": project_name, "ok": False, "error": result["errors"][0]["message"]})
                else:
                    results.append({"project": project_name, "ok": True})
            except Exception as e:
                results.append({"project": project_name, "ok": False, "error": str(e)})
        return results
