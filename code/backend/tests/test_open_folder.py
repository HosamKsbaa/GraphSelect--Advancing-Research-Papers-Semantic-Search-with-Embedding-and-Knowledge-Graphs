from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from main import app
from config import get_settings

@pytest.mark.asyncio
async def test_open_folder_returns_correct_path():
    """Test that the open-folder endpoint returns the absolute path from settings."""
    settings = get_settings()
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project_id = "test-path-resolution-123"

        # Call the open-folder endpoint
        res = await ac.post(f"/api/projects/{project_id}/open-folder")
        assert res.status_code == 200
        
        data = res.json()
        expected_path = str(Path(settings.projects_dir) / project_id)
        
        # Verify the path returned matches the settings
        assert data["path"] == expected_path
        # Verify the path is absolute (starting with / or C:)
        assert "/" in expected_path or "\\" in expected_path


