"""R1.4 — Embudo de convocatoria.

* `sesion/{s}/convocatoria/{idPersona}`: **el id del documento es el
  `id_persona`**, así que «una persona no puede estar dos veces en la misma
  sesión» es una propiedad del store (SPEC §6). Que no esté en dos sesiones
  del mismo estudio lo garantiza `participacionCuali.convocadoEn`, leído y
  escrito en la misma transacción que la alta.
* Cada transición registra estado anterior, nuevo, canal, timestamp y quién o
  qué la produjo (`eventos[]`).
* Los estados terminales sacan a la persona del embudo; volver exige
  `reingresar`, con motivo.
* **Los agregados se mantienen al escribir** (SPEC §6): `conteo` por estado,
  `cuotas[].cubierto` y `metricas` se actualizan en la misma transacción que
  cambia el estado. Firestore no hace `group by`.

Las funciones `aplicar_*` son puras sobre los diccionarios: las usan también
recepción, cierre, reemplazo, el webhook de WhatsApp y la cascada, para que
haya una sola definición de qué hace una transición.
"""

from . import historial, modelo, sesiones, util
from .errores import Conflicto, DatosInvalidos, NoEncontrado, TransicionInvalida

ACTOR_WHATSAPP = "sistema:whatsapp"
ACTOR_CIERRE = "sistema:cierre"
ACTOR_CASCADA = "sistema:cascada"


def ruta(sesion_id, id_persona):
    return f"sesion/{sesion_id}/convocatoria/{id_persona}"


def nueva(id_persona, segmento, orden, actor_uid, ahora, canal="manual",
          anulacion=None, es_reemplazo_de=None, puntaje=None):
    return {
        "idPersona": id_persona,
        "estado": modelo.CANDIDATO,
        "canal": canal,
        "segmento": {k: segmento.get(k) for k in modelo.DIMENSIONES_CUOTA},
        "ordenListaEspera": orden,
        "esReemplazoDe": es_reemplazo_de,
        "anulacion": anulacion,
        "puntaje": puntaje,
        "requiereReemplazo": False,
        "creadaEn": ahora,
        "eventos": [{"de": None, "a": modelo.CANDIDATO, "canal": canal,
                     "resultado": "incorporado", "ts": ahora, "actor": actor_uid}],
    }


def _metricas(sesion):
    return sesion.setdefault("metricas", {})


def _sumar(sesion, clave, n=1):
    m = _metricas(sesion)
    m[clave] = int(m.get(clave) or 0) + n


def contar_alta(sesion, conv):
    conteo = sesion.setdefault("conteo", {})
    conteo[conv["estado"]] = int(conteo.get(conv["estado"]) or 0) + 1
    if conv["estado"] in modelo.CUBREN_CUOTA:
        sesiones.ajustar_cubierto(sesion, conv["segmento"], +1)


def contar_baja(sesion, conv):
    conteo = sesion.setdefault("conteo", {})
    conteo[conv["estado"]] = max(0, int(conteo.get(conv["estado"]) or 0) - 1)
    if conv["estado"] in modelo.CUBREN_CUOTA:
        sesiones.ajustar_cubierto(sesion, conv["segmento"], -1)


def camino(desde, hasta):
    if hasta in modelo.TRANSICIONES.get(desde, set()):
        return (hasta,)
    if (desde, hasta) in modelo.ATAJOS:
        return modelo.ATAJOS[(desde, hasta)]
    raise TransicionInvalida(
        f"No se puede pasar de «{modelo.ETIQUETAS.get(desde, desde)}» a "
        f"«{modelo.ETIQUETAS.get(hasta, hasta)}».",
        {"desde": desde, "hasta": hasta,
         "permitidos": sorted(modelo.TRANSICIONES.get(desde, set()))})


def _paso(sesion, conv, destino, canal, actor_uid, ahora, resultado=None, motivo=None):
    origen = conv["estado"]
    evento = {"de": origen, "a": destino, "canal": canal, "resultado": resultado,
              "ts": ahora, "actor": actor_uid}
    if motivo:
        evento["motivo"] = motivo
    contar_baja(sesion, conv)
    conv["estado"] = destino
    contar_alta(sesion, conv)
    conv.setdefault("eventos", []).append(evento)
    conv["actualizadaEn"] = ahora

    # Métricas que después dan tasa de show, tiempo de convocatoria e
    # intentos por confirmación, por canal (SPEC §12).
    m = _metricas(sesion)
    if destino == modelo.INVITADO:
        _sumar(sesion, "invitados")
        m.setdefault("invitadoPrimeroEn", ahora)
        if sesion.get("estado") == modelo.PLANIFICADA:
            sesion["estado"] = modelo.CONVOCANDO
    if destino in (modelo.CONTACTADO, modelo.NO_CONTACTABLE) and canal == "manual":
        _sumar(sesion, f"intentos_{canal}")
    if destino == modelo.CONFIRMADO:
        _sumar(sesion, f"confirmaciones_{canal}")
    if destino in (modelo.SE_CAYO, modelo.NO_SHOW):
        conv["requiereReemplazo"] = sesion.get("estado") in modelo.SESION_ABIERTA
    if destino == modelo.REEMPLAZADO:
        conv["requiereReemplazo"] = False

    confirmados = int(sesion["conteo"].get(modelo.CONFIRMADO) or 0) + int(
        sesion["conteo"].get(modelo.ASISTIO) or 0)
    cupo = int(sesion.get("cupoObjetivo") or 0)
    if confirmados >= cupo > 0:
        m.setdefault("cupoConfirmadoEn", ahora)
        if sesion.get("estado") in (modelo.PLANIFICADA, modelo.CONVOCANDO):
            sesion["estado"] = modelo.CONFIRMADA
    elif sesion.get("estado") == modelo.CONFIRMADA:
        # Se cayó alguien y ya no alcanza: vuelve a convocatoria.
        sesion["estado"] = modelo.CONVOCANDO


def aplicar(sesion, conv, destino, canal, actor_uid, ahora, resultado=None, motivo=None):
    """Transición (con atajo si corresponde). Muta `sesion` y `conv`."""
    if destino not in modelo.ESTADOS:
        raise DatosInvalidos(f"Estado desconocido: {destino!r}.")
    if canal not in modelo.CANALES:
        raise DatosInvalidos(f"Canal desconocido: {canal!r}.")
    pasos = camino(conv["estado"], destino)
    for paso in pasos:
        _paso(sesion, conv, paso, canal, actor_uid, ahora,
              resultado=resultado if paso == destino else "implícito", motivo=motivo)
    return pasos


def aplicar_forzado(sesion, conv, destino, canal, actor_uid, ahora, motivo, anulacion):
    """Transición fuera del grafo, con anulación registrada (R1.7)."""
    _paso(sesion, conv, destino, canal, actor_uid, ahora, resultado="anulacion", motivo=motivo)
    conv["anulacionEstado"] = anulacion
    return (destino,)


def _campos_sesion(sesion):
    return {k: sesion[k] for k in ("conteo", "cuotas", "metricas", "estado") if k in sesion}


# ════════════════════════════════════════════════════════════════════
#  Operaciones
# ════════════════════════════════════════════════════════════════════

def transicionar(ctx, actor, sesion_id, id_persona, cuerpo):
    id_persona = util.validar_id_persona(id_persona)
    destino = cuerpo.get("a") or cuerpo.get("estado")
    if destino == modelo.REEMPLAZADO:
        raise DatosInvalidos("«Reemplazado» se marca al elegir el reemplazo, no a mano.")
    ahora = ctx.ahora()

    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        if not sesion:
            raise NoEncontrado("No existe esa sesión.")
        sesiones.exigir_abierta(sesion)
        conv = tx.get(ruta(sesion_id, id_persona))
        if not conv:
            raise NoEncontrado("Esa persona no está en el embudo de esta sesión.")
        canal = cuerpo.get("canal") or conv.get("canal") or "manual"
        estado_previo = sesion.get("estado")
        pasos = aplicar(sesion, conv, destino, canal, actor.uid, ahora,
                        resultado=cuerpo.get("resultado"))
        tx.set(ruta(sesion_id, id_persona), conv)
        tx.update(f"sesion/{sesion_id}", _campos_sesion(sesion))
        return {"convocatoria": conv, "pasos": list(pasos),
                "cupoAlcanzado": sesion.get("estado") == modelo.CONFIRMADA,
                "cupoRecienAlcanzado": (sesion.get("estado") == modelo.CONFIRMADA
                                        and estado_previo != modelo.CONFIRMADA)}

    return ctx.store.transaccion(tx_fn)


def registrar_intento(ctx, actor, sesion_id, id_persona, cuerpo):
    """Llamé y no atendió: un intento sin cambio de estado (métrica por canal)."""
    id_persona = util.validar_id_persona(id_persona)
    ahora = ctx.ahora()

    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        conv = tx.get(ruta(sesion_id, id_persona))
        if not sesion or not conv:
            raise NoEncontrado("No existe esa convocatoria.")
        sesiones.exigir_abierta(sesion)
        if conv["estado"] not in (modelo.INVITADO, modelo.CONTACTADO, modelo.ACEPTO):
            raise Conflicto("Solo se registran intentos de contacto mientras la convocatoria está en curso.")
        canal = cuerpo.get("canal") or conv.get("canal") or "manual"
        conv.setdefault("eventos", []).append({
            "de": conv["estado"], "a": conv["estado"], "canal": canal,
            "resultado": cuerpo.get("resultado") or "sin_respuesta", "ts": ahora,
            "actor": actor.uid})
        _sumar(sesion, f"intentos_{canal}")
        tx.set(ruta(sesion_id, id_persona), conv)
        tx.update(f"sesion/{sesion_id}", {"metricas": sesion["metricas"]})
        return {"convocatoria": conv}

    return ctx.store.transaccion(tx_fn)


def cambiar_canal(ctx, actor, sesion_id, id_persona, cuerpo):
    """R1.5 — el canal lo elige el coordinador, persona por persona."""
    id_persona = util.validar_id_persona(id_persona)
    canal = cuerpo.get("canal")
    if canal not in modelo.CANALES:
        raise DatosInvalidos("El canal es `manual` o `whatsapp`.")

    def tx_fn(tx):
        conv = tx.get(ruta(sesion_id, id_persona))
        if not conv:
            raise NoEncontrado("No existe esa convocatoria.")
        tx.update(ruta(sesion_id, id_persona), {"canal": canal, "degradacion": None})
        return {**conv, "canal": canal, "degradacion": None}

    return ctx.store.transaccion(tx_fn)


def reingresar(ctx, actor, sesion_id, id_persona, cuerpo):
    """Acción explícita para volver desde un terminal (R1.4)."""
    id_persona = util.validar_id_persona(id_persona)
    motivo = str(cuerpo.get("motivo") or "").strip()
    if not motivo:
        raise DatosInvalidos("Volver a meter a alguien al embudo requiere un motivo.")
    ahora = ctx.ahora()

    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        conv = tx.get(ruta(sesion_id, id_persona))
        if not sesion or not conv:
            raise NoEncontrado("No existe esa convocatoria.")
        sesiones.exigir_abierta(sesion)
        if conv["estado"] not in modelo.TERMINALES_REINGRESABLES:
            raise TransicionInvalida("Solo se reingresa desde rechazó, no contactable o no-show.")
        _paso(sesion, conv, modelo.INVITADO, conv.get("canal") or "manual", actor.uid, ahora,
              resultado="reingreso", motivo=motivo)
        conv["requiereReemplazo"] = False
        tx.set(ruta(sesion_id, id_persona), conv)
        tx.update(f"sesion/{sesion_id}", _campos_sesion(sesion))
        return {"convocatoria": conv}

    return ctx.store.transaccion(tx_fn)


def quitar_candidato(ctx, actor, sesion_id, id_persona):
    """Sacar de la lista de espera a alguien que nunca fue invitado."""
    id_persona = util.validar_id_persona(id_persona)

    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        conv = tx.get(ruta(sesion_id, id_persona))
        hist = tx.get(historial.ruta(id_persona))
        if not sesion or not conv:
            raise NoEncontrado("No existe esa convocatoria.")
        if conv["estado"] != modelo.CANDIDATO:
            raise Conflicto("Solo se puede quitar a quien todavía no fue invitado: lo demás queda registrado.")
        contar_baja(sesion, conv)
        tx.delete(ruta(sesion_id, id_persona))
        tx.update(f"sesion/{sesion_id}", _campos_sesion(sesion))
        if hist:
            historial.quitar_convocatoria(hist, sesion_id)
            if hist.get("total") or hist.get("convocadoEn"):
                tx.set(historial.ruta(id_persona), hist)
            else:
                tx.delete(historial.ruta(id_persona))
        return {"quitado": id_persona}

    return ctx.store.transaccion(tx_fn)


def invitar_propuestos(ctx, actor, sesion_id, cuerpo):
    """Pasa a `invitado` la lista propuesta (o la que mande el cliente)."""
    ids = [util.validar_id_persona(i) for i in cuerpo.get("ids") or []]
    canal = cuerpo.get("canal") or "manual"
    if canal not in modelo.CANALES:
        raise DatosInvalidos("Canal inválido.")
    ahora = ctx.ahora()

    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        if not sesion:
            raise NoEncontrado("No existe esa sesión.")
        sesiones.exigir_abierta(sesion)
        docs = tx.get_many([ruta(sesion_id, i) for i in ids])
        invitados = []
        for i in ids:
            conv = docs[ruta(sesion_id, i)]
            if not conv or conv["estado"] != modelo.CANDIDATO:
                continue
            conv["canal"] = canal
            aplicar(sesion, conv, modelo.INVITADO, canal, actor.uid, ahora, resultado="lista_de_invitacion")
            invitados.append((i, conv))
        for i, conv in invitados:
            tx.set(ruta(sesion_id, i), conv)
        tx.update(f"sesion/{sesion_id}", _campos_sesion(sesion))
        return {"invitados": [i for i, _ in invitados]}

    return ctx.store.transaccion(tx_fn)


# ════════════════════════════════════════════════════════════════════
#  Vista del tablero (pantalla 4)
# ════════════════════════════════════════════════════════════════════

def convocatorias(store, sesion_id):
    return [d for _, d in store.listar(f"sesion/{sesion_id}/convocatoria")]


def _publica(conv):
    salida = dict(conv)
    salida["codigo"] = util.codigo_de(conv["idPersona"])
    salida["etiqueta"] = modelo.ETIQUETAS.get(conv["estado"], conv["estado"])
    salida["siguientes"] = sorted(
        modelo.TRANSICIONES.get(conv["estado"], set()) - {modelo.REEMPLAZADO})
    salida["eventos"] = conv.get("eventos") or []
    return salida


def vista(ctx, sesion_id):
    sesion = sesiones.exigir(ctx.store, sesion_id)
    convs = convocatorias(ctx.store, sesion_id)
    convs.sort(key=lambda c: (modelo.ESTADOS.index(c["estado"]), c.get("ordenListaEspera") or 0))
    estudio = ctx.store.get(f"estudio/{sesion['estudioId']}") or {}
    cuota = sesiones.estado_de_cuota(sesion, convs)
    m = sesion.get("metricas") or {}
    confirmados_totales = int(m.get("confirmaciones_manual") or 0) + int(m.get("confirmaciones_whatsapp") or 0)
    return {
        "sesion": {"id": sesion_id, **sesion},
        "estudio": {"id": sesion["estudioId"], "nombre": estudio.get("nombre"),
                    "categoria": estudio.get("categoria")},
        "cuota": cuota,
        "conteo": {e: sum(1 for c in convs if c["estado"] == e) for e in modelo.ESTADOS},
        "convocatorias": [_publica(c) for c in convs],
        "pendientesDeReemplazo": [
            {"idPersona": c["idPersona"], "codigo": util.codigo_de(c["idPersona"]),
             "segmento": c["segmento"], "estado": c["estado"]}
            for c in convs if c.get("requiereReemplazo")],
        "alertasBaja": [a for a in sesion.get("alertasBaja") or [] if not a.get("resuelta")],
        "metricas": {
            **m,
            "intentosPorConfirmacion": {
                canal: (round(int(m.get(f"intentos_{canal}") or 0) /
                              int(m.get(f"confirmaciones_{canal}") or 1), 2)
                        if m.get(f"confirmaciones_{canal}") else None)
                for canal in modelo.CANALES},
            "confirmacionesTotales": confirmados_totales,
        },
        "etiquetas": modelo.ETIQUETAS,
    }
