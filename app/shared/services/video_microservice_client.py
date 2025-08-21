# app/shared/services/video_microservice_client.py - NUEVO ARCHIVO
import httpx
import json
import logging
from typing import Dict, Any, Optional
from fastapi import UploadFile, HTTPException
from app.config.settings import settings

logger = logging.getLogger(__name__)

class VideoMicroserviceClient:
    """Cliente para comunicación con microservicio de video"""
    
    def __init__(self):
        self.base_url = settings.VIDEO_MICROSERVICE_URL
        self.api_key = settings.VIDEO_MICROSERVICE_API_KEY
        self.timeout = 300  # 5 minutos para upload
    
    def _get_headers(self) -> Dict[str, str]:
        """Headers para autenticación"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers
    
    async def submit_video_for_processing(
        self,
        job_id: int,
        video_file: UploadFile,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enviar video al microservicio para procesamiento
        """
        try:
            logger.info(f"🔄 Enviando video al microservicio - Job ID: {job_id}")
            
            # Preparar datos
            files = {"video": (video_file.filename, video_file.file, video_file.content_type)}
            data = {
                "job_id": job_id,
                "callback_url": f"{settings.BASE_URL}/api/v1/admin/video-processing-complete",
                "metadata": json.dumps(metadata)
            }
            
            # Headers para multipart
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/process-video",
                    files=files,
                    data=data,
                    headers=headers
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"✅ Video enviado exitosamente - Job ID: {job_id}")
                    return result
                else:
                    error_msg = f"Error del microservicio: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    raise HTTPException(status_code=502, detail=error_msg)
                    
        except httpx.TimeoutException:
            error_msg = f"Timeout enviando video al microservicio - Job ID: {job_id}"
            logger.error(error_msg)
            raise HTTPException(status_code=504, detail="Timeout procesando video")
        except Exception as e:
            error_msg = f"Error comunicándose con microservicio: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=502, detail=error_msg)
    
    async def get_processing_status(self, job_id: int) -> Dict[str, Any]:
        """Consultar estado de procesamiento"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/job-status/{job_id}",
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    raise HTTPException(status_code=response.status_code, detail=response.text)
                    
        except Exception as e:
            logger.error(f"Error consultando estado job {job_id}: {e}")
            raise HTTPException(status_code=502, detail=f"Error consultando estado: {str(e)}")
    
    async def health_check(self) -> bool:
        """Verificar salud del microservicio"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except:
            return False