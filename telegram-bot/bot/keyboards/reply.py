from telegram import ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard(role: str) -> ReplyKeyboardMarkup:
    """Retorna el teclado persistente base correcto según el rol del usuario."""
    if role == "superadmin":
        keys = [
            [KeyboardButton("Nueva Recepción"), KeyboardButton("Consultar Hoja de Vida")],
            [KeyboardButton("Mis Órdenes Activas 🛠️"), KeyboardButton("Ingresar OTP 🔑")],
            [KeyboardButton("Buscar Repuesto 🔍"), KeyboardButton("Panel Super Admin 👑")],
        ]
    elif role == "jefe_taller":
        keys = [
            [KeyboardButton("Nueva Recepción"), KeyboardButton("Consultar Hoja de Vida")],
            [KeyboardButton("Mis Órdenes Activas 🛠️"), KeyboardButton("Ingresar OTP 🔑")]
        ]
    elif role == "technician":
        keys = [
            [KeyboardButton("Nueva Recepción"), KeyboardButton("Ingresar OTP 🔑")],
            [KeyboardButton("Mis Órdenes Activas 🛠️")]
        ]
    else:
        # Menú básico en caso de roles no reconocidos
        keys = [[KeyboardButton("Nueva Recepción")]]
        
    return ReplyKeyboardMarkup(keys, resize_keyboard=True)
