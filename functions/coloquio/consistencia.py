"""Verificación de consistencia que **repara**, no solo avisa (SPEC §13).

Los agregados mantenidos al escribir (`conteo`, `cuotas[].cubierto`,
`valorComprometido`) y el documento `participacionCuali` son la contrapartida
de no tener `group by`. Una transacción a medias o un bug los desincroniza y,
en el caso del historial, rompe tres cosas a la vez: fatiga, historial y el
índice de borrado. Esto los recalcula desde la fuente —las convocatorias,
asistencias e incentivos de cada sesión— y, con `reparar`, los reescribe.
"""

from . import historial, modelo, sesiones


def _sesion_esperada(store, sesion_id, sesion):
    convs = [d for _, d in store.listar(f"sesion/{sesion_id}/convocatoria")]
    incs = [d for _, d in store.listar(f"sesion/{sesion_id}/incentivo")]
    conteo = {e: sum(1 for c in convs if c["estado"] == e) for e in modelo.ESTADOS}
    cuotas = [dict(c) for c in sesion.get("cuotas") or []]
    sesiones.recalcular_cubierto(cuotas, convs)
    valor = round(sum(float(i.get("valor") or 0) for i in incs), 2)
    return convs, {"conteo": conteo, "cuotas": cuotas, "valorComprometido": valor}


def verificar(ctx, reparar=False):
    store = ctx.store
    hallazgos = []
    esperado_hist = {}
    valor_por_estudio = {}

    for sid, s in store.listar("sesion"):
        convs, esperado = _sesion_esperada(store, sid, s)
        actual_conteo = {e: int((s.get("conteo") or {}).get(e) or 0) for e in modelo.ESTADOS}
        dif = {}
        if actual_conteo != esperado["conteo"]:
            dif["conteo"] = {"actual": actual_conteo, "esperado": esperado["conteo"]}
        if [c.get("cubierto") for c in s.get("cuotas") or []] != [c["cubierto"] for c in esperado["cuotas"]]:
            dif["cuotas"] = {"esperado": [(c["dimension"], c["categoria"], c["cubierto"])
                                          for c in esperado["cuotas"]]}
        if round(float(s.get("valorComprometido") or 0), 2) != esperado["valorComprometido"]:
            dif["valorComprometido"] = {"actual": s.get("valorComprometido"),
                                        "esperado": esperado["valorComprometido"]}
        if dif:
            hallazgos.append({"tipo": "sesion", "id": sid, "diferencias": dif})
            if reparar:
                store.update(f"sesion/{sid}", esperado)
        eid = s.get("estudioId")
        valor_por_estudio[eid] = round(valor_por_estudio.get(eid, 0) + esperado["valorComprometido"], 2)

        # Reconstrucción del historial desde las sesiones.
        for c in convs:
            doc = esperado_hist.setdefault(c["idPersona"], historial.vacio())
            historial.registrar_convocatoria(doc, sid, s)
        if s.get("estado") == modelo.REALIZADA:
            for aid, _ in store.listar(f"sesion/{sid}/asistencia"):
                doc = esperado_hist.setdefault(aid, historial.vacio())
                historial.registrar_participacion(doc, sid, s)

    for eid, valor in valor_por_estudio.items():
        e = store.get(f"estudio/{eid}")
        if e is not None and round(float(e.get("valorComprometido") or 0), 2) != valor:
            hallazgos.append({"tipo": "estudio", "id": eid, "diferencias": {
                "valorComprometido": {"actual": e.get("valorComprometido"), "esperado": valor}}})
            if reparar:
                store.update(f"estudio/{eid}", {"valorComprometido": valor})

    # Historiales: los que difieren, los que faltan y los huérfanos.
    actuales = dict(store.listar("participacionCuali"))
    for pid in set(actuales) | set(esperado_hist):
        esperado = esperado_hist.get(pid)
        actual = actuales.get(pid)
        # Participaciones importadas a mano (P1) no salen de una sesión de acá:
        # se conservan.
        if actual and esperado is not None:
            importadas = [x for x in actual.get("sesiones") or [] if x.get("importada")]
            if importadas:
                esperado["sesiones"] = (esperado.get("sesiones") or []) + importadas
                historial.recomputar(esperado)

        def clave(doc):
            if not doc:
                return None
            return (sorted(x.get("sesionId") for x in doc.get("sesiones") or []),
                    sorted(x.get("sesionId") for x in doc.get("convocadoEn") or []))

        if clave(actual) != clave(esperado):
            hallazgos.append({"tipo": "participacionCuali", "id": pid,
                              "diferencias": {"actual": clave(actual), "esperado": clave(esperado)}})
            if reparar:
                if esperado is None:
                    store.delete(historial.ruta(pid))
                else:
                    store.set(historial.ruta(pid), esperado)

    return {"consistente": not hallazgos, "reparado": bool(reparar and hallazgos),
            "hallazgos": hallazgos}
