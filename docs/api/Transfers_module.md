# 📦 Módulo de Transferencias - TuStockYa

## 🎯 Propósito

El módulo de transferencias maneja todo el flujo de movimiento de productos entre ubicaciones (locales y bodegas), implementando los requerimientos funcionales **VE003**, **VE008**, **BG001-BG003**, y **CO001-CO007** del documento de especificaciones.

## 🏗️ Arquitectura

```
app/modules/transfers/
├── __init__.py          # Módulo principal
├── router.py            # Endpoints REST API
├── service.py           # Lógica de negocio
├── repository.py        # Acceso a datos
└── schemas.py           # Modelos Pydantic
```

## 🔄 Flujo Completo de Transferencia

### 1. **Vendedor** (VE003) - Solicitar Producto
```
POST /api/v1/transfers/request
```
- Solicita producto no disponible en su ubicación
- Especifica urgencia: `cliente` (presente) o `restock`
- Sistema valida disponibilidad antes de crear solicitud

### 2. **Bodeguero** (BG001-BG003) - Procesar Solicitud
```
GET /api/v1/transfers/warehouse/pending     # BG001: Ver pendientes
POST /api/v1/transfers/warehouse/accept     # BG002: Aceptar/rechazar
POST /api/v1/transfers/{id}/deliver-to-courier  # BG003: Entregar a corredor
```
- Ve solicitudes ordenadas por prioridad (cliente presente primero)
- Acepta tras verificar disponibilidad
- Entrega a corredor con **descuento automático de inventario**

### 3. **Corredor** (CO001-CO007) - Transportar
```
GET /api/v1/transfers/courier/available     # CO001: Ver disponibles
POST /api/v1/transfers/{id}/accept-courier  # CO002: Aceptar transporte
POST /api/v1/transfers/{id}/confirm-pickup  # CO003: Confirmar recolección
POST /api/v1/transfers/{id}/confirm-delivery # CO004: Confirmar entrega
```
- Acepta transporte disponible
- Confirma recolección en bodega (timestamp)
- Confirma entrega en destino (timestamp)

### 4. **Vendedor** (VE008) - Confirmar Recepción
```
GET /api/v1/transfers/pending-receptions    # Ver entregas pendientes
POST /api/v1/transfers/{id}/confirm-reception # VE008: Confirmar recepción
```
- Confirma recepción del producto
- **Actualización automática de inventario local**
- Marca transferencia como completada

## 📊 Estados de Transferencia

| Estado | Descripción | Acciones Disponibles |
|--------|-------------|---------------------|
| `pending` | Solicitud creada, esperando bodeguero | Bodeguero: aceptar/rechazar |
| `accepted` | Aceptada por bodeguero, esperando corredor | Corredor: aceptar transporte |
| `courier_assigned` | Corredor asignado, debe recoger | Corredor: confirmar recolección |
| `in_transit` | En camino al destino | Corredor: confirmar entrega |
| `delivered` | Entregado, esperando confirmación | Vendedor: confirmar recepción |
| `completed` | Proceso completado exitosamente | - |
| `cancelled` | Cancelado en cualquier punto | - |
| `delivery_failed` | Entrega fallida | Activar reversión |

## 🎛️ Dashboard por Rol

### Vendedor
- Mis solicitudes activas
- Entregas pendientes de confirmación (VE008)
- Estado de transferencias urgentes

### Bodeguero  
- Solicitudes pendientes de aceptación (BG001)
- Solicitudes aceptadas en preparación (BG002)
- Productos listos para entrega a corredor (BG003)

### Corredor
- Solicitudes disponibles para transporte (CO001)
- Mis transportes en curso (CO002-CO004)
- Historial de entregas (CO006)

### Administrador
- Vista consolidada de todas las transferencias
- Métricas de eficiencia del sistema
- Alertas de demoras y problemas

## 🔒 Sistema de Permisos

### Por Rol
- **Vendedor**: Solo sus propias transferencias
- **Bodeguero**: Transferencias de ubicaciones asignadas
- **Corredor**: Transferencias disponibles + sus asignadas
- **Administrador/Boss**: Todas las transferencias

### Por Estado
- `pending`: Solo bodeguero puede aceptar/rechazar
- `accepted`: Solo corredor puede aceptar transporte
- `courier_assigned`: Solo corredor asignado puede recoger
- `in_transit`: Solo corredor asignado puede entregar
- `delivered`: Solo vendedor solicitante puede confirmar

## 💾 Actualización Automática de Inventario

### BG003: Entrega a Corredor
```python
# Descuento automático en ubicación origen
product_size.quantity -= transfer.quantity
```

### VE008: Confirmación de Recepción
```python
# Suma automática en ubicación destino
# Si producto existe: sumar cantidad
# Si no existe: crear producto + talla en ubicación destino
```

## 🚨 Manejo de Excepciones

### CO007: Entrega Fallida
- Estado: `delivery_failed`
- Activar proceso de reversión automática (BG010)
- Restaurar inventario en bodega origen

### Timeouts y Alertas
- Cliente presente > 30 min: Alerta alta
- Entrega sin confirmar > 2 horas: Alerta media
- Transferencia > 24 horas: Alerta de revisión

## 📡 API Endpoints

### Vendedor
```bash
# Crear solicitud
POST /api/v1/transfers/request

# Ver mis solicitudes
GET /api/v1/transfers/my-requests?status=pending,in_transit

# Ver entregas pendientes
GET /api/v1/transfers/pending-receptions

# Confirmar recepción
POST /api/v1/transfers/{id}/confirm-reception

# Cancelar solicitud
POST /api/v1/transfers/{id}/cancel
```

### Bodeguero
```bash
# Ver pendientes
GET /api/v1/transfers/warehouse/pending

# Ver aceptadas
GET /api/v1/transfers/warehouse/accepted

# Aceptar/rechazar
POST /api/v1/transfers/warehouse/accept

# Entregar a corredor
POST /api/v1/transfers/{id}/deliver-to-courier
```

### Corredor
```bash
# Ver disponibles
GET /api/v1/transfers/courier/available

# Aceptar transporte
POST /api/v1/transfers/{id}/accept-courier

# Confirmar recolección
POST /api/v1/transfers/{id}/confirm-pickup

# Confirmar entrega
POST /api/v1/transfers/{id}/confirm-delivery

# Reportar incidencia
POST /api/v1/transfers/{id}/report-incident

# Ver historial
GET /api/v1/transfers/courier/delivery-history
```

### Administrativo
```bash
# Dashboard personalizado
GET /api/v1/transfers/dashboard

# Detalles específicos
GET /api/v1/transfers/{id}

# Métricas
GET /api/v1/transfers/admin/metrics

# Por estado
GET /api/v1/transfers/admin/status/{status}
```

## 🧪 Testing

Ejecutar tests completos:
```bash
python scripts/test_transfers_module.py
```

**Tests incluidos:**
- ✅ Flujo completo vendedor → bodeguero → corredor → vendedor
- ✅ Validaciones de permisos por rol
- ✅ Actualización automática de inventario
- ✅ Dashboards personalizados
- ✅ Funciones administrativas
- ✅ Manejo de excepciones

## 📈 Métricas Implementadas

### Por Transferencia
- Tiempo total de procesamiento
- Tiempo por etapa (solicitud → entrega → confirmación)
- Tasa de éxito/falla
- Productos más solicitados

### Por Usuario
- Performance de bodegueros (tiempo respuesta)
- Eficiencia de corredores (entregas/día)
- Solicitudes frecuentes de vendedores

### Sistémicas
- Volumen diario/semanal/mensual
- Cuellos de botella por ubicación
- Transferencias urgentes vs. restock
- Alertas de demoras

## 🔗 Integración con Otros Módulos

### Sales Module
- Verificar disponibilidad antes de venta
- Reservar productos durante proceso de venta

### Inventory Module (futuro)
- Sincronización de stock en tiempo real
- Auditoría de movimientos

### Notifications Module (futuro)
- Push notifications para cada etapa
- Alertas de demoras y problemas

## 🚀 Próximas Mejoras

### Fase 2: Optimizaciones
- [ ] Sistema de reservas integrado
- [ ] Predicción de demanda por ubicación
- [ ] Optimización de rutas para corredores
- [ ] Dashboard en tiempo real con WebSockets

### Fase 3: Analíticas Avanzadas
- [ ] Machine learning para predicción de stock
- [ ] Análisis de patrones de transferencia
- [ ] Recomendaciones automáticas de redistribución
- [ ] Integración con sistemas de forecast

## 📋 Checklist de Implementación

- [x] ✅ Modelos SQLAlchemy implementados
- [x] ✅ Schemas Pydantic completos
- [x] ✅ Repository con todas las consultas
- [x] ✅ Service con lógica de negocio
- [x] ✅ Router con todos los endpoints
- [x] ✅ Sistema de permisos por rol
- [x] ✅ Actualización automática de inventario
- [x] ✅ Dashboards personalizados
- [x] ✅ Tests completos
- [x] ✅ Documentación técnica
- [x] ✅ Integración en router principal

## 🎉 Estado: MÓDULO COMPLETO Y FUNCIONAL

El módulo de transferencias está **100% implementado** según los requerimientos del documento, incluyendo todos los flujos funcionales, validaciones, permisos y características avanzadas como actualización automática de inventario y dashboards personalizados por rol.