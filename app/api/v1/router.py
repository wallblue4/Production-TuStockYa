# app/api/v1/router.py - ACTUALIZADO CON CONTEXTO EXISTENTE
from fastapi import APIRouter
from app.api.v1.auth import router as auth_router

# ✅ IMPORTAR MÓDULOS
from app.modules.sales import sales_router
from app.modules.transfers.router import router as transfers_router # Importamos el nuevo router de transferencias

from app.modules.admin import admin_router


# Crear router principal de la API v1
api_router = APIRouter()

# ==================== RUTAS EXISTENTES ====================

# Incluir routers de módulos
api_router.include_router(auth_router, prefix="/auth", tags=["authentication"])

# ==================== NUEVAS RUTAS ====================

# ✅ AGREGAR MÓDULO DE VENTAS
api_router.include_router(
    sales_router,
    prefix="/vendor",  # Prefijo: /api/v1/vendor/...
    tags=["Vendor - Sales"]
)

# ✅ AGREGAR MÓDULO DE TRANSFERENCIAS
api_router.include_router(
    transfers_router,
    prefix="/transfers",  # Prefijo: /api/v1/transfers/...
    tags=["Transfers"]
)

api_router.include_router(
    admin_router,
    prefix="/admin",
    tags=["Admin - Administrador"]
)


# ==================== ENDPOINTS RAÍZ ACTUALIZADOS ====================

@api_router.get("/")
async def api_root():
    """Root endpoint de la API - ACTUALIZADO"""
    return {
        "message": "TuStockYa API v1",
        "version": "2.0.0",
        "status": "active",
        "docs": "/docs",
        "available_endpoints": {
            "authentication": "/api/v1/auth",
            "sales": "/api/v1/vendor/sales ✅ IMPLEMENTADO",
            "transfers": "/api/v1/transfers ✅ IMPLEMENTADO", # ✅ ACTUALIZADO
            "warehouse": "/api/v1/warehouse (próximamente)",
            "logistics": "/api/v1/logistics (próximamente)"
        },
        "modules_status": {
            "auth": "✅ Active - Login, JWT, permissions",
            "sales": "✅ Active - 16 endpoints del vendedor",
            "transfers": "✅ Active - Funcionalidades de transferencias", # ✅ NUEVO
            "warehouse": "⏳ Pending - Funcionalidades bodeguero",
            "courier": "⏳ Pending - Funcionalidades corredor",
            "admin": "⏳ Pending - Funcionalidades administrador"
        }
    }

@api_router.get("/health")
async def health_check():
    """Health check endpoint - MEJORADO"""
    return {
        "status": "healthy",
        "service": "TuStockYa API",
        "version": "2.0.0",
        "architecture": "modular_monolith",
        "database": "postgresql_external",
        "modules": {
            "auth": {
                "status": "active",
                "endpoints_count": 4,
                "features": ["JWT", "Roles", "Permissions"]
            },
            "sales": {
                "status": "active",
                "endpoints_count": 16,
                "features": [
                    "VE001 - Escaneo con IA",
                    "VE002 - Registro de ventas",
                    "VE005 - Ventas del día",
                    "VE016 - Sistema de reservas",
                    "VE018 - Productos alternativos"
                ]
            },
            "transfers": { # ✅ NUEVO
                "status": "active",
                "endpoints_count": "3+",
                "features": [
                    "VE003 - Solicitar productos",
                    "VE006 - Procesar devoluciones",
                    "VE008 - Confirmar recepción"
                ]
            }
        }
    }

@api_router.get("/modules")
async def list_modules():
    """
    Listado de módulos disponibles
    """
    return {
        "success": True,
        "modules": [
            {
                "name": "sales",
                "prefix": "/vendor/sales",
                "description": "Funcionalidades completas del vendedor",
                "features": [
                    "VE001 - Escaneo con IA",
                    "VE002 - Registro de ventas",
                    "VE003 - Consulta de productos",
                    "VE004 - Gastos operativos",
                    "VE005 - Ventas del día",
                    "VE007 - Solicitudes de descuento",
                    "VE016 - Sistema de reservas",
                    "VE018 - Productos alternativos"
                ],
                "status": "implemented"
            },
            {
                "name": "transfers",
                "prefix": "/transfers",
                "description": "Gestión de transferencias entre ubicaciones",
                "features": [
                    "VE003 - Solicitar productos",
                    "VE006 - Procesar devoluciones",
                    "VE008 - Confirmar recepción"
                ],
                "status": "implemented" # ✅ ACTUALIZADO
            },
            {
                "name": "warehouse",
                "prefix": "/warehouse",
                "description": "Funcionalidades del bodeguero",
                "features": [
                    "BG001-BG010 - Gestión completa de bodega",
                    "Ingreso con video para IA",
                    "Control de inventario"
                ],
                "status": "pending"
            },
            {
                "name": "courier",
                "prefix": "/courier",
                "description": "Funcionalidades del corredor",
                "features": [
                    "CO001-CO007 - Logística completa",
                    "Tracking de entregas",
                    "Gestión de incidencias"
                ],
                "status": "pending"
            },
            {
                "name": "admin",
                "prefix": "/admin",
                "description": "Funcionalidades del administrador",
                "features": [
                    "AD001-AD015 - Gestión administrativa",
                    "Reportes avanzados",
                    "Configuración del sistema"
                ],
                "status": "pending"
            }
        ]
    }

# ==================== ENDPOINTS PARA DESARROLLO ====================

@api_router.get("/dev/test-sales")
async def test_sales_module():
    """
    Endpoint para testear el módulo de ventas
    """
    return {
        "module": "sales",
        "test_status": "ready",
        "test_endpoints": [
            "GET /api/v1/vendor/sales/health - Test de estado",
            "POST /api/v1/vendor/sales/scan - Test de escaneo (requiere imagen)",
            "GET /api/v1/vendor/sales/dashboard - Test de dashboard",
            "POST /api/v1/vendor/sales/reserve-product - Test de reservas"
        ],
        "auth_required": True,
        "roles_allowed": ["vendedor", "administrador"],
        "test_users": [
            "vendedor@tustockya.com / vendedor123",
            "admin@tustockya.com / admin123"
        ]
    }

@api_router.get("/dev/test-transfers")
async def test_transfers_module():
    """
    Endpoint para testear el módulo de transferencias
    """
    return {
        "module": "transfers",
        "test_status": "ready",
        "test_endpoints": [
            "POST /api/v1/transfers/request - Solicitar productos",
            "POST /api/v1/transfers/process-return - Procesar devoluciones",
            "GET /api/v1/transfers/confirm-reception/{transfer_id} - Confirmar recepción"
        ],
        "auth_required": True,
        "roles_allowed": ["bodeguero", "administrador"],
        "test_users": [
            "bodeguero@tustockya.com / bodeguero123",
            "admin@tustockya.com / admin123"
        ]
    }

