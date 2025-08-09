# app/modules/admin/__init__.py - ACTUALIZADO

"""
Módulo Admin - Funcionalidades del Administrador

Este módulo implementa todas las funcionalidades requeridas para el rol de administrador:

- AD001: Gestionar múltiples locales de venta asignados ✅
- AD002: Supervisar múltiples bodegas bajo su responsabilidad ✅
- AD003: Crear usuarios vendedores en locales asignados ✅
- AD004: Crear usuarios bodegueros en bodegas asignadas ✅
- AD005: Asignar vendedores a locales específicos ✅
- AD006: Asignar bodegueros a bodegas específicas ✅
- AD007: Configurar costos fijos (arriendo, servicios, nómina) ✅
- AD008: Configurar costos variables (mercancía, comisiones) ✅
- AD009: Procesar ventas al por mayor ✅
- AD010: Generar reportes de ventas por local y período ✅
- AD011: Configurar alertas de inventario mínimo ✅
- AD012: Aprobar solicitudes de descuento de vendedores ✅
- AD013: Supervisar traslados entre locales y bodegas ✅
- AD014: Supervisar performance de vendedores y bodegueros ✅
- AD015: Gestionar asignación de modelos a bodegas específicas ✅
- AD016: Registro de inventario con video IA (MIGRADO DE BG010) ✅

**NUEVA FUNCIONALIDAD AD016:**
Registro estratégico de inventario mediante video IA, migrada desde el módulo warehouse 
para centralizar la gestión de inventario en manos de administradores.

Arquitectura:
- router.py: Endpoints FastAPI
- service.py: Lógica de negocio
- repository.py: Acceso a datos
- schemas.py: Modelos Pydantic de request/response
"""

from .router import router as admin_router
from .service import AdminService
from .repository import AdminRepository

__all__ = [
    "admin_router",
    "AdminService", 
    "AdminRepository"
]