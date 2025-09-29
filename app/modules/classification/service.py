# app/modules/classification/service.py
import httpx
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from .repository import ClassificationRepository
from .schemas import ScanResponse, ProductMatch, ScanResults

class ClassificationService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ClassificationRepository(db)
        self.microservice_url = "https://sneaker-api-v2.onrender.com"
    
    async def scan_product(self, image: UploadFile, current_user: Any, include_transfer_options: bool = True) -> Dict[str, Any]:
        """Procesar escaneo de producto con IA"""
        start_time = datetime.now()
        
        try:
            # Leer contenido de imagen
            content = await image.read()
            await image.seek(0)  # Reset file pointer
            
            # Intentar clasificación con microservicio
            classification_result = await self._call_classification_microservice(content)
            
            if classification_result:
                # Procesar resultados del microservicio
                processed_results = await self._process_classification_results(
                    classification_result, current_user, include_transfer_options
                )
            else:
                # Fallback si microservicio no disponible
                processed_results = await self._classification_fallback(current_user)
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return {
                "success": True,
                "scan_timestamp": datetime.now().isoformat(),
                "scanned_by": {
                    "user_id": current_user.id,
                    "email": current_user.email,
                    "name": f"{current_user.first_name} {current_user.last_name}",
                    "role": current_user.role,
                    "location_id": current_user.location_id
                },
                "user_location": f"Local #{current_user.location_id}",
                "results": processed_results,
                "availability_summary": self._calculate_availability_summary(processed_results),
                "processing_time_ms": round(processing_time, 2),
                "image_info": {
                    "filename": image.filename,
                    "size_bytes": len(content),
                    "content_type": image.content_type
                },
                "classification_service": {
                    "service": "microservice_integration",
                    "url": self.microservice_url,
                    "status": "available" if classification_result else "fallback"
                },
                "inventory_service": {
                    "source": "local_database",
                    "locations_searched": "all_active",
                    "include_transfer_options": include_transfer_options
                }
            }
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Error procesando escaneo",
                    "details": str(e),
                    "processing_time_ms": round(processing_time, 2)
                }
            )
    
    async def _call_classification_microservice(self, image_content: bytes) -> Dict[str, Any]:
        """Llamar al microservicio de clasificación"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                files = {"image": ("scan.jpg", image_content, "image/jpeg")}
                response = await client.post(
                    f"{self.microservice_url}/api/v2/classify",
                    files=files
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"Microservice error: {response.status_code}")
                    return None
                    
        except Exception as e:
            print(f"Error calling microservice: {e}")
            return None
    
    async def _process_classification_results(self, classification_result: Dict, current_user: Any, include_transfer_options: bool) -> Dict[str, Any]:
        """Procesar resultados de clasificación y agregar información de inventario"""
        results = classification_result.get('results', [])
        processed_matches = []
        
        for rank, result in enumerate(results[:5], 1):  # Top 5 resultados
            # Buscar producto en base de datos local
            local_products = self.repository.search_products_by_reference(
                result.get('reference_code', '')
            )
            
            if local_products:
                product = local_products[0]
                availability = self.repository.get_product_availability(
                    product['id'], f"Local #{current_user.location_id}"
                )
                
                match = ProductMatch(
                    rank=rank,
                    similarity_score=result.get('similarity_score', 0.0),
                    confidence_percentage=result.get('confidence_percentage', 0.0),
                    confidence_level=result.get('confidence_level', 'low'),
                    reference={
                        "code": product['reference_code'],
                        "brand": product['brand'],
                        "model": product['model'],
                        "color": product['color_info'] or 'N/A',
                        "description": product['description'],
                        "photo": product['image_url'] or ""
                    },
                    availability=self._format_availability(availability, include_transfer_options),
                    locations=availability,
                    pricing={
                        "unit_price": product['unit_price'],
                        "box_price": product['box_price'],
                        "has_pricing": True
                    },
                    classification_source="microservice",
                    inventory_source="local_database",
                    brand_extraction={
                        "original_brand": result.get('brand', ''),
                        "final_brand": product['brand'],
                        "extraction_method": "ai_classification"
                    },
                    suggestions=self._get_product_suggestions(product),
                    original_db_id=product['id'],
                    image_path=product['image_url'] or ""
                )
                processed_matches.append(match)
        
        return {
            "best_match": processed_matches[0] if processed_matches else None,
            "alternative_matches": processed_matches[1:] if len(processed_matches) > 1 else [],
            "total_matches_found": len(processed_matches)
        }
    
    async def _classification_fallback(self, current_user: Any) -> Dict[str, Any]:
        """Fallback cuando microservicio no está disponible"""
        return {
            "best_match": None,
            "alternative_matches": [],
            "total_matches_found": 0
        }
    
    def _format_availability(self, availability: Dict, include_transfer_options: bool) -> Dict[str, Any]:
        """Formatear información de disponibilidad"""
        current_stock = sum(item['quantity'] for item in availability['current_location'])
        other_stock = sum(item['quantity'] for item in availability['other_locations'])
        
        return {
            "summary": {
                "current_location": {
                    "has_stock": current_stock > 0,
                    "total_stock": current_stock
                },
                "other_locations": {
                    "has_stock": other_stock > 0,
                    "total_stock": other_stock
                },
                "total_system": {
                    "total_stock": current_stock + other_stock,
                    "total_locations": len(set(item['location'] for item in availability['other_locations'])) + (1 if current_stock > 0 else 0)
                }
            },
            "recommended_action": "Venta directa" if current_stock > 0 else ("Solicitar transferencia" if other_stock > 0 else "Producto no disponible"),
            "can_sell_now": current_stock > 0,
            "can_request_transfer": other_stock > 0 and include_transfer_options
        }
    
    def _get_product_suggestions(self, product: Dict) -> Dict[str, Any]:
        """Obtener sugerencias para el producto"""
        return {
            "can_add_to_inventory": True,
            "can_search_suppliers": False,
            "similar_products_available": len(self.repository.search_similar_products(product['brand'], product['model'])) > 0
        }
    
    def _calculate_availability_summary(self, results: Dict) -> Dict[str, Any]:
        """Calcular resumen de disponibilidad general"""
        if not results.get('best_match'):
            return {
                "products_available_locally": 0,
                "products_requiring_transfer": 0,
                "products_classified_only": 0,
                "can_sell_immediately": False,
                "transfer_options_available": False,
                "classification_successful": False
            }
        
        locally_available = 1 if results['best_match']['availability']['can_sell_now'] else 0
        transfer_available = 1 if results['best_match']['availability']['can_request_transfer'] else 0
        
        return {
            "products_available_locally": locally_available,
            "products_requiring_transfer": transfer_available,
            "products_classified_only": 1 if not locally_available and not transfer_available else 0,
            "can_sell_immediately": locally_available > 0,
            "transfer_options_available": transfer_available > 0,
            "classification_successful": True
        }