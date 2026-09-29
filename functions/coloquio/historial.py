"""R1.3 · R1.9 · R1.11 — `participacionCuali/{idPersona}`, el documento clave.

Un solo documento por persona sostiene tres requisitos (SPEC §6):

* **Fatiga cualitativa** (R1.3): de acá sale si participó de una sesión de la
  misma categoría dentro de la ventana, o si pasó el tope global.
* **Historial** (R1.9): cuántas veces, en qué estudios y categorías, en qué
  modalidad, cuándo fue la última.
* **Índice de borrado** (R1.11): `sesiones[]` (donde participó) y
  `convocadoEn[]` (donde está o estuvo en el embudo) dicen exactamente qué
  tocar ante una baja. La cascada es una lectura y unos borrados dirigidos,
  no un barrido.

Se mantiene en las mismas transacciones que cambian lo que resume: al
incorporar a alguien a un embudo y al cerrar la sesión. Como es una
dependencia concentrada, `consistencia.py` lo puede reconstruir.

La fatiga corre contra este registro, **no** contra `v_fatiga_panelista` de la
bóveda, que mide convocatorias a encuestas (R1.3).
"""

import datetime as dt

from .errores import NoEncontrado


def ruta(id_persona):
    return f"participacionCuali/{id_persona}"


def vacio():
    return {"total": 0, "ultimaEn": None, "porCategoria": {}, "sesiones": [],
            "convocadoEn": []}


def registrar_convocatoria(doc, sesion_id, sesion):
    doc = doc or vacio()
    lista = doc.setdefault("convocadoEn", [])
    if not any(c.get("sesionId") == sesion_id for c in lista):
        lista.append({"sesionId": sesion_id, "estudioId": sesion.get("estudioId")})
    return doc


def quitar_convocatoria(doc, sesion_id):
    if doc:
        doc["convocadoEn"] = [c for c in doc.get("convocadoEn") or []
                              if c.get("sesionId") != sesion_id]
    return doc


def sesion_del_mismo_estudio(doc, estudio_id, excepto_sesion=None):
    """La sesión del mismo estudio donde ya está la persona, si hay (R1.4)."""
    for c in (doc or {}).get("convocadoEn") or []:
        if c.get("estudioId") == estudio_id and c.get("sesionId") != excepto_sesion:
            return c.get("sesionId")
    return None


def registrar_participacion(doc, sesion_id, sesion, rol="participante"):
    """Al cerrar una sesión. Idempotente: una sesión cuenta una vez."""
    doc = doc or vacio()
    if any(s.get("sesionId") == sesion_id for s in doc.get("sesiones") or []):
        return doc
    fecha = sesion.get("fecha")
    categoria = sesion.get("categoria")
    doc.setdefault("sesiones", []).append({
        "sesionId": sesion_id,
        "estudioId": sesion.get("estudioId"),
        "refEstudio": sesion.get("refEstudio"),
        "categoria": categoria,
        "fecha": fecha,
        "modalidad": sesion.get("modalidad", "presencial"),
        "tipo": sesion.get("tipo", "grupo"),
        "rol": rol,
    })
    return recomputar(doc)


def recomputar(doc):
    """Total, última y por categoría a partir de `sesiones[]`."""
    sesiones = doc.get("sesiones") or []
    doc["total"] = len(sesiones)
    fechas = [s["fecha"] for s in sesiones if s.get("fecha")]
    doc["ultimaEn"] = max(fechas) if fechas else None
    por_categoria = {}
    for s in sesiones:
        c = por_categoria.setdefault(s.get("categoria") or "sin_categoria",
                                     {"total": 0, "ultimaEn": None})
        c["total"] += 1
        if s.get("fecha") and (c["ultimaEn"] is None or s["fecha"] > c["ultimaEn"]):
            c["ultimaEn"] = s["fecha"]
    doc["porCategoria"] = por_categoria
    return doc


def evaluar_fatiga(doc, categoria, config, ahora):
    """R1.3 — ¿excluido? y por qué. Solo cuenta participación efectiva."""
    sesiones = (doc or {}).get("sesiones") or []
    motivos = []
    ventana = ahora - dt.timedelta(days=int(config["ventanaDias"]))
    en_categoria = [s for s in sesiones
                    if s.get("categoria") == categoria and s.get("fecha") and s["fecha"] >= ventana]
    if len(en_categoria) >= int(config["maxPorCategoria"]):
        ultima = max(s["fecha"] for s in en_categoria)
        motivos.append({
            "regla": "categoria",
            "mensaje": (f"Participó de {len(en_categoria)} sesión(es) de «{categoria}» "
                        f"en los últimos {config['ventanaDias']} días (última: "
                        f"{ultima.date().isoformat()})."),
        })
    ventana_global = ahora - dt.timedelta(days=int(config["ventanaGlobalDias"]))
    en_global = [s for s in sesiones if s.get("fecha") and s["fecha"] >= ventana_global]
    if len(en_global) >= int(config["maxGlobal"]):
        motivos.append({
            "regla": "global",
            "mensaje": (f"Llegó al tope global: {len(en_global)} participaciones "
                        f"cualitativas en {config['ventanaGlobalDias']} días "
                        f"(máximo {config['maxGlobal']})."),
        })
    return {"excluido": bool(motivos), "motivos": motivos}


def resumen(doc):
    """Lo que se muestra junto a cada candidato (R1.9, en la pantalla de selección)."""
    doc = doc or vacio()
    return {
        "total": doc.get("total", 0),
        "ultimaEn": doc.get("ultimaEn"),
        "porCategoria": doc.get("porCategoria") or {},
        "sesiones": sorted(doc.get("sesiones") or [], key=lambda s: str(s.get("fecha")),
                           reverse=True),
    }


def ver(ctx, id_persona):
    doc = ctx.store.get(ruta(id_persona))
    if doc is None:
        raise NoEncontrado("Esa persona no tiene historial cualitativo en COLOQUIO.")
    salida = resumen(doc)
    nombres = {}
    for s in salida["sesiones"]:
        eid = s.get("estudioId")
        if eid not in nombres:
            nombres[eid] = ((ctx.store.get(f"estudio/{eid}") or {}).get("nombre")
                            if eid else s.get("etiqueta") or "Sesión histórica importada")
        s["estudioNombre"] = nombres[eid]
    salida["idPersona"] = id_persona
    salida["convocatoriasActivas"] = len(doc.get("convocadoEn") or [])
    return salida
