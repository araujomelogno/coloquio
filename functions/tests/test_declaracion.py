"""R5.2.a — la convocatoria se declara en la bóveda al invitar.

Contrato de `boveda/0016`: sin una convocatoria declarada y vigente para esa
persona y ese sistema, `contacto_para_convocatoria()` no entrega el contacto.
COLOQUIO declara con `declarar_convocatoria(id_persona, sesion_id,
fecha_sesion + 2 días)` en el paso `candidato → invitado`, fuera de la
transacción de Firestore y antes de ella.
"""

import datetime as dt

import pytest

import fabrica
from coloquio import declaracion, modelo
from coloquio.errores import Conflicto, ConvocatoriaRechazada, ServicioNoDisponible


def _candidatos(api, sid, n=3):
    ids = [fabrica.id_de(i) for i in (2, 3, 5, 6, 8, 9)[:n]]
    api("POST", f"/cuali/sesiones/{sid}/convocatorias", {"candidatos": ids})
    return ids


def _conv(api, sid, pid):
    return next(c for c in api("GET", f"/cuali/sesiones/{sid}/embudo")["convocatorias"]
                if c["idPersona"] == pid)


def test_invitar_declara_con_la_sesion_y_la_fecha_mas_dos_dias(api, ctx, sesion):
    sid = sesion["id"]
    ids = _candidatos(api, sid)
    r = api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": ids})
    assert r["invitados"] == ids and r["noDeclarados"] == []
    esperado = sesion["fecha"] + dt.timedelta(days=2)
    for pid in ids:
        assert ctx.bov.declaraciones[(pid, sid)] == esperado  # referencia = id de sesión
    # Y ahora la bóveda entrega el contacto, auditado con el email humano.
    c = api("GET", f"/cuali/convocatorias/{sid}/{ids[0]}/contacto", consulta={"canal": "celular"})
    assert c["dato"].startswith("099")
    assert ctx.bov.auditoria[-1]["actor"] == "coordinadora@equipos.com.uy"


def test_sin_declaracion_la_boveda_no_entrega(ctx):
    pid = fabrica.id_de(2)
    from coloquio.errores import ContactoRechazado

    with pytest.raises(ContactoRechazado, match="convocatoria activa"):
        ctx.bov.contacto(pid, "celular", "coordinadora@equipos.com.uy")


def test_el_candidato_no_invitado_no_tiene_contacto(api, ctx, sesion):
    """Leer el contacto no es una forma de declarar: primero se invita."""
    sid = sesion["id"]
    pid = _candidatos(api, sid, 1)[0]
    with pytest.raises(Conflicto, match="invitalo primero"):
        api("GET", f"/cuali/convocatorias/{sid}/{pid}/contacto")
    assert ctx.bov.declaraciones == {}


def test_invitar_de_a_uno_declara(api, ctx, sesion):
    sid = sesion["id"]
    pid = _candidatos(api, sid, 1)[0]
    api("PATCH", f"/cuali/convocatorias/{sid}/{pid}", {"a": "invitado"})
    assert (pid, sid) in ctx.bov.declaraciones


def test_si_la_boveda_rechaza_no_queda_invitado(api, ctx, sesion):
    """Retiró el consentimiento entre la selección y la invitación."""
    sid = sesion["id"]
    ids = _candidatos(api, sid, 3)
    ctx.bov.personas[ids[1]]["consiente"] = False
    r = api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": ids})
    assert r["invitados"] == [ids[0], ids[2]]
    assert r["noDeclarados"][0]["idPersona"] == ids[1]
    assert _conv(api, sid, ids[1])["estado"] == modelo.CANDIDATO
    with pytest.raises(ConvocatoriaRechazada):
        api("PATCH", f"/cuali/convocatorias/{sid}/{ids[1]}", {"a": "invitado"})
    assert _conv(api, sid, ids[1])["estado"] == modelo.CANDIDATO


def test_se_declara_antes_de_la_transaccion(api, ctx, sesion):
    """Con la bóveda caída no se invita a nadie: no queda nadie invitado cuyo
    contacto después no se va a poder leer."""
    sid = sesion["id"]
    ids = _candidatos(api, sid, 2)
    ctx.bov.falla = "bóveda no disponible"
    with pytest.raises(ServicioNoDisponible):
        api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": ids})
    with pytest.raises(ServicioNoDisponible):
        api("PATCH", f"/cuali/convocatorias/{sid}/{ids[0]}", {"a": "invitado"})
    assert {_conv(api, sid, i)["estado"] for i in ids} == {modelo.CANDIDATO}


def test_tope_de_sesenta_dias(api, ctx, sesion):
    sid = sesion["id"]
    api("PATCH", f"/cuali/sesiones/{sid}", {"fecha": "2026-12-20T19:00"})  # 80 días
    pid = _candidatos(api, sid, 1)[0]
    api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": [pid]})
    vence = ctx.bov.declaraciones[(pid, sid)]
    assert vence <= ctx.ahora() + dt.timedelta(days=60)
    assert vence == ctx.ahora() + declaracion.TOPE


def test_reprogramar_actualiza_no_duplica(api, ctx, sesion):
    sid = sesion["id"]
    ids = _candidatos(api, sid, 2)
    api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": ids})
    r = api("PATCH", f"/cuali/sesiones/{sid}", {"fecha": "2026-10-15T19:00"})
    assert r["redeclaracion"]["redeclarados"] == 2
    nueva = r["fecha"] + dt.timedelta(days=2)
    assert [k for k in ctx.bov.declaraciones if k[0] == ids[0]] == [(ids[0], sid)]
    assert ctx.bov.declaraciones[(ids[0], sid)] == nueva


def test_guardar_sin_cambiar_la_fecha_no_redeclara(api, ctx, sesion):
    sid = sesion["id"]
    ids = _candidatos(api, sid, 1)
    api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": ids})
    antes = len(ctx.bov.llamadas_declarar)
    r = api("PATCH", f"/cuali/sesiones/{sid}", {"lugar": "Sala 2, Pocitos"})
    assert "redeclaracion" not in r and len(ctx.bov.llamadas_declarar) == antes


def test_declaracion_vencida_se_repone_al_leer_el_contacto(api, ctx, sesion):
    """Una invitación anterior a R5.2.a, o una declaración que venció."""
    sid = sesion["id"]
    pid = _candidatos(api, sid, 1)[0]
    api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": [pid]})
    ctx.bov.declaraciones.clear()
    c = api("GET", f"/cuali/convocatorias/{sid}/{pid}/contacto")
    assert c["dato"] and (pid, sid) in ctx.bov.declaraciones


def test_whatsapp_desde_candidato_declara_antes_de_leer_el_celular(api, ctx, sesion):
    sid = sesion["id"]
    pid = _candidatos(api, sid, 1)[0]
    api("POST", f"/cuali/convocatorias/{sid}/{pid}/canal", {"canal": "whatsapp"})
    r = api("POST", f"/cuali/convocatorias/{sid}/{pid}/whatsapp", {"tipo": "invitacion"})
    assert r["enviado"] and _conv(api, sid, pid)["estado"] == modelo.INVITADO
    assert (pid, sid) in ctx.bov.declaraciones


def test_reingresar_vuelve_a_declarar(api, ctx, sesion):
    sid = sesion["id"]
    pid = _candidatos(api, sid, 1)[0]
    api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": [pid]})
    api("PATCH", f"/cuali/convocatorias/{sid}/{pid}", {"a": "rechazo"})
    antes = len(ctx.bov.llamadas_declarar)
    api("POST", f"/cuali/convocatorias/{sid}/{pid}/reingreso", {"motivo": "Llamó y ahora puede"})
    assert len(ctx.bov.llamadas_declarar) == antes + 1


def test_reemplazo_declara(api, ctx, sesion):
    sid = sesion["id"]
    ids = _candidatos(api, sid, 6)
    api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": ids[:1]})
    api("PATCH", f"/cuali/convocatorias/{sid}/{ids[0]}", {"a": "confirmado"})
    api("PATCH", f"/cuali/convocatorias/{sid}/{ids[0]}", {"a": "se_cayo"})
    p = api("POST", f"/cuali/sesiones/{sid}/reemplazo", {"idPersona": ids[0]})
    elegido = p["propuestos"][0]["idPersona"]
    api("POST", f"/cuali/sesiones/{sid}/reemplazo/resolver",
        {"accion": "reemplazar", "idPersona": ids[0], "reemplazo": elegido})
    assert (elegido, sid) in ctx.bov.declaraciones


def test_la_baja_se_lleva_las_declaraciones(api, ctx, sesion):
    sid = sesion["id"]
    pid = _candidatos(api, sid, 1)[0]
    api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": [pid]})
    ctx.bov.dar_de_baja(pid)
    assert not any(k[0] == pid for k in ctx.bov.declaraciones)


def test_vencimiento_rechaza_sesiones_pasadas(ctx):
    from coloquio.errores import DatosInvalidos

    with pytest.raises(DatosInvalidos, match="ya pasó"):
        declaracion.vencimiento({"fecha": ctx.ahora() - dt.timedelta(days=3)}, ctx.ahora())


def test_reemplazo_con_fatiga_sin_motivo_no_deja_declaracion(api, ctx, sesion):
    from coloquio.errores import RequiereAnulacion

    sid = sesion["id"]
    ids = _candidatos(api, sid, 1)
    api("POST", f"/cuali/sesiones/{sid}/invitacion", {"ids": ids})
    api("PATCH", f"/cuali/convocatorias/{sid}/{ids[0]}", {"a": "confirmado"})
    api("PATCH", f"/cuali/convocatorias/{sid}/{ids[0]}", {"a": "se_cayo"})
    seg = _conv(api, sid, ids[0])["segmento"]
    fatigado = next(pid for pid, p in ctx.bov.personas.items()
                    if p["segmento"] == seg and pid not in ids and p["consiente"])
    api("POST", "/cuali/historico", {"categoria": "bebidas", "fecha": "2026-08-01T19:00",
                                     "idPersonas": [fatigado]})
    with pytest.raises(RequiereAnulacion):
        api("POST", f"/cuali/sesiones/{sid}/reemplazo/resolver",
            {"accion": "reemplazar", "idPersona": ids[0], "reemplazo": fatigado})
    assert (fatigado, sid) not in ctx.bov.declaraciones
