"""R1.11 — Atender la cascada de baja. El requisito que no se negocia.

Cuando alguien ejerce su derecho de baja en `paneles`, la bóveda le genera a
COLOQUIO un pendiente. Este proceso:

1. lee los pendientes (`mis_borrados_pendientes()`);
2. **borra** todo lo de esa persona en el store de COLOQUIO: convocatorias,
   asistencias, incentivos, mensajes de WhatsApp y el documento de historial;
3. **verifica** que no quedó rastro, con consultas de grupo independientes del
   índice;
4. recién entonces confirma (`confirmar_borrado()`). Ante cualquier falla,
   `reportar_error_de_borrado()` y el pendiente queda abierto para reintento.
   **Nunca se confirma un borrado que no ocurrió**: la bóveda confía en esa
   confirmación (HANDOFF §4).

`participacionCuali/{id}` es el índice (SPEC §6): dice qué sesiones tocar, así
que la cascada es una lectura y unos borrados dirigidos. Las consultas de grupo
por `idPersona` son la red de seguridad por si el índice se desincronizó.

Si la persona estaba en un embudo activo (aceptó / confirmó), sale y la sesión
recibe una **alerta de baja** con el segmento perdido —sin el id, que ya no
debe existir acá— que dispara el flujo de reemplazo de R1.6.
"""

import traceback

from . import embudo, historial, incentivos, modelo, recepcion, util

SUBCOLECCIONES = ("convocatoria", "asistencia", "incentivo")
REFERENCIAS = ("esReemplazoDe", "reemplazadoPor")

# Qué alcances le tocan a COLOQUIO en la Fase 1. Una baja total o el retiro de
# contacto_participacion obligan a borrar todo: los datos de COLOQUIO existen
# porque la persona participó. Las demás finalidades (grabación, moderación
# automatizada, uso semántico cuali, difusión) no tienen datos en esta fase.
ALCANCES_QUE_BORRAN = {"total", "contacto_participacion"}


def _sesiones_de(ctx, id_persona):
    """Índice + red de seguridad: todas las sesiones donde hay algo suyo."""
    doc = ctx.store.get(historial.ruta(id_persona)) or {}
    ids = {s.get("sesionId") for s in doc.get("sesiones") or []}
    ids |= {c.get("sesionId") for c in doc.get("convocadoEn") or []}
    for sub in SUBCOLECCIONES:
        for ruta_doc, _ in ctx.store.grupo(sub, [("idPersona", "==", id_persona)]):
            ids.add(ruta_doc.split("/")[1])
    return sorted(i for i in ids if i)


def _borrar_de_sesion(ctx, sesion_id, id_persona):
    ahora = ctx.ahora()

    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        conv = tx.get(embudo.ruta(sesion_id, id_persona))
        inc = tx.get(incentivos.ruta(sesion_id, id_persona))
        asis = tx.get(recepcion.ruta(sesion_id, id_persona))
        estudio = tx.get(f"estudio/{sesion['estudioId']}") if sesion else None
        cambios = {}
        if sesion and conv:
            estado_previo = conv["estado"]
            embudo.contar_baja(sesion, conv)
            cambios.update(embudo._campos_sesion(sesion))
            if estado_previo in modelo.CUBREN_CUOTA - {modelo.ASISTIO} and \
                    sesion.get("estado") in modelo.SESION_ABIERTA:
                sesion.setdefault("alertasBaja", []).append({
                    "id": util.nuevo_uuid(),
                    "segmento": conv.get("segmento"),
                    "estadoPrevio": estado_previo,
                    "ts": ahora,
                    "resuelta": False,
                })
                # Si ya no alcanza el cupo, vuelve a convocatoria.
                confirmados = int(sesion["conteo"].get(modelo.CONFIRMADO) or 0) + int(
                    sesion["conteo"].get(modelo.ASISTIO) or 0)
                if sesion.get("estado") == modelo.CONFIRMADA and confirmados < int(sesion["cupoObjetivo"]):
                    cambios["estado"] = modelo.CONVOCANDO
                cambios["alertasBaja"] = sesion["alertasBaja"]
        if sesion and inc:
            incentivos.sumar_valor(sesion, -float(inc.get("valor") or 0))
            cambios["valorComprometido"] = sesion["valorComprometido"]
            if estudio:
                incentivos.sumar_valor(estudio, -float(inc.get("valor") or 0))
        if sesion:
            # El código de convocatoria es un fragmento del id: también se va.
            codigo = util.codigo_de(id_persona)
            tocado = False
            for d in sesion.get("decisionesCuota") or []:
                if (d.get("perdido") or {}).get("codigo") == codigo:
                    d["perdido"]["codigo"] = "BAJA"
                    tocado = True
                if (d.get("detalle") or {}).get("reemplazo") == codigo:
                    d["detalle"]["reemplazo"] = "BAJA"
                    tocado = True
            for a in sesion.get("alertasBaja") or []:
                if a.get("reemplazadoPor") == codigo:
                    a["reemplazadoPor"] = "BAJA"
                    tocado = True
            if tocado:
                cambios["decisionesCuota"] = sesion.get("decisionesCuota") or []
                cambios["alertasBaja"] = sesion.get("alertasBaja") or []
        for sub in SUBCOLECCIONES:
            tx.delete(f"sesion/{sesion_id}/{sub}/{id_persona}")
        if sesion and cambios:
            tx.update(f"sesion/{sesion_id}", cambios)
        if estudio and inc:
            tx.update(f"estudio/{sesion['estudioId']}",
                      {"valorComprometido": estudio["valorComprometido"]})

    ctx.store.transaccion(tx_fn)


def borrar_persona(ctx, id_persona):
    """Borra todo lo de una persona y verifica. Devuelve el detalle."""
    id_persona = util.validar_id_persona(id_persona)
    sesiones_tocadas = _sesiones_de(ctx, id_persona)
    for sid in sesiones_tocadas:
        _borrar_de_sesion(ctx, sid, id_persona)
    # Referencias desde la convocatoria de otra persona (quién reemplazó a quién).
    for campo in REFERENCIAS:
        for ruta_doc, _ in ctx.store.grupo("convocatoria", [(campo, "==", id_persona)]):
            ctx.store.update(ruta_doc, {campo: "baja"})
    mensajes = ctx.store.listar("mensajeWa", [("idPersona", "==", id_persona)])
    for wamid, _ in mensajes:
        ctx.store.delete(f"mensajeWa/{wamid}")
    ctx.store.delete(historial.ruta(id_persona))
    restos = rastro(ctx, id_persona)
    if restos:
        raise RuntimeError(f"Quedó rastro después del borrado: {restos}")
    return {"sesiones": len(sesiones_tocadas), "mensajes": len(mensajes)}


def rastro(ctx, id_persona):
    """Lo que quede de una persona en el store. Vacío = no quedó nada (DoD 9)."""
    restos = []
    if ctx.store.get(historial.ruta(id_persona)) is not None:
        restos.append(historial.ruta(id_persona))
    for sub in SUBCOLECCIONES:
        restos += [r for r, _ in ctx.store.grupo(sub, [("idPersona", "==", id_persona)])]
    for campo in REFERENCIAS:
        restos += [f"{r}#{campo}" for r, _ in ctx.store.grupo("convocatoria", [(campo, "==", id_persona)])]
    restos += [f"mensajeWa/{i}" for i, _ in
               ctx.store.listar("mensajeWa", [("idPersona", "==", id_persona)])]
    return restos


def procesar(ctx):
    """Una pasada sobre los pendientes. La llama el proceso programado."""
    pendientes = ctx.boveda.borrados_pendientes()
    resultado = {"pendientes": len(pendientes), "confirmados": 0, "errores": 0,
                 "sinDatosEnFase1": 0, "detalle": []}
    for p in pendientes:
        id_persona, alcance = p["idPersona"], p.get("alcance") or "total"
        try:
            if alcance in ALCANCES_QUE_BORRAN or p.get("finalidad") in ALCANCES_QUE_BORRAN:
                detalle = borrar_persona(ctx, id_persona)
            else:
                # Finalidad sin datos en la Fase 1: igual se verifica que no
                # haya nada que dependa de ella antes de confirmar.
                detalle = {"sinDatos": True}
                resultado["sinDatosEnFase1"] += 1
            ctx.boveda.confirmar_borrado(id_persona, alcance)
            resultado["confirmados"] += 1
            resultado["detalle"].append({"alcance": alcance, **detalle, "ok": True})
        except Exception as error:  # noqa: BLE001
            # El mensaje no lleva datos de la persona: solo el tipo y el texto
            # del error, que nombra rutas por id_persona.
            texto = f"{error.__class__.__name__}: {error}"[:500]
            print(f"[cascada] error borrando un pendiente: {texto}\n{traceback.format_exc()}")
            try:
                ctx.boveda.reportar_error_de_borrado(id_persona, texto, alcance)
            except Exception as error2:  # noqa: BLE001
                print(f"[cascada] tampoco se pudo reportar el error: {error2!r}")
            resultado["errores"] += 1
            resultado["detalle"].append({"alcance": alcance, "ok": False, "error": texto})
    return resultado
