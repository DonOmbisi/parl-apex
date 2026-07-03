import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from documents.quotation_generator import generate_quotation, format_ordinal_date

logger = logging.getLogger("parl_apex.routers.quotations")

router = APIRouter(prefix="/quotations", tags=["quotations"])

OUTPUT_DIR = Path("data/quotations")


class GenerateQuotationRequest(BaseModel):
    client_company: str = Field(..., description="Client company name")
    contact_person: str = Field(..., description="Contact person name and email")
    client_address: str = Field(..., description="Client address")
    requirement: str = Field(..., description="Product/Service requirement")
    salesperson: str = Field(..., description="Salesperson name")
    payment_terms: str = Field(..., description="Payment terms")
    valid_until: str = Field(..., description="Valid until date (ISO format)")
    quotation_number: str = Field(..., description="Quotation number")
    delivery_method: str = Field(..., description="Delivery method")
    line_item_name: str = Field(..., description="Line item name")
    line_item_qty: Optional[int] = Field(None, description="Line item quantity")
    line_item_version: Optional[str] = Field(None, description="Line item version")
    line_item_installation_type: Optional[str] = Field(None, description="Line item installation type")
    line_item_license_type: Optional[str] = Field(None, description="Line item license type")
    sub_total: float = Field(..., description="Subtotal amount")
    discount_percent: float = Field(..., description="Discount percentage")
    currency: str = Field(default="USD", description="Currency code")


class GenerateQuotationResponse(BaseModel):
    quotation_number: str = Field(..., description="The generated quotation number")
    file_path: str = Field(..., description="The absolute path to the generated file")
    download_url: str = Field(..., description="The URL to download the quotation")


@router.post("/generate", response_model=GenerateQuotationResponse)
async def generate_quotation_endpoint(body: GenerateQuotationRequest):
    """
    Generate a quotation document from form data.
    
    Accepts quotation fields, calculates discount and total,
    fills the PARL quotation template, and returns the generated document information.
    """
    logger.info(f"Generating quotation for: {body.quotation_number}")
    
    try:
        # Calculate discount amount and total cost
        discount_amount = body.sub_total * (body.discount_percent / 100)
        total_cost = body.sub_total - discount_amount
        
        # Parse valid_until date and format as ordinal
        try:
            valid_until_date = datetime.fromisoformat(body.valid_until)
            valid_until_formatted = format_ordinal_date(valid_until_date)
        except:
            valid_until_formatted = body.valid_until
        
        # Build data dictionary for generator
        data = {
            "client_company": body.client_company,
            "contact_person": body.contact_person,
            "client_address": body.client_address,
            "requirement": body.requirement,
            "salesperson": body.salesperson,
            "payment_terms": body.payment_terms,
            "valid_until": valid_until_formatted,
            "quotation_number": body.quotation_number,
            "delivery_method": body.delivery_method,
            "line_item_name": body.line_item_name,
            "total_cost": total_cost,
            "sub_total": body.sub_total,
            "discount_amount": discount_amount,
        }
        
        # Generate the quotation document
        file_path = generate_quotation(data)
        
        # Build download URL
        download_url = f"/quotations/download/{body.quotation_number}"
        
        logger.info(f"Successfully generated quotation {body.quotation_number} at {file_path}")
        
        return GenerateQuotationResponse(
            quotation_number=body.quotation_number,
            file_path=file_path,
            download_url=download_url,
        )
    
    except Exception as e:
        logger.error(f"Failed to generate quotation {body.quotation_number}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error generating quotation: {str(e)}"
        )


@router.get("/download/{quotation_number}")
async def download_quotation(quotation_number: str):
    """
    Download a generated quotation document by quotation number.
    """
    file_path = OUTPUT_DIR / f"{quotation_number}.docx"
    
    if not file_path.exists():
        logger.warning(f"Quotation file not found: {file_path}")
        raise HTTPException(
            status_code=404,
            detail=f"Quotation {quotation_number} not found"
        )
    
    logger.info(f"Downloading quotation: {quotation_number}")
    
    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{quotation_number}.docx",
        headers={"Content-Disposition": f"attachment; filename=\"{quotation_number}.docx\""}
    )
