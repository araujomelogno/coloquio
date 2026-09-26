"""R1.5 — Canal de convocatoria: manual y WhatsApp, elegido por persona.

Una interfaz, dos implementaciones:

* **Manual** (se construye primero, no depende de nada): el sistema muestra el
  contacto leído de la bóveda y el guion sugerido; el coordinador llama o
  escribe por fuera y registra el resultado con un clic por estado.
* **WhatsApp**: plantillas aprobadas por Meta; la respuesta del convocado
  mueve el embudo sola. Si el canal falla, la convocatoria **degrada a
  manual conservando su estado**.

El dato de contacto se obtiene con `contacto_para_convocatoria()` en el
momento de usarlo, con el email del usuario como `p_actor`, y **no se
persiste**: no va al evento del embudo, ni al documento, ni a un log (R1.12).
"""

import datetime as dt

from . import configuracion, embudo, estudios, modelo, sesiones, util, whatsapp
from .errores import Conflicto, DatosInvalidos, NoEncontrado, SinPermiso

MOTIVO_AUDITORIA = "convocatoria coloquio"


def _fecha_local(fecha):
    if not fecha:
        return "a confirmar"
    local = fecha.astimezone(util.TZ)
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    return f"{dias[local.weekday()]} {local.day:02d}/{local.month:02d} a las {local:%H:%M}"


def variables_guion(store, sesion, estudio, id_persona):
    regalo = configuracion.regalo(store, sesion.get("regaloId"))
    return {
        "tema": estudios.tema_para_guion(estudio),
        "fecha": _fecha_local(sesion.get("fecha")),
        "lugar": sesion.get("lugar") or "a confirmar",
        "duracion": sesion.get("duracionMinutos") or 90,
        "incentivo": regalo["nombre"] if regalo else "un obsequio",
        "codigo": util.codigo_de(id_persona),
    }


def guion_para(store, sesion, estudio, id_persona):
    texto = estudio.get("guion") or configuracion.guion(store)
    try:
        return texto.format(**variables_guion(store, sesion, estudio, id_persona))
    except (KeyError, IndexError, ValueError):
        return texto


def contacto(ctx, actor, sesion_id, id_persona, canal):
    """GET contacto puntual (auditado en la bóveda). No se guarda nada."""
    id_persona = util.validar_id_persona(id_persona)
    if canal not in ("celular", "email"):
        raise DatosInvalidos("El canal de contacto es `celular` o `email`.")
    if not actor.email:
        raise SinPermiso("Tu usuario no tiene email: la bóveda exige saber quién pide el contacto.")
    sesion = sesiones.exigir(ctx.store, sesion_id)
    sesiones.exigir_abierta(sesion)
    conv = ctx.store.get(embudo.ruta(sesion_id, id_persona))
    if not conv:
        raise NoEncontrado("Esa persona no está en el embudo de esta sesión.")
    if conv["estado"] in modelo.TERMINALES:
        raise Conflicto("Esa convocatoria está cerrada: no hay motivo para leer su contacto.")
    estudio = ctx.store.get(f"estudio/{sesion['estudioId']}") or {}
    dato = ctx.boveda.contacto(id_persona, canal, actor.email, MOTIVO_AUDITORIA)
    return {
        "canal": canal,
        "dato": dato,
        "vacio": not dato,
        "guion": guion_para(ctx.store, sesion, estudio, id_persona),
        "codigo": util.codigo_de(id_persona),
        "aviso": ("Este dato se leyó de la bóveda y la lectura quedó auditada a tu "
                  "nombre. No se guarda en COLOQUIO: no lo copies a planillas ni notas."),
    }


# ════════════════════════════════════════════════════════════════════
#  WhatsApp — envío
# ════════════════════════════════════════════════════════════════════

TIPOS = ("invitacion", "recordatorio", "confirmacion")


def _degradar(ctx, sesion_id, id_persona, motivo):
    ahora = ctx.ahora()

    def tx_fn(tx):
        conv = tx.get(embudo.ruta(sesion_id, id_persona))
        if not conv:
            return None
        conv["canal"] = "manual"
        conv["degradacion"] = {"motivo": str(motivo)[:300], "ts": ahora}
        conv.setdefault("eventos", []).append({
            "de": conv["estado"], "a": conv["estado"], "canal": "whatsapp",
            "resultado": "degradado_a_manual", "ts": ahora, "actor": embudo.ACTOR_WHATSAPP})
        tx.set(embudo.ruta(sesion_id, id_persona), conv)
        return conv

    return ctx.store.transaccion(tx_fn)


def enviar_whatsapp(ctx, actor, sesion_id, id_persona, cuerpo):
    id_persona = util.validar_id_persona(id_persona)
    tipo = cuerpo.get("tipo") or "invitacion"
    if tipo not in TIPOS:
        raise DatosInvalidos(f"Tipo de mensaje inválido: {tipo!r}.", {"tipos": list(TIPOS)})
    sesion = sesiones.exigir(ctx.store, sesion_id)
    sesiones.exigir_abierta(sesion)
    conv = ctx.store.get(embudo.ruta(sesion_id, id_persona))
    if not conv:
        raise NoEncontrado("Esa persona no está en el embudo de esta sesión.")
    if conv["estado"] in modelo.TERMINALES:
        raise Conflicto("Esa convocatoria está cerrada.")
    if tipo == "invitacion" and conv["estado"] not in (modelo.CANDIDATO, modelo.INVITADO):
        raise Conflicto("La invitación se manda a quien todavía no respondió.")
    if tipo == "confirmacion" and conv["estado"] != modelo.ACEPTO:
        raise Conflicto("La confirmación se pide a quien ya aceptó.")
    estudio = ctx.store.get(f"estudio/{sesion['estudioId']}") or {}
    cfg_wa = configuracion.whatsapp(ctx.store)
    ahora = ctx.ahora()
    ventana = conv.get("ventanaServicioHasta")
    en_ventana = bool(ventana and ventana > ahora)
    v = variables_guion(ctx.store, sesion, estudio, id_persona)
    si, no = whatsapp.payload(sesion_id, id_persona, "si"), whatsapp.payload(sesion_id, id_persona, "no")

    # Fuera de la transacción: el envío es un efecto externo y la transacción
    # se puede reintentar. El celular vive solo en esta variable local.
    try:
        celular = ctx.boveda.contacto(id_persona, "celular", actor.email, MOTIVO_AUDITORIA)
        if tipo != "invitacion" and en_ventana:
            texto = {
                "recordatorio": (f"Te recordamos el encuentro del {v['fecha']} en {v['lugar']}. "
                                 f"Tu código es {v['codigo']}. ¿Seguís pudiendo venir?"),
                "confirmacion": (f"¡Gracias! ¿Nos confirmás tu lugar para el {v['fecha']} en "
                                 f"{v['lugar']}? Tu código es {v['codigo']}."),
            }[tipo]
            wamid = ctx.canal_wa.enviar_texto_con_botones(
                celular, texto, [("Sí, confirmo", si), ("No puedo", no)])
            pago = False
        else:
            plantilla = {"invitacion": cfg_wa["plantillaInvitacion"],
                         "recordatorio": cfg_wa["plantillaRecordatorio"],
                         "confirmacion": cfg_wa["plantillaConfirmacion"]}[tipo]
            wamid = ctx.canal_wa.enviar_plantilla(
                celular, plantilla, cfg_wa["idioma"],
                [v["tema"], v["fecha"], v["lugar"], v["incentivo"], v["codigo"]],
                botones=(si, no))
            pago = True
        del celular
    except whatsapp.ErrorCanal as error:
        conv2 = _degradar(ctx, sesion_id, id_persona, str(error))
        return {"enviado": False, "degradado": True, "motivo": str(error), "convocatoria": conv2}
    except Exception as error:  # noqa: BLE001 — contacto rechazado u otro
        from .errores import ErrorApi

        if isinstance(error, ErrorApi):
            conv2 = _degradar(ctx, sesion_id, id_persona, error.mensaje)
            return {"enviado": False, "degradado": True, "motivo": error.mensaje,
                    "convocatoria": conv2}
        raise

    def tx_fn(tx):
        s = tx.get(f"sesion/{sesion_id}")
        c = tx.get(embudo.ruta(sesion_id, id_persona))
        c["canal"] = "whatsapp"
        if c["estado"] == modelo.CANDIDATO:
            embudo.aplicar(s, c, modelo.INVITADO, "whatsapp", actor.uid, ahora,
                           resultado=f"wa_{tipo}")
        else:
            c.setdefault("eventos", []).append({
                "de": c["estado"], "a": c["estado"], "canal": "whatsapp",
                "resultado": f"wa_{tipo}_enviado", "ts": ahora, "actor": actor.uid})
        m = s.setdefault("metricas", {})
        m["intentos_whatsapp"] = int(m.get("intentos_whatsapp") or 0) + 1
        if pago:
            m["plantillasWhatsapp"] = int(m.get("plantillasWhatsapp") or 0) + 1
        else:
            m["mensajesEnVentanaWhatsapp"] = int(m.get("mensajesEnVentanaWhatsapp") or 0) + 1
        tx.set(embudo.ruta(sesion_id, id_persona), c)
        tx.update(f"sesion/{sesion_id}", embudo._campos_sesion(s))
        tx.set(f"mensajeWa/{wamid}", {"sesionId": sesion_id, "idPersona": id_persona,
                                      "tipo": tipo, "ts": ahora, "pago": pago})
        return c

    conv = ctx.store.transaccion(tx_fn)
    return {"enviado": True, "degradado": False, "pago": pago, "enVentana": en_ventana,
            "convocatoria": conv}


# ════════════════════════════════════════════════════════════════════
#  WhatsApp — webhook
# ════════════════════════════════════════════════════════════════════

def _respuesta(ctx, sesion_id, id_persona, afirmativo):
    """La respuesta del convocado actualiza el embudo automáticamente."""
    ahora = ctx.ahora()

    def tx_fn(tx):
        s = tx.get(f"sesion/{sesion_id}")
        c = tx.get(embudo.ruta(sesion_id, id_persona))
        if not s or not c or s.get("estado") not in modelo.SESION_ABIERTA:
            return {"ignorado": True}
        c["ventanaServicioHasta"] = ahora + dt.timedelta(hours=whatsapp.VENTANA_SERVICIO_HORAS)
        c["respuestaPendienteRevision"] = False
        estado = c["estado"]
        destino = None
        if afirmativo:
            destino = {modelo.INVITADO: modelo.ACEPTO, modelo.CONTACTADO: modelo.ACEPTO,
                       modelo.ACEPTO: modelo.CONFIRMADO}.get(estado)
        else:
            destino = {modelo.INVITADO: modelo.RECHAZO, modelo.CONTACTADO: modelo.RECHAZO,
                       modelo.ACEPTO: modelo.SE_CAYO, modelo.CONFIRMADO: modelo.SE_CAYO}.get(estado)
        if destino:
            embudo.aplicar(s, c, destino, "whatsapp", embudo.ACTOR_WHATSAPP, ahora,
                           resultado="respuesta_whatsapp")
        else:
            c.setdefault("eventos", []).append({
                "de": estado, "a": estado, "canal": "whatsapp",
                "resultado": "respuesta_sin_efecto", "ts": ahora, "actor": embudo.ACTOR_WHATSAPP})
        tx.set(embudo.ruta(sesion_id, id_persona), c)
        tx.update(f"sesion/{sesion_id}", embudo._campos_sesion(s))
        return {"de": estado, "a": c["estado"]}

    return ctx.store.transaccion(tx_fn)


def _marcar_revision(ctx, sesion_id, id_persona):
    ahora = ctx.ahora()

    def tx_fn(tx):
        c = tx.get(embudo.ruta(sesion_id, id_persona))
        if not c:
            return
        c["ventanaServicioHasta"] = ahora + dt.timedelta(hours=whatsapp.VENTANA_SERVICIO_HORAS)
        # No se guarda qué escribió: puede traer cualquier cosa. Se avisa que
        # hay que mirarlo en el teléfono.
        c["respuestaPendienteRevision"] = True
        tx.set(embudo.ruta(sesion_id, id_persona), c)

    ctx.store.transaccion(tx_fn)


def procesar_webhook(ctx, cuerpo):
    procesados = []
    for evento in whatsapp.interpretar_webhook(cuerpo):
        if evento["tipo"] == "respuesta":
            p = evento["payload"]
            try:
                id_persona = util.validar_id_persona(p["idPersona"])
            except Exception:  # noqa: BLE001
                continue
            if p["respuesta"] not in ("si", "no"):
                continue
            procesados.append(_respuesta(ctx, p["sesionId"], id_persona, p["respuesta"] == "si"))
        elif evento["tipo"] == "texto":
            ref = ctx.store.get(f"mensajeWa/{evento['contextoId']}") if evento.get("contextoId") else None
            if not ref:
                continue
            if evento["afirmativo"] is None:
                _marcar_revision(ctx, ref["sesionId"], ref["idPersona"])
                procesados.append({"revision": True})
            else:
                procesados.append(_respuesta(ctx, ref["sesionId"], ref["idPersona"], evento["afirmativo"]))
        elif evento["tipo"] == "estado" and evento.get("estado") == "failed":
            ref = ctx.store.get(f"mensajeWa/{evento['wamid']}") if evento.get("wamid") else None
            if ref:
                _degradar(ctx, ref["sesionId"], ref["idPersona"],
                          f"Entrega fallida: {evento.get('error') or 'sin detalle'}")
                procesados.append({"degradado": True})
    return {"procesados": len(procesados)}
