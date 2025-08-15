# app/config/database.py - ACTUALIZADO
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .settings import settings

# Configuración del engine con SSL para producción
engine_kwargs = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "echo": settings.debug
}

# Agregar SSL para producción en Render
if "render" in settings.database_url:
    engine_kwargs["connect_args"] = {
        "sslmode": "require"
    }

# Create engine
engine = create_engine(
    settings.database_url_with_ssl,
    **engine_kwargs
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Database dependency
def get_db():
    """Database dependency for FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()