# app/main.py - ACTUALIZADO
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config.settings import settings
from app.core.middleware import setup_middleware
from app.api.v1.router import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 TuStockYa API Starting...")
    print(f"📍 Version: {settings.version}")
    print(f"🌍 Environment: {'Development' if settings.debug else 'Production'}")
    print(f"🔐 JWT Algorithm: {settings.algorithm}")
    print(f"⏰ Token Expire: {settings.access_token_expire_minutes} minutes")
    print(f"🗄️  Database: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'localhost'}")
    
    yield
    
    
    # Shutdown
    print("🛑 TuStockYa API Shutting down...")

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Sistema de Gestión de Inventario y Ventas para Calzado Deportivo",
    docs_url="/docs" if settings.debug else "/docs",  # Mantener docs en producción
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan
)

# Setup middleware
setup_middleware(app)

# Include routers
app.include_router(api_router, prefix="/api/v1")

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "🚀 TuStockYa API - Sistema de Gestión de Inventario",
        "version": settings.version,
        "status": "running",
        "environment": "production" if not settings.debug else "development",
        "docs": "/docs",
        "api": "/api/v1"
    }

# Health check para Render
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.version,
        "app": settings.app_name,
        "environment": "production" if not settings.debug else "development"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )