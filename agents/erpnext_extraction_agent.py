"""
ERPNext Extraction Agent
========================
Takes the raw ``ERPNextConnectorResult`` produced by the ERPNext connector
and turns it into typed graph entities and relationships ready to be written
into a client's Kuzu knowledge graph.

Mapping rules
-------------
For each invoice record:

  Invoice entity  ──[HAS_INVOICE]──►  Organization entity
    • source_name  = invoice name (e.g. "SINV-00042")
    • source_type  = "Invoice"
    • target_name  = client / org name
    • target_type  = "Organization"
    • rel_type     = "HAS_INVOICE"          (always)
    • evidence     = "ERPNext: <invoice_name>"

  Customer entity ──[OWES_INVOICE]──►  Invoice entity
    • source_name  = customer name
    • source_type  = "Customer"
    • target_name  = invoice name
    • rel_type     = "OWES_INVOICE" | "OWES_OVERDUE_INVOICE"
    • evidence     = "ERPNext: <invoice_name>"

The relationship type explicitly distinguishes overdue invoices from merely
unpaid ones so downstream queries can surface urgency without extra logic.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModel

from connectors.erpnext_connector import ERPNextConnectorResult, RawInvoice

logger = logging.getLogger("parl_apex.agents.erpnext_extraction")

# ─────────────────────────────────────────────────────────────────────────────
# Typed output schemas
# ─────────────────────────────────────────────────────────────────────────────

class GraphRelationship(BaseModel):
    """A single relationship to be written to the Kuzu knowledge graph."""
    source_name: str
    source_type: str
    target_name: str
    target_type: str
    relationship_type: str
    evidence: str


class ERPNextExtractionOutput(BaseModel):
    """The full set of entities and relationships extracted from one connector run."""
    client_name: str
    relationships: list[GraphRelationship] = Field(default_factory=list)
    summary: str = Field(
        description="One-sentence plain-English summary of what was extracted."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic extraction (no LLM needed for structured invoice data)
# The agent is still declared for future use with unstructured commentary
# fields that may be added to invoices — but the core mapping is rule-based
# because the input is already machine-structured.
# ─────────────────────────────────────────────────────────────────────────────

def extract_from_connector_result(result: ERPNextConnectorResult) -> ERPNextExtractionOutput:
    """
    Converts a raw ``ERPNextConnectorResult`` into graph-ready relationships.

    This is a deterministic, rule-based extraction — no LLM call needed for
    structured invoice data.  The Pydantic AI agent below remains available
    for future use with free-text invoice notes or narrative fields.
    """
    relationships: list[GraphRelationship] = []
    org_name = result.client_name

    for invoice in result.invoices:
        evidence = f"ERPNext: {invoice.name} | {invoice.posting_date} | {invoice.currency} {invoice.outstanding_amount:.2f} outstanding"

        # 1. Link the organization to the invoice
        relationships.append(
            GraphRelationship(
                source_name=org_name,
                source_type="Organization",
                target_name=invoice.name,
                target_type="Invoice",
                relationship_type="HAS_INVOICE",
                evidence=evidence,
            )
        )

        # 2. Determine customer relationship type based on status
        rel_type = (
            "OWES_OVERDUE_INVOICE"
            if invoice.status.upper() == "OVERDUE"
            else "OWES_INVOICE"
        )

        relationships.append(
            GraphRelationship(
                source_name=invoice.customer,
                source_type="Customer",
                target_name=invoice.name,
                target_type="Invoice",
                relationship_type=rel_type,
                evidence=evidence,
            )
        )

    overdue_count = sum(
        1 for inv in result.invoices if inv.status.upper() == "OVERDUE"
    )
    unpaid_count = len(result.invoices) - overdue_count

    summary = (
        f"Extracted {len(result.invoices)} invoice(s) for '{org_name}': "
        f"{overdue_count} overdue, {unpaid_count} unpaid (not yet overdue). "
        f"Total relationships written: {len(relationships)}."
    )

    return ERPNextExtractionOutput(
        client_name=org_name,
        relationships=relationships,
        summary=summary,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic AI agent — for future use with free-text narrative fields
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a data extraction specialist at Predictive Analytical Resources Limited (PARL).
You receive raw invoice records from an ERPNext system and must extract graph entities
and relationships. Rules:

1. Every invoice becomes an Invoice entity linked to the organization with HAS_INVOICE.
2. Every customer becomes a Customer entity.
3. If an invoice status is "Overdue", use OWES_OVERDUE_INVOICE as the relationship type.
4. If an invoice status is "Unpaid", use OWES_INVOICE as the relationship type.
5. Never invent data — only extract what is present in the input.
6. Always populate the evidence field with the invoice document name and date.
"""

if not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = "mock-groq-api-key-placeholder"

try:
    _model = GroqModel("llama-3.3-70b-versatile")
    erpnext_extraction_agent = Agent(
        _model,
        output_type=ERPNextExtractionOutput,
        system_prompt=_SYSTEM_PROMPT,
    )
    logger.info("Initialized ERPNext Extraction Agent with Groq llama-3.3-70b-versatile.")
except Exception as e:
    logger.error(f"Failed to initialize ERPNext Extraction Agent model: {e}")
    erpnext_extraction_agent = Agent(
        "groq:llama-3.3-70b-versatile",
        output_type=ERPNextExtractionOutput,
        system_prompt=_SYSTEM_PROMPT,
    )
