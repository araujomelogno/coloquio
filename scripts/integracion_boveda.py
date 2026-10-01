#!/usr/bin/env python3
"""Integración con la bóveda real: `BovedaPostgres` conectado como `coloquio_app`.

Prueba el contrato de la Fase 5 y de R5.2.a contra las migraciones de `paneles`
(no contra el doble en memoria): gate de la vista, rechazo sin declaración,
`declarar_convocatoria()` con tope, gate y actualización, contacto auditado con
el email humano, y el flujo invitar → contacto del dominio.

Contra el cluster de pruebas de `paneles` (arma el escenario con el dueño y lo
borra al final):

    source ../paneles/scripts/pg_pruebas.sh
    python3 scripts/integracion_boveda.py

Variables: `DSN_BOVEDA` (dueño) y `DSN_BOVEDA_COLOQUIO` (el rol del consumidor).
Escribe filas de prueba: **no correrlo contra producción**.
"""
import datetime as dt
import os
import sys
import uuid

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "functions"))
sys.path.insert(0, os.path.join(RAIZ, "functions", "tests"))
import psycopg
from psycopg.rows import dict_row
from coloquio import auth, boveda, contexto, motor, ruteo, store
from coloquio.errores import ContactoRechazado, ConvocatoriaRechazada, DatosInvalidos
import fabrica

DUENO = os.environ.get("DSN_BOVEDA", "postgresql://postgres@localhost:55432/paneles_boveda")
COLO = os.environ.get("DSN_BOVEDA_COLOQUIO", "postgresql://coloquio_app@localhost:55432/paneles_boveda")
d = psycopg.connect(DUENO, row_factory=dict_row, autocommit=True)
marca = f"INTEG-COLOQUIO-{uuid.uuid4().hex[:6]}"
with d.cursor() as c:
    c.execute("insert into texto_consentimiento (finalidad, version, cuerpo) values ('contacto_participacion', %s, 'x') on conflict do nothing", (marca,))
    ids = []
    for i, cons in enumerate((True, False)):
        c.execute("insert into persona (documento, nombre, celular, email, estado) values (%s,'Integ',%s,%s,'activa') returning id_persona",
                  (f"{marca}-{i}", f"+59899000{i}{i}{i}", f"{marca}{i}@ej.invalid"))
        pid = str(c.fetchone()["id_persona"]); ids.append(pid)
        if cons:
            c.execute("insert into consentimiento (id_persona, finalidad, estado, version_texto) values (%s,'contacto_participacion','vigente',%s)", (pid, marca))
con, sin = ids
b = boveda.BovedaPostgres(dsn=COLO)
ok = lambda m: print("  ✓", m)
try:
    assert b.sistema() == "coloquio"; ok("sistema_de_la_conexion() = coloquio")
    assert con in {x["idPersona"] for x in b.convocables(ids=ids)} and sin not in {x["idPersona"] for x in b.convocables(ids=ids)}
    ok("v_persona_convocable: solo quien consintió")
    try: b.contacto(con, "celular", "coord@equipos.com.uy"); raise SystemExit("debió rechazar")
    except ContactoRechazado as e: assert "convocatoria activa" in e.mensaje; ok("sin declaración: rechazado")
    ahora = dt.datetime.now(dt.timezone.utc)
    b.declarar_convocatoria(con, "sesion-A", ahora + dt.timedelta(days=2)); ok("declarar_convocatoria() aceptada")
    b.declarar_convocatoria(con, "sesion-A", ahora + dt.timedelta(days=5))
    with d.cursor() as c:
        c.execute("select count(*) n, max(vence_en) v from convocatoria_externa where id_persona=%s", (con,)); r = c.fetchone()
    assert r["n"] == 1 and r["v"] > ahora + dt.timedelta(days=4); ok("misma referencia: actualiza, no duplica")
    dato = b.contacto(con, "celular", "coord@equipos.com.uy"); assert dato.endswith("000000"); ok("con declaración: entrega el contacto")
    with d.cursor() as c:
        c.execute("select actor_uid, sistema from reidentificacion where id_persona=%s order by creado_en desc limit 1", (con,)); r = c.fetchone()
    assert r["actor_uid"] == "coord@equipos.com.uy" and r["sistema"] == "coloquio"; ok("auditoría con el email humano, sistema coloquio")
    try: b.declarar_convocatoria(con, "sesion-B", ahora + dt.timedelta(days=61)); raise SystemExit("tope")
    except DatosInvalidos as e: ok("tope de 60 días: " + e.mensaje[:60])
    try: b.declarar_convocatoria(sin, "sesion-A", ahora + dt.timedelta(days=2)); raise SystemExit("gate")
    except ConvocatoriaRechazada: ok("sin consentimiento: ConvocatoriaRechazada")
    b.cerrar()

    # ── El dominio entero con la bóveda real ──
    st = store.StoreMemoria()
    reloj = lambda: dt.datetime.now(dt.timezone.utc)
    ctx = contexto.Contexto(st, motor=motor.MotorMemoria({}), canal_wa=fabrica.CanalFalso(), reloj=reloj,
                            fabrica_boveda=lambda: boveda.BovedaPostgres(dsn=COLO))
    yo = auth.Actor("u1", "coord@equipos.com.uy", auth.ROLES, "Coord", token="t")
    api = lambda m, p, body=None, q=None: ruteo.despachar(m, p, body or {}, q or {}, yo, ctx)[1]
    e = api("POST", "/cuali/estudios", {"nombre": "Integ", "categoria": "bebidas"})
    api("POST", f"/cuali/estudios/{e['id']}/pauta", {"topicos": [{"titulo": "T", "minutos": 10}]})
    fecha = (dt.datetime.now() + dt.timedelta(days=4)).strftime("%Y-%m-%dT19:00")
    s = api("POST", "/cuali/sesiones", {"estudioId": e["id"], "fecha": fecha, "lugar": "Sala", "cupoObjetivo": 2})
    r = api("POST", f"/cuali/sesiones/{s['id']}/convocatorias", {"candidatos": ids})
    assert r["incorporados"] == [con] and r["sinConsentimientoVigente"] == [sin]
    r = api("POST", f"/cuali/sesiones/{s['id']}/invitacion", {"ids": [con]})
    assert r["invitados"] == [con]; ok("dominio: invitar declara con la sesión como referencia")
    with d.cursor() as c:
        c.execute("select referencia from convocatoria_externa where id_persona=%s and referencia=%s", (con, s["id"])); assert c.fetchone()
    k = api("GET", f"/cuali/convocatorias/{s['id']}/{con}/contacto", q={"canal": "email"})
    assert k["dato"].endswith("@ej.invalid"); ok("dominio: el embudo lee el contacto")
    ctx.cerrar()
finally:
    with d.cursor() as c:
        for pid in ids:
            c.execute("delete from reidentificacion where id_persona=%s", (pid,))
            c.execute("delete from persona where id_persona=%s", (pid,))
        c.execute("delete from texto_consentimiento where version=%s", (marca,))
print("integración OK")
