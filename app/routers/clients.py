import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
import yaml
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from agents.extraction_agent import extraction_agent, StructuredFindings
from graph import get_client_graph

logger = logging.getLogger("parl_apex.routers.clients")

router = APIRouter(prefix="/clients", tags=["clients"])

def slugify(name: str) -> str:
    """
    Converts an organization name to a clean, lowercase snake_case slug
    suitable for file paths and identifiers.
    """
    s = name.lower().strip()
    s = re.sub(r'[\s\-]+', '_', s)
    s = re.sub(r'[^\w]', '', s)
    return s

class ExtractRequest(BaseModel):
    report: str = Field(description="The raw text of the deep research report.")

class SeedRequest(BaseModel):
    organization_name: str = Field(description="The name of the organization.")
    sector: str | None = Field(default=None, description="The sector of the organization.")
    findings: StructuredFindings = Field(description="The extracted structured findings.")

@router.post("/extract", response_model=StructuredFindings)
async def extract_findings(body: ExtractRequest):
    """
    Accepts a raw research report and uses the Extraction Agent to
    produce a structured findings object.
    """
    logger.info("Received request to extract findings from research report.")
    try:
        result = await extraction_agent.run(body.report)
        logger.info("Successfully extracted structured findings from report.")
        return result.output
    except Exception as e:
        logger.error(f"Failed to extract findings: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error running extraction agent: {str(e)}"
        )

@router.post("/seed")
async def seed_client(body: SeedRequest):
    """
    Accepts structured findings for a client, automatically creates their
    configuration file, initializes their Kuzu knowledge graph, and seeds
    the graph with entities and relationships from the findings.
    """
    org_name = body.organization_name
    sector = body.sector or "Unknown"
    findings = body.findings
    
    slug = slugify(org_name)
    client_dir = Path("clients") / slug
    config_path = client_dir / "config.yaml"
    graph_path = f"graphs/{slug}.db"
    
    logger.info(f"Seeding client '{org_name}' (slug: '{slug}')")
    
    try:
        # 1. Create client configuration folder and config.yaml if they don't exist
        os.makedirs(client_dir, exist_ok=True)
        
        if not config_path.exists():
            config_data = {
                "name": org_name,
                "sector": sector,
                "connectors": [],
                "agents": [],
                "graph_path": graph_path
            }
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(config_data, f, sort_keys=False)
            logger.info(f"Created new client configuration file at: {config_path}")
        else:
            # If it exists, read it and merge the sector if it was "Unknown"
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f) or {}
                if config_data.get("sector") == "Unknown" and sector != "Unknown":
                    config_data["sector"] = sector
                    with open(config_path, "w", encoding="utf-8") as f:
                        yaml.safe_dump(config_data, f, sort_keys=False)
                    logger.info(f"Updated sector to '{sector}' in existing configuration for {org_name}")
            except Exception as ex:
                logger.warning(f"Failed to update existing config file: {ex}")
        
        # 2. Get/Initialize the Kuzu knowledge graph
        # This automatically sets up tables if they don't exist
        graph = get_client_graph(org_name, graph_path)
        
        # 3. Write findings into the graph as entities and relationships
        # We track counts of items we are processing
        entity_count = 1  # 1 for the client organization itself
        rel_count = 0
        
        # Helper to safely strip/clean names
        def clean(s: str) -> str:
            return s.strip()
            
        # Write Funding Sources: Funder -> FUNDS -> Org
        for funder in findings.funding_sources:
            f_name = clean(funder)
            if f_name:
                graph.add_relationship(
                    source_name=f_name,
                    source_type="Funder",
                    target_name=org_name,
                    target_type="Organization",
                    relationship_type="FUNDS",
                    evidence="Consult Ralph Research Output"
                )
                entity_count += 1
                rel_count += 1
                
        # Write Technologies: Org -> HAS_SYSTEM -> Tech
        for tech in findings.technologies:
            t_name = clean(tech)
            if t_name:
                graph.add_relationship(
                    source_name=org_name,
                    source_type="Organization",
                    target_name=t_name,
                    target_type="Technology",
                    relationship_type="HAS_SYSTEM",
                    evidence="Consult Ralph Research Output"
                )
                entity_count += 1
                rel_count += 1
                
        # Write Challenges: Org -> HAS_CHALLENGE -> Challenge
        for challenge in findings.challenges:
            c_name = clean(challenge)
            if c_name:
                graph.add_relationship(
                    source_name=org_name,
                    source_type="Organization",
                    target_name=c_name,
                    target_type="Challenge",
                    relationship_type="HAS_CHALLENGE",
                    evidence="Consult Ralph Research Output"
                )
                entity_count += 1
                rel_count += 1
                
        # Write Strategic Priorities: Org -> HAS_PRIORITY -> Priority
        for priority in findings.strategic_priorities:
            p_name = clean(priority)
            if p_name:
                graph.add_relationship(
                    source_name=org_name,
                    source_type="Organization",
                    target_name=p_name,
                    target_type="Priority",
                    relationship_type="HAS_PRIORITY",
                    evidence="Consult Ralph Research Output"
                )
                entity_count += 1
                rel_count += 1

        # 4. Log the seed operation for audit trail
        timestamp = datetime.now(timezone.utc).isoformat()
        logger.info(
            f"[AUDIT TRAIL] Timestamp: {timestamp} | Client Seeding | "
            f"Org: '{org_name}' | Sector: '{sector}' | "
            f"Entities Merged: {entity_count} | Relationships Merged: {rel_count}"
        )
        
        return {
            "client_id": slug,
            "entities_added": entity_count,
            "relationships_added": rel_count,
            "status": "success",
            "message": f"Client '{org_name}' successfully seeded."
        }

    except Exception as e:
        logger.error(f"Failed to seed client '{org_name}': {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error seeding client graph: {str(e)}"
        )
