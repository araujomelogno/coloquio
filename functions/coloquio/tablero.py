"""Tablero: sesiones de la semana y métricas de la fase (SPEC §12, P1).

La tasa de show y su tendencia son lo que el responsable de operaciones
necesita para dejar de adivinar el ratio de sobre-reclutamiento.
"""

import datetime as dt

from . import modelo, sesiones


def resumen(ctx):
    ahora = ctx.ahora()
    todas = sesiones.listar(ctx)
    semana = [s for s in todas if s.get("fecha") and
              ahora - dt.timedelta(days=1) <= s["fecha"] <= ahora + dt.timedelta(days=7)
              and s.get("estado") != modelo.CANCELADA]
    realizadas = sorted([s for s in todas if s.get("estado") == modelo.REALIZADA],
                        key=lambda s: s["fecha"])
    tendencia = [{
        "sesionId": s["id"], "nombre": s.get("nombre"), "estudio": s.get("estudioNombre"),
        "fecha": s["fecha"],
        "showRate": (s.get("metricas") or {}).get("showRate"),
        "ratioConfigurado": s.get("ratioSobrerreclutamiento"),
        "ratioRealNecesario": (s.get("metricas") or {}).get("ratioRealNecesario"),
        "horasDeConvocatoria": (s.get("metricas") or {}).get("horasDeConvocatoria"),
        "cuotaCompleta": (s.get("metricas") or {}).get("cuotaCompletaAlCierre"),
    } for s in realizadas]
    con_show = [t["showRate"] for t in tendencia if t["showRate"] is not None]
    m_tot = {}
    for s in todas:
        for k, v in (s.get("metricas") or {}).items():
            if k.startswith(("intentos_", "confirmaciones_")) or k in (
                    "anulacionesFatiga", "reconvocatoriasBloqueadas", "plantillasWhatsapp",
                    "mensajesEnVentanaWhatsapp"):
                m_tot[k] = m_tot.get(k, 0) + int(v or 0)
    return {
        "semana": semana,
        "enConvocatoria": [s for s in todas if s.get("estado") in (modelo.PLANIFICADA, modelo.CONVOCANDO,
                                                                   modelo.CONFIRMADA)],
        "tendenciaShow": tendencia[-20:],
        "showRatePromedio": round(sum(con_show) / len(con_show), 4) if con_show else None,
        "sesionesRealizadas": len(realizadas),
        "sesionesConCuotaCompleta": sum(1 for t in tendencia if t["cuotaCompleta"]),
        "totales": m_tot,
        "intentosPorConfirmacion": {
            c: (round(m_tot.get(f"intentos_{c}", 0) / m_tot[f"confirmaciones_{c}"], 2)
                if m_tot.get(f"confirmaciones_{c}") else None) for c in modelo.CANALES},
    }
