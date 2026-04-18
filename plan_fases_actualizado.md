### Fase 1 — Infraestructura y Modelos (Semana 1-2)
- Estructura del monorepo y Docker Compose
- Modelos de base de datos y migraciones (Alembic) (incl. Pedidos de Importación y Repuestos)
- Configuración PostgreSQL con RLS multi-tenant (Soporte para Centros de Servicio y Distribuidores)
- Maestro de VINs (modelo + importación CSV)
- API base con autenticación JWT + roles (superadmin, admin, technician, client, parts_dealer)
- Motor de plantillas y lógica existente para Certificados de Aduana / Fichas Técnicas

### Fase 2 — Bot de Telegram + Flujo Core (Semana 3-4)
- Bot de Telegram con handlers principales
- Flujo de recepción (incluyendo OCR de matrícula)
- Procesamiento de multimedia (fotos, audios, **videos**, archivos)
- Generación de PDF de orden de entrada + firma OTP
- **Flujos Red (Centros/Distribuidores):** Módulo de creación y consulta de Pedidos de Repuestos (Aplica para Centros de Servicio y Repuesteros. Permite montar pedidos enviando un archivo Excel o escaneando códigos de barras con la cámara del celular para ir agregando referencias).
- Flujos Super Admin: Consulta de Fichas Técnicas, Certificados de Aduanas, Seguimiento de Importaciones
- Integración con la API backend

### Fase 3 — Agente IA (Semana 5-6)
- Integración Speech-to-Text (Whisper)
- OCR de matrículas para extracción de placa
- Orquestador IA con LangChain
- Extracción automática de datos de mensajes
- Detección de intención y cierre de etapas (incl. solicitudes de pedidos de repuestos)
- Clasificación y enrutamiento inteligente

### Fase 4 — Garantías y Liquidaciones (Semana 7-8)
- Flujo completo de garantías con pre-aprobación del admin
- Revisiones de kilometraje (gratuitas y pagadas)
- Alistamientos PDI
- **Módulo de Gestión de Inventario/Repuestos** (Centro de Servicio o Repuestero crea pedidos vía Excel o Escáner de código de barras -> Admin aprueba -> Envío a Softway)
- **Liquidaciones mensuales** (cálculo + informe PDF/Excel)

### Fase 5 — Integración Softway (Semana 9-10)
- Cliente API/HTTP para portal Softway
- Módulo de Activaciones de Garantía
- Módulo de Reclamos de Garantía
- Módulo de Pedidos de Repuestos (Envío automatizado desde solicitudes de taller)
- Cola de sincronización con reintentos

### Fase 6 — Dashboard Admin Esencial (Semana 11)
- Panel de pre-aprobación de garantías (Lista simple)
- **Panel de aprobación de Pedidos de Repuestos de Centros de Servicio**
- Gestión del maestro de VINs y Base de Datos de Fichas Técnicas
- Gestión y seguimiento de Pedidos de Importación
- Archivo documental (búsqueda y exportación SIC)
- **Panel de permanencia en taller** (Lista con semáforo, sin Kanban visual complejo)
- Dashboard de KPIs básicos

### Fase 7 — Despliegue Primera Etapa (Semana 12)
- Tests de integración de flujos core
- Despliegue en producción
- (Todo el flujo operativo funciona vía Telegram + PDFs + Softway)
