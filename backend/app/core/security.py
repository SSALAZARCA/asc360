import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from app.config import settings

ALGORITHM = "HS256"

def decode_access_token(token: str) -> Optional[dict]:
    """Decodifica y valida un JWT. Retorna el payload o None si es inválido."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        # Verificar que el token no haya expirado
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            return None
        return payload
    except JWTError:
        return None

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Crear token de acceso JWT."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=1440) # 24 horas por defecto
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verificar la contraseña en plano vs el hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    """Obtener hash de una contraseña plana."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
