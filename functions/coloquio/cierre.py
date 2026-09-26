"""R1.8 — Cierre de sesión y registro de participación propio. Y la cancelación.

Al cerrar, **en una sola transacción**:

* quien estaba confirmado y no llegó pasa a `no-show`;
* por cada asistencia se escribe la participación en `participacionCuali`
  (estudio, categoría, sesión, rol, fecha) — el registro cualitativo es de
  COLOQUIO y **no se escribe en la bóveda**;
* toda asistencia tiene su compromiso de incentivo;
* la sesión queda `realizada` con su tasa de show.

Consecuencia asumida y documentada (SPEC §13): el muestreo de `paneles` no
ve estas participaciones.
"""

from . import configuracion, embudo, historial, incentivos, modelo, pii, util
from .errores import Conflicto, DatosInvalidos, NoEncontrado


def cerrar(ctx, actor, sesion_id, cuerpo):
    notas = str(cuerpo.get("notasSesion") or "").strip()
    pii.validar_texto_libre(notas, "notas de la sesión")
    ahora = ctx.ahora()

    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        if not sesion:
            raise NoEncontrado("No existe esa sesión.")
        if sesion.get("estado") not in modelo.SESION_ABIERTA:
            raise Conflicto(f"La sesión ya está {sesion.get('estado')}.")
        convs = {i: d for i, d in tx.listar(f"sesion/{sesion_id}/convocatoria")}
        asist = {i: d for i, d in tx.listar(f"sesion/{sesion_id}/asistencia")}
        incs = {i: d for i, d in tx.listar(f"sesion/{sesion_id}/incentivo")}
        if not asist and not cuerpo.get("confirmarSinAsistentes"):
            raise Conflicto(
                "No hay ninguna asistencia registrada. Si la sesión no se hizo, "
                "cancelala; si se hizo sin registrar, confirmá el cierre sin asistentes.")
        hists = tx.get_many([historial.ruta(i) for i in asist])
        estudio = tx.get(f"estudio/{sesion['estudioId']}")
        regalo = None
        if sesion.get("regaloId"):
            regalo = tx.get(f"catalogoRegalo/{sesion['regaloId']}")
            if regalo:
                regalo = {"id": sesion["regaloId"], **regalo}

        no_show = []
        for i, conv in convs.items():
            if conv["estado"] == modelo.CONFIRMADO and i not in asist:
                embudo.aplicar(sesion, conv, modelo.NO_SHOW, conv.get("canal") or "manual",
                               embudo.ACTOR_CIERRE, ahora, resultado="cierre")
                conv["requiereReemplazo"] = False
                no_show.append(i)

        nuevos_incentivos = []
        for i in asist:
            if i not in incs:
                inc = incentivos.nuevo(i, regalo, ahora)
                incentivos.sumar_valor(sesion, inc["valor"])
                incentivos.sumar_valor(estudio, inc["valor"])
                nuevos_incentivos.append((i, inc))

        # La tasa de show se mide sobre quienes llegaron confirmados al día.
        presentes = len(asist)
        confirmados_al_dia = presentes + len(no_show)
        m = sesion.setdefault("metricas", {})
        m["showRate"] = round(presentes / confirmados_al_dia, 4) if confirmados_al_dia else None
        m["presentes"] = presentes
        m["noShows"] = len(no_show)
        m["cuotaCompletaAlCierre"] = all(
            int(c.get("cubierto") or 0) >= int(c.get("objetivo") or 0)
            for c in sesion.get("cuotas") or [])
        invitados = int(m.get("invitados") or 0)
        m["ratioRealNecesario"] = round(invitados / presentes, 3) if presentes else None
        if m.get("invitadoPrimeroEn") and m.get("cupoConfirmadoEn"):
            m["horasDeConvocatoria"] = round(
                (m["cupoConfirmadoEn"] - m["invitadoPrimeroEn"]).total_seconds() / 3600, 1)

        # ── escrituras ──
        for i in no_show:
            tx.set(embudo.ruta(sesion_id, i), convs[i])
        for i, inc in nuevos_incentivos:
            tx.set(incentivos.ruta(sesion_id, i), inc)
        for i in asist:
            doc = historial.registrar_participacion(hists[historial.ruta(i)], sesion_id, sesion)
            tx.set(historial.ruta(i), doc)
        tx.update(f"sesion/{sesion_id}", {
            **embudo._campos_sesion(sesion),
            "estado": modelo.REALIZADA,
            "metricas": m,
            "valorComprometido": sesion.get("valorComprometido", 0),
            "notasSesion": notas,
            "cerradaEn": ahora,
            "cerradaPor": actor.uid,
        })
        tx.update(f"estudio/{sesion['estudioId']}",
                  {"valorComprometido": estudio.get("valorComprometido", 0)})
        return {"estado": modelo.REALIZADA, "presentes": presentes, "noShows": no_show,
                "showRate": m["showRate"], "participacionesEscritas": len(asist),
                "incentivosComprometidos": len(asist)}

    return ctx.store.transaccion(tx_fn)


def cancelar(ctx, actor, sesion_id, cuerpo):
    """Sesión cancelada con gente confirmada: estado propio, con los incentivos
    que se decidan compensar registrados a mano (caso borde de la SPEC)."""
    motivo = str(cuerpo.get("motivo") or "").strip()
    if not motivo:
        raise DatosInvalidos("Indicá el motivo de la cancelación.")
    pii.validar_texto_libre(motivo, "motivo")
    resolucion = str(cuerpo.get("resolucionIncentivos") or "").strip()
    pii.validar_texto_libre(resolucion, "resolución de incentivos")
    compensar = [util.validar_id_persona(i) for i in cuerpo.get("compensar") or []]
    regalo = configuracion.regalo(ctx.store, cuerpo.get("regaloId")) if compensar else None
    if compensar and not regalo:
        raise DatosInvalidos("Para compensar hay que elegir un regalo del catálogo.")
    ahora = ctx.ahora()

    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        if not sesion:
            raise NoEncontrado("No existe esa sesión.")
        if sesion.get("estado") not in modelo.SESION_ABIERTA:
            raise Conflicto(f"La sesión ya está {sesion.get('estado')}.")
        convs = tx.get_many([embudo.ruta(sesion_id, i) for i in compensar])
        estudio = tx.get(f"estudio/{sesion['estudioId']}")
        existentes = tx.get_many([incentivos.ruta(sesion_id, i) for i in compensar])
        confirmados = int(sesion.get("conteo", {}).get(modelo.CONFIRMADO) or 0) + int(
            sesion.get("conteo", {}).get(modelo.ACEPTO) or 0)
        creados = []
        for i in compensar:
            conv = convs[embudo.ruta(sesion_id, i)]
            if not conv or conv["estado"] not in (modelo.ACEPTO, modelo.CONFIRMADO):
                raise Conflicto(f"{util.codigo_de(i)} no estaba confirmado: no corresponde compensarlo.")
            if existentes[incentivos.ruta(sesion_id, i)]:
                continue
            inc = incentivos.nuevo(i, regalo, ahora, motivo="cancelacion")
            incentivos.sumar_valor(sesion, inc["valor"])
            incentivos.sumar_valor(estudio, inc["valor"])
            creados.append((i, inc))
        for i, inc in creados:
            tx.set(incentivos.ruta(sesion_id, i), inc)
        tx.update(f"sesion/{sesion_id}", {
            "estado": modelo.CANCELADA,
            "cancelacion": {"motivo": motivo, "resolucionIncentivos": resolucion,
                            "confirmadosAlCancelar": confirmados,
                            "compensados": len(creados), "actorUid": actor.uid, "ts": ahora},
            "valorComprometido": sesion.get("valorComprometido", 0),
        })
        tx.update(f"estudio/{sesion['estudioId']}",
                  {"valorComprometido": estudio.get("valorComprometido", 0)})
        return {"estado": modelo.CANCELADA, "compensados": [i for i, _ in creados]}

    return ctx.store.transaccion(tx_fn)
