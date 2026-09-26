"""R1.10 — Incentivos como módulo propio.

El incentivo cualitativo es un **regalo por sesión**, con un valor de otro
orden que el de una encuesta. No son puntos y no pasan por el ledger de
gamificación de `paneles`. El sistema registra compromiso y entrega
(`comprometido → entregado`); no ejecuta pagos ni resuelve el tratamiento
fiscal.

El valor comprometido por sesión y por estudio es un agregado mantenido al
escribir (SPEC §6): se ajusta en la misma transacción que crea o reasigna un
compromiso. `consistencia.py` lo recalcula y repara.
"""

from . import configuracion, modelo, sesiones, util
from .errores import Conflicto, DatosInvalidos, NoEncontrado


def ruta(sesion_id, id_persona):
    return f"sesion/{sesion_id}/incentivo/{id_persona}"


def nuevo(id_persona, regalo, ahora, motivo="asistencia"):
    return {
        "idPersona": id_persona,
        "regaloId": regalo["id"] if regalo else None,
        "regaloNombre": regalo.get("nombre") if regalo else None,
        "valor": float(regalo.get("valor") or 0) if regalo else 0.0,
        "moneda": (regalo or {}).get("moneda") or "UYU",
        "estado": modelo.COMPROMETIDO,
        "motivoCompromiso": motivo,
        "comprometidoEn": ahora,
        "entregadoEn": None,
        "entregadoPor": None,
    }


def sumar_valor(doc, delta):
    doc["valorComprometido"] = round(float(doc.get("valorComprometido") or 0) + float(delta), 2)


def vista(ctx, sesion_id):
    sesion = sesiones.exigir(ctx.store, sesion_id)
    items = [d for _, d in ctx.store.listar(f"sesion/{sesion_id}/incentivo")]
    for i in items:
        i["codigo"] = util.codigo_de(i["idPersona"])
    items.sort(key=lambda i: (i["estado"] == modelo.ENTREGADO, i["codigo"]))
    estudio = ctx.store.get(f"estudio/{sesion['estudioId']}") or {}
    return {
        "sesion": {"id": sesion_id, **sesion},
        "estudio": {"id": sesion["estudioId"], "nombre": estudio.get("nombre"),
                    "valorComprometido": estudio.get("valorComprometido", 0)},
        "items": items,
        "totales": {
            "comprometido": round(sum(i["valor"] for i in items), 2),
            "entregado": round(sum(i["valor"] for i in items if i["estado"] == modelo.ENTREGADO), 2),
            "pendientes": sum(1 for i in items if i["estado"] == modelo.COMPROMETIDO),
            "entregados": sum(1 for i in items if i["estado"] == modelo.ENTREGADO),
        },
        "catalogo": configuracion.listar_regalos(ctx.store, solo_activos=True),
    }


def asignar(ctx, actor, sesion_id, id_persona, cuerpo):
    id_persona = util.validar_id_persona(id_persona)
    regalo = configuracion.regalo(ctx.store, cuerpo.get("regaloId"))
    if not regalo or not regalo.get("activo", True):
        raise DatosInvalidos("Elegí un regalo activo del catálogo.")

    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        inc = tx.get(ruta(sesion_id, id_persona))
        if not sesion or not inc:
            raise NoEncontrado("No hay un compromiso de incentivo para esa persona en esta sesión.")
        estudio = tx.get(f"estudio/{sesion['estudioId']}")
        if inc["estado"] != modelo.COMPROMETIDO:
            raise Conflicto("Ese incentivo ya se entregó: no se puede cambiar el regalo.")
        delta = float(regalo.get("valor") or 0) - float(inc.get("valor") or 0)
        inc.update({"regaloId": regalo["id"], "regaloNombre": regalo["nombre"],
                    "valor": float(regalo.get("valor") or 0),
                    "moneda": regalo.get("moneda") or "UYU",
                    "asignadoPor": actor.uid, "asignadoEn": ctx.ahora()})
        sumar_valor(sesion, delta)
        sumar_valor(estudio, delta)
        tx.set(ruta(sesion_id, id_persona), inc)
        tx.update(f"sesion/{sesion_id}", {"valorComprometido": sesion["valorComprometido"]})
        tx.update(f"estudio/{sesion['estudioId']}", {"valorComprometido": estudio["valorComprometido"]})
        return inc

    return ctx.store.transaccion(tx_fn)


def entregar(ctx, actor, sesion_id, id_persona):
    id_persona = util.validar_id_persona(id_persona)
    ahora = ctx.ahora()

    def tx_fn(tx):
        inc = tx.get(ruta(sesion_id, id_persona))
        if not inc:
            raise NoEncontrado("No hay un compromiso de incentivo para esa persona en esta sesión.")
        if inc["estado"] == modelo.ENTREGADO:
            raise Conflicto("Ese incentivo ya figura como entregado.")
        if not inc.get("regaloId"):
            raise Conflicto("Asigná un regalo antes de marcarlo entregado.")
        inc.update({"estado": modelo.ENTREGADO, "entregadoEn": ahora, "entregadoPor": actor.uid})
        tx.set(ruta(sesion_id, id_persona), inc)
        return inc

    return ctx.store.transaccion(tx_fn)


def por_estudio(ctx, estudio_id):
    """Lo que el investigador necesita para cotizar: comprometido por sesión."""
    estudio = ctx.store.get(f"estudio/{estudio_id}")
    if not estudio:
        raise NoEncontrado("No existe ese estudio.")
    filas = []
    for sid, s in ctx.store.listar("sesion", [("estudioId", "==", estudio_id)]):
        filas.append({"sesionId": sid, "nombre": s.get("nombre"), "fecha": s.get("fecha"),
                      "estado": s.get("estado"), "valorComprometido": s.get("valorComprometido", 0)})
    filas.sort(key=lambda f: str(f.get("fecha") or ""))
    return {"estudioId": estudio_id, "valorComprometido": estudio.get("valorComprometido", 0),
            "sesiones": filas}
