import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import SpotDiagnostic
from agents.spot_agent import spot_agent
from agents.spot_schemas import SpotDiagnosticOutput
from connectors.espocrm_connector import create_finding_record
from pydantic import BaseModel

logger = logging.getLogger("parl_apex.routers.spot")

router = APIRouter(prefix="/spot", tags=["spot"])

class SpotDiagnoseRequest(BaseModel):
    organization_name: str
    sector: str
    context: dict

@router.post("/diagnose", response_model=SpotDiagnosticOutput)
@router.post("/analyze", response_model=SpotDiagnosticOutput)
async def diagnose(
    body: SpotDiagnoseRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Runs the SPOT diagnostic agent on the provided organizational context,
    persists the structured recommendation results to the SQLite database,
    and returns the typed diagnostic output.
    """
    logger.info(f"Received SPOT diagnostic request for: {body.organization_name} in sector: {body.sector}")
    
    try:
        # Construct the input prompt for the agent
        prompt = (
            f"Organization Name: {body.organization_name}\n"
            f"Sector: {body.sector}\n"
            f"Context Details:\n{body.context}"
        )
        
        # Run the Pydantic AI agent (executes async)
        result = await spot_agent.run(prompt)
        
        # The typed output is in result.output
        diagnostic_output = result.output
        
        # Persist to SQLite database
        db_diagnostic = SpotDiagnostic(
            org_name=body.organization_name,
            sector=body.sector,
            context_data=body.context,
            result_data=diagnostic_output.model_dump()
        )
        
        db.add(db_diagnostic)
        await db.commit()
        await db.refresh(db_diagnostic)

        for index, use_case in enumerate(diagnostic_output.use_cases, start=1):
            try:
                finding_id = await create_finding_record(
                    use_case.model_dump(),
                    diagnostic_output.organization_name,
                )
                logger.info(
                    "Created EspoCRM Finding from SPOT report for %s use_case_rank=%s finding_id=%s",
                    diagnostic_output.organization_name,
                    index,
                    finding_id,
                )
            except Exception as e:
                logger.error(
                    "Failed to create EspoCRM Finding from SPOT report for %s use_case_rank=%s: %s",
                    diagnostic_output.organization_name,
                    index,
                    e,
                    exc_info=True,
                )
        
        logger.info(f"Successfully generated and persisted SPOT diagnostic for {body.organization_name} with ID: {db_diagnostic.id}")
        return diagnostic_output

    except Exception as e:
        logger.error(f"Failed to generate SPOT diagnostic: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while running the SPOT diagnostic agent: {str(e)}"
        )
