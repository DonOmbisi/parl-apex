"""
ERPNext Connector
=================
Fetches a narrow, authorised slice of data from an ERPNext instance:
  - Outstanding (unpaid) Sales Invoices
  - Overdue Sales Invoices (payment_status == "Overdue")

Authentication is done using an ERPNext API key/secret pair, read
exclusively from environment variables referenced by the client's
``credentials_ref`` configuration field.  Nothing is hardcoded.

Environment variable convention
--------------------------------
Given a ``credentials_ref`` of ``NAIROBI_RETAIL_ERPNEXT``, the connector
reads:

    NAIROBI_RETAIL_ERPNEXT_URL      # e.g. https://nairobi.erpnext.com
    NAIROBI_RETAIL_ERPNEXT_API_KEY  # ERPNext API key
    NAIROBI_RETAIL_ERPNEXT_SECRET   # ERPNext API secret

This keeps every client's credentials isolated and prevents cross-client
credential bleed even if configs are stored in the same repository.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("parl_apex.connectors.erpnext")


# ─────────────────────────────────────────────────────────────────────────────
# Raw data models (what the ERPNext API returns, before extraction)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RawInvoice:
    """Minimal representation of a single ERPNext Sales Invoice record."""
    name: str                   # ERPNext document name, e.g. "SINV-00042"
    customer: str               # Customer name
    posting_date: str           # ISO date string
    due_date: str               # ISO date string
    grand_total: float          # Invoice total (before tax deductions)
    outstanding_amount: float   # Remaining unpaid amount
    currency: str
    status: str                 # "Unpaid", "Overdue", "Paid", "Cancelled", etc.


@dataclass
class ERPNextConnectorResult:
    """Aggregated result returned from a single connector run."""
    client_name: str
    credentials_ref: str
    fetched_at: str             # ISO 8601 UTC timestamp
    invoices: list[RawInvoice] = field(default_factory=list)
    error: Optional[str] = None
    success: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Connector
# ─────────────────────────────────────────────────────────────────────────────

class ERPNextConnector:
    """
    Fetches outstanding and overdue Sales Invoices from a single ERPNext
    instance identified by ``credentials_ref``.
    """

    # ERPNext REST List endpoint for Sales Invoice
    _INVOICE_ENDPOINT = "/api/resource/Sales Invoice"

    # Only retrieve these fields to stay narrow; do not expand without cause.
    _FIELDS = [
        "name",
        "customer",
        "posting_date",
        "due_date",
        "grand_total",
        "outstanding_amount",
        "currency",
        "status",
    ]

    def __init__(self, client_name: str, credentials_ref: str):
        self.client_name = client_name
        self.credentials_ref = credentials_ref

        prefix = credentials_ref.upper()
        self.base_url = os.getenv(f"{prefix}_URL", "").rstrip("/")
        self.api_key = os.getenv(f"{prefix}_API_KEY", "")
        self.api_secret = os.getenv(f"{prefix}_SECRET", "")

        if not all([self.base_url, self.api_key, self.api_secret]):
            raise EnvironmentError(
                f"ERPNext credentials for '{credentials_ref}' are incomplete. "
                f"Expected env vars: {prefix}_URL, {prefix}_API_KEY, {prefix}_SECRET"
            )

    def _auth_header(self) -> dict:
        """Returns the token authentication header required by ERPNext."""
        return {"Authorization": f"token {self.api_key}:{self.api_secret}"}

    def _build_params(self, filters: list) -> dict:
        """Builds the query params for the ERPNext List API."""
        import json
        return {
            "fields": json.dumps(self._FIELDS),
            "filters": json.dumps(filters),
            "limit_page_length": 100,   # cap per run — intentionally bounded
            "order_by": "due_date asc",
        }

    async def fetch(self) -> ERPNextConnectorResult:
        """
        Fetches outstanding and overdue invoices from ERPNext.
        Returns an ``ERPNextConnectorResult`` regardless of success or failure.
        Errors are captured in the result so the caller can log them distinctly.
        """
        fetched_at = datetime.now(timezone.utc).isoformat()
        invoices: list[RawInvoice] = []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Two targeted queries — one for each status we care about
                for status in ("Unpaid", "Overdue"):
                    params = self._build_params(
                        filters=[["Sales Invoice", "status", "=", status]]
                    )
                    url = f"{self.base_url}{self._INVOICE_ENDPOINT}"
                    logger.debug(
                        f"[{self.client_name}] Fetching {status} invoices from {url}"
                    )
                    response = await client.get(
                        url, headers=self._auth_header(), params=params
                    )
                    response.raise_for_status()
                    records = response.json().get("data", [])
                    logger.info(
                        f"[{self.client_name}] Fetched {len(records)} {status} invoices"
                    )
                    for r in records:
                        invoices.append(
                            RawInvoice(
                                name=r.get("name", ""),
                                customer=r.get("customer", ""),
                                posting_date=r.get("posting_date", ""),
                                due_date=r.get("due_date", ""),
                                grand_total=float(r.get("grand_total", 0)),
                                outstanding_amount=float(r.get("outstanding_amount", 0)),
                                currency=r.get("currency", "KES"),
                                status=r.get("status", status),
                            )
                        )

            return ERPNextConnectorResult(
                client_name=self.client_name,
                credentials_ref=self.credentials_ref,
                fetched_at=fetched_at,
                invoices=invoices,
                success=True,
            )

        except httpx.HTTPStatusError as exc:
            msg = (
                f"HTTP {exc.response.status_code} from ERPNext for client "
                f"'{self.client_name}': {exc.response.text[:300]}"
            )
            logger.error(f"[{self.client_name}] ERPNext connector FAILED: {msg}")
            return ERPNextConnectorResult(
                client_name=self.client_name,
                credentials_ref=self.credentials_ref,
                fetched_at=fetched_at,
                invoices=[],
                error=msg,
                success=False,
            )
        except Exception as exc:
            msg = f"Unexpected error for client '{self.client_name}': {exc}"
            logger.error(f"[{self.client_name}] ERPNext connector FAILED: {msg}", exc_info=True)
            return ERPNextConnectorResult(
                client_name=self.client_name,
                credentials_ref=self.credentials_ref,
                fetched_at=fetched_at,
                invoices=[],
                error=msg,
                success=False,
            )
