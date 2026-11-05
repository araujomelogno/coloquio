"""El Definition of Done de la Fase 1 (SPEC §11), de punta a punta, en memoria.

Un focus group presencial entero: estudio y pauta, selección mixta con
evidencia e historial, gate de consentimiento forzado, fatiga con anulación,
convocatoria por los dos canales, caída con reemplazo del mismo segmento y el
caso sin candidatos, recepción de ocho, cierre, baja en cascada sin rastro y
auditoría de PII del store.
"""

import datetime as dt

import pytest

import fabrica
from coloquio import cascada, modelo, pii, util, whatsapp
from coloquio.errores import (
    Conflicto, ContactoRechazado, FugaDePII, RequiereAnulacion, TransicionInvalida,
)


def _embudo(api, sid):
    return api("GET", f"/cuali/sesiones/{sid}/embudo")


def _conv(api, sid, pid):
    return next(c for c in _embudo(api, sid)["convocatorias"] if c["idPersona"] == pid)


def _llenar_sesion(api, sid, filtros=None):
    """Selección demográfica + incorporación + lista de invitación propuesta."""
    sel = api("POST", f"/cuali/sesiones/{sid}/candidatos",
              {"modo": "demografica", "filtros": filtros or {"tramoEtario": ["25-34", "35-44"]}})
    ids = [c["idPersona"] for c in sel["candidatos"]]
    api("POST", f"/cuali/sesiones/{sid}/convocatorias", {"candidatos": ids})
    propuesta = api("GET", f"/cuali/sesiones/{sid}/invitacion")
    api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": propuesta["propuestos"]})
    return propuesta


def _confirmar(api, sid, pid):
    api("PATCH", f"/cuali/convocatorias/{sid}/{pid}", {"a": "acepto"})
    api("PATCH", f"/cuali/convocatorias/{sid}/{pid}", {"a": "confirmado"})


# ── 1 · Estudio, pauta y sesión ────────────────────────────────────

def test_sesion_sin_pauta_no_se_abre(api):
    e = api("POST", "/cuali/estudios", {"nombre": "Sin pauta", "categoria": "banca"})
    assert util.validar_id_persona(e["refEstudio"])  # emite un uuid
    with pytest.raises(Conflicto, match="pauta"):
        api("POST", "/cuali/sesiones", {"estudioId": e["id"], "fecha": "2026-10-10T19:00",
                                        "lugar": "Sala", "cupoObjetivo": 8})


def test_pauta_versionada(api, sesion):
    eid = sesion["estudio"]["id"]
    api("POST", f"/cuali/estudios/{eid}/pauta", {"topicos": [{"titulo": "Nuevo", "minutos": 20}]})
    e = api("GET", f"/cuali/estudios/{eid}")
    assert e["pautaActiva"]["version"] == 2
    assert [v["activa"] for v in e["versionesPauta"]] == [True, False]
    assert sesion["pautaVersion"] == 1  # la sesión quedó atada a la versión con que se abrió


# ── 2 · Selección mixta con evidencia e historial ──────────────────

def test_demografica_no_toca_el_motor(api, ctx, sesion):
    r = api("POST", f"/cuali/sesiones/{sesion['id']}/candidatos",
            {"modo": "demografica", "filtros": {"sexo": ["F"]}})
    assert r["abrioSemantica"] is False and ctx.motor.llamadas == 0
    assert r["candidatos"] and all(c["segmento"]["sexo"] == "F" for c in r["candidatos"])


def test_mixta_con_evidencia_e_historial(api, ctx, sesion):
    r = api("POST", f"/cuali/sesiones/{sesion['id']}/candidatos",
            {"modo": "mixta", "filtros": {"sexo": ["M"]}, "criterios": ["toma cerveza artesanal"]})
    assert r["abrioSemantica"] is True and ctx.motor.llamadas == 1
    primero = r["candidatos"][0]
    assert primero["segmento"]["sexo"] == "M"
    assert "cerveza" in primero["evidencia"][0]["respuesta"].lower()
    assert primero["evidencia"][0]["estudio"]
    assert "historial" in primero and primero["historial"]["total"] == 0


def test_motor_caido_degrada_y_lo_dice(api, ctx, sesion):
    ctx.motor.falla = "paneles no responde"
    r = api("POST", f"/cuali/sesiones/{sesion['id']}/candidatos",
            {"modo": "semantica", "criterios": ["cerveza"]})
    assert r["degradaciones"] and "paneles no responde" in r["degradaciones"][0]["motivo"]
    assert r["candidatos"]  # sigue pudiendo convocar


# ── 3 · Gate de consentimiento: intentar forzarlo ──────────────────

def test_nadie_sin_consentimiento_aparece_ni_entra(api, ctx, sesion):
    sin = [pid for pid, p in ctx.bov.personas.items() if not p["consiente"]]
    assert sin
    r = api("POST", f"/cuali/sesiones/{sesion['id']}/candidatos",
            {"modo": "semantica", "criterios": ["cerveza artesanal amigos vino mate"], "limite": 500})
    vistos = {c["idPersona"] for c in r["candidatos"] + r["excluidosPorFatiga"]}
    assert not vistos & set(sin)
    assert r["descartadosPorGate"] > 0  # el motor los rankeó; la vista los sacó
    # Forzarlo por la API de incorporación:
    res = api("POST", f"/cuali/sesiones/{sesion['id']}/convocatorias", {"candidatos": sin[:2]})
    assert res["incorporados"] == [] and set(res["sinConsentimientoVigente"]) == set(sin[:2])
    # Y el contacto tampoco sale:
    with pytest.raises(ContactoRechazado):
        ctx.bov.contacto(sin[0], "celular", "coordinadora@equipos.com.uy")


def test_consentimiento_de_ambito_estudio_no_entra_ni_para_su_estudio(api, ctx, sesion):
    """`boveda/0021`: `finalidades` solo lista consentimientos con `ref_estudio
    is null`. Un contacto_participacion de ámbito estudio no habilita a nadie,
    tampoco en el estudio que lo otorgó: el doble no puede ser más generoso que
    la vista, o las pruebas pasan y producción no."""
    pid = fabrica.id_de(1)
    ctx.bov.personas[pid]["refEstudio"] = sesion["estudio"]["refEstudio"]
    assert pid not in {b["idPersona"] for b in ctx.bov.convocables()}
    assert ctx.bov.convocables(ids=[pid]) == []
    r = api("POST", f"/cuali/sesiones/{sesion['id']}/candidatos",
            {"modo": "demografica", "filtros": {}, "limite": 500})
    assert pid not in {c["idPersona"] for c in r["candidatos"] + r["excluidosPorFatiga"]}
    res = api("POST", f"/cuali/sesiones/{sesion['id']}/convocatorias", {"candidatos": [pid]})
    assert res["incorporados"] == [] and res["sinConsentimientoVigente"] == [pid]
    # Las funciones de la 0016 preguntan a la misma vista.
    from coloquio.errores import ConvocatoriaRechazada
    with pytest.raises(ConvocatoriaRechazada):
        ctx.bov.declarar_convocatoria(pid, sesion["id"], ctx.ahora() + dt.timedelta(days=5))
    with pytest.raises(ContactoRechazado):
        ctx.bov.contacto(pid, "celular", "coordinadora@equipos.com.uy")


# ── 4 · Filtro de fatiga con anulación registrada ──────────────────

def test_fatiga_excluye_y_la_anulacion_queda_registrada(api, ctx, sesion):
    pid = fabrica.id_de(4)
    api("POST", "/cuali/historico", {"categoria": "bebidas", "fecha": "2026-06-01T19:00",
                                     "idPersonas": [pid], "etiqueta": "Grupo cerveza 2026"})
    r = api("POST", f"/cuali/sesiones/{sesion['id']}/candidatos", {"modo": "demografica"})
    excluido = next(c for c in r["excluidosPorFatiga"] if c["idPersona"] == pid)
    assert excluido["fatiga"]["motivos"][0]["regla"] == "categoria"
    with pytest.raises(RequiereAnulacion):
        api("POST", f"/cuali/sesiones/{sesion['id']}/convocatorias", {"candidatos": [pid]})
    res = api("POST", f"/cuali/sesiones/{sesion['id']}/convocatorias",
              {"candidatos": [pid], "anulacion": {"motivo": "Perfil muy difícil de conseguir"}})
    assert res["conAnulacion"] == [pid]
    conv = _conv(api, sesion["id"], pid)
    assert conv["anulacion"]["motivo"] == "Perfil muy difícil de conseguir"
    assert conv["anulacion"]["actorUid"] == "u-coord"
    m = _embudo(api, sesion["id"])["metricas"]
    assert m["anulacionesFatiga"] == 1 and m["reconvocatoriasBloqueadas"] == 1


def test_umbral_de_fatiga_configurable(api, sesion):
    pid = fabrica.id_de(4)
    api("POST", "/cuali/historico", {"categoria": "bebidas", "fecha": "2026-06-01T19:00",
                                     "idPersonas": [pid]})
    api("PUT", "/cuali/config/fatiga", {"ventanaDias": 60, "maxPorCategoria": 1,
                                        "ventanaGlobalDias": 365, "maxGlobal": 3})
    r = api("POST", f"/cuali/sesiones/{sesion['id']}/candidatos", {"modo": "demografica"})
    assert pid in {c["idPersona"] for c in r["candidatos"]}


def test_dos_sesiones_del_mismo_estudio_no(api, sesion):
    otra = api("POST", "/cuali/sesiones", {
        "estudioId": sesion["estudio"]["id"], "fecha": "2026-10-09T19:00", "lugar": "Sala",
        "cupoObjetivo": 8})
    pid = fabrica.id_de(1)
    api("POST", f"/cuali/sesiones/{sesion['id']}/convocatorias", {"candidatos": [pid]})
    res = api("POST", f"/cuali/sesiones/{otra['id']}/convocatorias", {"candidatos": [pid]})
    assert res["incorporados"] == [] and res["enOtraSesionDelEstudio"][0]["sesionId"] == sesion["id"]


# ── 5 · Embudo por los dos canales ─────────────────────────────────

def test_embudo_manual_y_whatsapp(api, ctx, sesion):
    sid = sesion["id"]
    propuesta = _llenar_sesion(api, sid)
    assert len(propuesta["propuestos"]) == 12  # 8 × 1.5
    assert "33%" in propuesta["supuesto"]
    manual, wa = propuesta["propuestos"][:6], propuesta["propuestos"][6:]

    # Manual: contacto puntual, auditado con el email humano, no persistido.
    c = api("GET", f"/cuali/convocatorias/{sid}/{manual[0]}/contacto", consulta={"canal": "celular"})
    assert c["dato"].startswith("099") and util.codigo_de(manual[0]) in c["guion"]
    assert ctx.bov.auditoria[-1]["actor"] == "coordinadora@equipos.com.uy"
    assert c["dato"] not in str(ctx.store.todos())
    for pid in manual:
        _confirmar(api, sid, pid)  # atajo: invitado → contactado → aceptó

    # WhatsApp: plantilla con botones cuyo payload es el id, no el teléfono.
    for pid in wa:
        api("POST", f"/cuali/convocatorias/{sid}/{pid}/canal", {"canal": "whatsapp"})
        r = api("POST", f"/cuali/convocatorias/{sid}/{pid}/whatsapp", {"tipo": "invitacion"})
        assert r["enviado"] and r["pago"]
    envio = ctx.canal_wa.enviados[0]
    assert envio["botones"][0] == whatsapp.payload(sid, wa[0], "si")
    assert not any(p["celular"] in str(ctx.store.todos()) for p in ctx.bov.personas.values())

    # Respuesta «sí» por botón → aceptó, y se abre la ventana de servicio.
    webhook = {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "59899000000", "profile": {"name": "NO GUARDAR"}}],
        "messages": [{"type": "button", "context": {"id": envio["wamid"]},
                      "button": {"payload": whatsapp.payload(sid, wa[0], "si")}}]}}]}]}
    api("POST", "/cuali/webhooks/whatsapp", webhook)
    conv = _conv(api, sid, wa[0])
    assert conv["estado"] == modelo.ACEPTO and conv["ventanaServicioHasta"]
    assert "NO GUARDAR" not in str(ctx.store.todos()) and "59899000000" not in str(ctx.store.todos())

    # La confirmación cae en la ventana: mensaje libre, no plantilla paga.
    r = api("POST", f"/cuali/convocatorias/{sid}/{wa[0]}/whatsapp", {"tipo": "confirmacion"})
    assert r["enviado"] and r["pago"] is False and r["enVentana"]
    api("POST", "/cuali/webhooks/whatsapp", {"entry": [{"changes": [{"value": {"messages": [
        {"type": "interactive", "interactive": {"button_reply": {
            "id": whatsapp.payload(sid, wa[0], "si")}}}]}}]}]})
    assert _conv(api, sid, wa[0])["estado"] == modelo.CONFIRMADO

    # Entrega fallida → degrada a manual conservando el estado.
    estado_antes = _conv(api, sid, wa[1])["estado"]
    api("POST", "/cuali/webhooks/whatsapp", {"entry": [{"changes": [{"value": {"statuses": [
        {"id": ctx.canal_wa.enviados[1]["wamid"], "status": "failed",
         "errors": [{"title": "Número bloqueado"}]}]}}]}]})
    conv = _conv(api, sid, wa[1])
    assert conv["canal"] == "manual" and conv["estado"] == estado_antes
    assert "bloqueado" in conv["degradacion"]["motivo"]

    # Plantilla rechazada al enviar → también degrada.
    ctx.canal_wa.falla = "Plantilla rechazada por Meta"
    r = api("POST", f"/cuali/convocatorias/{sid}/{wa[2]}/whatsapp", {"tipo": "recordatorio"})
    assert r["degradado"] and _conv(api, sid, wa[2])["canal"] == "manual"

    vista = _embudo(api, sid)
    canales_confirmados = vista["metricas"]
    assert canales_confirmados["confirmaciones_manual"] == 6
    assert canales_confirmados["confirmaciones_whatsapp"] == 1
    assert vista["cuota"]["confirmados"] == 7


def test_transiciones_invalidas_y_terminales(api, sesion):
    sid = sesion["id"]
    propuesta = _llenar_sesion(api, sid)
    pid = propuesta["propuestos"][0]
    with pytest.raises(TransicionInvalida):
        api("PATCH", f"/cuali/convocatorias/{sid}/{pid}", {"a": "asistio"})
    api("PATCH", f"/cuali/convocatorias/{sid}/{pid}", {"a": "rechazo"})
    with pytest.raises(TransicionInvalida):
        api("PATCH", f"/cuali/convocatorias/{sid}/{pid}", {"a": "contactado"})
    api("POST", f"/cuali/convocatorias/{sid}/{pid}/reingreso", {"motivo": "Llamó para decir que sí puede"})
    conv = _conv(api, sid, pid)
    assert conv["estado"] == modelo.INVITADO
    ultimo = conv["eventos"][-1]
    assert ultimo["de"] == "rechazo" and ultimo["actor"] == "u-coord" and ultimo["canal"] == "manual"


def test_cupo_alcanzado_avisa(api, sesion):
    sid = sesion["id"]
    propuesta = _llenar_sesion(api, sid)
    for pid in propuesta["propuestos"][:8]:
        _confirmar(api, sid, pid)
    vista = _embudo(api, sid)
    assert vista["cuota"]["cupoAlcanzado"] and vista["sesion"]["estado"] == modelo.CONFIRMADA
    assert vista["sesion"]["metricas"]["cupoConfirmadoEn"]


# ── 6 · Reemplazo del mismo segmento, y el caso sin candidatos ─────

def test_reemplazo_restituye_el_segmento(api, sesion):
    sid = sesion["id"]
    propuesta = _llenar_sesion(api, sid)
    for pid in propuesta["propuestos"][:8]:
        _confirmar(api, sid, pid)
    caido = propuesta["propuestos"][0]
    api("PATCH", f"/cuali/convocatorias/{sid}/{caido}", {"a": "se_cayo"})
    vista = _embudo(api, sid)
    assert vista["pendientesDeReemplazo"][0]["idPersona"] == caido
    seg = _conv(api, sid, caido)["segmento"]

    p = api("POST", f"/cuali/sesiones/{sid}/reemplazo", {"idPersona": caido})
    assert not p["sinReemplazo"] and p["propuestos"]
    for cand in p["propuestos"]:
        assert all(cand["segmento"][d] == seg[d] for d in p["dimensionesConCuota"])

    elegido = p["propuestos"][0]["idPersona"]
    api("POST", f"/cuali/sesiones/{sid}/reemplazo/resolver",
        {"accion": "reemplazar", "idPersona": caido, "reemplazo": elegido})
    assert _conv(api, sid, caido)["estado"] == modelo.REEMPLAZADO
    nuevo = _conv(api, sid, elegido)
    assert nuevo["estado"] == modelo.INVITADO and nuevo["esReemplazoDe"] == caido


def test_sin_candidatos_lo_informa_y_registra_la_salida(api, ctx, sesion):
    sid = sesion["id"]
    # Una sola persona de 25-34 en todo el panel: no hay con qué reemplazarla.
    pid = fabrica.id_de(3)
    ctx.bov.personas = {pid: ctx.bov.personas[pid]}
    api("POST", f"/cuali/sesiones/{sid}/convocatorias", {"candidatos": [pid]})
    api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": [pid]})
    _confirmar(api, sid, pid)
    api("PATCH", f"/cuali/convocatorias/{sid}/{pid}", {"a": "se_cayo"})

    p = api("POST", f"/cuali/sesiones/{sid}/reemplazo", {"idPersona": pid})
    assert p["sinReemplazo"] and "Ningún candidato" in p["mensaje"]
    assert {o["salida"] for o in p["opciones"]} == {"bajar_cupo", "correr_fecha", "aceptar_incompleta"}

    api("POST", f"/cuali/sesiones/{sid}/reemplazo/resolver",
        {"accion": "sin_reemplazo", "idPersona": pid, "salida": "bajar_cupo"})
    s = api("GET", f"/cuali/sesiones/{sid}")
    assert s["cupoObjetivo"] == 7
    decision = s["decisionesCuota"][-1]
    assert decision["salida"] == "bajar_cupo" and decision["actorUid"] == "u-coord"


def test_reemplazo_que_rompe_la_cuota_exige_aceptarlo(api, sesion):
    sid = sesion["id"]
    propuesta = _llenar_sesion(api, sid)
    caido = propuesta["propuestos"][0]
    _confirmar(api, sid, caido)
    api("PATCH", f"/cuali/convocatorias/{sid}/{caido}", {"a": "se_cayo"})
    seg = _conv(api, sid, caido)["segmento"]
    distinto = next(c for c in _embudo(api, sid)["convocatorias"]
                    if c["estado"] == "candidato" and c["segmento"]["sexo"] != seg["sexo"])
    with pytest.raises(Conflicto, match="no restituye"):
        api("POST", f"/cuali/sesiones/{sid}/reemplazo/resolver",
            {"accion": "reemplazar", "idPersona": caido, "reemplazo": distinto["idPersona"]})
    r = api("POST", f"/cuali/sesiones/{sid}/reemplazo/resolver",
            {"accion": "reemplazar", "idPersona": caido, "reemplazo": distinto["idPersona"],
             "aceptarCuotaIncompleta": True})
    assert "sexo" in r["rompeCuota"]
    assert api("GET", f"/cuali/sesiones/{sid}")["decisionesCuota"][-1]["salida"] == "reemplazo_rompe_cuota"


# ── 7 y 8 · Recepción de ocho y cierre ─────────────────────────────

def _sesion_confirmada(api, sid, n=9):
    propuesta = _llenar_sesion(api, sid)
    for pid in propuesta["propuestos"][:n]:
        _confirmar(api, sid, pid)
    return propuesta["propuestos"]


def test_recepcion_y_cierre(api, ctx, sesion):
    sid = sesion["id"]
    ids = _sesion_confirmada(api, sid)
    # Ocho llegan; se los busca por código, como desde el teléfono.
    for pid in ids[:8]:
        r = api("POST", f"/cuali/sesiones/{sid}/asistencias", {"codigo": util.codigo_de(pid)})
    assert r["presentes"] == 8
    with pytest.raises(Conflicto, match="ya figura"):
        api("POST", f"/cuali/sesiones/{sid}/asistencias", {"idPersona": ids[0]})
    # Alguien que se presenta sin estar confirmado → se señala.
    no_conf = ids[10]
    with pytest.raises(RequiereAnulacion):
        api("POST", f"/cuali/sesiones/{sid}/asistencias", {"idPersona": no_conf})
    r = api("POST", f"/cuali/sesiones/{sid}/asistencias",
            {"idPersona": no_conf, "anulacion": {"motivo": "Vino con la invitación impresa"}})
    assert r["conAnulacion"]
    lista = api("GET", f"/cuali/sesiones/{sid}/recepcion")
    assert lista["presentes"] == 9

    # Incentivos comprometidos por asistencia; asignar y entregar.
    inc = api("GET", f"/cuali/sesiones/{sid}/incentivos")
    assert len(inc["items"]) == 9 and inc["totales"]["comprometido"] == 9 * 1500
    otro = api("POST", "/cuali/regalos", {"nombre": "Canasta", "valor": 2000})
    api("PATCH", f"/cuali/incentivos/{sid}/{ids[0]}", {"regaloId": otro["id"]})
    api("POST", f"/cuali/incentivos/{sid}/{ids[0]}/entrega")
    inc = api("GET", f"/cuali/sesiones/{sid}/incentivos")
    assert inc["totales"]["comprometido"] == 8 * 1500 + 2000 and inc["totales"]["entregados"] == 1
    assert api("GET", f"/cuali/estudios/{sesion['estudio']['id']}/incentivos")["valorComprometido"] == 14000

    # Cierre: el confirmado que no vino es no-show; participación escrita.
    r = api("POST", f"/cuali/sesiones/{sid}/cerrar", {"notasSesion": "Buena dinámica grupal."})
    assert r["noShows"] == [ids[8]] and r["participacionesEscritas"] == 9
    assert r["showRate"] == round(9 / 10, 4)
    h = api("GET", f"/cuali/personas/{ids[0]}/historial")
    assert h["total"] == 1 and h["porCategoria"]["bebidas"]["total"] == 1
    assert h["sesiones"][0]["estudioNombre"] == "Cervezas 2026"

    # La próxima selección de la misma categoría ya lo excluye.
    e2 = api("POST", "/cuali/estudios", {"nombre": "Aguas saborizadas", "categoria": "bebidas"})
    api("POST", f"/cuali/estudios/{e2['id']}/pauta", {"topicos": [{"titulo": "Uso", "minutos": 30}]})
    s2 = api("POST", "/cuali/sesiones", {"estudioId": e2["id"], "fecha": "2026-11-01T19:00",
                                         "lugar": "Sala", "cupoObjetivo": 8})
    sel = api("POST", f"/cuali/sesiones/{s2['id']}/candidatos", {"modo": "demografica", "limite": 500})
    assert ids[0] in {c["idPersona"] for c in sel["excluidosPorFatiga"]}
    tab = api("GET", "/cuali/tablero")
    assert tab["sesionesRealizadas"] == 1 and tab["showRatePromedio"] == 0.9

    # Y la consistencia de los agregados se sostiene.
    assert api("POST", "/cuali/cumplimiento/consistencia")["consistente"]


def test_notas_de_sesion_no_admiten_pii(api, sesion):
    sid = sesion["id"]
    ids = _sesion_confirmada(api, sid, n=1)
    api("POST", f"/cuali/sesiones/{sid}/asistencias", {"idPersona": ids[0]})
    from coloquio.errores import DatosInvalidos

    with pytest.raises(DatosInvalidos, match="dato personal"):
        api("POST", f"/cuali/sesiones/{sid}/cerrar",
            {"notasSesion": "La señora de Pocitos, cel 099 123 456, habló mucho"})


# ── 9 · Baja en cascada, sin rastro ────────────────────────────────

def test_baja_en_cascada_borra_todo_y_confirma(api, ctx, sesion):
    sid = sesion["id"]
    ids = _sesion_confirmada(api, sid)
    for pid in ids[:8]:
        api("POST", f"/cuali/sesiones/{sid}/asistencias", {"idPersona": pid})
    api("POST", f"/cuali/sesiones/{sid}/cerrar", {})
    victima = ids[0]
    assert cascada.rastro(ctx, victima)  # hay datos antes

    ctx.bov.dar_de_baja(victima)
    r = api("POST", "/cuali/cumplimiento/cascada")
    assert r["confirmados"] == 1 and r["errores"] == 0
    assert (victima, "total") in ctx.bov.confirmados and not ctx.bov.pendientes
    assert cascada.rastro(ctx, victima) == []
    assert victima not in str(ctx.store.todos())
    assert util.codigo_de(victima) not in str(ctx.store.todos())
    assert api("POST", "/cuali/cumplimiento/consistencia")["consistente"]


def test_baja_en_embudo_activo_dispara_reemplazo(api, ctx, sesion):
    sid = sesion["id"]
    ids = _sesion_confirmada(api, sid, n=8)
    victima = ids[2]
    seg = _conv(api, sid, victima)["segmento"]
    ctx.bov.dar_de_baja(victima)
    api("POST", "/cuali/cumplimiento/cascada")
    vista = _embudo(api, sid)
    assert victima not in {c["idPersona"] for c in vista["convocatorias"]}
    alerta = vista["alertasBaja"][0]
    assert alerta["segmento"] == seg and alerta["estadoPrevio"] == "confirmado"
    assert vista["sesion"]["estado"] == modelo.CONVOCANDO  # ya no alcanza el cupo
    p = api("POST", f"/cuali/sesiones/{sid}/reemplazo", {"alertaId": alerta["id"]})
    assert p["propuestos"]
    api("POST", f"/cuali/sesiones/{sid}/reemplazo/resolver",
        {"accion": "reemplazar", "alertaId": alerta["id"], "reemplazo": p["propuestos"][0]["idPersona"]})
    assert not _embudo(api, sid)["alertasBaja"]


def test_borrado_fallido_no_se_confirma(api, ctx, sesion, monkeypatch):
    sid = sesion["id"]
    ids = _sesion_confirmada(api, sid, n=1)
    ctx.bov.dar_de_baja(ids[0])

    def falla(*a, **k):
        raise RuntimeError("Firestore no disponible")

    monkeypatch.setattr(cascada, "_borrar_de_sesion", falla)
    r = api("POST", "/cuali/cumplimiento/cascada")
    assert r["confirmados"] == 0 and r["errores"] == 1
    assert (ids[0], "total") in ctx.bov.pendientes  # queda abierto para reintento
    assert ctx.bov.pendientes[(ids[0], "total")]["intentos"] == 1


# ── 10 · Auditoría de PII del store ────────────────────────────────

def test_auditoria_del_store_sin_pii(api, ctx, sesion):
    test_recepcion_y_cierre(api, ctx, sesion)
    for ruta, doc in ctx.store.todos().items():
        assert pii.hallazgos(doc, ruta.split("/")[0]) == [], ruta
    contactos = [p["celular"] for p in ctx.bov.personas.values()] + \
                [p["email"] for p in ctx.bov.personas.values()]
    volcado = str(ctx.store.todos())
    assert not any(c in volcado for c in contactos)


def test_el_store_rechaza_pii(ctx):
    with pytest.raises(FugaDePII):
        ctx.store.set("sesion/x/convocatoria/y", {"estado": "invitado", "celular": "099"})
    with pytest.raises(FugaDePII):
        ctx.store.set("participacionCuali/y", {"fechaNacimiento": "1980-01-01"})
    with pytest.raises(FugaDePII):
        ctx.store.transaccion(lambda tx: tx.set("sesion/x", {"notasSesion": "mail a@b.com"}))


# ── 11 · Cero escrituras en la bóveda fuera de la superficie ───────

def test_boveda_solo_superficie_fase5():
    import pathlib
    import re

    fuente = (pathlib.Path(__file__).parent.parent / "coloquio" / "boveda.py").read_text()
    clase = fuente[fuente.index("class BovedaPostgres"):fuente.index("class BovedaMemoria")]
    sql = " ".join(re.findall(r'"([^"]*)"', clase)).lower()
    permitidos = {"v_persona_convocable", "contacto_para_convocatoria", "mis_borrados_pendientes",
                  "declarar_convocatoria",
                  "confirmar_borrado", "reportar_error_de_borrado", "sistema_de_la_conexion"}
    for palabra in re.findall(r"\bfrom\s+([a-z_]+)", sql):
        assert palabra in permitidos, palabra
    # Y toda función que se ejecute es de la superficie (R5.2.a suma una).
    llamadas = set(re.findall(r"\bselect\s+([a-z_]+)\(", sql))
    assert "declarar_convocatoria" in llamadas
    assert llamadas <= permitidos, llamadas - permitidos
    for prohibido in ("insert ", "update ", "delete ", " persona ", "consentimiento ", "participacion "):
        assert prohibido not in sql, prohibido


def test_contacto_exige_actor_humano(ctx):
    with pytest.raises(Exception, match="email del usuario"):
        ctx.bov.contacto(fabrica.id_de(1), "celular", None)


def test_ahora_fijo(ctx):
    assert ctx.ahora() == dt.datetime(2026, 10, 1, 12, 0, tzinfo=dt.timezone.utc)


# ── R1.18 · Modo laxo y detalle de cumplimiento del criterio semántico ─

def _semantica(api, sid, criterios, **extra):
    return api("POST", f"/cuali/sesiones/{sid}/candidatos",
               {"modo": "semantica", "criterios": criterios, "limite": 500, **extra})


def _frase(ctx, pid):
    return ctx.motor.corpus[pid][0]["texto"]


def test_r118_sin_modo_corre_en_laxo_y_lo_dice(api, ctx, sesion):
    r = _semantica(api, sesion["id"], ["cerveza artesanal amigos"])
    assert ctx.motor.ultima["modo"] == "laxo"  # explícito: el default de paneles es estricto
    assert r["modoSemantico"] == "laxo"
    # Cada criterio semántico viaja con su `duro`.
    semanticos = [c for c in ctx.motor.ultima["criterios"] if c["tipo"] == "semantico"]
    assert semanticos == [{"tipo": "semantico", "texto": "cerveza artesanal amigos", "duro": False}]
    # Laxo: los dudosos están, marcados (antes desaparecían en silencio).
    assert any(c["penalizado"] for c in r["candidatos"])
    assert r["calidad"]["penalizados"] == sum(1 for c in r["candidatos"] if c["penalizado"])
    # Una demográfica no tiene modo semántico que mostrar.
    d = api("POST", f"/cuali/sesiones/{sesion['id']}/candidatos", {"modo": "demografica"})
    assert d["modoSemantico"] is None and d["calidad"] is None
    # `paneles` caído: degrada a demográfica pura (sin cambios) y no se
    # atribuye un modo a una lista que el motor no tocó.
    ctx.motor.falla = "paneles no responde"
    caido = _semantica(api, sesion["id"], ["cerveza"])
    assert caido["candidatos"] and caido["modoSemantico"] is None
    assert "paneles no responde" in caido["degradaciones"][0]["motivo"]


def test_r118_modo_semantico_invalido_se_rechaza(api, sesion):
    from coloquio.errores import DatosInvalidos
    with pytest.raises(DatosInvalidos, match="Modo semántico"):
        _semantica(api, sesion["id"], ["cerveza"], modoSemantico="mas_o_menos")


def test_r118_criterio_duro_en_laxo_deja_afuera_igual(api, ctx, sesion):
    sid = sesion["id"]
    blando = _semantica(api, sid, ["cerveza artesanal amigos", "vino tinto comidas"])
    assert blando["modoSemantico"] == "laxo"
    # Sin `duro`, quien solo habla de cerveza entra penalizado (sin evidencia de vino).
    assert any("vino" not in _frase(ctx, c["idPersona"]) for c in blando["candidatos"])

    duro = _semantica(api, sid, ["cerveza artesanal amigos", {"texto": "vino tinto comidas", "duro": True}])
    assert duro["modoSemantico"] == "laxo"
    assert {"tipo": "semantico", "texto": "vino tinto comidas", "duro": True} in ctx.motor.ultima["criterios"]
    assert duro["candidatos"] and all("vino" in _frase(ctx, c["idPersona"]) for c in duro["candidatos"])
    assert duro["excluidosSemanticos"]["porMotivo"]["sin_evidencia"] > 0

    # Un dudoso en el criterio duro también queda afuera en laxo; sin `duro`, entra marcado.
    vino = duro["candidatos"][0]["idPersona"]
    ctx.motor.veredictos[vino] = "dudoso"
    r = _semantica(api, sid, [{"texto": "vino tinto comidas", "duro": True}])
    assert vino not in {c["idPersona"] for c in r["candidatos"]}
    assert r["excluidosSemanticos"]["porMotivo"]["dudoso"] >= 1
    r = _semantica(api, sid, ["vino tinto comidas"])
    assert next(c for c in r["candidatos"] if c["idPersona"] == vino)["penalizado"] is True
    # Y `no_cumple` deja afuera en los dos modos, duro o no.
    ctx.motor.veredictos[vino] = "no_cumple"
    r = _semantica(api, sid, ["vino tinto comidas"])
    assert vino not in {c["idPersona"] for c in r["candidatos"]}
    assert r["excluidosSemanticos"]["porMotivo"]["no_cumple"] == 1


def test_r118_estricto_informa_excluidos_por_motivo(api, ctx, sesion):
    sid = sesion["id"]
    industrial = [pid for pid, rs in ctx.motor.corpus.items() if "industrial" in rs[0]["texto"]]
    artesanal = [pid for pid, rs in ctx.motor.corpus.items() if "artesanal" in rs[0]["texto"]]
    ctx.motor.veredictos[artesanal[0]] = "no_cumple"
    r = _semantica(api, sid, ["cerveza artesanal amigos"], modoSemantico="estricto")
    assert ctx.motor.ultima["modo"] == "estricto" and r["modoSemantico"] == "estricto"
    ex = r["excluidosSemanticos"]
    assert ex["porMotivo"] == {"no_cumple": 1, "dudoso": len(industrial), "sin_evidencia": 0}
    assert ex["total"] == 1 + len(industrial)
    assert r["candidatos"] and not any(c["penalizado"] for c in r["candidatos"])
    assert not {c["idPersona"] for c in r["candidatos"]} & set(industrial)


def test_r118_estricto_que_vacia_no_cae_a_demografica(api, ctx, sesion):
    """Si el estricto deja afuera a todos, la lista queda vacía y lo dice:
    caer a demográfica pura metería a los que el modo acaba de excluir."""
    r = _semantica(api, sesion["id"], ["cerveza artesanal amigos", "vino tinto comidas"],
                   modoSemantico="estricto")
    assert r["candidatos"] == [] and r["modoSemantico"] == "estricto"
    ex = r["excluidosSemanticos"]
    # Nadie habla de cerveza y de vino a la vez: todos afuera, por el primer
    # motivo que encontró (`dudoso` en el primer criterio le gana a la falta de
    # evidencia en el segundo, como en `paneles`).
    assert ex["total"] == len(ctx.motor.corpus) - sum(  # todos los que el recall encontró
        1 for rs in ctx.motor.corpus.values() if "mate" in rs[0]["texto"] or "azucaradas" in rs[0]["texto"])
    assert sum(ex["porMotivo"].values()) == ex["total"]
    assert ex["porMotivo"]["sin_evidencia"] > 0 and ex["porMotivo"]["dudoso"] > 0
    assert "estricto" in r["degradaciones"][-1]["motivo"]


def test_r118_dudoso_aparece_marcado_con_razon_y_evidencia(api, ctx, sesion):
    r = _semantica(api, sesion["id"], ["cerveza artesanal amigos"])
    dudoso = next(c for c in r["candidatos"] if "industrial" in _frase(ctx, c["idPersona"]))
    assert dudoso["penalizado"] is True and dudoso["confianzaBaja"] is True
    assert dudoso["verificacionIncompleta"] is False
    ev = dudoso["evidencia"][0]
    assert ev["veredicto"] == "dudoso" and ev["razon"]
    assert "industrial" in ev["respuesta"] and ev["estudio"] and ev["pregunta"]
    # El verificado, en cambio, entra limpio.
    bueno = next(c for c in r["candidatos"] if "artesanal" in _frase(ctx, c["idPersona"]))
    assert not (bueno["penalizado"] or bueno["confianzaBaja"] or bueno["verificacionIncompleta"])


def test_r118_verificacion_caida_no_es_dudoso(api, ctx, sesion):
    ctx.motor.verificacion_caida = True
    for modo in ("laxo", "estricto"):  # sin_verificar entra en los dos modos
        r = _semantica(api, sesion["id"], ["cerveza artesanal amigos"], modoSemantico=modo)
        assert r["candidatos"] and r["excluidosSemanticos"]["total"] == 0
        for c in r["candidatos"]:
            assert c["verificacionIncompleta"] is True and c["confianzaBaja"] is True
            assert c["penalizado"] is False  # nadie juzgó la evidencia: no es haber dudado
            assert {e["veredicto"] for e in c["evidencia"]} == {"sin_verificar"}
        assert r["calidad"]["sinVerificar"] == len(r["candidatos"])
        assert r["calidad"]["penalizados"] == 0


def test_r118_normalizar_no_descarta_lo_que_manda_paneles(monkeypatch):
    """El camino de producción: el cuerpo que sale a `POST /api/consultas` y
    la respuesta cruda de `paneles` (forma de `consultas._combinar`)."""
    import io
    import json

    from coloquio import motor

    crudo = {
        "modo": "estricto",
        "items": [{
            "id_persona": "p1", "estado": "pendiente", "puntaje": 0.7, "confianza": "baja",
            "penalizado": False, "verificacion_incompleta": True,
            "criterios": [
                {"tipo": "demografico", "criterio": "sexo", "veredicto": "cumple"},
                {"tipo": "semantico", "criterio": "toma cerveza", "veredicto": "sin_verificar",
                 "estado": "pendiente", "razon": "verificador caído",
                 "evidencia": {"valor_texto": "Tomo cerveza", "pregunta_texto": "¿Qué toma?",
                               "estudio": "Hábitos 2025", "fecha_campo": "2025-11-01"}}],
        }],
        "excluidos": [
            {"id_persona": "x1", "estado": "descartada", "criterio": "c", "motivo": "no_cumple"},
            {"id_persona": "x2", "estado": "descartada", "criterio": "c", "motivo": "dudoso"},
            {"id_persona": "x3", "estado": "descartada", "criterio": "c", "motivo": "sin_evidencia"},
            {"id_persona": "x4", "estado": "descartada", "criterio": "c", "motivo": "irrelevante"},
            {"id_persona": "x5", "estado": "descartada", "criterio": "c",
             "motivo": "sin_evidencia_pertinente"},
        ],
        "degradaciones": [],
    }
    enviado = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(pedido, timeout=None):
        enviado.update(json.loads(pedido.data.decode("utf-8")))
        return Resp(json.dumps(crudo).encode("utf-8"))

    monkeypatch.setattr(motor.urllib.request, "urlopen", urlopen)
    r = motor.MotorPanelesHttp("https://paneles.test/api").consultar(
        {"sexo": ["F"]}, [{"texto": "toma cerveza", "duro": True}, "vino"], "tok", modo="estricto")
    assert enviado["modo"] == "estricto"
    assert [c.get("duro") for c in enviado["criterios"] if c["tipo"] == "semantico"] == [True, False]
    assert not any("peso" in c or "umbral_distancia" in c for c in enviado["criterios"])
    item = r["items"][0]
    assert item["verificacionIncompleta"] is True and item["penalizado"] is False
    assert item["confianzaBaja"] is True and item["estado"] == "pendiente"
    assert item["evidencia"] == [{"criterio": "toma cerveza", "veredicto": "sin_verificar",
                                  "estado": "pendiente", "razon": "verificador caído",
                                  "respuesta": "Tomo cerveza", "pregunta": "¿Qué toma?",
                                  "estudio": "Hábitos 2025", "fechaCampo": "2025-11-01"}]
    assert r["modo"] == "estricto"
    assert r["excluidos"] == {"total": 5, "porMotivo": {"no_cumple": 1, "dudoso": 1, "sin_evidencia": 3}}
    # Un campo ausente no se lee a favor (contrato v2 de paneles).
    sin_marcas = motor.normalizar_resultado({"items": [{"id_persona": "p", "criterios": [
        {"tipo": "semantico", "veredicto": "dudoso"}]}]})["items"][0]
    assert sin_marcas["penalizado"] is True and sin_marcas["confianzaBaja"] is True


def _incorporar_con_marcas(api, sid, flojos=None, verificados=None):
    """Lista de espera con 25-34 y 35-44. Entran penalizados los primeros
    `flojos` en el orden de la lista (para que el desempate viejo los
    prefiriera), o todos menos los últimos `verificados`."""
    sel = api("POST", f"/cuali/sesiones/{sid}/candidatos",
              {"modo": "demografica", "filtros": {"tramoEtario": ["25-34", "35-44"]}})
    ids = [c["idPersona"] for c in sel["candidatos"]]
    corte = flojos if flojos is not None else len(ids) - verificados
    pedidos = [{"idPersona": i, "penalizado": True, "confianzaBaja": True} if n < corte
               else {"idPersona": i} for n, i in enumerate(ids)]
    api("POST", f"/cuali/sesiones/{sid}/convocatorias", {"candidatos": pedidos})
    return ids[:corte], ids[corte:]


def test_r118_propuesta_no_usa_penalizados_si_hay_verificados(api, ctx, sesion):
    from coloquio import embudo, sesiones as mod_sesiones

    sid = sesion["id"]
    flojos, verificados = _incorporar_con_marcas(api, sid, 15)
    assert _conv(api, sid, flojos[0])["marcasEvidencia"] == ["penalizado", "confianzaBaja"]
    assert _conv(api, sid, verificados[0])["marcasEvidencia"] == []
    p = api("GET", f"/cuali/sesiones/{sid}/invitacion")
    assert len(p["propuestos"]) == p["metaInvitacionTotal"] and not p["deficitRestante"]
    assert not set(p["propuestos"]) & set(flojos)
    assert p["conEvidenciaFloja"] == [] and p["avisos"] == []
    # La prueba no es trivial: sin las marcas, la misma lista los habría elegido.
    s = mod_sesiones.exigir(ctx.store, sid)
    convs = [{**c, "marcasEvidencia": []} for c in embudo.convocatorias(ctx.store, sid)]
    assert set(mod_sesiones.proponer_invitacion(s, convs)["propuestos"]) & set(flojos)


def test_r118_propuesta_recurre_a_penalizados_y_lo_dice(api, sesion):
    sid = sesion["id"]
    flojos, verificados = _incorporar_con_marcas(api, sid, verificados=3)
    p = api("GET", f"/cuali/sesiones/{sid}/invitacion")
    assert set(p["propuestos"][:3]) == set(verificados)  # primero los verificados
    assert p["conEvidenciaFloja"] and set(p["conEvidenciaFloja"]) <= set(flojos)
    assert p["avisos"][0]["tipo"] == "evidencia_floja"
    assert str(len(p["conEvidenciaFloja"])) in p["avisos"][0]["mensaje"]


def test_r118_reemplazo_ofrece_primero_verificados(api, ctx, sesion):
    sid = sesion["id"]
    flojos, _ = _incorporar_con_marcas(api, sid, 15)
    propuesta = api("GET", f"/cuali/sesiones/{sid}/invitacion")
    api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": propuesta["propuestos"]})
    caido = propuesta["propuestos"][0]
    _confirmar(api, sid, caido)
    api("PATCH", f"/cuali/convocatorias/{sid}/{caido}", {"a": "se_cayo"})
    p = api("POST", f"/cuali/sesiones/{sid}/reemplazo", {"idPersona": caido})
    marcas = [c["evidenciaFloja"] for c in p["propuestos"]]
    assert marcas == sorted(marcas)  # los verificados, antes
    assert any(c["idPersona"] in flojos and c["marcasEvidencia"] for c in p["propuestos"] + p["parciales"])
