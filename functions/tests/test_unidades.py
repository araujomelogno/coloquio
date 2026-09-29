"""Piezas sueltas: PII, WhatsApp, auth, ruteo, store y consistencia."""

import hashlib
import hmac
import json

import pytest

import fabrica
from coloquio import auth, modelo, pii, ruteo, sesiones, store, whatsapp
from coloquio.errores import NoAutenticado, SinPermiso


# ── PII ──

def test_lista_de_pii_es_espejo_de_paneles():
    # Si `paneles` cambia `panel_api.pii.CAMPOS_PII`, esto tiene que cambiar a mano.
    assert pii.CAMPOS_PII == frozenset({
        "documento", "cedula", "ci", "dni", "pasaporte", "rut",
        "nombre", "nombres", "apellido", "apellidos", "nombre_completo",
        "email", "correo", "mail", "e_mail",
        "celular", "telefono", "movil", "whatsapp",
        "direccion", "domicilio",
        "fecha_nacimiento", "fecha_nac", "nacimiento", "fnac",
        "contacto", "observaciones",
    })


@pytest.mark.parametrize("clave", ["fechaNacimiento", "Celular", "E-Mail", "nombreCompleto",
                                   "observaciones", "whatsapp"])
def test_claves_pii_en_camelcase(clave):
    assert pii.hallazgos({"x": {clave: "algo"}}, "sesion")


def test_nombre_permitido_solo_donde_nombra_cosas():
    assert pii.hallazgos({"nombre": "Cervezas 2026"}, "estudio") == []
    assert pii.hallazgos({"nombre": "Ana"}, "participacionCuali")


@pytest.mark.parametrize("texto,patron", [
    ("escribile a ana@gmail.com", "email"),
    ("cel 099 123 456", "telefono"),
    ("CI 1.234.567-8", "cedula"),
])
def test_texto_libre_con_pii(texto, patron):
    assert patron in pii.patrones_en_texto(texto)


def test_texto_libre_normal_pasa():
    assert pii.patrones_en_texto("Grupo de 8, sala 2, duró 95 minutos. Buena dinámica.") == []


# ── WhatsApp ──

@pytest.mark.parametrize("entrada,salida", [
    ("099 123 456", "59899123456"), ("99123456", "59899123456"),
    ("+598 99 123 456", "59899123456"), ("+54 9 11 5555 6666", "5491155556666"),
])
def test_normalizar_celular(entrada, salida):
    assert whatsapp.normalizar_celular(entrada) == salida


def test_celular_vacio_degrada():
    with pytest.raises(whatsapp.ErrorCanal):
        whatsapp.normalizar_celular("")


def test_firma_del_webhook():
    cuerpo = json.dumps({"entry": []}).encode()
    firma = "sha256=" + hmac.new(b"secreto", cuerpo, hashlib.sha256).hexdigest()
    assert whatsapp.firma_valida(cuerpo, firma, "secreto")
    assert not whatsapp.firma_valida(cuerpo, firma, "otro")
    assert not whatsapp.firma_valida(cuerpo, None, "secreto")


def test_webhook_no_expone_remitente():
    eventos = whatsapp.interpretar_webhook({"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "59899111222", "profile": {"name": "Ana Pérez"}}],
        "messages": [{"from": "59899111222", "type": "text", "text": {"body": "sí"},
                      "context": {"id": "wamid.X"}}]}}]}]})
    assert eventos == [{"tipo": "texto", "contextoId": "wamid.X", "afirmativo": True}]


def test_cliente_arma_plantilla_con_payload():
    pedidos = []
    cliente = whatsapp.ClienteWhatsApp("tok", "123", pedir=lambda url, d: pedidos.append((url, d))
                                       or {"messages": [{"id": "wamid.1"}]})
    wamid = cliente.enviar_plantilla("099123456", "coloquio_invitacion", "es", ["a"], botones=("c1|s|p|si",))
    assert wamid == "wamid.1"
    url, datos = pedidos[0]
    assert url.endswith("/123/messages") and datos["to"] == "59899123456"
    assert datos["template"]["components"][1]["parameters"][0]["payload"] == "c1|s|p|si"


# ── Auth ──

def test_roles_y_permisos():
    coord = auth.Actor("u", roles=["coordinador"])
    inv = auth.Actor("u", roles=["investigador"])
    assert coord.puede("convocar") and not coord.puede("configurar")
    assert inv.puede("gestionar_estudios") and not inv.puede("recibir")
    with pytest.raises(SinPermiso):
        inv.exigir("recibir")


def test_actor_desde_padron():
    st = store.StoreMemoria()
    st.set("rolUsuario/u1", {"roles": ["coordinador"]})
    headers = {"Authorization": "Bearer t"}
    a = auth.actor_de_request(headers, st, lambda t: {"uid": "u1", "email": "a@equipos.com.uy"},
                              lambda uid: {"rol": "analista", "nombre": "A"})
    assert a.roles == ("coordinador",) and a.email == "a@equipos.com.uy"
    # El admin de paneles es administrador de COLOQUIO por construcción.
    b = auth.actor_de_request(headers, st, lambda t: {"uid": "u2"}, lambda uid: {"rol": "admin"})
    assert "administrador" in b.roles
    with pytest.raises(SinPermiso, match="padrón"):
        auth.actor_de_request(headers, st, lambda t: {"uid": "u3"}, lambda uid: {"activo": False})
    with pytest.raises(SinPermiso, match="no tenés roles"):
        auth.actor_de_request(headers, st, lambda t: {"uid": "u4"}, lambda uid: {"rol": "analista"})
    with pytest.raises(NoAutenticado):
        auth.actor_de_request({}, st, None, None)


# ── Ruteo: los contratos de la SPEC §8 existen ──

@pytest.mark.parametrize("metodo,camino", [
    ("POST", "/cuali/estudios"),
    ("POST", "/cuali/estudios/e1/pauta"),
    ("POST", "/cuali/sesiones"),
    ("POST", "/cuali/sesiones/s1/candidatos"),
    ("POST", "/cuali/sesiones/s1/convocatorias"),
    ("PATCH", "/cuali/convocatorias/s1/p1"),
    ("GET", "/cuali/convocatorias/s1/p1/contacto"),
    ("POST", "/cuali/sesiones/s1/reemplazo"),
    ("POST", "/cuali/sesiones/s1/asistencias"),
    ("POST", "/cuali/sesiones/s1/cerrar"),
    ("GET", "/cuali/personas/p1/historial"),
    ("GET", "/cuali/sesiones/s1/embudo"),
    ("POST", "/cuali/webhooks/whatsapp"),
])
def test_contratos_de_la_spec(metodo, camino):
    assert ruteo.resolver(metodo, camino)


def test_solo_el_webhook_y_el_entorno_son_publicos():
    publicas = [(m, p) for m, _, perm, _, p in ruteo.RUTAS if perm is None]
    assert sorted(publicas) == sorted([("GET", "/entorno"), ("GET", "/webhooks/whatsapp"),
                                       ("POST", "/webhooks/whatsapp")])


# ── Store en memoria: imita las reglas de transacción de Firestore ──

def test_lectura_despues_de_escritura_falla():
    st = store.StoreMemoria()

    def fn(tx):
        tx.set("a/1", {"x": 1})
        tx.get("a/2")

    with pytest.raises(store.LecturaDespuesDeEscritura):
        st.transaccion(fn)
    assert st.get("a/1") is None  # no se aplicó nada


def test_grupo_y_listar():
    st = store.StoreMemoria()
    st.set("sesion/s1/convocatoria/p1", {"idPersona": "p1"})
    st.set("sesion/s2/convocatoria/p1", {"idPersona": "p1"})
    st.set("sesion/s2/convocatoria/p2", {"idPersona": "p2"})
    assert len(st.grupo("convocatoria", [("idPersona", "==", "p1")])) == 2
    assert [i for i, _ in st.listar("sesion/s2/convocatoria")] == ["p1", "p2"]


# ── Sobre-reclutamiento ──

def test_propuesta_de_invitacion_respeta_la_cuota():
    sesion = {"cupoObjetivo": 4, "ratioSobrerreclutamiento": 1.5, "cuotas": [
        {"dimension": "sexo", "categoria": "F", "objetivo": 2},
        {"dimension": "sexo", "categoria": "M", "objetivo": 2}]}
    espera = [{"idPersona": f"f{i}", "estado": "candidato", "ordenListaEspera": i,
               "segmento": {"sexo": "F"}} for i in range(6)]
    espera += [{"idPersona": "m0", "estado": "candidato", "ordenListaEspera": 10,
                "segmento": {"sexo": "M"}}]
    r = sesiones.proponer_invitacion(sesion, espera)
    # Meta 6 (3 F + 3 M). Hay un solo M: se toma y se informa el déficit en
    # vez de completar con mujeres de más.
    assert "m0" in r["propuestos"] and sum(p.startswith("f") for p in r["propuestos"]) == 3
    assert r["deficitRestante"] == [{"dimension": "sexo", "categoria": "M", "faltan": 2}]


def test_meta_de_invitacion():
    assert modelo.meta_invitacion(8, 1.5) == 12
    assert modelo.meta_invitacion(8, 1.3) == 11
    assert modelo.tasa_caida_supuesta(1.5) == pytest.approx(0.3333, abs=1e-3)


# ── Consistencia: repara ──

def test_consistencia_repara_contadores(api, ctx, sesion):
    pid = fabrica.id_de(1)
    api("POST", f"/cuali/sesiones/{sesion['id']}/convocatorias", {"candidatos": [pid]})
    s = ctx.store.get(f"sesion/{sesion['id']}")
    s["conteo"]["candidato"] = 99
    ctx.store.set(f"sesion/{sesion['id']}", s)
    ctx.store.delete(f"participacionCuali/{pid}")
    r = api("POST", "/cuali/cumplimiento/consistencia", {"reparar": True})
    assert not r["consistente"] and r["reparado"]
    tipos = {h["tipo"] for h in r["hallazgos"]}
    assert tipos == {"sesion", "participacionCuali"}
    assert api("POST", "/cuali/cumplimiento/consistencia")["consistente"]


def test_secreto_placeholder_es_vacio():
    from coloquio import config

    c = config.cargar({"WHATSAPP_TOKEN": "-", "WHATSAPP_PHONE_NUMBER_ID": " 123 "})
    assert c.wa_token == "" and c.wa_phone_number_id == "123" and not c.whatsapp_configurado


def test_secretos_declarados_en_main():
    """Un secreto que el código lee y `main.SECRETOS` no declara no llega al
    runtime: `firebase deploy` solo monta los declarados (lección de `paneles`)."""
    import pathlib
    import re

    raiz = pathlib.Path(__file__).parent.parent
    leidos = set(re.findall(r'_secreto\(e, "([A-Z_]+)"\)', (raiz / "coloquio" / "config.py").read_text()))
    main = (raiz / "main.py").read_text()
    bloque = main[main.index("SECRETOS = ["):main.index("]", main.index("SECRETOS = ["))]
    declarados = set(re.findall(r'"([A-Z_]+)"', bloque))
    assert leidos == declarados
