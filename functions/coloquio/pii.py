"""R1.12 — cero PII en el store de COLOQUIO.

Es la condición que hace admisible usar Firestore (SPEC §7.2) y por eso es un
invariante del store, no una recomendación: **toda** escritura pasa por
`validar_sin_pii()` dentro de `store.py`, sin excepción y sin forma de
apagarla desde el código de dominio.

Dos controles:

* **Por nombre de campo.** La misma lista que `pii.CAMPOS_PII` de `panel_api`
  (que a su vez es espejo de `campo_pii` del store semántico). Además acá se
  normaliza camelCase → snake_case, porque Firestore invita a `fechaNacimiento`
  y esa clave tiene que caer igual que `fecha_nacimiento`.
* **Por contenido, en los campos de texto libre.** La validación por nombre no
  ve «la señora de Pocitos, cel 099 123 456» escrita en una nota de sesión
  (SPEC §13, riesgo de cumplimiento). Para los pocos campos que admiten texto
  libre se buscan los patrones que sí se pueden detectar sin adivinar:
  emails, números de teléfono y cédulas. No es infalible —un nombre propio no
  tiene patrón— y la interfaz lo advierte; pero cierra la fuga más probable.

**Las notas libres sobre una persona no existen** (R1.12): ningún documento de
`convocatoria`, `asistencia`, `incentivo` o `participacionCuali` tiene un campo
de texto libre, y `TEXTO_LIBRE_POR_COLECCION` lo hace explícito.
"""

import re

from .errores import FugaDePII

# Espejo de `panel_api.pii.CAMPOS_PII`. Si `paneles` agrega un campo, se agrega
# acá: `tests/test_pii.py` fija la lista para que un cambio sea deliberado.
CAMPOS_PII = frozenset({
    "documento", "cedula", "ci", "dni", "pasaporte", "rut",
    "nombre", "nombres", "apellido", "apellidos", "nombre_completo",
    "email", "correo", "mail", "e_mail",
    "celular", "telefono", "movil", "whatsapp",
    "direccion", "domicilio",
    "fecha_nacimiento", "fecha_nac", "nacimiento", "fnac",
    "contacto", "observaciones",
})

# `nombre` es legítimo cuando nombra una cosa y no a una persona: el estudio,
# la sesión, un regalo del catálogo, una categoría.
COLECCIONES_QUE_PERMITEN_NOMBRE = frozenset({
    "estudio", "catalogoRegalo", "config", "sesion",
})

# Los únicos campos que admiten texto libre, por colección raíz. Todo lo que
# está acá se revisa por contenido además de por nombre.
TEXTO_LIBRE_POR_COLECCION = {
    "estudio": {"nombre", "cliente", "descripcion", "guion", "titulo",
                "objetivo", "repreguntas"},
    "sesion": {"nombre", "lugar", "notasSesion", "motivo", "resolucion",
               "resolucionIncentivos"},
    "catalogoRegalo": {"nombre"},
    "config": {"nombre", "guion", "texto"},
}
# `motivo` aparece además en anulaciones de cualquier colección: es texto que
# escribe una persona y se revisa siempre.
TEXTO_LIBRE_SIEMPRE = frozenset({"motivo"})

_RE_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Un teléfono: 8 o más dígitos, admitiendo separadores sueltos (099 123 456,
# +598 99-123-456). Un año o un cupo no llegan a 8 dígitos seguidos.
_RE_TELEFONO = re.compile(r"(?:\+?\d[\s.\-]?){8,}")
# Cédula uruguaya con formato: 1.234.567-8 / 1234567-8.
_RE_CEDULA = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-\d\b")


def normalizar_clave(clave):
    """`fechaNacimiento` → `fecha_nacimiento`; `E-Mail` → `e_mail`."""
    texto = re.sub(r"[\s\-]+", "_", str(clave).strip())
    texto = _RE_CAMEL.sub("_", texto)
    return re.sub(r"_+", "_", texto).lower()


def _recorrer(objeto, camino=()):
    """(camino, clave, valor) de todo el árbol."""
    if isinstance(objeto, dict):
        for clave, valor in objeto.items():
            yield camino, str(clave), valor
            yield from _recorrer(valor, camino + (str(clave),))
    elif isinstance(objeto, (list, tuple, set)):
        for item in objeto:
            yield from _recorrer(item, camino)


def patrones_en_texto(texto):
    """Qué patrones de PII aparecen en un texto libre."""
    if not isinstance(texto, str) or not texto:
        return []
    hallados = []
    if _RE_EMAIL.search(texto):
        hallados.append("email")
    if _RE_CEDULA.search(texto):
        hallados.append("cedula")
    if _RE_TELEFONO.search(texto):
        hallados.append("telefono")
    return hallados


def _textos(valor):
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, (list, tuple)):
        for item in valor:
            yield from _textos(item)


def hallazgos(payload, coleccion=""):
    """Lista de problemas de PII en `payload`. Vacía = se puede escribir."""
    permite_nombre = coleccion in COLECCIONES_QUE_PERMITEN_NOMBRE
    libres = TEXTO_LIBRE_POR_COLECCION.get(coleccion, set()) | TEXTO_LIBRE_SIEMPRE
    problemas = []
    for camino, clave, valor in _recorrer(payload):
        normalizada = normalizar_clave(clave)
        if normalizada in CAMPOS_PII and not (permite_nombre and normalizada == "nombre"):
            problemas.append({"campo": ".".join(camino + (clave,)), "motivo": "campo_pii"})
            continue
        if clave in libres:
            for texto in _textos(valor):
                for patron in patrones_en_texto(texto):
                    problemas.append({
                        "campo": ".".join(camino + (clave,)),
                        "motivo": f"texto_con_{patron}",
                    })
    return problemas


def validar_sin_pii(payload, coleccion=""):
    """Aborta si `payload` lleva PII. La llama el store antes de cada escritura."""
    problemas = hallazgos(payload, coleccion)
    if problemas:
        raise FugaDePII(
            "Se intentó escribir un dato personal en el store de COLOQUIO; la "
            "operación se abortó. Los datos de contacto se leen de la bóveda al "
            "usarlos y no se guardan, y las notas no pueden identificar a nadie.",
            {"coleccion": coleccion or "desconocida", "problemas": problemas},
        )
    return payload


def validar_texto_libre(texto, campo="texto"):
    """Chequeo previo para dar un error amable antes de llegar al store."""
    patrones = patrones_en_texto(texto)
    if patrones:
        from .errores import DatosInvalidos

        raise DatosInvalidos(
            f"El campo «{campo}» parece contener un dato personal "
            f"({', '.join(patrones)}). Las notas son de la sesión, no de las "
            "personas: no escribas teléfonos, emails ni documentos.",
            {"campo": campo, "patrones": patrones},
        )
    return texto
