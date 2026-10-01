"""Utilidades chicas compartidas por el dominio."""

import datetime as dt
import re
import uuid
from zoneinfo import ZoneInfo

from .config import ZONA_HORARIA
from .errores import DatosInvalidos

TZ = ZoneInfo(ZONA_HORARIA)
_RE_SLUG = re.compile(r"[^a-z0-9_]+")
_RE_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def nuevo_uuid():
    return str(uuid.uuid4())


def validar_id_persona(valor):
    """`id_persona` es un uuid de la bóveda. Ninguna otra cosa entra al store."""
    texto = str(valor or "").strip().lower()
    if not _RE_UUID.match(texto):
        raise DatosInvalidos(f"id_persona inválido: {valor!r}.")
    return texto


def slug(texto):
    return _RE_SLUG.sub("_", str(texto or "").strip().lower()).strip("_")


def parse_fecha(valor, campo="fecha"):
    """ISO local de Montevideo (`2026-10-02T19:00`) → datetime UTC."""
    if isinstance(valor, dt.datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=TZ)
    if not valor:
        raise DatosInvalidos(f"Falta «{campo}».")
    try:
        fecha = dt.datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        raise DatosInvalidos(f"«{campo}» no es una fecha válida: {valor!r}.")
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=TZ)
    return fecha.astimezone(dt.timezone.utc)


def entero(valor, campo, minimo=None, maximo=None, por_defecto=None):
    if valor in (None, ""):
        if por_defecto is not None:
            return por_defecto
        raise DatosInvalidos(f"Falta «{campo}».")
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise DatosInvalidos(f"«{campo}» tiene que ser un número entero.")
    if minimo is not None and n < minimo:
        raise DatosInvalidos(f"«{campo}» tiene que ser ≥ {minimo}.")
    if maximo is not None and n > maximo:
        raise DatosInvalidos(f"«{campo}» tiene que ser ≤ {maximo}.")
    return n


def numero(valor, campo, minimo=None, por_defecto=None):
    if valor in (None, ""):
        if por_defecto is not None:
            return por_defecto
        raise DatosInvalidos(f"Falta «{campo}».")
    try:
        n = float(valor)
    except (TypeError, ValueError):
        raise DatosInvalidos(f"«{campo}» tiene que ser un número.")
    if minimo is not None and n < minimo:
        raise DatosInvalidos(f"«{campo}» tiene que ser ≥ {minimo}.")
    return n


def codigo_de(id_persona):
    """Código de convocatoria: los 6 primeros caracteres del id, en mayúscula.

    Es lo que el participante dice al llegar (R1.7). No es PII: es un
    fragmento del seudónimo, y sin la bóveda no identifica a nadie.
    """
    return str(id_persona).replace("-", "")[:6].upper()
