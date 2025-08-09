from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App Info
    app_name: str = "TuStockYa API"
    version: str = "2.0.0"
    debug: bool = False
    
    # Database
    database_url: str
    redis_url: Optional[str] = None
    
    # Security
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 1 week
    
    # External Services
    cloudinary_cloud_name: Optional[str] = None
    cloudinary_api_key: Optional[str] = None
    cloudinary_api_secret: Optional[str] = None
    cloudinary_folder: str = "tustockya"
    
    # File Upload
    max_image_size: int = 10 * 1024 * 1024  # 10MB
    allowed_image_formats: set = {"image/jpeg", "image/png", "image/webp", "image/jpg"}

    # ✅ NUEVO: Microservicio Video
    VIDEO_MICROSERVICE_URL: str = Field(
        default="http://localhost:8001",  # Para desarrollo local
        description="URL del microservicio de procesamiento de video"
    )
    VIDEO_MICROSERVICE_API_KEY: Optional[str] = Field(
        default=None,
        description="API Key para autenticar con microservicio"
    )
    
    # ✅ NUEVO: Webhooks
    BASE_URL: str = Field(
        default="http://localhost:8000",
        description="URL base de este sistema para webhooks"
    )
    
    # ✅ NUEVO: Configuración de video
    MAX_VIDEO_SIZE_MB: int = Field(default=100, description="Tamaño máximo de video en MB")
    MAX_VIDEO_DURATION_SECONDS: int = Field(default=180, description="Duración máxima en segundos")

    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()