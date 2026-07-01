import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import os
import tempfile
import shutil

from app.main import app
from app.database import Base, get_db
from agents.spot_schemas import SpotDiagnosticOutput, UseCaseRecommendation

# Setup a clean, temporary SQLite database for testing the database persistence
@pytest.fixture(scope="function")
async def test_db():
    temp_dir = tempfile.mkdtemp()
    db_file = os.path.join(temp_dir, "test_spot.db")
    database_url = f"sqlite+aiosqlite:///{db_file}"
    
    engine = create_async_engine(database_url, echo=False)
    TestingSessionLocal = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async def override_get_db():
        async with TestingSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # Override the dependency in the app
    app.dependency_overrides[get_db] = override_get_db
    
    yield TestingSessionLocal
    
    # Clean up overrides and files
    app.dependency_overrides.clear()
    await engine.dispose()
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass

@pytest.mark.anyio
async def test_spot_agent_properties():
    from agents.spot_agent import spot_agent, SPOT_SYSTEM_PROMPT
    
    # Verify that the agent is initialized with correct parameters
    assert spot_agent is not None
    assert spot_agent.output_type == SpotDiagnosticOutput
    assert "Kenyan shillings" in SPOT_SYSTEM_PROMPT
    assert "150,000" in SPOT_SYSTEM_PROMPT
    assert spot_agent.model.model_name == "llama-3.3-70b-versatile"

@pytest.mark.anyio
async def test_spot_diagnose_endpoint_and_persistence(test_db):
    # Define a mock recommendation and output matching our strictly-typed schema
    mock_recommendation = UseCaseRecommendation(
        title="Daily Invoice Matching Workflow",
        department="Finance",
        pain_point="Manual invoice matching takes 3 days per week.",
        proposed_solution="Process change: Re-organize reconciliation workflow to match invoices daily.",
        estimated_cost_kes=180000,
        optimistic_90_day_roi="60% time savings",
        conservative_90_day_roi="25% time savings",
        confidence="high",
        confidence_reasoning="The context directly states the finance team spends 24 weekly hours on manual invoice matching.",
        key_assumptions=["Accountants will follow the daily schedule"],
        identified_risks=["Initial pushback due to change in daily routine"],
        applicable_ibm_products=["IBM Watsonx"]
    )
    
    mock_output = SpotDiagnosticOutput(
        organization_name="Nairobi Flour Mills",
        sector="Agriculture & Manufacturing",
        executive_summary="This diagnostic outlines a high-ROI workflow adjustment for invoice matching.",
        use_cases=[mock_recommendation],
        organizational_readiness_assessment="Medium-high: Staff are willing but need training.",
        information_gaps=["Need invoice volume statistics for the last 6 months."]
    )
    
    # Prepare request payload
    payload = {
        "organization_name": "Nairobi Flour Mills",
        "sector": "Agriculture & Manufacturing",
        "context": {
            "financial_pain": "Invoice matching is highly manual, done by 2 accountants.",
            "weekly_hours": 24
        }
    }
    
    # Mock the spot_agent.run method
    # We patch it in app.routers.spot where it's imported
    with patch("app.routers.spot.spot_agent.run", new_callable=AsyncMock) as mock_run:
        # Pydantic AI agent run returns a RunResult which has an .output property
        mock_result = AsyncMock()
        mock_result.output = mock_output
        mock_run.return_value = mock_result
        
        # Call the endpoint using AsyncClient with ASGI transport
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/spot/diagnose", json=payload)
            
        # Assertions on API response
        assert response.status_code == 200
        data = response.json()
        assert data["organization_name"] == "Nairobi Flour Mills"
        assert data["sector"] == "Agriculture & Manufacturing"
        assert len(data["use_cases"]) == 1
        assert data["use_cases"][0]["department"] == "Finance"
        assert data["use_cases"][0]["estimated_cost_kes"] == 180000
        
        # Verify database persistence
        # Query the database directly to confirm the record was saved
        async with test_db() as session:
            from sqlalchemy import select
            from app.models import SpotDiagnostic
            
            stmt = select(SpotDiagnostic).where(SpotDiagnostic.org_name == "Nairobi Flour Mills")
            result = await session.execute(stmt)
            db_record = result.scalar_one_or_none()
            
            assert db_record is not None
            assert db_record.sector == "Agriculture & Manufacturing"
            assert db_record.context_data == payload["context"]
            assert db_record.result_data["executive_summary"] == mock_output.executive_summary
            assert len(db_record.result_data["use_cases"]) == 1
            assert db_record.result_data["use_cases"][0]["estimated_cost_kes"] == 180000
