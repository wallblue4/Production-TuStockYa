from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey, Numeric, UniqueConstraint, CheckConstraint , Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.config.database import Base
from enum import Enum
from pydantic import BaseModel , Field, ConfigDict, field_validator, FieldValidationInfo


from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Float,
    Text, ForeignKey, Numeric, UniqueConstraint, CheckConstraint
)

from sqlalchemy.types import Date



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
    cost_configurations = relationship("CostConfiguration", back_populates="location")

class User(Base):
    """Modelo de Usuario - EXACTO A BD"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255), nullable=False)
    role = Column(String(50), default='seller', nullable=False)  # ✅ CORREGIDO: 'vendedor'
    location_id = Column(Integer, ForeignKey("locations.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    
    # Relationships
    location = relationship("Location", back_populates="users")
    sales = relationship("Sale", back_populates="seller")
    expenses = relationship("Expense", back_populates="user")
    location_assignments = relationship("UserLocationAssignment", back_populates="user")

    created_cost_configurations = relationship("CostConfiguration", foreign_keys="CostConfiguration.created_by_user_id")
    paid_cost_payments = relationship("CostPayment", foreign_keys="CostPayment.paid_by_user_id")
    created_cost_exceptions = relationship("CostPaymentException", foreign_keys="CostPaymentException.created_by_user_id")
    deleted_cost_archives = relationship("CostDeletionArchive", foreign_keys="CostDeletionArchive.deleted_by_user_id")
    
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
    request_type = Column(String(20), default='transfer')
    original_transfer_id = Column(Integer, ForeignKey('transfer_requests.id'))
    
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


class AdminLocationAssignment(Base):
    """Modelo de Asignación de Administradores a Ubicaciones"""
    __tablename__ = "admin_location_assignments"
    
    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    assigned_at = Column(DateTime, server_default=func.current_timestamp())
    assigned_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Quién hizo la asignación
    notes = Column(Text, nullable=True)
    
    # Constraint para evitar duplicados
    __table_args__ = (
        UniqueConstraint('admin_id', 'location_id', name='admin_location_unique'),
    )
    
    # Relationships
    admin = relationship("User", foreign_keys=[admin_id])
    location = relationship("Location")
    assigned_by = relationship("User", foreign_keys=[assigned_by_user_id])

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


class VideoProcessingJob(Base):
    """Tabla específica para jobs de procesamiento de video con IA"""
    __tablename__ = "video_processing_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Información del archivo
    video_file_path = Column(String(500), nullable=False)
    original_filename = Column(String(255))
    file_size_bytes = Column(Integer)
    
    # Ubicación y cantidad
    warehouse_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    estimated_quantity = Column(Integer, nullable=False)
    
    # Información del producto esperado
    product_brand = Column(String(255))
    product_model = Column(String(255))
    expected_sizes = Column(Text)  # JSON array: ["40", "41", "42"]
    notes = Column(Text)
    
    # Estado del procesamiento
    processing_status = Column(String(50), default="processing")  # processing, completed, failed
    
    # IA Results
    ai_results_json = Column(Text)  # JSON con todos los resultados de IA
    confidence_score = Column(Numeric(5, 4), default=0.0)  # 0.0000 - 1.0000
    detected_brand = Column(String(255))
    detected_model = Column(String(255))
    detected_colors = Column(Text)  # JSON array
    detected_sizes = Column(Text)   # JSON array
    
    # Metadatos del procesamiento
    frames_extracted = Column(Integer)
    processing_time_seconds = Column(Integer)
    microservice_job_id = Column(String(100))  # ID del microservicio
    
    # Auditoría
    processed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=func.now())
    processing_started_at = Column(DateTime)
    processing_completed_at = Column(DateTime)
    
    # Manejo de errores
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # Resultados finales
    created_product_id = Column(Integer, ForeignKey("products.id"))  # Producto creado tras procesamiento
    created_inventory_change_id = Column(Integer, ForeignKey("inventory_changes.id"))  # Cambio de inventario final
    
    # Relationships
    warehouse = relationship("Location")
    processed_by = relationship("User")
    created_product = relationship("Product")
    created_inventory_change = relationship("InventoryChange")
    
    def __repr__(self):
        return f"<VideoProcessingJob(id={self.id}, status={self.processing_status}, brand={self.detected_brand})>"


class CostConfiguration(Base):
    """Modelo de Configuración de Costos"""
    __tablename__ = "cost_configurations"
    
    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    cost_type = Column(String(50), nullable=False)  # 'arriendo', 'servicios', etc.
    amount = Column(Numeric(10, 2), nullable=False)
    frequency = Column(String(20), nullable=False)  # 'daily', 'weekly', 'monthly', etc.
    description = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Constraints
    __table_args__ = (
        CheckConstraint('amount > 0', name='chk_cost_amount_positive'),
        CheckConstraint('end_date IS NULL OR end_date >= start_date', name='chk_cost_date_order'),
        CheckConstraint("frequency IN ('daily', 'weekly', 'monthly', 'quarterly', 'annual')", name='chk_cost_frequency_valid'),
        CheckConstraint("cost_type IN ('arriendo', 'servicios', 'nomina', 'mercancia', 'comisiones', 'transporte', 'otros')", name='chk_cost_type_valid'),
    )
    
    # Relationships
    location = relationship("Location", back_populates="cost_configurations")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    payments = relationship("CostPayment", back_populates="cost_configuration", cascade="all, delete-orphan")
    exceptions = relationship("CostPaymentException", back_populates="cost_configuration", cascade="all, delete-orphan")

class CostPayment(Base):
    """Modelo de Pagos Realizados"""
    __tablename__ = "cost_payments"
    
    id = Column(Integer, primary_key=True, index=True)
    cost_configuration_id = Column(Integer, ForeignKey("cost_configurations.id"), nullable=False)
    due_date = Column(Date, nullable=False)
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(String(50), nullable=False)
    payment_reference = Column(String(255))
    notes = Column(Text)
    paid_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    
    # Constraints
    __table_args__ = (
        CheckConstraint('amount > 0', name='chk_payment_amount_positive'),
    )
    
    # Relationships
    cost_configuration = relationship("CostConfiguration", back_populates="payments")
    paid_by = relationship("User", foreign_keys=[paid_by_user_id])

class CostPaymentException(Base):
    """Modelo de Excepciones de Pago"""
    __tablename__ = "cost_payment_exceptions"
    
    id = Column(Integer, primary_key=True, index=True)
    cost_configuration_id = Column(Integer, ForeignKey("cost_configurations.id"), nullable=False)
    exception_date = Column(Date, nullable=False)
    exception_type = Column(String(20), nullable=False)  # 'skip', 'different_amount', 'postponed'
    original_amount = Column(Numeric(10, 2))
    new_amount = Column(Numeric(10, 2))
    new_due_date = Column(Date)
    reason = Column(Text)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    
    # Constraints
    __table_args__ = (
        CheckConstraint("exception_type IN ('skip', 'different_amount', 'postponed')", name='chk_exception_type_valid'),
    )
    
    # Relationships
    cost_configuration = relationship("CostConfiguration", back_populates="exceptions")
    created_by = relationship("User", foreign_keys=[created_by_user_id])

class CostDeletionArchive(Base):
    """Modelo de Archivo de Eliminaciones"""
    __tablename__ = "cost_deletion_archives"
    
    id = Column(Integer, primary_key=True, index=True)
    original_cost_id = Column(Integer, nullable=False)
    configuration_data = Column(Text, nullable=False)
    paid_payments_data = Column(Text)
    exceptions_data = Column(Text)
    deleted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    deletion_date = Column(DateTime, server_default=func.current_timestamp())
    deletion_reason = Column(String(100))
    
    # Relationships
    deleted_by = relationship("User", foreign_keys=[deleted_by_user_id])