"""
Linear Autopilot - Automates project management via the Linear GraphQL API.

Supports creating, updating, and deleting projects.
"""

import os
import requests


LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearAutopilot:
    def __init__(self, api_key: str = None):
        """Initialize the Linear Autopilot client.

        Args:
            api_key: Linear API key. Falls back to LINEAR_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("LINEAR_API_KEY")
        if not self.api_key:
            raise ValueError("Linear API key is required. Set LINEAR_API_KEY env var or pass api_key.")
        self.headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }

    def _execute(self, query: str, variables: dict = None) -> dict:
        """Execute a GraphQL query/mutation against the Linear API."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = requests.post(LINEAR_API_URL, json=payload, headers=self.headers)
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            errors = "; ".join(e["message"] for e in data["errors"])
            raise RuntimeError(f"Linear API error: {errors}")

        return data.get("data", {})

    def create_project(self, name: str, team_id: str, description: str = None, **kwargs) -> dict:
        """Create a new project in Linear.

        Args:
            name: Project name.
            team_id: ID of the team to create the project in.
            description: Optional project description.
            **kwargs: Additional project fields (e.g. state, color, targetDate).

        Returns:
            Created project data.
        """
        mutation = """
        mutation CreateProject($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                success
                project {
                    id
                    name
                    description
                    state
                    url
                }
            }
        }
        """
        input_data = {"name": name, "teamIds": [team_id]}
        if description is not None:
            input_data["description"] = description
        input_data.update(kwargs)

        result = self._execute(mutation, {"input": input_data})
        project_create = result.get("projectCreate", {})
        if not project_create.get("success"):
            raise RuntimeError(f"Failed to create project '{name}'")
        return project_create["project"]

    def update_project(self, project_id: str, **kwargs) -> dict:
        """Update an existing project in Linear.

        Args:
            project_id: ID of the project to update.
            **kwargs: Fields to update (e.g. name, description, state, color, targetDate).

        Returns:
            Updated project data.
        """
        mutation = """
        mutation UpdateProject($id: String!, $input: ProjectUpdateInput!) {
            projectUpdate(id: $id, input: $input) {
                success
                project {
                    id
                    name
                    description
                    state
                    url
                }
            }
        }
        """
        result = self._execute(mutation, {"id": project_id, "input": kwargs})
        project_update = result.get("projectUpdate", {})
        if not project_update.get("success"):
            raise RuntimeError(f"Failed to update project '{project_id}'")
        return project_update["project"]

    def delete_project(self, project_id: str) -> bool:
        """Delete a project from Linear.

        Args:
            project_id: ID of the project to delete.

        Returns:
            True if the project was successfully deleted.

        Raises:
            RuntimeError: If the deletion fails.
        """
        mutation = """
        mutation DeleteProject($id: String!) {
            projectDelete(id: $id) {
                success
            }
        }
        """
        result = self._execute(mutation, {"id": project_id})
        project_delete = result.get("projectDelete", {})
        if not project_delete.get("success"):
            raise RuntimeError(f"Failed to delete project '{project_id}'")
        return True

    def get_project(self, project_id: str) -> dict:
        """Fetch a project by ID.

        Args:
            project_id: ID of the project to retrieve.

        Returns:
            Project data.
        """
        query = """
        query GetProject($id: String!) {
            project(id: $id) {
                id
                name
                description
                state
                url
            }
        }
        """
        result = self._execute(query, {"id": project_id})
        project = result.get("project")
        if not project:
            raise RuntimeError(f"Project '{project_id}' not found")
        return project
