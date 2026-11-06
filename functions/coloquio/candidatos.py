"""R1.15 · R1.16 · R1.17 — lo que la pantalla de selección pide de un candidato.

Tres niveles, los mismos de `paneles` (addendum §1), y cada uno con su costo:

* **Columnas (R1.15).** Los atributos de los `id_persona` que la lista ya
  tiene, en una sola llamada a `atributos_de_personas()`. Agregar una columna
  **no** vuelve a correr la búsqueda. Lo ausente no viene: no se inventa un
  nulo. La elección de columnas se recuerda **por usuario**
  (`preferencia/{uid}`), con claves de atributo y nada más.
* **Ficha seudónima (R1.16).** `ficha_candidato()` más el historial
  cualitativo, que es de COLOQUIO. Sin PII y sin registro de reidentificación:
  es lo que la búsqueda ya mostraba, de a una persona.
* **Identificar (R1.17).** `identificar_candidatos()` sobre los tildados de una
  sesión, con el id de la sesión como referencia y el email del usuario humano
  como actor. Es una **acción**: ninguna otra ruta la dispara. Lo que vuelve
  —nombre, email, celular— es PII: viaja al navegador y muere ahí. Esta
  función **no escribe nada** en el store: ni la lista, ni un evento, ni un
  contador, ni un log (R1.12). La auditoría la escribe la bóveda.
"""

from . import atributos, historial, sesiones, util
from .boveda import TOPE_IDENTIFICAR
from .errores import DatosInvalidos

TOPE_VALORES = 500


def _ids(crudos, tope, que):
    if not isinstance(crudos, list) or not crudos:
        raise DatosInvalidos(f"Hace falta la lista de {que}.")
    ids = list(dict.fromkeys(util.validar_id_persona(i) for i in crudos))
    if len(ids) > tope:
        raise DatosInvalidos(f"Son {len(ids)} {que} y el tope es {tope} por pedido.")
    return ids


# ── R1.15 · columnas ──

def valores(ctx, cuerpo):
    """Los atributos de los ids que la lista ya tiene. No corre la búsqueda."""
    ids = _ids(cuerpo.get("ids"), TOPE_VALORES, "personas")
    claves = cuerpo.get("atributos")
    filas = ctx.boveda.atributos(ids)
    if claves:
        pedidas = set(atributos.validar_columnas(claves))
        filas = [f for f in filas if f["atributo"] in pedidas]
    return {"filas": filas}


def _ruta_preferencia(uid):
    return f"preferencia/{uid}"


def preferencias(ctx, actor):
    doc = ctx.store.get(_ruta_preferencia(actor.uid)) or {}
    return {"columnasSeleccion": doc.get("columnasSeleccion") or []}


def guardar_preferencias(ctx, actor, cuerpo):
    columnas = atributos.validar_columnas(cuerpo.get("columnasSeleccion") or [])
    ctx.store.set(_ruta_preferencia(actor.uid),
                  {"columnasSeleccion": columnas, "actualizadaEn": ctx.ahora()})
    return {"columnasSeleccion": columnas}


# ── R1.16 · ficha seudónima ──

def ficha(ctx, id_persona):
    id_persona = util.validar_id_persona(id_persona)
    salida = ctx.boveda.ficha(id_persona)
    salida["codigo"] = util.codigo_de(id_persona)
    salida["historial"] = historial.completo(ctx, id_persona)
    return salida


# ── R1.17 · identificar ──

def identificar(ctx, actor, sesion_id, cuerpo):
    """Nombre, email y celular de los tildados. **No escribe en el store.**"""
    sesiones.exigir(ctx.store, sesion_id)
    ids = _ids(cuerpo.get("ids"), TOPE_IDENTIFICAR, "candidatos tildados")
    filas = ctx.boveda.identificar(ids, sesion_id, actor.email)
    for f in filas:
        f["codigo"] = util.codigo_de(f["idPersona"])
    return {
        "identificados": filas,
        "pedidos": len(ids),
        # La bóveda no dice por qué alguien no vino (sin consentimiento de
        # contacto, o ya no activa): solo se cuenta.
        "noIdentificados": len(ids) - len(filas),
    }
