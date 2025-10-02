# app/modules/classification/router.py
from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.auth.dependencies import require_roles
from .service import ClassificationService
from .schemas import ScanResponse

router = APIRouter()

@router.post("/scan")
async def scan_product(
    image: UploadFile = File(..., description="Imagen del producto a escanear"),
    include_transfer_options: bool = Query(True, description="Incluir opciones de transferencia"),
    current_user = Depends(require_roles(["seller", "administrador", "boss"])),
    db: Session = Depends(get_db)
):
    """
    VE001: Escaneo de productos con IA y verificación de stock
    
    **Funcionalidad:**
    - Clasificación automática usando microservicio de IA
    - Búsqueda en inventario local por ubicación
    - Verificación de disponibilidad en otras ubicaciones
    - Sugerencias de transferencia cuando sea necesario
    - Fallback cuando microservicio no esté disponible
    
    **Respuesta incluye:**
    - Producto mejor coincidencia con confianza
    - Productos alternativos
    - Disponibilidad por ubicación
    - Opciones de transferencia
    - Información de precios
    """
    service = ClassificationService(db)
    return await service.scan_product(image, current_user, include_transfer_options)

@router.get("/health")
async def classification_health():
    """Health check del módulo de clasificación"""
    return {
        "service": "classification",
        "status": "healthy",
        "version": "1.0.0",
        "features": [
            "Escaneo con IA",
            "Búsqueda en inventario local",
            "Verificación de disponibilidad",
            "Sugerencias de transferencia"
        ]
    }