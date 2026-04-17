import re

# Expresión regular nacional de matrícula de motocicleta colombiana
PLATE_REGEX = re.compile(r"[A-Z]{3}\d{2}[A-Z0-9]", re.IGNORECASE)

# ----- Selector de Taller (superadmin) -----
SELECTING_TENANT = 40

# ----- Estados del Conversation Handler de Onboarding -----
O_PHONE = 21
O_NAME = 22
O_EMAIL = 23
O_TENANT = 24
O_ROLE = 25
O_CONFIRM = 26

# ----- Estados del Conversation Handler de Hoja de Vida -----
L_ASKING_PLATE = 31

# ----- Estados del Conversation Handler de Recepción Visual -----
ASKING_PLATE = 1
CONFIRMING_OCR = 2
CORRECTING_DATA = 3
CONFIRMING_CLIENT = 4
ASKING_PHONE = 5
ASKING_KM = 6
ASKING_PHOTOS = 7
ASKING_MOTIVE = 8
CONFIRMING_MOTIVE = 9
CORRECTING_MOTIVE = 10
CONFIRMING_KM = 11

# ----- Estados post-recepción (ciclo de vida del técnico) -----
AWAITING_DIAGNOSIS = 50       # Esperando diagnóstico del técnico (diferido)
AWAITING_PARTS = 51           # Esperando info del repuesto requerido
AWAITING_EXTERNAL_DEST = 52   # Esperando destino del trabajo externo
