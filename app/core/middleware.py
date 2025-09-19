from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from app.config.settings import settings
import time
import logging

logger = logging.getLogger(__name__)

def setup_middleware(app: FastAPI):
    """Configure all middleware for the application"""

    # CORS - Enhanced security configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type", 
            "Accept",
            "Origin",
            "X-Requested-With",
            "X-CSRF-Token"
        ],
        max_age=3600  # Cache preflight requests for 1 hour
    )
    
    # Trusted hosts (configure for production)
    # app.add_middleware(
    #     TrustedHostMiddleware, 
    #     allowed_hosts=["localhost", "127.0.0.1"]
    # )
    
    @app.middleware("http")
    async def log_requests(request, call_next):
        start_time = time.time()
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        logger.info(
            f"{request.method} {request.url.path} - "
            f"Status: {response.status_code} - "
            f"Time: {process_time:.4f}s"
        )
        
        return response