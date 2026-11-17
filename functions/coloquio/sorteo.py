"""R1.19 — la selección de candidatos es un sorteo con semilla.

`f_persona_convocable_filtrada()` ordenaba por `id_persona` y cortaba: la
misma búsqueda devolvía siempre a la misma gente, y el resto del segmento no
existía para el sistema. Ahora ordena por `md5(id_persona || semilla),
id_persona`, la misma cuenta que `demografia.ORDEN_DE_SORTEO` de `paneles`
(D89). No se usa `random()`: misma semilla y mismos datos, misma selección.

* **La semilla vive en la sesión** (R1.19.c), no en la ejecución como en
  `paneles`. La lista de candidatos se arma a lo largo de días: si cada
  búsqueda reordenara, el coordinador perdería el hilo. Se genera la primera
  vez que se busca en la sesión, se guarda, y la usan todas las búsquedas
  siguientes. Queda para siempre: con ella se rehace una selección vieja.
* **Volver a sortear** genera otra y **deja rastro**: cada semilla queda en
  `sesion.sorteos` con quién y cuándo, y `metricas.resorteos` las cuenta. Sortear
  cinco veces hasta que guste la lista es un sesgo de selección; que se vea.
* **Con cuotas, el sorteo es por estrato** (R1.19.f): cada celda de cuota trae
  su total elegible y su tanda sorteada. Ninguna queda representada solo por
  los que cayeron en una tanda global, y la factibilidad se ve al armar.
"""

import copy
import hashlib
import re
import secrets

from .errores import DatosInvalidos, NoEncontrado

_PATRON = re.compile(r"[A-Za-z0-9_-]{1,64}")


def nueva():
    """Corta y copiable, como en `paneles` (`consultas.nueva_semilla`)."""
    return secrets.token_hex(6)


def normalizar(crudo):
    """Letras, números, «-» o «_», hasta 64 (`consultas.normalizar_semilla`)."""
    if crudo in (None, ""):
        return None
    semilla = str(crudo).strip()
    if not _PATRON.fullmatch(semilla):
        raise DatosInvalidos("La semilla tiene que ser letras, números, «-» o «_» (hasta 64).",
                             {"campo": "semilla"})
    return semilla


def clave(id_persona, semilla):
    """La posición de una persona en el sorteo: `md5(id_persona || semilla)`,
    la misma cuenta que la bóveda hace en SQL."""
    return hashlib.md5(f"{id_persona}{semilla}".encode()).hexdigest()


def ordenar(ids, semilla):
    """Orden total del sorteo: la clave, y el id para desempatar."""
    return sorted(ids, key=lambda i: (clave(i, semilla), i))


# ── La semilla de la sesión ──

def _registro(semilla, motivo, actor, ahora):
    return {"semilla": semilla, "motivo": motivo, "actorUid": actor.uid, "ts": ahora}


def semilla_de_la_sesion(ctx, actor, sesion_id):
    """La de la sesión; si todavía no tiene, se genera y se guarda. En una
    transacción: dos búsquedas simultáneas no pueden dejar dos semillas."""
    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        if not sesion:
            raise NoEncontrado("No existe esa sesión.")
        if sesion.get("semilla"):
            return sesion["semilla"]
        semilla = nueva()
        tx.update(f"sesion/{sesion_id}", {
            "semilla": semilla,
            "sorteos": list(sesion.get("sorteos") or []) + [
                _registro(semilla, "inicial", actor, ctx.ahora())]})
        return semilla
    return ctx.store.transaccion(tx_fn)


def resortear(ctx, actor, sesion_id):
    """«Volver a sortear»: otra semilla, guardada, y el rastro de que se sorteó."""
    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        if not sesion:
            raise NoEncontrado("No existe esa sesión.")
        semilla = nueva()
        sorteos = list(sesion.get("sorteos") or []) + [
            _registro(semilla, "resorteo", actor, ctx.ahora())]
        metricas = dict(sesion.get("metricas") or {})
        metricas["resorteos"] = int(metricas.get("resorteos") or 0) + 1
        tx.update(f"sesion/{sesion_id}", {"semilla": semilla, "sorteos": sorteos,
                                          "metricas": metricas})
        return {"semilla": semilla, "anterior": sesion.get("semilla"),
                "resorteos": metricas["resorteos"], "sorteos": sorteos}
    return ctx.store.transaccion(tx_fn)


# ── Estratos ──

def filtros_de_celda(filtros, dimension, categoria):
    """Los filtros de la búsqueda, acotados a una celda de cuota. `None` si la
    búsqueda ya excluye esa categoría: la celda no tiene a nadie."""
    salida = copy.deepcopy(filtros or {})
    cond = dict(salida.get(dimension) or {})
    if "en" in cond and categoria not in cond["en"]:
        return None
    cond["en"] = [categoria]
    salida[dimension] = cond
    return salida


def celdas(sesion):
    """Las celdas de cuota de la sesión, con su meta de invitación."""
    from . import modelo

    ratio = sesion.get("ratioSobrerreclutamiento") or 1
    return [{"dimension": c["dimension"], "categoria": c["categoria"],
             "metaInvitacion": modelo.meta_invitacion(c["objetivo"], ratio)}
            for c in sesion.get("cuotas") or []]


def factibilidad(ctx, sesion, filtros=None):
    """R1.19.f — por celda de cuota, cuántos elegibles hay en el panel contra
    cuántos hay que invitar. Se ve al armar la sesión, no a tres horas del
    grupo. Elegibles = con contacto vigente y el filtro; antes de la fatiga,
    que es de COLOQUIO y se aplica a quien sale en la lista."""
    salida = []
    for c in celdas(sesion):
        fc = filtros_de_celda(filtros, c["dimension"], c["categoria"])
        total = 0 if fc is None else ctx.boveda.sorteados(fc, limite=1)["total"]
        falta = max(0, c["metaInvitacion"] - total)
        salida.append({**c, "elegibles": total, "factible": falta == 0, "faltan": falta,
                       "mensaje": (None if falta == 0 else
                                   f"{c['dimension']} = {c['categoria']}: hay que invitar a "
                                   f"{c['metaInvitacion']} y hay {total} elegible(s) en el panel"
                                   f"{' con este filtro' if filtros else ''}.")})
    return salida
