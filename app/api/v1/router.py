from fastapi import APIRouter
from app.api.v1.auth import router as auth_router

# Crear router principal de la API v1
api_router = APIRouter()

# Incluir routers de módulos
api_router.include_router(auth_router, prefix="/auth", tags=["authentication"])

# Placeholder para futuros módulos
# api_router.include_router(sales_router, prefix="/sales", tags=["sales"])
# api_router.include_router(warehouse_router, prefix="/warehouse", tags=["warehouse"])
# api_router.include_router(logistics_router, prefix="/logistics", tags=["logistics"])

@api_router.get("/")
async def api_root():
    """Root endpoint de la API"""
    return {
        "message": "TuStockYa API v1",
        "version": "2.0.0",
        "status": "active",
        "docs": "/docs",
        "available_endpoints": {
            "authentication": "/api/v1/auth",
            "sales": "/api/v1/sales (próximamente)",
            "warehouse": "/api/v1/warehouse (próximamente)",
            "logistics": "/api/v1/logistics (próximamente)"
        }
    }

@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "TuStockYa API",
        "version": "2.0.0"
    }