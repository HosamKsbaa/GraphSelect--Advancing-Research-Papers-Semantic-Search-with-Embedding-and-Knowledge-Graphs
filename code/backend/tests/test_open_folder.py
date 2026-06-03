import pytest
from httpx import AsyncClient
from main import app
from config import get_settings

@pytest.mark.asyncio
async def test_open_folder_returns_correct_path():
    """Test that the open-folder endpoint returns the absolute path from settings."""
    settings = get_settings()
    
    async with AsyncClient(base_url="http://localhost:8000") as ac:
        # Create a mock project first to get an ID
        create_res = await ac.post("/api/projects", json={
            "name": "Test Path Resolution",
            "description": "Test",
            "topic": "Test"
        })
        assert create_res.status_code == 201
        project_id = create_res.json()["id"]

        # Call the open-folder endpoint
        res = await ac.post(f"/api/projects/{project_id}/open-folder")
        assert res.status_code == 200
        
        data = res.json()
        expected_path = f"{settings.projects_dir}/{project_id}"
        
        # Verify the path returned matches the settings
        assert data["path"] == expected_path
        # Verify the path is absolute (starting with / or C:)
        assert "/" in expected_path or "\\" in expected_path
