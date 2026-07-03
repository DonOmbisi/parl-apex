import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("parl_apex.connectors.quotation")

ESPOCRM_OPPORTUNITY_ENTITY = "Opportunity"
ESPOCRM_ACCOUNT_ENTITY = "Account"
ESPOCRM_CONTACT_ENTITY = "Contact"
ESPOCRM_PRODUCT_ENTITY = "Product"


def _base_url() -> str:
    base_url = os.getenv("ESPOCRM_BASE_URL", "").rstrip("/")
    if not base_url:
        raise EnvironmentError("ESPOCRM_BASE_URL is required")
    return base_url


def _quotation_headers() -> dict[str, str]:
    api_key = os.getenv("ESPOCRM_QUOTATION_API_KEY")
    if not api_key:
        raise EnvironmentError("ESPOCRM_QUOTATION_API_KEY is required")
    return {"X-Api-Key": api_key, "Content-Type": "application/json"}


def _entity_url(entity: str) -> str:
    return f"{_base_url()}/api/v1/{entity}"


def _record_url(entity: str, record_id: str) -> str:
    return f"{_entity_url(entity)}/{record_id}"


def _espocrm_list(data: Any) -> list[dict]:
    if isinstance(data, dict):
        if isinstance(data.get("list"), list):
            return data["list"]
        if isinstance(data.get("records"), list):
            return data["records"]
    if isinstance(data, list):
        return data
    return []


async def fetch_opportunity_data(opportunity_id: str) -> dict:
    """
    Fetch all data needed for a quotation from EspoCRM.
    
    Returns a dictionary containing:
    - opportunity: name, amount, closeDate, assignedUser, description
    - account: name, billingAddress (if linked)
    - contact: firstName, lastName, emailAddress (if linked)
    - line_items: list of products/line items linked to the opportunity
    """
    async with httpx.AsyncClient(timeout=30.0, headers=_quotation_headers()) as client:
        # Fetch the Opportunity record
        opportunity_url = _record_url(ESPOCRM_OPPORTUNITY_ENTITY, opportunity_id)
        response = await client.get(opportunity_url)
        response.raise_for_status()
        opportunity = response.json()
        
        # Extract opportunity fields
        result = {
            "opportunity": {
                "id": opportunity.get("id"),
                "name": opportunity.get("name") or "",
                "amount": opportunity.get("amount") or 0,
                "amountCurrency": opportunity.get("amountCurrency") or "USD",
                "closeDate": opportunity.get("closeDate") or "",
                "assignedUser": opportunity.get("assignedUserName") or "",
                "description": opportunity.get("description") or "",
            },
            "account": {},
            "contact": {},
            "line_items": [],
        }
        
        # Fetch linked Account if present
        account_id = opportunity.get("accountId")
        if account_id:
            try:
                account_url = _record_url(ESPOCRM_ACCOUNT_ENTITY, account_id)
                account_response = await client.get(account_url)
                account_response.raise_for_status()
                account = account_response.json()
                result["account"] = {
                    "id": account.get("id"),
                    "name": account.get("name") or "",
                    "billingAddress": account.get("billingAddress") or "",
                }
            except Exception as e:
                logger.warning(f"Failed to fetch account {account_id}: {e}")
                result["account"] = {"name": "", "billingAddress": ""}
        
        # Fetch linked Contact if present
        contact_id = opportunity.get("contactId")
        if contact_id:
            try:
                contact_url = _record_url(ESPOCRM_CONTACT_ENTITY, contact_id)
                contact_response = await client.get(contact_url)
                contact_response.raise_for_status()
                contact = contact_response.json()
                result["contact"] = {
                    "id": contact.get("id"),
                    "firstName": contact.get("firstName") or "",
                    "lastName": contact.get("lastName") or "",
                    "emailAddress": contact.get("emailAddress") or "",
                }
            except Exception as e:
                logger.warning(f"Failed to fetch contact {contact_id}: {e}")
                result["contact"] = {"firstName": "", "lastName": "", "emailAddress": ""}
        
        # Fetch line items/products linked to the opportunity
        # EspoCRM typically stores line items in a related entity like OpportunityItem
        try:
            # Try to fetch opportunity items
            items_url = f"{_entity_url(ESPOCRM_OPPORTUNITY_ENTITY)}/{opportunity_id}/opportunityItem"
            items_response = await client.get(items_url)
            items_response.raise_for_status()
            items = _espocrm_list(items_response.json())
            
            for item in items:
                product_id = item.get("productId")
                product_name = item.get("name") or ""
                quantity = item.get("quantity") or 1
                unit_price = item.get("unitPrice") or 0
                total_price = item.get("totalPrice") or (quantity * unit_price)
                
                # If product is linked, fetch product details
                if product_id:
                    try:
                        product_url = _record_url(ESPOCRM_PRODUCT_ENTITY, product_id)
                        product_response = await client.get(product_url)
                        product_response.raise_for_status()
                        product = product_response.json()
                        product_name = product.get("name") or product_name
                    except Exception as e:
                        logger.warning(f"Failed to fetch product {product_id}: {e}")
                
                result["line_items"].append({
                    "name": product_name,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "total_price": total_price,
                })
        except Exception as e:
            logger.warning(f"Failed to fetch line items for opportunity {opportunity_id}: {e}")
            # If no line items found, use the opportunity itself as a single line item
            if result["opportunity"]["amount"]:
                result["line_items"].append({
                    "name": result["opportunity"]["name"],
                    "quantity": 1,
                    "unit_price": result["opportunity"]["amount"],
                    "total_price": result["opportunity"]["amount"],
                })
        
        return result
