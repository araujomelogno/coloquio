"""Sesión: armado, cupo, cuotas, sobre-reclutamiento (R1.1, R1.6).

* **Una sesión no se puede abrir sin pauta activa** (R1.1). Queda atada a la
  versión vigente al abrirla.
* La sesión declara cupo objetivo, cuotas de composición (por dimensión:
  sexo, tramo etario, localidad) y ratio de sobre-reclutamiento. De ahí sale la
  **meta de invitación** de cada segmento: `ceil(objetivo × ratio)`, y el
  supuesto que la sostiene —la tasa de caída `1 − 1/ratio`— se muestra.
* El estado de cuota —cuántos faltan de cada segmento— se calcula a partir de
  las convocatorias y se muestra en todo momento (R1.6), no solo al armar.
"""

import math

from . import configuracion, estudios, modelo, pii, util
from .errores import Conflicto, DatosInvalidos, NoEncontrado


def exigir(store, sesion_id):
    d = store.get(f"sesion/{sesion_id}")
    if not d:
        raise NoEncontrado("No existe esa sesión.")
    return d


def exigir_abierta(sesion):
    if sesion.get("estado") not in modelo.SESION_ABIERTA:
        raise Conflicto(f"La sesión está {sesion.get('estado')}: ya no admite cambios de convocatoria.")


def normalizar_cuotas(crudas, cupo):
    cuotas, vistos = [], set()
    for c in crudas or []:
        dimension = str(c.get("dimension") or "").strip()
        if dimension not in modelo.DIMENSIONES_CUOTA:
            raise DatosInvalidos(f"Dimensión de cuota inválida: {dimension!r}.",
                                 {"validas": list(modelo.DIMENSIONES_CUOTA)})
        categoria = str(c.get("categoria") or "").strip()
        if not categoria:
            raise DatosInvalidos(f"Falta la categoría en una cuota de {dimension}.")
        if (dimension, categoria) in vistos:
            raise DatosInvalidos(f"La cuota {dimension} = {categoria} está repetida.")
        vistos.add((dimension, categoria))
        cuotas.append({
            "dimension": dimension,
            "categoria": categoria,
            "objetivo": util.entero(c.get("objetivo"), f"objetivo de {categoria}", 0, 1000),
            "cubierto": 0,
        })
    for dim in modelo.DIMENSIONES_CUOTA:
        total = sum(c["objetivo"] for c in cuotas if c["dimension"] == dim)
        if total > cupo:
            raise DatosInvalidos(
                f"Las cuotas de {dim} suman {total} y el cupo es {cupo}.")
    return cuotas


def _campos(ctx, cuerpo, parcial=False):
    datos = {}

    def tiene(campo):
        return not parcial or campo in cuerpo

    if tiene("fecha"):
        datos["fecha"] = util.parse_fecha(cuerpo.get("fecha"))
    if tiene("lugar"):
        lugar = str(cuerpo.get("lugar") or "").strip()
        if not lugar:
            raise DatosInvalidos("Falta el lugar de la sesión.")
        pii.validar_texto_libre(lugar, "lugar")
        datos["lugar"] = lugar
    if tiene("nombre"):
        nombre = str(cuerpo.get("nombre") or "").strip()
        pii.validar_texto_libre(nombre, "nombre")
        datos["nombre"] = nombre
    if tiene("tipo"):
        tipo = cuerpo.get("tipo") or "grupo"
        if tipo not in modelo.TIPOS_SESION:
            raise DatosInvalidos("El tipo es `grupo` o `idi`.")
        datos["tipo"] = tipo
    if tiene("cupoObjetivo"):
        datos["cupoObjetivo"] = util.entero(cuerpo.get("cupoObjetivo"), "cupoObjetivo", 1, 200)
    if tiene("ratioSobrerreclutamiento"):
        ratio = util.numero(cuerpo.get("ratioSobrerreclutamiento"), "ratioSobrerreclutamiento",
                            1, por_defecto=1.5)
        if ratio > 5:
            raise DatosInvalidos("Un ratio de sobre-reclutamiento mayor a 5 no es razonable.")
        datos["ratioSobrerreclutamiento"] = round(ratio, 3)
    if tiene("moderadorUid"):
        datos["moderadorUid"] = cuerpo.get("moderadorUid") or None
    if tiene("regaloId"):
        regalo_id = cuerpo.get("regaloId") or None
        if regalo_id and not configuracion.regalo(ctx.store, regalo_id):
            raise DatosInvalidos("El regalo elegido no está en el catálogo.")
        datos["regaloId"] = regalo_id
    if tiene("duracionMinutos"):
        datos["duracionMinutos"] = util.entero(cuerpo.get("duracionMinutos"), "duracionMinutos",
                                               10, 600, por_defecto=90)
    return datos


def crear(ctx, actor, cuerpo):
    estudio_id = cuerpo.get("estudioId")
    estudio = estudios.exigir(ctx.store, estudio_id)
    if estudio.get("estado") == "cerrado":
        raise Conflicto("El estudio está cerrado.")
    pauta = estudios.pauta_activa(ctx.store, estudio_id)
    if not pauta:
        raise Conflicto(
            "Una sesión no se puede abrir sin pauta activa: la pauta es el "
            "instrumento. Cargá la pauta del estudio primero (R1.1).")
    datos = _campos(ctx, cuerpo)
    datos["cuotas"] = normalizar_cuotas(cuerpo.get("cuotas"), datos["cupoObjetivo"])
    datos.update({
        "estudioId": estudio_id,
        "refEstudio": estudio["refEstudio"],
        "categoria": estudio["categoria"],
        "modalidad": "presencial",   # la virtual llega en la Fase 2
        "pautaId": pauta["id"],
        "pautaVersion": pauta["version"],
        "estado": modelo.PLANIFICADA,
        "conteo": {e: 0 for e in modelo.ESTADOS},
        "metricas": {},
        "alertasBaja": [],
        "decisionesCuota": [],
        "valorComprometido": 0,
        "creadaPor": actor.uid,
        "creadaEn": ctx.ahora(),
    })
    if not datos.get("duracionMinutos"):
        datos["duracionMinutos"] = pauta.get("minutosTotales") or 90
    sesion_id = util.nuevo_uuid()
    ctx.store.set(f"sesion/{sesion_id}", datos)
    return {"id": sesion_id, **datos}


def editar(ctx, actor, sesion_id, cuerpo):
    """Cambia fecha, lugar, cupo, cuotas o ratio mientras la sesión esté abierta.

    Las cuotas se recalculan contra las convocatorias actuales: `cubierto` nunca
    lo decide el cliente.
    """
    campos = _campos(ctx, cuerpo, parcial=True)

    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        if not sesion:
            raise NoEncontrado("No existe esa sesión.")
        exigir_abierta(sesion)
        convocatorias = [d for _, d in tx.listar(f"sesion/{sesion_id}/convocatoria")]
        cambios = dict(campos)
        cupo = cambios.get("cupoObjetivo", sesion["cupoObjetivo"])
        if "cuotas" in cuerpo or "cupoObjetivo" in cambios:
            crudas = cuerpo.get("cuotas", sesion.get("cuotas"))
            cuotas = normalizar_cuotas(crudas, cupo)
            recalcular_cubierto(cuotas, convocatorias)
            cambios["cuotas"] = cuotas
        if not cambios:
            raise DatosInvalidos("No hay nada para cambiar.")
        cambios.update({"actualizadaPor": actor.uid, "actualizadaEn": ctx.ahora()})
        tx.update(f"sesion/{sesion_id}", cambios)
        return {"id": sesion_id, **sesion, **cambios}

    return ctx.store.transaccion(tx_fn)


def listar(ctx, estado=None, desde=None, hasta=None):
    filtros = []
    if estado:
        filtros.append(("estado", "==", estado))
    items = [{"id": i, **d} for i, d in ctx.store.listar("sesion", filtros)]
    if desde:
        items = [s for s in items if s.get("fecha") and s["fecha"] >= desde]
    if hasta:
        items = [s for s in items if s.get("fecha") and s["fecha"] <= hasta]
    items.sort(key=lambda s: str(s.get("fecha") or ""))
    nombres = {}
    for s in items:
        eid = s.get("estudioId")
        if eid not in nombres:
            e = ctx.store.get(f"estudio/{eid}") or {}
            nombres[eid] = e.get("nombre")
        s["estudioNombre"] = nombres[eid]
    return items


# ════════════════════════════════════════════════════════════════════
#  Cuotas
# ════════════════════════════════════════════════════════════════════

def cumple(segmento, dimension, categoria):
    return (segmento or {}).get(dimension) == categoria


def recalcular_cubierto(cuotas, convocatorias):
    for c in cuotas:
        c["cubierto"] = sum(
            1 for conv in convocatorias
            if conv.get("estado") in modelo.CUBREN_CUOTA
            and cumple(conv.get("segmento"), c["dimension"], c["categoria"]))
    return cuotas


def ajustar_cubierto(sesion, segmento, delta):
    """Mantiene `cuotas[].cubierto` en la misma transacción que la transición."""
    for c in sesion.get("cuotas") or []:
        if cumple(segmento, c["dimension"], c["categoria"]):
            c["cubierto"] = max(0, int(c.get("cubierto") or 0) + delta)


def dimensiones_con_cuota(sesion):
    return sorted({c["dimension"] for c in sesion.get("cuotas") or []})


def estado_de_cuota(sesion, convocatorias):
    """Por cuota: objetivo, cubierto, meta de invitación, invitados, en espera."""
    ratio = sesion.get("ratioSobrerreclutamiento") or 1
    filas = []
    for c in sesion.get("cuotas") or []:
        def cuenta(estados):
            return sum(1 for conv in convocatorias
                       if conv.get("estado") in estados
                       and cumple(conv.get("segmento"), c["dimension"], c["categoria"]))
        cubierto = cuenta(modelo.CUBREN_CUOTA)
        filas.append({
            "dimension": c["dimension"],
            "categoria": c["categoria"],
            "objetivo": c["objetivo"],
            "cubierto": cubierto,
            "faltan": max(0, c["objetivo"] - cubierto),
            "metaInvitacion": modelo.meta_invitacion(c["objetivo"], ratio),
            "enInvitacion": cuenta(modelo.EN_INVITACION),
            "enEspera": cuenta({modelo.CANDIDATO}),
        })
    cupo = sesion.get("cupoObjetivo") or 0
    confirmados = sum(1 for conv in convocatorias
                      if conv.get("estado") in (modelo.CONFIRMADO, modelo.ASISTIO))
    return {
        "cupoObjetivo": cupo,
        "ratio": ratio,
        "tasaCaidaSupuesta": modelo.tasa_caida_supuesta(ratio),
        "metaInvitacionTotal": modelo.meta_invitacion(cupo, ratio),
        "invitados": sum(1 for conv in convocatorias if conv.get("estado") in modelo.EN_INVITACION),
        "aceptaron": sum(1 for conv in convocatorias if conv.get("estado") in modelo.CUBREN_CUOTA),
        "confirmados": confirmados,
        "cupoAlcanzado": confirmados >= cupo > 0,
        "cuotas": filas,
        "cuotaCompleta": all(f["faltan"] == 0 for f in filas),
    }


def avisos_de_disponibilidad(sesion, disponibles, ya_en_sesion):
    """R1.6 / caso borde: segmento sin candidatos suficientes.

    Se informa al armar, antes de empezar a convocar. `disponibles` son los
    candidatos seleccionables (sin fatiga); `ya_en_sesion` las convocatorias
    existentes (activas).
    """
    ratio = sesion.get("ratioSobrerreclutamiento") or 1
    avisos = []
    for c in sesion.get("cuotas") or []:
        meta = modelo.meta_invitacion(c["objetivo"], ratio)
        tiene = sum(1 for conv in ya_en_sesion
                    if conv.get("estado") in modelo.ACTIVOS | modelo.CUBREN_CUOTA
                    and cumple(conv.get("segmento"), c["dimension"], c["categoria"]))
        hay = sum(1 for d in disponibles if cumple(d.get("segmento"), c["dimension"], c["categoria"]))
        if tiene + hay < meta:
            avisos.append({
                "dimension": c["dimension"], "categoria": c["categoria"],
                "metaInvitacion": meta, "yaEnSesion": tiene, "disponibles": hay,
                "faltan": meta - tiene - hay,
                "mensaje": (f"{c['dimension']} = {c['categoria']}: hacen falta {meta} "
                            f"invitaciones y entre la sesión y esta selección hay "
                            f"{tiene + hay}. Ampliá el criterio o revisá la cuota "
                            "antes de convocar."),
            })
    return avisos


def proponer_invitacion(sesion, convocatorias):
    """R1.6 — la lista de invitación que cumple la cuota **asumiendo** la caída.

    Greedy sobre la lista de espera (en su orden): toma primero a quienes
    cubren los segmentos con más déficit contra su meta de invitación, hasta
    llegar a la meta total. Devuelve los ids propuestos y el supuesto.
    """
    ratio = sesion.get("ratioSobrerreclutamiento") or 1
    meta_total = modelo.meta_invitacion(sesion.get("cupoObjetivo") or 0, ratio)
    cuotas = sesion.get("cuotas") or []
    invitados = [c for c in convocatorias if c.get("estado") in modelo.EN_INVITACION]
    espera = sorted([c for c in convocatorias if c.get("estado") == modelo.CANDIDATO],
                    key=lambda c: c.get("ordenListaEspera") or 0)

    def deficit(lista):
        salida = {}
        for c in cuotas:
            meta = modelo.meta_invitacion(c["objetivo"], ratio)
            tiene = sum(1 for x in lista if cumple(x.get("segmento"), c["dimension"], c["categoria"]))
            salida[(c["dimension"], c["categoria"])] = meta - tiene
        return salida

    elegidos = []
    actuales = list(invitados)
    while len(actuales) < meta_total and espera:
        faltas = deficit(actuales)

        def aporte(conv):
            return sum(max(0, f) for (dim, cat), f in faltas.items()
                       if cumple(conv.get("segmento"), dim, cat))

        # Penaliza a quien agrega a un segmento que ya superó su meta.
        def exceso(conv):
            return sum(1 for (dim, cat), f in faltas.items()
                       if f <= 0 and cumple(conv.get("segmento"), dim, cat))

        mejor = max(espera, key=lambda c: (aporte(c), -exceso(c), -(c.get("ordenListaEspera") or 0)))
        if cuotas and aporte(mejor) == 0 and any(f > 0 for f in faltas.values()):
            # Nadie en espera aporta a un segmento con déficit: se corta y se
            # informa, en vez de completar con cualquiera.
            break
        espera.remove(mejor)
        elegidos.append(mejor["idPersona"])
        actuales.append(mejor)
    faltas = deficit(actuales)
    return {
        "propuestos": elegidos,
        "metaInvitacionTotal": meta_total,
        "yaInvitados": len(invitados),
        "tasaCaidaSupuesta": modelo.tasa_caida_supuesta(ratio),
        "supuesto": (f"Se invita a {meta_total} para sentar {sesion.get('cupoObjetivo')}: "
                     f"se asume que se cae el {round(modelo.tasa_caida_supuesta(ratio) * 100)}% "
                     f"(ratio {ratio})."),
        "deficitRestante": [
            {"dimension": d, "categoria": c, "faltan": f}
            for (d, c), f in faltas.items() if f > 0],
    }


def horas_hasta(sesion, ahora):
    fecha = sesion.get("fecha")
    if not fecha:
        return None
    return math.floor((fecha - ahora).total_seconds() / 3600)
