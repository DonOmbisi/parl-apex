import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from pathlib import Path
import os
import shutil
import tempfile
import yaml

from app.main import app
from app.database import Base, get_db
from agents.extraction_agent import StructuredFindings

@pytest.fixture(scope="function")
def temp_clients_dir():
    # Create a temporary directory for clients config files and database
    temp_dir = tempfile.mkdtemp()
    
    # We will patch the Path("clients") in app.routers.clients to point to this temp dir
    # And the data/graphs folder to live in this temp dir
    old_cwd = os.getcwd()
    os.chdir(temp_dir)
    
    # Create required subfolders in the temporary working directory
    os.makedirs("clients", exist_ok=True)
    os.makedirs("data/graphs", exist_ok=True)
    
    yield temp_dir
    
    # Restore cwd and clean up
    os.chdir(old_cwd)
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass

@pytest.mark.anyio
async def test_slugify():
    from app.routers.clients import slugify
    assert slugify("Kenya Red Cross") == "kenya_red_cross"
    assert slugify("Nairobi-Retail   Store!") == "nairobi_retail_store"
    assert slugify("Mombasa Shipping") == "mombasa_shipping"

@pytest.mark.anyio
async def test_extract_findings_endpoint():
    # Mock the extraction agent run
    mock_findings = StructuredFindings(
        sector="Non-Profit",
        description="Providing humanitarian relief and disaster response in Kenya.",
        funding_sources=["IFRC", "USAID", "Local Donors"],
        technologies=["KoboToolbox", "ODK", "Salesforce"],
        challenges=["Inefficient logistics", "Slow manual tracking"],
        strategic_priorities=["Digitalize field operations", "Enhance donor engagement"]
    )
    
    payload = {"report": "Raw research report text for Kenya Red Cross..."}
    
    with patch("app.routers.clients.extraction_agent.run", new_callable=AsyncMock) as mock_run:
        mock_result = AsyncMock()
        mock_result.output = mock_findings
        mock_run.return_value = mock_result
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/clients/extract", json=payload)
            
        assert response.status_code == 200
        data = response.json()
        assert data["sector"] == "Non-Profit"
        assert "KoboToolbox" in data["technologies"]
        assert "Inefficient logistics" in data["challenges"]

@pytest.mark.anyio
async def test_seed_client_endpoint(temp_clients_dir):
    mock_findings = StructuredFindings(
        sector="Non-Profit",
        description="Humanitarian relief organization.",
        funding_sources=["IFRC", "USAID"],
        technologies=["KoboToolbox"],
        challenges=["Slow tracking"],
        strategic_priorities=["Digitalization"]
    )
    
    payload = {
        "organization_name": "Kenya Red Cross",
        "sector": "Non-Profit",
        "findings": mock_findings.model_dump()
    }
    
    # We patch get_client_graph to use the temporary directory's graph path
    # and avoid Kuzu locks or files in the real directory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/clients/seed", json=payload)
        
    assert response.status_code == 200
    data = response.json()
    assert data["client_id"] == "kenya_red_cross"
    assert data["status"] == "success"
    assert data["entities_added"] == 6  # 1 (Org) + 2 (Funders) + 1 (Tech) + 1 (Challenge) + 1 (Priority)
    assert data["relationships_added"] == 5  # 2 + 1 + 1 + 1
    
    # Verify the config.yaml file was created correctly
    config_file = Path("clients") / "kenya_red_cross" / "config.yaml"
    assert config_file.exists()
    
    with open(config_file, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)
        
    assert config_data["name"] == "Kenya Red Cross"
    assert config_data["sector"] == "Non-Profit"
    assert config_data["connectors"] == []
    assert config_data["graph_path"] == "graphs/kenya_red_cross.db"
    
    # Close all graphs to release file locks on the Kuzu DB in the temp dir
    from graph import close_all_graphs
    close_all_graphs()
