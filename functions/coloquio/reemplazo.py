"""R1.6 — Reemplazo con revalidación de cuota. El requisito más valioso de la fase.

* Ante un `no-show`, una baja de último momento (`se cayó`) o una baja del
  panel (alerta de la cascada, R1.11), el sistema propone candidatos que
  **restituyen el segmento perdido**: coinciden con quien se fue en todas las
  dimensiones que tienen cuota. No «cualquiera de la lista de espera».
* Primero se busca en la lista de espera de la sesión; si no alcanza, en el
  panel (bóveda + fatiga), con el segmento como filtro.
* Si nadie restituye el segmento, **se informa explícitamente** y se ofrecen
  las tres salidas: bajar el cupo, correr la fecha o aceptar la cuota
  incompleta. La elegida queda registrada con usuario y hora. Nunca se propone
  un reemplazo que rompe la cuota sin decirlo: si se elige uno que no
  coincide, hay que aceptarlo explícitamente y queda registrado igual.
"""

from . import configuracion, declaracion, embudo, historial, modelo, seleccion, sesiones, util
from .errores import Conflicto, DatosInvalidos, NoEncontrado


def _perdido(sesion, sesion_id, store, cuerpo):
    """El segmento que se perdió: de una convocatoria o de una alerta de baja."""
    alerta_id = cuerpo.get("alertaId")
    if alerta_id:
        alerta = next((a for a in sesion.get("alertasBaja") or []
                       if a.get("id") == alerta_id and not a.get("resuelta")), None)
        if not alerta:
            raise NoEncontrado("No hay una alerta de baja abierta con ese id.")
        return {"tipo": "alerta", "id": alerta_id, "segmento": alerta["segmento"],
                "estado": alerta.get("estadoPrevio"), "codigo": "BAJA"}
    id_persona = util.validar_id_persona(cuerpo.get("idPersona"))
    conv = store.get(embudo.ruta(sesion_id, id_persona))
    if not conv:
        raise NoEncontrado("Esa persona no está en el embudo de esta sesión.")
    if conv["estado"] not in (modelo.SE_CAYO, modelo.NO_SHOW):
        raise Conflicto("Solo se reemplaza a quien se cayó o no se presentó.")
    return {"tipo": "convocatoria", "id": id_persona, "segmento": conv["segmento"],
            "estado": conv["estado"], "codigo": util.codigo_de(id_persona)}


def _describir(segmento, dims):
    return ", ".join(f"{d} = {segmento.get(d)}" for d in dims) or "sin cuotas"


def _diferencias(segmento, perdido, dimensiones):
    return [d for d in dimensiones if (segmento or {}).get(d) != perdido.get(d)]


def proponer(ctx, actor, sesion_id, cuerpo):
    sesion = sesiones.exigir(ctx.store, sesion_id)
    sesiones.exigir_abierta(sesion)
    perdido = _perdido(sesion, sesion_id, ctx.store, cuerpo)
    dims = sesiones.dimensiones_con_cuota(sesion)
    convs = embudo.convocatorias(ctx.store, sesion_id)

    espera = sorted([c for c in convs if c["estado"] == modelo.CANDIDATO],
                    key=lambda c: c.get("ordenListaEspera") or 0)
    propuestos, parciales = [], []
    for c in espera:
        rompe = _diferencias(c["segmento"], perdido["segmento"], dims)
        item = {"idPersona": c["idPersona"], "codigo": util.codigo_de(c["idPersona"]),
                "segmento": c["segmento"], "origen": "lista_de_espera",
                "anulacion": c.get("anulacion"), "rompe": rompe}
        (parciales if rompe else propuestos).append(item)

    # Si la lista de espera no restituye el segmento, se busca en el panel.
    del_panel = []
    if not propuestos:
        filtros = {d: [perdido["segmento"].get(d)] for d in dims if perdido["segmento"].get(d)}
        en_sesion = {c["idPersona"] for c in convs}
        base = [b for b in ctx.boveda.convocables(filtros, ref_estudio=sesion.get("refEstudio"), limite=200)
                if b["idPersona"] not in en_sesion]
        hists = ctx.store.get_many([historial.ruta(b["idPersona"]) for b in base])
        cfg = configuracion.fatiga(ctx.store)
        ahora = ctx.ahora()
        for b in base:
            h = hists.get(historial.ruta(b["idPersona"]))
            if historial.sesion_del_mismo_estudio(h, sesion["estudioId"]):
                continue
            if historial.evaluar_fatiga(h, sesion["categoria"], cfg, ahora)["excluido"]:
                continue
            del_panel.append({"idPersona": b["idPersona"], "codigo": util.codigo_de(b["idPersona"]),
                              "segmento": b["segmento"], "origen": "panel",
                              "historial": historial.resumen(h), "rompe": []})
            if len(del_panel) >= 20:
                break
        propuestos = del_panel

    sin_reemplazo = not propuestos
    return {
        "perdido": perdido,
        "dimensionesConCuota": dims,
        "propuestos": propuestos,
        "parciales": parciales,
        "sinReemplazo": sin_reemplazo,
        "opciones": ([{"salida": k, "etiqueta": v} for k, v in modelo.SALIDAS_SIN_REEMPLAZO.items()]
                     if sin_reemplazo else []),
        "mensaje": (
            "Ningún candidato disponible restituye el segmento perdido "
            f"({_describir(perdido['segmento'], dims)}). "
            "Elegí una salida: bajar el cupo, correr la fecha o aceptar la sesión "
            "con la cuota incompleta." if sin_reemplazo else
            f"{len(propuestos)} candidato(s) restituyen el segmento perdido."),
        "cuota": sesiones.estado_de_cuota(sesion, convs),
    }


def _registrar_decision(sesion, perdido, salida, actor_uid, ahora, detalle=None):
    sesion.setdefault("decisionesCuota", []).append({
        "id": util.nuevo_uuid(),
        "salida": salida,
        "perdido": {"tipo": perdido["tipo"], "segmento": perdido["segmento"],
                    "codigo": perdido["codigo"]},
        "detalle": detalle or {},
        "actorUid": actor_uid,
        "ts": ahora,
    })


def resolver(ctx, actor, sesion_id, cuerpo):
    accion = cuerpo.get("accion")
    if accion == "reemplazar":
        return _reemplazar(ctx, actor, sesion_id, cuerpo)
    if accion == "sin_reemplazo":
        return _sin_reemplazo(ctx, actor, sesion_id, cuerpo)
    raise DatosInvalidos("La acción es `reemplazar` o `sin_reemplazo`.")


def _marcar_perdido(sesion, conv_perdido, perdido, actor_uid, ahora, resolucion, reemplazo_id=None):
    """Aplica al que se fue: `reemplazado` o la salida elegida."""
    if perdido["tipo"] == "alerta":
        for a in sesion.get("alertasBaja") or []:
            if a.get("id") == perdido["id"]:
                a.update({"resuelta": True, "resolucion": resolucion, "resueltaEn": ahora,
                          "reemplazadoPor": util.codigo_de(reemplazo_id) if reemplazo_id else None})
        return None
    if resolucion == "reemplazo":
        embudo.aplicar(sesion, conv_perdido, modelo.REEMPLAZADO, conv_perdido.get("canal") or "manual",
                       actor_uid, ahora, resultado="reemplazado")
        conv_perdido["reemplazadoPor"] = reemplazo_id
    else:
        conv_perdido["requiereReemplazo"] = False
        conv_perdido["resolucionCuota"] = resolucion
    return conv_perdido


def _reemplazar(ctx, actor, sesion_id, cuerpo):
    sesion = sesiones.exigir(ctx.store, sesion_id)
    sesiones.exigir_abierta(sesion)
    perdido = _perdido(sesion, sesion_id, ctx.store, cuerpo)
    reemplazo_id = util.validar_id_persona(cuerpo.get("reemplazo"))
    dims = sesiones.dimensiones_con_cuota(sesion)
    acepta_romper = bool(cuerpo.get("aceptarCuotaIncompleta"))
    ahora = ctx.ahora()

    en_espera = ctx.store.get(embudo.ruta(sesion_id, reemplazo_id))
    if en_espera is None:
        # Del panel: entra por el mismo camino que cualquier candidato (gate de
        # la vista, fatiga, un estudio por persona) y queda invitado.
        vigentes = {b["idPersona"]: b for b in ctx.boveda.convocables(
            ids=[reemplazo_id], ref_estudio=sesion.get("refEstudio"))}
        if reemplazo_id not in vigentes:
            raise Conflicto("Esa persona no tiene consentimiento vigente de contacto: no se puede convocar.")
        rompe = _diferencias(vigentes[reemplazo_id]["segmento"], perdido["segmento"], dims)
        if rompe and not acepta_romper:
            raise Conflicto(
                "Ese candidato no restituye el segmento perdido (difiere en "
                f"{', '.join(rompe)}). Para usarlo igual hay que aceptar la cuota "
                "incompleta explícitamente.", {"rompe": rompe})
        # Queda invitado: se declara antes (R5.2.a). Si la bóveda la rechaza,
        # no entra al embudo. Pero solo si va a poder entrar: si la frena la
        # fatiga (sin motivo) o ya está en otra sesión del estudio,
        # `_incorporar_tx` lo rechaza y no tiene que quedar una declaración.
        hist = ctx.store.get(historial.ruta(reemplazo_id))
        fatiga = historial.evaluar_fatiga(hist, sesion["categoria"], configuracion.fatiga(ctx.store), ahora)
        motivo = str((cuerpo.get("anulacion") or {}).get("motivo") or "").strip()
        entra = (not historial.sesion_del_mismo_estudio(hist, sesion["estudioId"], excepto_sesion=sesion_id)
                 and (not fatiga["excluido"] or (motivo and actor.puede("anular_fatiga"))))
        if entra:
            declaracion.declarar(ctx, sesion_id, sesion, reemplazo_id)
        seleccion._incorporar_tx(
            ctx, actor, sesion_id, {reemplazo_id: cuerpo}, vigentes, [],
            str((cuerpo.get("anulacion") or {}).get("motivo") or ""),
            configuracion.fatiga(ctx.store), ahora,
            es_reemplazo_de=perdido["id"], estado_final=modelo.INVITADO)
    elif en_espera["estado"] != modelo.CANDIDATO:
        raise Conflicto("El reemplazo tiene que estar en la lista de espera (estado candidato).")
    else:
        rompe = _diferencias(en_espera["segmento"], perdido["segmento"], dims)
        if rompe and not acepta_romper:
            raise Conflicto(
                "Ese candidato no restituye el segmento perdido (difiere en "
                f"{', '.join(rompe)}). Para usarlo igual hay que aceptar la cuota "
                "incompleta explícitamente.", {"rompe": rompe})
        declaracion.declarar(ctx, sesion_id, sesion, reemplazo_id)

    def tx_fn(tx):
        s = tx.get(f"sesion/{sesion_id}")
        conv_r = tx.get(embudo.ruta(sesion_id, reemplazo_id))
        conv_p = tx.get(embudo.ruta(sesion_id, perdido["id"])) if perdido["tipo"] == "convocatoria" else None
        rompe = _diferencias(conv_r["segmento"], perdido["segmento"], dims)
        if rompe and not acepta_romper:
            raise Conflicto(
                "Ese candidato no restituye el segmento perdido (difiere en "
                f"{', '.join(rompe)}). Para usarlo igual hay que aceptar la cuota "
                "incompleta explícitamente.", {"rompe": rompe})
        if conv_r["estado"] == modelo.CANDIDATO:
            conv_r["esReemplazoDe"] = perdido["id"]
            embudo.aplicar(s, conv_r, modelo.INVITADO, conv_r.get("canal") or "manual",
                           actor.uid, ahora, resultado="reemplazo")
        _marcar_perdido(s, conv_p, perdido, actor.uid, ahora, "reemplazo", reemplazo_id)
        if rompe:
            _registrar_decision(s, perdido, "reemplazo_rompe_cuota", actor.uid, ahora,
                                {"reemplazo": util.codigo_de(reemplazo_id), "rompe": rompe})
        tx.set(embudo.ruta(sesion_id, reemplazo_id), conv_r)
        if conv_p:
            tx.set(embudo.ruta(sesion_id, perdido["id"]), conv_p)
        tx.update(f"sesion/{sesion_id}", {
            **embudo._campos_sesion(s),
            "alertasBaja": s.get("alertasBaja") or [],
            "decisionesCuota": s.get("decisionesCuota") or []})
        return {"reemplazo": conv_r, "rompeCuota": rompe}

    return ctx.store.transaccion(tx_fn)


def _sin_reemplazo(ctx, actor, sesion_id, cuerpo):
    salida = cuerpo.get("salida")
    if salida not in modelo.SALIDAS_SIN_REEMPLAZO:
        raise DatosInvalidos("La salida es bajar_cupo, correr_fecha o aceptar_incompleta.",
                             {"salidas": list(modelo.SALIDAS_SIN_REEMPLAZO)})
    nueva_fecha = util.parse_fecha(cuerpo.get("nuevaFecha"), "nuevaFecha") if salida == "correr_fecha" else None
    ahora = ctx.ahora()
    sesion0 = sesiones.exigir(ctx.store, sesion_id)
    perdido = _perdido(sesion0, sesion_id, ctx.store, cuerpo)

    def tx_fn(tx):
        s = tx.get(f"sesion/{sesion_id}")
        sesiones.exigir_abierta(s)
        conv_p = tx.get(embudo.ruta(sesion_id, perdido["id"])) if perdido["tipo"] == "convocatoria" else None
        detalle = {}
        cambios = {}
        if salida == "bajar_cupo":
            nuevo_cupo = max(1, int(s["cupoObjetivo"]) - 1)
            for c in s.get("cuotas") or []:
                if sesiones.cumple(perdido["segmento"], c["dimension"], c["categoria"]):
                    c["objetivo"] = max(0, int(c["objetivo"]) - 1)
            detalle = {"cupoAnterior": s["cupoObjetivo"], "cupoNuevo": nuevo_cupo}
            s["cupoObjetivo"] = nuevo_cupo
            cambios.update({"cupoObjetivo": nuevo_cupo, "cuotas": s["cuotas"]})
        elif salida == "correr_fecha":
            detalle = {"fechaAnterior": s.get("fecha"), "fechaNueva": nueva_fecha}
            cambios["fecha"] = nueva_fecha
        _marcar_perdido(s, conv_p, perdido, actor.uid, ahora, salida)
        _registrar_decision(s, perdido, salida, actor.uid, ahora, detalle)
        if conv_p:
            tx.set(embudo.ruta(sesion_id, perdido["id"]), conv_p)
        tx.update(f"sesion/{sesion_id}", {
            **cambios, "alertasBaja": s.get("alertasBaja") or [],
            "decisionesCuota": s["decisionesCuota"]})
        return {"salida": salida, "detalle": detalle}

    resultado = ctx.store.transaccion(tx_fn)
    if salida == "correr_fecha":
        # Reprogramar es volver a declarar la misma referencia con otra fecha.
        s = sesiones.exigir(ctx.store, sesion_id)
        resultado["redeclaracion"] = declaracion.redeclarar_sesion(
            ctx, sesion_id, s, embudo.convocatorias(ctx.store, sesion_id))
    return resultado
