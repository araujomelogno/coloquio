"""Configuración administrable desde la aplicación (R1.3, R1.10, P1).

Los umbrales de fatiga, las categorías, el guion y las plantillas de WhatsApp
son datos, no constantes en el código: los ajustan los investigadores.
"""

from . import modelo, pii, util
from .errores import DatosInvalidos, NoEncontrado


def _leer(store, doc, defecto):
    guardado = store.get(f"config/{doc}") or {}
    return {**defecto, **guardado}


def fatiga(store):
    return _leer(store, "fatigaCuali", modelo.FATIGA_POR_DEFECTO)


def guardar_fatiga(ctx, actor, cuerpo):
    datos = {
        "ventanaDias": util.entero(cuerpo.get("ventanaDias"), "ventanaDias", 1, 3650),
        "maxPorCategoria": util.entero(cuerpo.get("maxPorCategoria"), "maxPorCategoria", 1, 50),
        "ventanaGlobalDias": util.entero(cuerpo.get("ventanaGlobalDias"), "ventanaGlobalDias", 1, 3650),
        "maxGlobal": util.entero(cuerpo.get("maxGlobal"), "maxGlobal", 1, 100),
        "actualizadoPor": actor.uid,
        "actualizadoEn": ctx.ahora(),
    }
    ctx.store.set("config/fatigaCuali", datos)
    return fatiga(ctx.store)


def categorias(store):
    doc = store.get("config/categorias")
    return (doc or {}).get("items") or list(modelo.CATEGORIAS_POR_DEFECTO)


def guardar_categorias(ctx, actor, cuerpo):
    items, vistos = [], set()
    for c in cuerpo.get("items") or []:
        etiqueta = str(c.get("etiqueta") or "").strip()
        s = util.slug(c.get("slug") or etiqueta)
        if not s or s in vistos:
            continue
        # Las categorías son claves de `participacionCuali.porCategoria`: una
        # que se llame como un campo de PII rompería la validación del store.
        if s in pii.CAMPOS_PII:
            raise DatosInvalidos(f"«{s}» no se puede usar como categoría.")
        vistos.add(s)
        items.append({"slug": s, "etiqueta": etiqueta or s})
    if not items:
        raise DatosInvalidos("Tiene que haber al menos una categoría.")
    ctx.store.set("config/categorias", {"items": items, "actualizadoPor": actor.uid,
                                        "actualizadoEn": ctx.ahora()})
    return items


def exigir_categoria(store, slug):
    if slug not in {c["slug"] for c in categorias(store)}:
        raise DatosInvalidos(f"Categoría desconocida: {slug!r}.",
                             {"validas": [c["slug"] for c in categorias(store)]})
    return slug


def whatsapp(store):
    return _leer(store, "whatsapp", modelo.WHATSAPP_POR_DEFECTO)


def guardar_whatsapp(ctx, actor, cuerpo):
    datos = {k: str(cuerpo.get(k) or modelo.WHATSAPP_POR_DEFECTO[k]).strip()
             for k in modelo.WHATSAPP_POR_DEFECTO}
    datos.update({"actualizadoPor": actor.uid, "actualizadoEn": ctx.ahora()})
    ctx.store.set("config/whatsapp", datos)
    return whatsapp(ctx.store)


def guion(store):
    return (store.get("config/guion") or {}).get("texto") or modelo.GUION_POR_DEFECTO


def guardar_guion(ctx, actor, cuerpo):
    texto = str(cuerpo.get("texto") or "").strip()
    if not texto:
        raise DatosInvalidos("El guion no puede estar vacío.")
    pii.validar_texto_libre(texto, "guion")
    ctx.store.set("config/guion", {"texto": texto, "actualizadoPor": actor.uid,
                                   "actualizadoEn": ctx.ahora()})
    return {"texto": texto}


# ── R1.10 · catálogo de regalos ──

def listar_regalos(store, solo_activos=False):
    items = [{"id": i, **d} for i, d in store.listar("catalogoRegalo")]
    if solo_activos:
        items = [r for r in items if r.get("activo", True)]
    return sorted(items, key=lambda r: (not r.get("activo", True), r.get("nombre", "")))


def guardar_regalo(ctx, actor, cuerpo, regalo_id=None):
    nombre = str(cuerpo.get("nombre") or "").strip()
    if not nombre:
        raise DatosInvalidos("El regalo necesita un nombre.")
    datos = {
        "nombre": nombre,
        "valor": util.numero(cuerpo.get("valor"), "valor", 0),
        "moneda": str(cuerpo.get("moneda") or "UYU").strip().upper()[:3],
        "activo": bool(cuerpo.get("activo", True)),
        "actualizadoPor": actor.uid,
        "actualizadoEn": ctx.ahora(),
    }
    if regalo_id:
        if not ctx.store.get(f"catalogoRegalo/{regalo_id}"):
            raise NoEncontrado("No existe ese regalo.")
    else:
        regalo_id = util.slug(nombre)[:40] + "_" + util.nuevo_uuid()[:6]
    ctx.store.set(f"catalogoRegalo/{regalo_id}", datos)
    return {"id": regalo_id, **datos}


def regalo(store, regalo_id):
    if not regalo_id:
        return None
    r = store.get(f"catalogoRegalo/{regalo_id}")
    return {"id": regalo_id, **r} if r else None
