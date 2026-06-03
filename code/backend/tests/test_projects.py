import pytest
from httpx import AsyncClient
from datetime import datetime

@pytest.mark.asyncio
async def test_touch_project(client: AsyncClient, test_project_id: str):
    """Test that touching a project updates its last_accessed_at timestamp."""
    response = await client.post(f"/api/projects/{test_project_id}/touch")
    assert response.status_code == 200
    data = response.json()
    assert data["last_accessed_at"] is not None

@pytest.mark.asyncio
async def test_archive_project(client: AsyncClient, test_project_id: str):
    """Test that archiving a project works and filters it out by default."""
    response = await client.patch(f"/api/projects/{test_project_id}/archive")
    assert response.status_code == 200
    
    # Should not appear in default list
    list_response = await client.get("/api/projects")
    assert list_response.status_code == 200
    projects = list_response.json()
    assert not any(p["id"] == test_project_id for p in projects)
    
    # Should appear when include_archived is True
    list_all_response = await client.get("/api/projects?include_archived=true")
    assert list_all_response.status_code == 200
    all_projects = list_all_response.json()
    assert any(p["id"] == test_project_id for p in all_projects)
