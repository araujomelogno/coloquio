"""El Definition of Done de la Fase 1 (SPEC §11), de punta a punta, en memoria.

Un focus group presencial entero: estudio y pauta, selección mixta con
evidencia e historial, gate de consentimiento forzado, fatiga con anulación,
convocatoria por los dos canales, caída con reemplazo del mismo segmento y el
caso sin candidatos, recepción de ocho, cierre, baja en cascada sin rastro y
auditoría de PII del store.
"""

import datetime as dt
import re
import uuid

import pytest

import fabrica
from coloquio import cascada, modelo, pii, util, whatsapp
from coloquio.errores import (
    Conflicto, ContactoRechazado, DatosInvalidos, FugaDePII, NoEncontrado, RequiereAnulacion,
    SinPermiso, TransicionInvalida,
)


def _embudo(api, sid):
    return api("GET", f"/cuali/sesiones/{sid}/embudo")


def _conv(api, sid, pid):
    return next(c for c in _embudo(api, sid)["convocatorias"] if c["idPersona"] == pid)


def _llenar_sesion(api, sid, filtros=None):
    """Selección demográfica + incorporación + lista de invitación propuesta."""
    sel = api("POST", f"/cuali/sesiones/{sid}/candidatos",
              {"modo": "demografica", "filtros": filtros or {"tramo_etario": ["25-34", "35-44"]}})
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
    assert pid not in ctx.bov.convocables(limite=5000)
    assert ctx.bov.vigentes([pid]) == set()
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
                  # boveda/0034 — la superficie de selección (R1.14 a R1.17).
                  "v_atributo_catalogo", "f_persona_convocable_filtrada", "atributos_de_personas",
                  "ficha_candidato", "identificar_candidatos",
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
              {"modo": "demografica", "filtros": {"tramo_etario": ["25-34", "35-44"]}})
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


# ════════════════════════════════════════════════════════════════════
#  R1.14 a R1.17 · la superficie de selección de la bóveda (`boveda/0034`)
# ════════════════════════════════════════════════════════════════════

def _buscar(api, sid, filtros, actor=None, **extra):
    return api("POST", f"/cuali/sesiones/{sid}/candidatos",
               {"modo": "demografica", "filtros": filtros, "limite": 500, **extra}, actor=actor)


def _valores_de(ctx, pid):
    return {f["atributo"]: f for f in ctx.bov.atributos([pid])}


def _ids_que_cumplen(ctx, predicado):
    """Los convocables (contacto vigente) según los valores de la bóveda."""
    filas = {}
    for f in ctx.bov.atributos(list(ctx.bov.personas)):
        filas.setdefault(f["idPersona"], {})[f["atributo"]] = f
    vigentes = ctx.bov.vigentes(list(ctx.bov.personas))
    return {i for i in vigentes if predicado(filas.get(i, {}))}


# ── R1.14 · formulario desde el catálogo ──

def test_r114_el_catalogo_sale_de_la_boveda_y_un_atributo_nuevo_aparece(api, ctx, sesion):
    claves = [a["clave"] for a in api("GET", "/cuali/atributos")["items"]]
    assert "nse_2019" not in claves                       # dado de baja: no se ofrece
    nivel = next(a for a in api("GET", "/cuali/atributos")["items"] if a["clave"] == "nivel_educativo")
    assert "terciaria" not in [c["clave"] for c in nivel["categorias"]]  # categoría de baja
    # Un atributo creado en `paneles` aparece sin desplegar nada, y se puede filtrar.
    ctx.bov.catalogo_tabla.append({
        "clave": "mascota", "etiqueta": "Tiene mascota", "tipo": "categorico", "orden": 45,
        "categorias": [{"clave": "perro", "etiqueta": "Perro"}, {"clave": "gato", "etiqueta": "Gato"}]})
    for i, pid in enumerate(list(ctx.bov.personas)[:10]):
        ctx.bov.personas[pid]["atributos"]["mascota"] = ("perro", "gato")[i % 2]
    items = api("GET", "/cuali/atributos")["items"]
    claves = [a["clave"] for a in items]
    assert claves.index("mascota") == claves.index("localidad") + 1    # en su `orden`
    r = _buscar(api, sesion["id"], {"mascota": {"en": ["gato"]}})
    esperados = _ids_que_cumplen(ctx, lambda f: f.get("mascota", {}).get("valor") == "gato")
    assert esperados and {c["idPersona"] for c in r["candidatos"] + r["excluidosPorFatiga"]} == esperados


def test_r114_varias_categorias_son_o_y_atributos_distintos_son_y(api, ctx, sesion):
    # Un categórico con ocho categorías.
    barrios = [f"barrio_{n}" for n in range(8)]
    ctx.bov.catalogo_tabla.append({
        "clave": "barrio", "etiqueta": "Barrio", "tipo": "categorico", "orden": 41,
        "categorias": [{"clave": b, "etiqueta": b.replace("_", " ")} for b in barrios]})
    for i, pid in enumerate(ctx.bov.personas):
        ctx.bov.personas[pid]["atributos"]["barrio"] = barrios[i % 8]
    vistos = lambda r: {c["idPersona"] for c in r["candidatos"] + r["excluidosPorFatiga"]}
    sid = sesion["id"]
    uno = vistos(_buscar(api, sid, {"barrio": {"en": ["barrio_1"]}}))
    otro = vistos(_buscar(api, sid, {"barrio": {"en": ["barrio_6"]}}))
    los_dos = vistos(_buscar(api, sid, {"barrio": {"en": ["barrio_1", "barrio_6"]}}))
    assert uno and otro and los_dos == uno | otro                        # o
    mujeres = vistos(_buscar(api, sid, {"sexo": {"en": ["F"]}}))
    cruce = vistos(_buscar(api, sid, {"barrio": {"en": ["barrio_1", "barrio_6"]}, "sexo": ["F"]}))
    assert cruce == los_dos & mujeres and cruce != los_dos               # y


def test_r114_cada_tipo_tiene_su_operador(api, ctx, sesion):
    sid = sesion["id"]
    vistos = lambda r: {c["idPersona"] for c in r["candidatos"] + r["excluidosPorFatiga"]}
    # numérico → rango
    r = vistos(_buscar(api, sid, {"hijos": {"min": 1, "max": 1}}))
    assert r == _ids_que_cumplen(ctx, lambda f: f.get("hijos", {}).get("valorNum") == 1)
    # fecha → rango
    r = vistos(_buscar(api, sid, {"ultima_compra": {"desde": "2025-03-01", "hasta": "2025-06-30"}}))
    assert r and r == _ids_que_cumplen(
        ctx, lambda f: "2025-03-01" <= (f.get("ultima_compra", {}).get("valorFecha") or "") <= "2025-06-30")
    # derivado sin categorías (la edad) → rango, sobre el valor efectivo
    r = vistos(_buscar(api, sid, {"edad": {"min": 35, "max": 44}}))
    assert r and r == _ids_que_cumplen(ctx, lambda f: 35 <= (f.get("edad", {}).get("valorNum") or 0) <= 44)
    # derivado con categorías (el tramo) → combo; incluye el tramo cargado sin edad
    r = vistos(_buscar(api, sid, {"tramo_etario": {"en": ["25-34"]}}))
    assert r == _ids_que_cumplen(ctx, lambda f: f.get("tramo_etario", {}).get("valor") == "25-34")
    con_tramo_cargado = {pid for pid, p in ctx.bov.personas.items() if "tramo_etario" in p["atributos"]}
    assert r & con_tramo_cargado                     # sin edad, cuenta el tramo cargado


def test_r114_lo_que_no_se_puede_aplicar_es_error_no_un_filtro_ignorado(api, ctx, sesion):
    sid = sesion["id"]
    for filtros, texto in (
            ({"color_favorito": ["rojo"]}, "no está en el catálogo"),
            ({"nse_2019": ["alto"]}, "dado de baja"),
            ({"nivel_educativo": ["terciaria"]}, "no tiene la(s) categoría(s)"),
            ({"sexo": {"min": 3}}, "admite"),
            ({"hijos": {"min": "muchos"}}, "no se puede leer")):
        with pytest.raises(DatosInvalidos, match=re.escape(texto)):
            _buscar(api, sid, filtros)
    # En mixta también: la bóveda valida antes de cruzar con el ranking.
    with pytest.raises(DatosInvalidos, match="no está en el catálogo"):
        api("POST", f"/cuali/sesiones/{sid}/candidatos",
            {"modo": "mixta", "filtros": {"color_favorito": ["rojo"]}, "criterios": ["cerveza"]})


def test_r114_un_atributo_especial_se_puede_usar_como_cualquiera(api, ctx, sesion):
    """Decisión de producto (2026-11-06): los atributos `es_especial` están
    disponibles igual que los demás. El catálogo conserva la marca."""
    religion = next(a for a in api("GET", "/cuali/atributos")["items"] if a["clave"] == "religion")
    assert religion["esEspecial"] is True
    r = _buscar(api, sesion["id"], {"religion": ["ninguna"]})
    assert {c["idPersona"] for c in r["candidatos"] + r["excluidosPorFatiga"]} == _ids_que_cumplen(
        ctx, lambda f: f.get("religion", {}).get("valor") == "ninguna")


def test_r114_mixta_vuelve_a_filtrar_igual_que_la_boveda(api, ctx, sesion):
    """La mixta re-filtra los ids del ranking con los valores de la bóveda
    (`atributos.cumple`). Tiene que dar lo mismo que `f_persona_convocable_
    filtrada()` sobre el panel entero, filtro por filtro."""
    from coloquio import atributos

    cat = ctx.bov.catalogo()
    todos = list(ctx.bov.personas)
    filas = atributos.filas_por_persona(ctx.bov.atributos(todos))
    vigentes = ctx.bov.vigentes(todos)
    for filtros in ({"sexo": ["F"]}, {"tramo_etario": ["25-34", "45-54"], "localidad": ["Montevideo"]},
                    {"edad": {"min": 30, "max": 40}}, {"hijos": {"max": 1}},
                    {"ultima_compra": {"desde": "2025-05-01"}}, {"nivel_educativo": ["sin_dato"]}):
            normal = atributos.normalizar_filtros(filtros)
            local = {i for i in vigentes if atributos.cumple(filas.get(i, {}), normal, cat)}
            assert local == set(ctx.bov.convocables(normal, limite=5000)), filtros
    # Y de punta a punta: mixta ⊆ el filtro demográfico.
    r = api("POST", f"/cuali/sesiones/{sesion['id']}/candidatos",
            {"modo": "mixta", "filtros": {"localidad": ["Canelones"]}, "criterios": ["cerveza"]})
    assert r["candidatos"] and {c["idPersona"] for c in r["candidatos"]} <= set(
        ctx.bov.convocables({"localidad": {"en": ["Canelones"]}}, limite=5000))
    assert ctx.motor.ultima["criterios"][0] == {
        "tipo": "demografico", "dimension": "localidad", "operador": "in", "valor": ["Canelones"]}


def test_r114_ningun_atributo_se_nombra_en_el_codigo(ctx):
    """«Si aparece `sexo` escrito a mano en el front, el requisito está
    incumplido.» Se buscan las claves del catálogo de prueba, entre comillas,
    en todo el código de COLOQUIO: funciones y front."""
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parent.parent.parent
    archivos = list((raiz / "functions" / "coloquio").glob("*.py")) + \
        list((raiz / "web" / "public" / "js").rglob("*.js"))
    claves = {a["clave"] for a in fabrica.catalogo()} | {"tramoEtario", "edadMin", "edadMax"}
    alternativas = "|".join(map(re.escape, sorted(claves)))
    # Entre comillas (`'sexo'`) o como propiedad (`segmento.sexo`, `{ sexo: … }`).
    patron = re.compile(r"""['"`](%s)['"`]|\.(%s)\b|[{,]\s*(%s)\s*:""" % ((alternativas,) * 3))
    hallados = [f"{a.relative_to(raiz)}: {m.group(0)}"
                for a in archivos for m in patron.finditer(a.read_text(encoding="utf-8"))]
    assert hallados == []


# ── Cuotas por cualquier atributo del catálogo ──

def test_r114_cuotas_por_cualquier_atributo_con_categorias(api, ctx, sesion):
    eid = sesion["estudio"]["id"]
    base = {"estudioId": eid, "fecha": "2026-10-09T19:00", "lugar": "Sala", "cupoObjetivo": 6}
    s = api("POST", "/cuali/sesiones", {**base, "cuotas": [
        {"dimension": "nivel_educativo", "categoria": "terciario", "objetivo": 3},
        {"dimension": "nivel_educativo", "categoria": "secundaria", "objetivo": 3}]})
    r = _buscar(api, s["id"], {"nivel_educativo": ["terciario", "secundaria"]})
    ids = [c["idPersona"] for c in r["candidatos"]]
    for c in r["candidatos"]:
        assert c["segmento"] == {"nivel_educativo": _valores_de(ctx, c["idPersona"])["nivel_educativo"]["valor"]}
    api("POST", f"/cuali/sesiones/{s['id']}/convocatorias", {"candidatos": ids})
    estado = api("GET", f"/cuali/sesiones/{s['id']}/embudo")["cuota"]
    assert {(q["categoria"], q["enEspera"]) for q in estado["cuotas"]} == {
        ("terciario", sum(1 for c in r["candidatos"] if c["segmento"]["nivel_educativo"] == "terciario")),
        ("secundaria", sum(1 for c in r["candidatos"] if c["segmento"]["nivel_educativo"] == "secundaria"))}
    # Un numérico no tiene categorías: no lleva cuota. Una categoría ajena, tampoco.
    with pytest.raises(DatosInvalidos, match="Dimensión de cuota inválida"):
        api("POST", "/cuali/sesiones", {**base, "cuotas": [{"dimension": "hijos", "categoria": "1", "objetivo": 2}]})
    with pytest.raises(DatosInvalidos, match="no es una categoría"):
        api("POST", "/cuali/sesiones", {**base, "cuotas": [{"dimension": "sexo", "categoria": "Z", "objetivo": 2}]})


def test_r114_sumar_una_dimension_de_cuota_completa_el_segmento_de_quien_ya_esta(api, ctx, sesion):
    sid = sesion["id"]
    _llenar_sesion(api, sid)
    antes = _embudo(api, sid)["convocatorias"]
    assert all("localidad" not in c["segmento"] for c in antes)   # solo las dimensiones con cuota
    cuotas = [{k: q[k] for k in ("dimension", "categoria", "objetivo")} for q in sesion["cuotas"]]
    api("PATCH", f"/cuali/sesiones/{sid}", {"cuotas": cuotas + [
        {"dimension": "localidad", "categoria": "Montevideo", "objetivo": 3}]})
    despues = _embudo(api, sid)
    for c in despues["convocatorias"]:
        assert c["segmento"]["localidad"] == _valores_de(ctx, c["idPersona"])["localidad"]["valor"]
    mvd = next(q for q in despues["cuota"]["cuotas"] if q["dimension"] == "localidad")
    assert mvd["enInvitacion"] + mvd["enEspera"] == sum(
        1 for c in despues["convocatorias"] if c["segmento"]["localidad"] == "Montevideo"
        and c["estado"] in ("invitado", "candidato"))


def test_r114_una_cuota_sobre_un_atributo_dado_de_baja_sigue_legible(api, ctx, sesion):
    sid = sesion["id"]
    _llenar_sesion(api, sid)
    next(a for a in ctx.bov.catalogo_tabla if a["clave"] == "tramo_etario")["activo"] = False
    e = _embudo(api, sid)                             # no se rompe ni se borra
    assert {q["dimension"] for q in e["cuota"]["cuotas"]} == {"sexo", "tramo_etario"}
    api("PATCH", f"/cuali/sesiones/{sid}", {"cupoObjetivo": 9})  # cambiar el cupo sigue andando


# ── R1.15 · columnas elegibles ──

def test_r115_agregar_una_columna_no_vuelve_a_correr_la_busqueda(api, ctx, sesion):
    r = _buscar(api, sesion["id"], {}, limite=200)
    ids = [c["idPersona"] for c in r["candidatos"] + r["excluidosPorFatiga"]][:200]
    assert len(ids) >= 80
    antes = dict(ctx.bov.llamadas)
    v = api("POST", "/cuali/atributos/valores", {"ids": ids, "atributos": ["nivel_educativo", "hijos"]})
    assert ctx.bov.llamadas["filtrada"] == antes["filtrada"]            # no hubo búsqueda
    assert ctx.bov.llamadas["atributos"] == antes["atributos"] + 1      # una sola llamada
    assert {f["atributo"] for f in v["filas"]} == {"nivel_educativo", "hijos"}
    assert ctx.motor.llamadas == 0


def test_r115_ausente_no_es_vacio(api, ctx, sesion):
    sin_dato_cargado = fabrica.id_de(3)    # i % 4 == 3 → «sin_dato» declarado
    ausente = fabrica.id_de(4)             # i % 4 == 0 → nunca se cargó
    filas = api("POST", "/cuali/atributos/valores",
                {"ids": [sin_dato_cargado, ausente], "atributos": ["nivel_educativo"]})["filas"]
    assert [(f["idPersona"], f["valor"], f["etiquetaValor"]) for f in filas] == [
        (sin_dato_cargado, "sin_dato", "Sin dato")]                      # el ausente no viene
    assert all(f["valor"] is not None for f in ctx.bov.atributos(list(ctx.bov.personas)))


def test_r115_las_columnas_se_recuerdan_por_usuario(api, ctx):
    otra = fabrica.actor(roles=("investigador",), uid="u-inv", email="investigadora@equipos.com.uy")
    assert api("GET", "/cuali/preferencias")["columnasSeleccion"] == []
    api("PUT", "/cuali/preferencias", {"columnasSeleccion": ["nivel_educativo", "hijos"]})
    api("PUT", "/cuali/preferencias", {"columnasSeleccion": ["religion"]}, actor=otra)
    ctx.reloj.avanzar(days=1)   # «al día siguiente»
    assert api("GET", "/cuali/preferencias")["columnasSeleccion"] == ["nivel_educativo", "hijos"]
    assert api("GET", "/cuali/preferencias", actor=otra)["columnasSeleccion"] == ["religion"]
    with pytest.raises(DatosInvalidos):
        api("PUT", "/cuali/preferencias", {"columnasSeleccion": ["Ana Pérez <a@b.com>"]})


def test_r115_un_atributo_dado_de_baja_desaparece_de_las_columnas_sin_error(api, ctx):
    api("PUT", "/cuali/preferencias", {"columnasSeleccion": ["nivel_educativo", "hijos"]})
    next(a for a in ctx.bov.catalogo_tabla if a["clave"] == "hijos")["activo"] = False
    ids = list(ctx.bov.personas)[:20]
    filas = api("POST", "/cuali/atributos/valores",
                {"ids": ids, "atributos": api("GET", "/cuali/preferencias")["columnasSeleccion"]})["filas"]
    assert filas and {f["atributo"] for f in filas} == {"nivel_educativo"}
    assert "hijos" not in [a["clave"] for a in api("GET", "/cuali/atributos")["items"]]


# ── R1.16 · ficha seudónima ──

def test_r116_ficha_seudonima_con_historial_completo_y_sin_registro(api, ctx, sesion):
    pid = fabrica.id_de(3)
    for categoria, fecha in (("bebidas", "2025-11-10T19:00"), ("banca", "2026-02-05T19:00"),
                             ("alimentos", "2026-06-20T19:00")):
        api("POST", "/cuali/historico", {"categoria": categoria, "fecha": fecha,
                                         "etiqueta": f"Grupo de {categoria}", "idPersonas": [pid]})
    reid, store_antes = len(ctx.bov.reidentificacion), str(ctx.store.todos())
    f = api("GET", f"/cuali/candidatos/{pid}/ficha")
    assert len(ctx.bov.reidentificacion) == reid and str(ctx.store.todos()) == store_antes
    assert pii.hallazgos(f) == []
    assert not any(v in str(f) for v in (fabrica.nombre_de(3), ctx.bov.personas[pid]["email"],
                                         ctx.bov.personas[pid]["celular"]))
    assert f["estado"] == "activa" and f["enroladoEn"].startswith("2024-04-01")
    assert [p["etiqueta"] for p in f["paneles"]] == ["Panel general"]     # la membresía de baja no
    por_attr = {a["atributo"]: a for a in f["atributos"]}
    assert por_attr["edad"]["procedencia"] == "envejecido"              # i % 7 == 3
    assert por_attr["nivel_educativo"]["etiquetaValor"] == "Sin dato"
    assert "nse_2019" not in por_attr
    sesiones_ = f["historial"]["sesiones"]
    assert len(sesiones_) == 3 and f["historial"]["total"] == 3
    assert {(s["categoria"], s["fecha"].date().isoformat(), s["estudioNombre"]) for s in sesiones_} == {
        ("bebidas", "2025-11-10", "Grupo de bebidas"), ("banca", "2026-02-05", "Grupo de banca"),
        ("alimentos", "2026-06-20", "Grupo de alimentos")}
    assert all(s["modalidad"] == "presencial" for s in sesiones_)


def test_r116_ficha_de_quien_no_esta_en_la_vista(api, ctx):
    pid = fabrica.id_de(5)
    ctx.bov.dar_de_baja(pid)
    with pytest.raises(NoEncontrado):
        api("GET", f"/cuali/candidatos/{pid}/ficha")
    # Quien no consintió el contacto pero sigue en la vista (uso semántico)
    # tiene ficha, como en la bóveda; lo que no tiene es contacto.
    assert api("GET", f"/cuali/candidatos/{fabrica.id_de(17)}/ficha")["estado"] == "activa"


# ── R1.17 · identificar los tildados ──

def test_r117_cargar_resultados_no_reidentifica(api, ctx, sesion):
    _buscar(api, sesion["id"], {})
    _buscar(api, sesion["id"], {"sexo": ["F"]})
    api("POST", f"/cuali/sesiones/{sesion['id']}/candidatos",
        {"modo": "mixta", "filtros": {"sexo": ["F"]}, "criterios": ["cerveza"]})
    assert ctx.bov.reidentificacion == [] and ctx.bov.llamadas["identificar"] == 0


def test_r117_identificar_veinte_audita_veinte_y_no_deja_nada_en_el_store(api, ctx, sesion, capsys):
    sid = sesion["id"]
    r = _buscar(api, sid, {})
    tildados = [c["idPersona"] for c in r["candidatos"]][:20]
    antes = str(ctx.store.todos())
    res = api("POST", f"/cuali/sesiones/{sid}/identificar", {"ids": tildados})
    assert res["pedidos"] == 20 and len(res["identificados"]) == 20 and res["noIdentificados"] == 0
    p0 = ctx.bov.personas[res["identificados"][0]["idPersona"]]
    assert {res["identificados"][0][k] for k in ("nombre", "email", "celular")} == {
        p0["nombre"], p0["email"], p0["celular"]}
    filas = [f for f in ctx.bov.reidentificacion if f["via"] == "identificar_candidatos"]
    assert len(filas) == 20 and {f["idPersona"] for f in filas} == set(tildados)
    assert all(f["motivo"] == "seleccion_cuali" and f["sistema"] == "coloquio"
               and f["contexto"]["referencia"] == sid and f["actor"] == "coordinadora@equipos.com.uy"
               for f in filas)
    # R1.12: la PII viajó al navegador y murió ahí. Nada en el store —ni un
    # nombre, ni un contador— y nada en el log.
    assert str(ctx.store.todos()) == antes
    volcado = str(ctx.store.todos()) + capsys.readouterr().out
    for i in res["identificados"]:
        assert i["nombre"] not in volcado and i["email"] not in volcado and i["celular"] not in volcado
    # Y después del flujo entero tampoco aparece ningún nombre del panel.
    test_auditoria_del_store_sin_pii(api, ctx, sesion)
    assert not any(fabrica.nombre_de(n) in str(ctx.store.todos()) for n in range(96))


def test_r117_reaplica_el_gate_y_respeta_los_limites(api, ctx, sesion):
    sid = sesion["id"]
    sin = fabrica.id_de(17)                                            # no consintió contacto
    res = api("POST", f"/cuali/sesiones/{sid}/identificar", {"ids": [fabrica.id_de(1), sin]})
    assert [i["idPersona"] for i in res["identificados"]] == [fabrica.id_de(1)]
    assert res["noIdentificados"] == 1
    assert sin not in {f["idPersona"] for f in ctx.bov.reidentificacion}
    with pytest.raises(DatosInvalidos, match="tope es 200"):
        api("POST", f"/cuali/sesiones/{sid}/identificar",
            {"ids": [str(uuid.uuid4()) for _ in range(201)]})
    with pytest.raises(DatosInvalidos, match="tope es 200"):    # y la bóveda también lo frena
        ctx.bov.identificar([str(uuid.uuid4()) for _ in range(201)], sid, "a@equipos.com.uy")
    with pytest.raises(NoEncontrado):                           # la referencia es una sesión real
        api("POST", "/cuali/sesiones/no-existe/identificar", {"ids": [fabrica.id_de(1)]})
    with pytest.raises(DatosInvalidos, match="email del usuario"):
        ctx.bov.identificar([fabrica.id_de(1)], sid, None)


def test_r117_sin_el_permiso_la_lista_sigue_seudonima(api, ctx, sesion):
    sin_permiso = fabrica.actor(roles=("coordinador", "investigador"), uid="u-sp",
                                email="sinpermiso@equipos.com.uy")
    assert "identificar" not in api("GET", "/cuali/yo", actor=sin_permiso)["permisos"]
    r = _buscar(api, sesion["id"], {"sexo": ["F"]}, actor=sin_permiso)
    assert r["candidatos"]                                              # la lista anda
    assert not any(k in c for c in r["candidatos"] for k in ("nombre", "email", "celular"))
    with pytest.raises(SinPermiso):
        api("POST", f"/cuali/sesiones/{sesion['id']}/identificar",
            {"ids": [r["candidatos"][0]["idPersona"]]}, actor=sin_permiso)
    assert ctx.bov.reidentificacion == []
    # El rol propio lo habilita, sumado a los otros.
    con = fabrica.actor(roles=("coordinador", "identificador"), uid="u-id", email="id@equipos.com.uy")
    assert api("POST", f"/cuali/sesiones/{sesion['id']}/identificar",
               {"ids": [r["candidatos"][0]["idPersona"]]}, actor=con)["identificados"]


def test_r117_identificar_no_es_convocar(api, ctx, sesion):
    """`contacto_para_convocatoria()` no cambia: sin convocatoria declarada
    sigue sin entregar el contacto, aunque la persona ya esté identificada."""
    pid = fabrica.id_de(1)
    api("POST", f"/cuali/sesiones/{sesion['id']}/identificar", {"ids": [pid]})
    with pytest.raises(ContactoRechazado, match="no hay motivo"):
        ctx.bov.contacto(pid, "celular", "coordinadora@equipos.com.uy")
