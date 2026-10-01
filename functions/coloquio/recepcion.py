"""R1.7 — Recepción y verificación de identidad. Pantalla pensada para teléfono.

**Cómo se identifica a alguien sin PII en COLOQUIO.** Cada convocado tiene un
**código de convocatoria** (6 caracteres del `id_persona`) que se le da al
invitarlo —el guion y los mensajes de WhatsApp lo incluyen— y que dice al
llegar. El coordinador lo busca y marca la llegada. Si hace falta más, puede
pedir el celular a la bóveda (auditado) y compararlo con el de la persona.

* Llegada de alguien **confirmado** → `asistió`, con hora y quién verificó.
* Alguien que se presenta **sin estar confirmado** → se señala antes de
  dejarlo entrar (409 `requiere_anulacion`); aceptarlo requiere una anulación
  registrada con motivo.
* Toda asistencia deja un **compromiso de incentivo** con el regalo por
  defecto de la sesión (R1.10).
"""

from . import configuracion, embudo, incentivos, modelo, sesiones, util
from .errores import Conflicto, DatosInvalidos, NoEncontrado, RequiereAnulacion

VISIBLES = {modelo.ACEPTO, modelo.CONFIRMADO, modelo.ASISTIO}


def ruta(sesion_id, id_persona):
    return f"sesion/{sesion_id}/asistencia/{id_persona}"


def lista(ctx, sesion_id):
    sesion = sesiones.exigir(ctx.store, sesion_id)
    convs = embudo.convocatorias(ctx.store, sesion_id)
    asist = {d["idPersona"]: d for _, d in ctx.store.listar(f"sesion/{sesion_id}/asistencia")}
    items = []
    for c in convs:
        items.append({
            "idPersona": c["idPersona"],
            "codigo": util.codigo_de(c["idPersona"]),
            "segmento": c["segmento"],
            "estado": c["estado"],
            "etiqueta": modelo.ETIQUETAS[c["estado"]],
            "confirmado": c["estado"] == modelo.CONFIRMADO,
            "llegoEn": (asist.get(c["idPersona"]) or {}).get("llegoEn"),
            "esperado": c["estado"] in VISIBLES,
        })
    items.sort(key=lambda i: (not i["esperado"], i["estado"] == modelo.ASISTIO, i["codigo"]))
    presentes = sum(1 for i in items if i["estado"] == modelo.ASISTIO)
    confirmados = sum(1 for i in items if i["estado"] in (modelo.CONFIRMADO, modelo.ASISTIO))
    return {
        "sesion": {"id": sesion_id, "nombre": sesion.get("nombre"), "fecha": sesion.get("fecha"),
                   "lugar": sesion.get("lugar"), "estado": sesion.get("estado"),
                   "cupoObjetivo": sesion.get("cupoObjetivo")},
        "presentes": presentes,
        "confirmados": confirmados,
        "cupoObjetivo": sesion.get("cupoObjetivo"),
        "items": items,
    }


def _resolver_persona(convs, cuerpo):
    if cuerpo.get("idPersona"):
        return util.validar_id_persona(cuerpo["idPersona"])
    codigo = str(cuerpo.get("codigo") or "").strip().upper().replace("-", "")
    if not codigo:
        raise DatosInvalidos("Indicá el código de convocatoria.")
    coinciden = [c["idPersona"] for c in convs if util.codigo_de(c["idPersona"]) == codigo]
    if not coinciden:
        raise NoEncontrado(
            f"El código {codigo} no está en el embudo de esta sesión. No dejes pasar a "
            "nadie sin verificar: puede ser de otra sesión.")
    if len(coinciden) > 1:
        raise Conflicto("Ese código coincide con más de una persona: elegí de la lista.")
    return coinciden[0]


def registrar(ctx, actor, sesion_id, cuerpo):
    convs0 = embudo.convocatorias(ctx.store, sesion_id)
    id_persona = _resolver_persona(convs0, cuerpo)
    motivo = str((cuerpo.get("anulacion") or {}).get("motivo") or "").strip()
    ahora = ctx.ahora()
    regalo_por_defecto = None

    sesion0 = sesiones.exigir(ctx.store, sesion_id)
    if sesion0.get("regaloId"):
        regalo_por_defecto = configuracion.regalo(ctx.store, sesion0["regaloId"])

    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        if sesion.get("estado") not in modelo.SESION_ABIERTA:
            raise Conflicto(f"La sesión está {sesion.get('estado')}: no admite check-in.")
        conv = tx.get(embudo.ruta(sesion_id, id_persona))
        estudio = tx.get(f"estudio/{sesion['estudioId']}")
        if not conv:
            raise NoEncontrado("Esa persona no está en el embudo de esta sesión.")
        if conv["estado"] == modelo.ASISTIO:
            raise Conflicto(f"{util.codigo_de(id_persona)} ya figura como presente.")
        anulacion = None
        if conv["estado"] == modelo.CONFIRMADO:
            embudo.aplicar(sesion, conv, modelo.ASISTIO, conv.get("canal") or "manual",
                           actor.uid, ahora, resultado="check_in")
        else:
            if not motivo:
                raise RequiereAnulacion(
                    f"{util.codigo_de(id_persona)} no está confirmado para esta sesión "
                    f"(estado: {modelo.ETIQUETAS[conv['estado']]}). Para dejarlo entrar "
                    "hay que registrar una anulación con motivo.",
                    {"idPersona": id_persona, "estado": conv["estado"],
                     "codigo": util.codigo_de(id_persona)})
            anulacion = {"regla": "no_confirmado", "motivo": motivo, "actorUid": actor.uid,
                         "ts": ahora, "estadoPrevio": conv["estado"]}
            embudo.aplicar_forzado(sesion, conv, modelo.ASISTIO, conv.get("canal") or "manual",
                                   actor.uid, ahora, motivo, anulacion)
        asistencia = {"idPersona": id_persona, "llegoEn": ahora, "verificadaPor": actor.uid,
                      "modalidad": sesion.get("modalidad", "presencial"),
                      "verificacion": "codigo" if cuerpo.get("codigo") else "lista",
                      "anulacion": anulacion}
        inc = incentivos.nuevo(id_persona, regalo_por_defecto, ahora)
        incentivos.sumar_valor(sesion, inc["valor"])
        incentivos.sumar_valor(estudio, inc["valor"])
        tx.set(embudo.ruta(sesion_id, id_persona), conv)
        tx.set(ruta(sesion_id, id_persona), asistencia)
        tx.set(incentivos.ruta(sesion_id, id_persona), inc)
        tx.update(f"sesion/{sesion_id}", {**embudo._campos_sesion(sesion),
                                          "valorComprometido": sesion["valorComprometido"]})
        tx.update(f"estudio/{sesion['estudioId']}", {"valorComprometido": estudio["valorComprometido"]})
        presentes = int(sesion["conteo"].get(modelo.ASISTIO) or 0)
        return {"asistencia": asistencia, "codigo": util.codigo_de(id_persona),
                "presentes": presentes, "cupoObjetivo": sesion.get("cupoObjetivo"),
                "conAnulacion": bool(anulacion)}

    return ctx.store.transaccion(tx_fn)
