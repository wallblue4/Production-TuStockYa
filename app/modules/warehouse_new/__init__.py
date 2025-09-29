# app/modules/warehouse_new/__init__.py
"""
Módulo Warehouse - Funcionalidades del Bodeguero

Este módulo implementa las operaciones principales del bodeguero:
- BG001: Recibir y procesar solicitudes de productos
- BG002: Confirmar disponibilidad y preparar productos  
- BG003: Entregar productos a corredor con descuento automático
- BG006: Consultar inventario disponible por ubicación

Arquitectura:
- router.py: Endpoints del bodeguero
- service.py: Lógica de negocio de bodega
- repository.py: Acceso a datos de bodega
- schemas.py: Modelos de request/response
"""

from .router import router
from .service import WarehouseService
from .repository import WarehouseRepository

__all__ = [
    "router",
    "WarehouseService", 
    "WarehouseRepository"
]