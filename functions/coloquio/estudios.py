"""R1.1 — Estudio y pauta.

* El estudio emite un `refEstudio` (uuid): el mismo identificador que `paneles`
  usa para cruzar encuesta ↔ cuestionario. Un estudio mixto cuanti-cuali trae
  el `ref_estudio` de su encuesta y lo comparte.
* La pauta es el instrumento del cualitativo: tópicos ordenados con objetivo,
  minutos estimados y repreguntas previstas. Es **versionada**: guardar crea
  una versión nueva y desactiva la anterior, en la misma transacción. Una
  sesión queda atada a la versión con la que se abrió.
"""

from . import configuracion, pii, util
from .errores import DatosInvalidos, NoEncontrado


def _estudio_publico(estudio_id, d):
    return {"id": estudio_id, **d}


def crear(ctx, actor, cuerpo):
    nombre = str(cuerpo.get("nombre") or "").strip()
    if not nombre:
        raise DatosInvalidos("El estudio necesita un nombre.")
    categoria = configuracion.exigir_categoria(ctx.store, util.slug(cuerpo.get("categoria")))
    ref = cuerpo.get("refEstudio")
    ref = util.validar_id_persona(ref) if ref else util.nuevo_uuid()
    for campo in ("nombre", "cliente", "descripcion"):
        pii.validar_texto_libre(cuerpo.get(campo) or "", campo)
    datos = {
        "refEstudio": ref,
        "nombre": nombre,
        "cliente": str(cuerpo.get("cliente") or "").strip(),
        "descripcion": str(cuerpo.get("descripcion") or "").strip(),
        "categoria": categoria,
        "estado": "activo",
        "pautaActivaId": None,
        "pautaActivaVersion": 0,
        "valorComprometido": 0,
        "creadoPor": actor.uid,
        "creadoEn": ctx.ahora(),
    }
    estudio_id = util.nuevo_uuid()
    ctx.store.set(f"estudio/{estudio_id}", datos)
    return _estudio_publico(estudio_id, datos)


def exigir(store, estudio_id):
    d = store.get(f"estudio/{estudio_id}")
    if not d:
        raise NoEncontrado("No existe ese estudio.")
    return d


def listar(ctx):
    items = [_estudio_publico(i, d) for i, d in ctx.store.listar("estudio")]
    items.sort(key=lambda e: str(e.get("creadoEn") or ""), reverse=True)
    return items


def ver(ctx, estudio_id):
    d = exigir(ctx.store, estudio_id)
    pautas = [{"id": i, **p} for i, p in ctx.store.listar(f"estudio/{estudio_id}/pauta")]
    pautas.sort(key=lambda p: -p.get("version", 0))
    sesiones = [{"id": i, **s} for i, s in
                ctx.store.listar("sesion", [("estudioId", "==", estudio_id)])]
    sesiones.sort(key=lambda s: str(s.get("fecha") or ""))
    return {
        **_estudio_publico(estudio_id, d),
        "pautaActiva": next((p for p in pautas if p.get("activa")), None),
        "versionesPauta": [{"id": p["id"], "version": p["version"], "activa": p.get("activa"),
                            "creadaEn": p.get("creadaEn"), "topicos": len(p.get("topicos") or [])}
                           for p in pautas],
        "sesiones": sesiones,
    }


def editar(ctx, actor, estudio_id, cuerpo):
    exigir(ctx.store, estudio_id)
    cambios = {}
    for campo in ("nombre", "cliente", "descripcion", "guion"):
        if campo in cuerpo:
            texto = str(cuerpo.get(campo) or "").strip()
            pii.validar_texto_libre(texto, campo)
            cambios[campo] = texto
    if "estado" in cuerpo:
        if cuerpo["estado"] not in ("activo", "cerrado"):
            raise DatosInvalidos("Estado de estudio inválido.")
        cambios["estado"] = cuerpo["estado"]
    if not cambios:
        raise DatosInvalidos("No hay nada para cambiar.")
    cambios.update({"actualizadoPor": actor.uid, "actualizadoEn": ctx.ahora()})
    ctx.store.update(f"estudio/{estudio_id}", cambios)
    return ver(ctx, estudio_id)


def _normalizar_topicos(crudos):
    topicos = []
    for i, t in enumerate(crudos or []):
        titulo = str(t.get("titulo") or "").strip()
        if not titulo:
            raise DatosInvalidos(f"El tópico {i + 1} no tiene título.")
        repreguntas = [str(r).strip() for r in (t.get("repreguntas") or []) if str(r).strip()]
        objetivo = str(t.get("objetivo") or "").strip()
        for texto in [titulo, objetivo, *repreguntas]:
            pii.validar_texto_libre(texto, f"tópico {i + 1}")
        topicos.append({
            "orden": i + 1,
            "titulo": titulo,
            "objetivo": objetivo,
            "minutos": util.entero(t.get("minutos"), f"minutos del tópico {i + 1}", 1, 600),
            "repreguntas": repreguntas,
        })
    if not topicos:
        raise DatosInvalidos("La pauta necesita al menos un tópico.")
    return topicos


def guardar_pauta(ctx, actor, estudio_id, cuerpo):
    topicos = _normalizar_topicos(cuerpo.get("topicos"))
    pauta_id = util.nuevo_uuid()
    ahora = ctx.ahora()

    def tx_fn(tx):
        estudio = tx.get(f"estudio/{estudio_id}")
        if not estudio:
            raise NoEncontrado("No existe ese estudio.")
        anteriores = tx.listar(f"estudio/{estudio_id}/pauta", [("activa", "==", True)])
        version = int(estudio.get("pautaActivaVersion") or 0) + 1
        for pid, _ in anteriores:
            tx.update(f"estudio/{estudio_id}/pauta/{pid}", {"activa": False})
        datos = {
            "version": version,
            "activa": True,
            "topicos": topicos,
            "minutosTotales": sum(t["minutos"] for t in topicos),
            "creadaPor": actor.uid,
            "creadaEn": ahora,
        }
        tx.set(f"estudio/{estudio_id}/pauta/{pauta_id}", datos)
        tx.update(f"estudio/{estudio_id}", {"pautaActivaId": pauta_id,
                                            "pautaActivaVersion": version})
        return {"id": pauta_id, **datos}

    return ctx.store.transaccion(tx_fn)


def pauta_activa(store, estudio_id):
    activas = store.listar(f"estudio/{estudio_id}/pauta", [("activa", "==", True)])
    if not activas:
        return None
    pid, datos = activas[0]
    return {"id": pid, **datos}


def tema_para_guion(estudio):
    return estudio.get("descripcion") or estudio.get("nombre") or "un tema de actualidad"

