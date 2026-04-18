| # | Etapa | Descripción | Interacción Telegram |
|---|-------|-------------|---------------------|
| 1 | **Agendamiento** | Cliente agenda cita online o vía Telegram | Bot envía recordatorios, recibe confirmación |
| 2 | **Recepción e Inspección** | Ingreso y recolección de evidencia multimedia. IA identifica partes de **desgaste** (ej: pastas de freno, llantas) de una lista predefinida, provee precio/referencia al instante, asesor pregunta al cliente en vivo. Toda falla compleja va a diagnóstico. **→ Genera PDF de orden de entrada** (incluyendo si autorizó o no el cambio de desgaste) | Técnico envía notas de desgaste ("Pastillas malas"). IA responde: "Valor pastillas: $45.000 + MO: $10.000. ¿Cliente autoriza?". Técnico responde sí/no. |
| 3 | **Programación (Kanban)** | La motocicleta ingresa a la cola de trabajo programada en el tablero Kanban. | Automático (Mueve a "Próximos Trabajos") |
| 4 | **Diagnóstico Técnico** | El técnico designado evalúa fallas profundas o reportes del cliente (ej. sonidos de motor) anotados en la recepción. | Técnico envía multimedia con hallazgos técnicos. |
| 5 | **Presupuesto/Aprobación** | Estimación de costos (desgaste no decidido + diagnóstico), cliente aprueba o rechaza por el bot. | Cliente recibe presupuesto y aprueba vía bot. |
| 6 | **Reparación** | Ejecución del trabajo autorizado, actualización de progreso. | Técnico reporta avance vía audio/fotos/video. |
| 7 | **Control de calidad** | Verificación final antes de entrega. | Supervisor confirma QC vía bot. |
| 8 | **Facturación** | Generación de factura y opciones de pago. | Cliente recibe factura. |
| 9 | **Entrega** | Devolución del vehículo. **→ Genera PDF de orden de salida con firma** | Notificación al cliente de vehículo listo. |
| 10| **Seguimiento** | Encuesta de satisfacción y recordatorios futuros. | Bot envía encuesta interactiva. |
| * | *Garantía (Transversal)* | Cuando el diagnóstico (paso 4) identifica un defecto cubierto. Se crea reclamo, pasa a pre-aprobación y luego a Softway. | Técnico reporta defecto vía Telegram, admin aprueba desde dashboard. |
| * | *Pedido de Repuestos (Transversal)* | Centros de Servicio y Repuesteros pueden solicitar stock de repuestos. | El usuario monta el pedido enviando un archivo Excel con las referencias, o usando la cámara para escanear los códigos de barras de los repuestos e irlos agregando al carrito del bot. |
