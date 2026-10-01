"""R5.2.a — declarar en la bóveda las convocatorias de COLOQUIO.

Desde la `boveda/0016`, `contacto_para_convocatoria()` entrega un contacto solo
si el sistema que llama **declaró** una convocatoria vigente para esa persona.
Las convocatorias de COLOQUIO viven en Firestore y la bóveda no las ve, así
que COLOQUIO las declara:

    select declarar_convocatoria(id_persona, sesion_id, fecha_sesion + 2 días)

Cuándo:

* **Al invitar** (`candidato → invitado`), sea por la lista de invitación, por
  el botón de la fila, por un reemplazo o por la invitación de WhatsApp.
* **Al reingresar** a alguien desde un terminal: vuelve a estar invitado.
* **Al reprogramar** la sesión: se vuelve a declarar con la misma referencia y
  la fecha nueva, para todos los que siguen en curso. Actualiza, no duplica.

Cómo, y por qué así:

* **Fuera de la transacción de Firestore, y antes.** Una transacción se puede
  reintentar y la bóveda no participa de ella. Declarando antes, si la bóveda
  rechaza (la persona retiró el consentimiento) o no responde, la persona
  **no queda invitada**: COLOQUIO no muestra como invitado a alguien cuyo
  contacto la bóveda no va a entregar.
* **El vencimiento es la fecha de la sesión más dos días, con el tope de la
  bóveda.** Más de 60 días se rechaza; para una sesión muy lejana se declara
  hasta el tope (con un día de margen) y la reprogramación o la próxima
  lectura de contacto lo renuevan.
* **La referencia es el id de sesión de COLOQUIO.** Para la bóveda es opaca.
"""

import datetime as dt

from . import boveda as mod_boveda, modelo
from .errores import ConvocatoriaRechazada, DatosInvalidos

MARGEN_DESPUES_DE_LA_SESION = dt.timedelta(days=2)
# Un día menos que el tope de la bóveda, para no rozarlo por diferencias de reloj.
TOPE = dt.timedelta(days=mod_boveda.TOPE_DECLARACION_DIAS - 1)

# Los estados que tienen una convocatoria viva y por lo tanto una declaración.
EN_CURSO = {modelo.INVITADO, modelo.CONTACTADO, modelo.ACEPTO, modelo.CONFIRMADO}


def vencimiento(sesion, ahora):
    fecha = sesion.get("fecha")
    if not fecha:
        raise DatosInvalidos("La sesión no tiene fecha: no se puede declarar la convocatoria.")
    vence = fecha + MARGEN_DESPUES_DE_LA_SESION
    if vence <= ahora:
        raise DatosInvalidos(
            "La sesión ya pasó hace más de dos días: no se puede convocar para ella. "
            "Si se reprogramó, cambiá la fecha en Armado.")
    return min(vence, ahora + TOPE)


def declarar(ctx, sesion_id, sesion, id_persona):
    """Declara una persona. Lanza `ConvocatoriaRechazada` si la bóveda no la acepta."""
    ctx.boveda.declarar_convocatoria(id_persona, sesion_id, vencimiento(sesion, ctx.ahora()))


def declarar_varias(ctx, sesion_id, sesion, ids):
    """Declara una lista. Devuelve (declarados, rechazados).

    Un rechazo por persona (consentimiento) no frena al resto. Si la bóveda no
    responde, `ServicioNoDisponible` se propaga: no tiene sentido invitar a
    nadie cuyo contacto no se va a poder leer.
    """
    vence = vencimiento(sesion, ctx.ahora())
    declarados, rechazados = [], []
    for i in ids:
        try:
            ctx.boveda.declarar_convocatoria(i, sesion_id, vence)
            declarados.append(i)
        except ConvocatoriaRechazada as error:
            rechazados.append({"idPersona": i, "motivo": error.mensaje})
    return declarados, rechazados


def redeclarar_sesion(ctx, sesion_id, sesion, convocatorias):
    """Tras reprogramar: misma referencia, fecha nueva, para los que siguen en curso.

    No lanza: la reprogramación ya ocurrió en COLOQUIO. Informa qué pasó para
    que la pantalla lo muestre.
    """
    ids = [c["idPersona"] for c in convocatorias if c.get("estado") in EN_CURSO]
    if not ids:
        return {"redeclarados": 0, "rechazados": [], "error": None}
    try:
        declarados, rechazados = declarar_varias(ctx, sesion_id, sesion, ids)
    except Exception as error:  # noqa: BLE001 — bóveda caída o fecha inválida
        mensaje = getattr(error, "mensaje", None) or str(error)
        return {"redeclarados": 0, "rechazados": [], "error": mensaje}
    return {"redeclarados": len(declarados), "rechazados": rechazados, "error": None}
