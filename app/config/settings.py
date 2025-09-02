# app/config/settings.py - ACTUALIZADO
from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    # App Info
    app_name: str = "TuStockYa API"
    version: str = "2.0.0"
    debug: bool = False
    
    # Database - Configuración para Render
    database_url: str = os.getenv("DATABASE_URL", "postgresql://tustockya:O23WBhBX6WzqJPZLuJOvixxduQfC1WI1@dpg-d1d3pc6mcj7s73fcs1o0-a.oregon-postgres.render.com/tustockya")
    redis_url: Optional[str] = None
    
    # Security
    secret_key: str = os.getenv("SECRET_KEY", "change-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080
    
    # External Services
    cloudinary_cloud_name: Optional[str] = None
    cloudinary_api_key: Optional[str] = None
    cloudinary_api_secret: Optional[str] = None
    cloudinary_folder: str = "tustockya"

    
    # File Upload
    max_image_size: int = 10 * 1024 * 1024
    allowed_image_formats: set = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
    
    # Server - Configuración para Render
    host: str = "0.0.0.0"
    port: int = int(os.getenv("PORT", 10000))

    VIDEO_MICROSERVICE_URL: str = os.getenv(
        "VIDEO_MICROSERVICE_URL", 
        "https://video-processing-microservice.onrender.com"  
    )
    VIDEO_MICROSERVICE_API_KEY: Optional[str] = os.getenv("VIDEO_MICROSERVICE_API_KEY","a7F!kP@8j#xT&z4cQv*bN2yM$wG6uH9eD0rL%sI3oU1tY_pA")
    VIDEO_MICROSERVICE_TIMEOUT: int = int(os.getenv("VIDEO_MICROSERVICE_TIMEOUT", "300"))
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:10000")

    
    # SSL para PostgreSQL en producción
    @property
    def database_url_with_ssl(self) -> str:
        """Agregar SSL para conexiones de producción"""
        if self.database_url and "render" in self.database_url:
            if "?sslmode=" not in self.database_url:
                return f"{self.database_url}?sslmode=require"
        return self.database_url
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = 'ignore'

settings = Settings()
