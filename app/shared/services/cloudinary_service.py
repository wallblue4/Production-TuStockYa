# app/services/cloudinary_service.py - CREAR NUEVO ARCHIVO

import cloudinary
import cloudinary.uploader
import cloudinary.api
from fastapi import UploadFile, HTTPException
from app.config.settings import settings
from typing import Optional
import uuid
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class CloudinaryService:
    
    def __init__(self):
        """Inicializar configuración de Cloudinary"""
        try:
            # Verificar que las credenciales estén configuradas
            if not all([settings.cloudinary_cloud_name, settings.cloudinary_api_key, settings.cloudinary_api_secret]):
                logger.warning("⚠️ Cloudinary no está completamente configurado")
                self.configured = False
                return
            
            cloudinary.config(
                cloud_name=settings.cloudinary_cloud_name,
                api_key=settings.cloudinary_api_key,
                api_secret=settings.cloudinary_api_secret,
                secure=True
            )
            
            self.configured = True
            logger.info("✅ Cloudinary configurado correctamente")
            
        except Exception as e:
            logger.error(f"❌ Error configurando Cloudinary: {e}")
            self.configured = False
    
    async def upload_product_reference_image(
        self, 
        image_file: UploadFile,
        product_reference: str,
        user_id: int
    ) -> str:
        """
        Subir imagen de referencia del producto a Cloudinary
        
        Args:
            image_file: Archivo de imagen a subir
            product_reference: Código de referencia del producto
            user_id: ID del usuario que sube la imagen
            
        Returns:
            str: URL segura de la imagen subida
            
        Raises:
            HTTPException: Si hay error en la subida
        """
        if not self.configured:
            raise HTTPException(
                status_code=500,
                detail="Cloudinary no está configurado correctamente"
            )
        
        try:
            # Validar tipo de archivo
            if not image_file.content_type.startswith('image/'):
                raise HTTPException(
                    status_code=400,
                    detail="El archivo debe ser una imagen válida"
                )
            
            # Validar tamaño
            if image_file.size > settings.max_image_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"La imagen no debe superar {settings.max_image_size // (1024*1024)}MB"
                )
            
            # Generar identificador único
            file_id = str(uuid.uuid4())[:8]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Generar public_id único
            safe_reference = self._sanitize_filename(product_reference)
            public_id = f"products/{safe_reference}_{timestamp}_{file_id}"
            
            # Leer contenido del archivo
            await image_file.seek(0)  # Asegurar posición inicial
            file_content = await image_file.read()
            
            logger.info(f"📤 Subiendo imagen: {public_id}")
            
            # Subir a Cloudinary con optimizaciones
            result = cloudinary.uploader.upload(
                file_content,
                public_id=public_id,
                folder=f"{settings.cloudinary_folder}/products",
                transformation=[
                    {
                        "width": 800, 
                        "height": 600, 
                        "crop": "fit",
                        "quality": "auto:good",
                        "format": "auto"  # Optimización automática de formato
                    }
                ],
                tags=[
                    "product_reference",
                    "inventory_entry",
                    f"user_{user_id}",
                    f"ref_{safe_reference}"
                ],
                context={
                    "alt": f"Imagen de referencia - {product_reference}",
                    "user_id": str(user_id),
                    "product_ref": product_reference,
                    "upload_source": "admin_inventory_entry"
                },
                # Configuraciones adicionales
                resource_type="image",
                overwrite=False,  # No sobrescribir si existe
                unique_filename=True,
                use_filename=False
            )
            
            # Verificar resultado exitoso
            if 'secure_url' not in result:
                raise Exception("Cloudinary no retornó URL válida")
            
            logger.info(f"✅ Imagen subida exitosamente: {result['secure_url']}")
            logger.info(f"📊 Detalles: {result.get('bytes', 0)} bytes, {result.get('format', 'unknown')} format")
            
            return result["secure_url"]
            
        except HTTPException:
            # Re-lanzar HTTPExceptions tal como están
            raise
        except Exception as e:
            logger.error(f"❌ Error subiendo imagen a Cloudinary: {str(e)}")
            raise HTTPException(
                status_code=500, 
                detail=f"Error subiendo imagen: {str(e)}"
            )
    
    async def delete_image(self, image_url: str) -> bool:
        """
        Eliminar imagen de Cloudinary usando su URL
        
        Args:
            image_url: URL de la imagen a eliminar
            
        Returns:
            bool: True si se eliminó exitosamente, False en caso contrario
        """
        if not self.configured:
            logger.warning("⚠️ Cloudinary no configurado, no se puede eliminar imagen")
            return False
        
        try:
            # Extraer public_id de la URL de Cloudinary
            public_id = self._extract_public_id_from_url(image_url)
            
            if not public_id:
                logger.warning(f"⚠️ No se pudo extraer public_id de URL: {image_url}")
                return False
            
            logger.info(f"🗑️ Eliminando imagen: {public_id}")
            
            # Eliminar de Cloudinary
            result = cloudinary.uploader.destroy(public_id)
            success = result.get("result") == "ok"
            
            if success:
                logger.info(f"✅ Imagen eliminada: {public_id}")
            else:
                logger.warning(f"⚠️ No se pudo eliminar imagen: {public_id} - {result}")
                
            return success
            
        except Exception as e:
            logger.error(f"❌ Error eliminando imagen: {str(e)}")
            return False
    
    def get_image_info(self, image_url: str) -> Optional[dict]:
        """
        Obtener información detallada de una imagen en Cloudinary
        
        Args:
            image_url: URL de la imagen
            
        Returns:
            dict: Información de la imagen o None si no se encuentra
        """
        if not self.configured:
            return None
        
        try:
            public_id = self._extract_public_id_from_url(image_url)
            
            if not public_id:
                return None
            
            # Obtener información de Cloudinary
            result = cloudinary.api.resource(public_id)
            
            return {
                "public_id": result.get("public_id"),
                "format": result.get("format"),
                "width": result.get("width"),
                "height": result.get("height"),
                "bytes": result.get("bytes"),
                "created_at": result.get("created_at"),
                "tags": result.get("tags", []),
                "context": result.get("context", {}),
                "secure_url": result.get("secure_url")
            }
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo info de imagen: {str(e)}")
            return None
    
    def _extract_public_id_from_url(self, image_url: str) -> Optional[str]:
        """
        Extraer public_id de una URL de Cloudinary
        
        Formato URL: https://res.cloudinary.com/[cloud]/image/upload/[transformations/]v[version]/[public_id].[format]
        """
        try:
            if "cloudinary.com" not in image_url:
                return None
            
            # Dividir URL por partes
            parts = image_url.split("/")
            
            # Encontrar la posición de "upload"
            upload_index = -1
            for i, part in enumerate(parts):
                if part == "upload":
                    upload_index = i
                    break
            
            if upload_index == -1:
                return None
            
            # El public_id está después de "upload" (saltando transformaciones y versión)
            public_id_parts = parts[upload_index + 1:]
            
            # Filtrar transformaciones y versión
            filtered_parts = []
            for part in public_id_parts:
                # Saltar transformaciones (contienen _,c_,w_,h_, etc.)
                if any(x in part for x in ["c_", "w_", "h_", "q_", "f_"]):
                    continue
                # Saltar versión (v123456)
                if part.startswith("v") and part[1:].isdigit():
                    continue
                filtered_parts.append(part)
            
            if not filtered_parts:
                return None
            
            # Reconstruir public_id sin extensión
            public_id = "/".join(filtered_parts)
            
            # Remover extensión del último segmento
            if "." in public_id:
                public_id = public_id.rsplit(".", 1)[0]
            
            return public_id
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo public_id: {str(e)}")
            return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Limpiar nombre de archivo para uso seguro en Cloudinary
        """
        import re
        
        # Remover caracteres especiales y espacios
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', filename)
        
        # Limitar longitud
        sanitized = sanitized[:50]
        
        # Asegurar que no esté vacío
        if not sanitized:
            sanitized = "product"
        
        return sanitized
    
    def health_check(self) -> dict:
        """
        Verificar estado de conexión con Cloudinary
        
        Returns:
            dict: Estado de salud del servicio
        """
        try:
            if not self.configured:
                return {
                    "status": "error",
                    "message": "Cloudinary no está configurado",
                    "configured": False
                }
            
            # Probar conexión básica con API de Cloudinary
            result = cloudinary.api.ping()
            
            return {
                "status": "healthy",
                "message": "Cloudinary funcionando correctamente",
                "configured": True,
                "cloud_name": settings.cloudinary_cloud_name,
                "api_response": result
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error conectando con Cloudinary: {str(e)}",
                "configured": self.configured
            }

# ==================== INSTANCIA GLOBAL DEL SERVICIO ====================

cloudinary_service = CloudinaryService()