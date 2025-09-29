# app/modules/classification/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.shared.schemas.common import BaseResponse, ProductInfo

class ScanRequest(BaseModel):
    include_transfer_options: bool = Field(True, description="Incluir opciones de transferencia")

class BrandExtraction(BaseModel):
    original_brand: str
    final_brand: str
    extraction_method: str

class ProductReference(BaseModel):
    code: str
    brand: str
    model: str
    color: str
    description: str
    photo: str

class AvailabilitySummary(BaseModel):
    current_location: Dict[str, Any]
    other_locations: Dict[str, Any]
    total_system: Dict[str, Any]

class ProductMatch(BaseModel):
    rank: int
    similarity_score: float
    confidence_percentage: float
    confidence_level: str
    reference: ProductReference
    availability: Dict[str, Any]
    locations: Dict[str, Any]
    pricing: Dict[str, Any]
    classification_source: str
    inventory_source: str
    brand_extraction: BrandExtraction
    suggestions: Dict[str, Any]
    original_db_id: int
    image_path: str

class ScanResults(BaseModel):
    best_match: Optional[ProductMatch]
    alternative_matches: List[ProductMatch]
    total_matches_found: int

class ScanResponse(BaseResponse):
    scan_timestamp: datetime
    scanned_by: Dict[str, Any]
    user_location: str
    results: ScanResults
    availability_summary: Dict[str, Any]
    processing_time_ms: float
    image_info: Dict[str, Any]
    classification_service: Dict[str, Any]
    inventory_service: Dict[str, Any]