# app/modules/warehouse/__init__.py - ACTUALIZADO

"""
Módulo Warehouse - Funcionalidades del Bodeguero

Este módulo implementa todas las funcionalidades requeridas para el rol de bodeguero:

- BG001: Recibir y procesar solicitudes de productos ✅
- BG002: Confirmar disponibilidad y preparar productos ✅  
- BG003: Entregar productos a corredor ✅
- BG004: Recibir devoluciones de productos ✅
- BG005: Actualizar ubicaciones de productos entre bodegas/locales ✅
- BG006: Consultar inventario disponible por ubicación general ✅
- BG007: Registrar historial de entregas y recepciones ✅
- BG008: Gestionar múltiples bodegas asignadas ✅
- BG009: Reportar discrepancias de inventario ✅
- BG010: Revertir movimientos de inventario en caso de entrega fallida ✅

**NOTA:** La funcionalidad de "Ingreso de nueva mercancía mediante video para entrenamiento de IA" 
fue MIGRADA al módulo Admin como AD016, ya que corresponde a una función estratégica 
de gestión de inventario que debe ser manejada por administradores.

Arquitectura:
- router.py: Endpoints FastAPI
- service.py: Lógica de negocio
- repository.py: Acceso a datos
- schemas.py: Modelos Pydantic de request/response
"""

from .router import router as warehouse_router
from .service import WarehouseService
from .repository import WarehouseRepository

__all__ = [
    "warehouse_router",
    "WarehouseService", 
    "WarehouseRepository"
]