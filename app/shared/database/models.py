from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.config.database import Base

class TimestampMixin:
    """Mixin para timestamps automáticos"""
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=False)

# ===== TABLAS BASE =====

class Location(Base):
    """Modelo de Ubicación (Local/Bodega) - EXACTO A BD"""
    __tablename__ = "locations"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)
    address = Column(Text)
    phone = Column(String(50))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    
    # Relationships
    users = relationship("User", back_populates="location")
    expenses = relationship("Expense", back_populates="location")
    sales = relationship("Sale", back_populates="location")

class User(Base):
    """Modelo de Usuario - EXACTO A BD"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255), nullable=False)
    role = Column(String(50), default='vendedor', nullable=False)  # ✅ CORREGIDO: 'vendedor'
    location_id = Column(Integer, ForeignKey("locations.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    
    # Relationships
    location = relationship("Location", back_populates="users")
    sales = relationship("Sale", back_populates="seller")
    expenses = relationship("Expense", back_populates="user")
    location_assignments = relationship("UserLocationAssignment", back_populates="user")
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

# ===== PRODUCTOS =====

class Product(Base, TimestampMixin):
    """Modelo de Producto - EXACTO A BD"""
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    reference_code = Column(String(255), nullable=False, index=True)
    description = Column(String(255), nullable=False)  # ✅ CORREGIDO: Required
    brand = Column(String(255))
    model = Column(String(255))
    color_info = Column(String(255))
    video_url = Column(String(255))
    image_url = Column(String(255))
    total_quantity = Column(Integer, default=0)  # ✅ AGREGADO
    location_name = Column(String(255), nullable=False, index=True)
    unit_price = Column(Numeric(10, 2), default=0.0)
    box_price = Column(Numeric(10, 2), default=0.0)
    is_active = Column(Integer, default=1)  # ✅ CORREGIDO: Integer, not Boolean
    
    # ✅ CONSTRAINT AGREGADO
    __table_args__ = (
        UniqueConstraint('reference_code', 'location_name', name='products_unique_per_location'),
    )
    
    # Relationships
    sizes = relationship("ProductSize", back_populates="product")
    mappings = relationship("ProductMapping", back_populates="product")
    inventory_changes = relationship("InventoryChange", back_populates="product")

class ProductSize(Base, TimestampMixin):
    """Modelo de Tallas de Producto - EXACTO A BD"""
    __tablename__ = "product_sizes"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    size = Column(String(255), nullable=False)
    quantity = Column(Integer, default=0)
    quantity_exhibition = Column(Integer, default=0)
    location_name = Column(String(255), nullable=False)
    
    # Relationships
    product = relationship("Product", back_populates="sizes")

class ProductMapping(Base):
    """Modelo de Mapeo de Productos con IA - EXACTO A BD"""
    __tablename__ = "product_mappings"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    api_reference_code = Column(String(255), nullable=False, index=True)
    model_name = Column(String(255), index=True)
    similarity_score = Column(Numeric(10, 2), default=1.0)
    original_db_id = Column(Integer)
    image_path = Column(String(255))
    created_at = Column(DateTime, nullable=False)
    
    # Relationships
    product = relationship("Product", back_populates="mappings")

class InventoryChange(Base):
    """Modelo de Cambios de Inventario - EXACTO A BD"""
    __tablename__ = "inventory_changes"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    change_type = Column(String(255), nullable=False)
    size = Column(String(255))
    quantity_before = Column(Integer)
    quantity_after = Column(Integer)
    reference_id = Column(Integer)
    user_id = Column(Integer)
    notes = Column(String(255))
    created_at = Column(DateTime, nullable=False)
    
    # Relationships
    product = relationship("Product", back_populates="inventory_changes")

# ===== VENTAS =====

class Sale(Base):
    """Modelo de Venta - EXACTO A BD"""
    __tablename__ = "sales"
    
    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    receipt_image = Column(Text)
    sale_date = Column(DateTime, server_default=func.current_timestamp())
    status = Column(String(50), default='completed')
    notes = Column(Text)
    requires_confirmation = Column(Boolean, default=False)
    confirmed = Column(Boolean, default=True)
    confirmed_at = Column(DateTime)
    
    # Relationships
    seller = relationship("User", back_populates="sales")
    location = relationship("Location", back_populates="sales")
    items = relationship("SaleItem", back_populates="sale")
    payments = relationship("SalePayment", back_populates="sale")

class SaleItem(Base):
    """Modelo de Item de Venta - EXACTO A BD"""
    __tablename__ = "sale_items"
    
    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    sneaker_reference_code = Column(String(255), nullable=False)
    brand = Column(String(255), nullable=False)
    model = Column(String(255), nullable=False)
    color = Column(String(255))
    size = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    
    # Relationships
    sale = relationship("Sale", back_populates="items")

class SalePayment(Base):
    """Modelo de Método de Pago - EXACTO A BD"""
    __tablename__ = "sale_payments"
    
    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    payment_type = Column(String(50), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    reference = Column(String(255))
    created_at = Column(DateTime, server_default=func.current_timestamp())
    
    # Relationships
    sale = relationship("Sale", back_populates="payments")

# ===== GASTOS =====

class Expense(Base):
    """Modelo de Gastos - EXACTO A BD"""
    __tablename__ = "expenses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    concept = Column(String(255), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    receipt_image = Column(Text)
    expense_date = Column(DateTime, server_default=func.current_timestamp())
    notes = Column(Text)
    
    # Relationships
    user = relationship("User", back_populates="expenses")
    location = relationship("Location", back_populates="expenses")

# ===== TRANSFERENCIAS =====

class TransferRequest(Base):
    """Modelo de Solicitud de Transferencia - EXACTO A BD"""
    __tablename__ = "transfer_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    destination_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    sneaker_reference_code = Column(String(255), nullable=False)
    brand = Column(String(255), nullable=False)
    model = Column(String(255), nullable=False)
    size = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    purpose = Column(String(50), nullable=False)
    pickup_type = Column(String(50), nullable=False)
    destination_type = Column(String(50), default='bodega')
    courier_id = Column(Integer, ForeignKey("users.id"))
    warehouse_keeper_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String(50), default='pending')
    requested_at = Column(DateTime, server_default=func.current_timestamp())
    accepted_at = Column(DateTime)
    picked_up_at = Column(DateTime)
    delivered_at = Column(DateTime)
    notes = Column(Text)
    confirmed_reception_at = Column(DateTime)
    received_quantity = Column(Integer)
    reception_notes = Column(Text)
    courier_accepted_at = Column(DateTime)
    courier_notes = Column(Text)
    estimated_pickup_time = Column(Integer)
    pickup_notes = Column(Text)
    
    # Relationships
    requester = relationship("User", foreign_keys=[requester_id])
    courier = relationship("User", foreign_keys=[courier_id])
    warehouse_keeper = relationship("User", foreign_keys=[warehouse_keeper_id])
    source_location = relationship("Location", foreign_keys=[source_location_id])
    destination_location = relationship("Location", foreign_keys=[destination_location_id])

# ===== SISTEMA DE RESERVAS =====

class ProductReservation(Base):
    """Modelo de Reservas de Productos - EXACTO A BD"""
    __tablename__ = "product_reservations"
    
    id = Column(Integer, primary_key=True, index=True)
    sneaker_reference_code = Column(String(255), nullable=False)
    size = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    purpose = Column(String(50), nullable=False)
    status = Column(String(50), default='active')
    reserved_at = Column(DateTime, server_default=func.current_timestamp())
    expires_at = Column(DateTime, nullable=False)
    released_at = Column(DateTime)
    
    # Relationships
    user = relationship("User")
    location = relationship("Location")

# ===== OTROS MODELOS =====

class DiscountRequest(Base):
    """Modelo de Solicitudes de Descuento - EXACTO A BD"""
    __tablename__ = "discount_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(50), default='pending')
    administrator_id = Column(Integer, ForeignKey("users.id"))
    requested_at = Column(DateTime, server_default=func.current_timestamp())
    reviewed_at = Column(DateTime)
    admin_comments = Column(Text)
    
    # Relationships
    seller = relationship("User", foreign_keys=[seller_id])
    administrator = relationship("User", foreign_keys=[administrator_id])

class UserLocationAssignment(Base):
    """Modelo de Asignación de Usuarios a Ubicaciones - EXACTO A BD"""
    __tablename__ = "user_location_assignments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    role_at_location = Column(String(50), default='bodeguero', nullable=False)
    is_active = Column(Boolean, default=True)
    assigned_at = Column(DateTime, server_default=func.current_timestamp())
    
    # ✅ CONSTRAINT AGREGADO
    __table_args__ = (
        UniqueConstraint('user_id', 'location_id', name='user_location_assignments_user_id_location_id_key'),
    )
    
    # Relationships
    user = relationship("User", back_populates="location_assignments")
    location = relationship("Location")

class ReturnRequest(Base):
    """Modelo de Solicitudes de Devolución - EXACTO A BD"""
    __tablename__ = "return_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    original_transfer_id = Column(Integer, ForeignKey("transfer_requests.id"), nullable=False)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    destination_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    sneaker_reference_code = Column(String(255), nullable=False)
    size = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    courier_id = Column(Integer, ForeignKey("users.id"))
    warehouse_keeper_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String(50), default='pending')
    requested_at = Column(DateTime, server_default=func.current_timestamp())
    completed_at = Column(DateTime)
    notes = Column(Text)
    
    # Relationships
    original_transfer = relationship("TransferRequest")
    requester = relationship("User", foreign_keys=[requester_id])
    courier = relationship("User", foreign_keys=[courier_id])
    warehouse_keeper = relationship("User", foreign_keys=[warehouse_keeper_id])

class ReturnNotification(Base):
    """Modelo de Notificaciones de Devolución - EXACTO A BD"""
    __tablename__ = "return_notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    transfer_request_id = Column(Integer, ForeignKey("transfer_requests.id"), nullable=False)
    returned_to_location = Column(String(255), nullable=False)
    returned_at = Column(DateTime, server_default=func.current_timestamp())
    notes = Column(Text)
    read_by_requester = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    
    # Relationships
    transfer_request = relationship("TransferRequest")

class TransportIncident(Base):
    """Modelo de Incidencias de Transporte - EXACTO A BD"""
    __tablename__ = "transport_incidents"
    
    id = Column(Integer, primary_key=True, index=True)
    transfer_request_id = Column(Integer, ForeignKey("transfer_requests.id"), nullable=False)
    courier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    incident_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    reported_at = Column(DateTime, server_default=func.current_timestamp())
    resolved = Column(Boolean, default=False)
    resolution_notes = Column(Text)
    
    # Relationships
    transfer_request = relationship("TransferRequest")
    courier = relationship("User")

# app/shared/database/models.py - AGREGAR al final
class VideoProcessingJob(Base):
    """Tabla para tracking de jobs de procesamiento de video"""
    __tablename__ = "video_processing_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(50), unique=True, nullable=False, index=True)
    
    # Datos de input
    warehouse_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    estimated_quantity = Column(Integer, nullable=False)
    product_brand = Column(String(255))
    product_model = Column(String(255))
    expected_sizes = Column(Text)  # JSON string de tallas
    notes = Column(Text)
    
    # Estado del procesamiento
    status = Column(String(50), default="submitted", index=True)  # submitted, processing, completed, failed
    progress_percentage = Column(Integer, default=0)
    
    # Resultados
    ai_results = Column(Text)  # JSON string
    detected_products = Column(Text)  # JSON string
    confidence_score = Column(Numeric(3, 2))
    
    # Productos creados
    created_products = Column(Text)  # JSON string con IDs de productos creados
    
    # Tracking
    submitted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_at = Column(DateTime, server_default=func.current_timestamp())
    processing_started_at = Column(DateTime)
    processing_completed_at = Column(DateTime)
    
    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # Relationships
    warehouse_location = relationship("Location")
    submitted_by = relationship("User")