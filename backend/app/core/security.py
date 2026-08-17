"""Аутентификация: пароли и JWT-токены.

Токен передаётся в заголовке Authorization: Bearer <token>.

Пароли хешируются библиотекой bcrypt напрямую, без passlib. Причина:
passlib 1.7.4 не поддерживается с 2020 года и при каждом обращении пытается
прочитать bcrypt.__about__.__version__, которого в bcrypt 4.x больше нет.
Ошибка перехватывается самой passlib и на работу не влияет, но в журнал
при каждом старте попадает трассировка AttributeError — она выглядит как
сбой и уже дважды приводила к лишнему разбирательству.

Формат хешей не меняется: passlib использовала тот же bcrypt и те же
хеши вида $2b$12$..., поэтому учётные записи, созданные раньше,
продолжают работать без каких-либо миграций.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

#: Стоимость хеширования. 12 раундов — примерно 0,3 с на подбор одного
#: варианта, разумный баланс между стойкостью и временем входа.
BCRYPT_ROUNDS = 12

#: bcrypt использует только первые 72 байта пароля. Более длинный пароль
#: молча обрезался бы, поэтому такой случай отклоняется явно.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Пароль слишком длинный: bcrypt учитывает только первые "
            f"{MAX_PASSWORD_BYTES} байт"
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    encoded = plain.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        # Такой пароль невозможно было задать, значит он заведомо неверный
        return False
    try:
        return bcrypt.checkpw(encoded, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Повреждённый или чужой формат хеша в базе
        return False


def create_access_token(
    username: str, role: str, expires_minutes: Optional[int] = None
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: Dict[str, Any] = {
        "sub": username,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
