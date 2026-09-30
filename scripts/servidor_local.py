#!/usr/bin/env python3
"""Servidor local de COLOQUIO: la app y la API reales, con stores en memoria.

    python3 scripts/servidor_local.py            # http://localhost:8765
    python3 scripts/servidor_local.py --puerto 9000 --vacio

Sirve `web/public` y rutea `/api/cuali/**` a `coloquio.ruteo` —el mismo código
que corre en Cloud Functions— con `StoreMemoria`, `BovedaMemoria` (un panel
ficticio de 96 personas) y `MotorMemoria`. No toca Firestore, ni la bóveda, ni
Meta. El ingreso es por selección de usuario de prueba.

Sirve para recorrer la interfaz, hacer demos y probar con Playwright. No es un
entorno de producción.
"""

import argparse
import datetime as dt
import http.server
import json
import os
import sys
import urllib.parse

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "functions"))
sys.path.insert(0, os.path.join(RAIZ, "functions", "tests"))

import fabrica  # noqa: E402
from coloquio import auth, ruteo  # noqa: E402
from coloquio.errores import ErrorApi  # noqa: E402

USUARIOS = {
    "u-coord": {"nombre": "Carla Coordinadora", "email": "coordinacion@equipos.com.uy",
                "roles": ["coordinador"], "rol": "operaciones"},
    "u-inv": {"nombre": "Iván Investigador", "email": "investigacion@equipos.com.uy",
              "roles": ["investigador"], "rol": "analista"},
    "u-admin": {"nombre": "Ana Administradora", "email": "admin@equipos.com.uy",
                "roles": ["administrador", "coordinador", "investigador"], "rol": "admin"},
}


def sembrar(ctx):
    """Un estudio con pauta y una sesión lista para seleccionar, y memoria de
    fatiga para que el filtro tenga algo que mostrar."""
    a = auth.Actor("u-admin", "admin@equipos.com.uy", USUARIOS["u-admin"]["roles"], "Ana")

    def api(metodo, camino, cuerpo=None):
        return ruteo.despachar(metodo, camino, cuerpo or {}, {}, a, ctx)[1]

    r1 = api("POST", "/cuali/regalos", {"nombre": "Orden de compra $1.500", "valor": 1500})
    api("POST", "/cuali/regalos", {"nombre": "Canasta de productos", "valor": 2000})
    e = api("POST", "/cuali/estudios", {"nombre": "Cervezas artesanales 2026", "cliente": "Cervecería del Sur",
                                        "categoria": "bebidas",
                                        "descripcion": "hábitos de consumo de cerveza"})
    api("POST", f"/cuali/estudios/{e['id']}/pauta", {"topicos": [
        {"titulo": "Caldeamiento", "objetivo": "Presentación y rutina de consumo", "minutos": 10},
        {"titulo": "Ocasiones de consumo", "objetivo": "Mapear cuándo, dónde y con quién",
         "minutos": 30, "repreguntas": ["¿Qué cambia un fin de semana?", "¿Quién elige la cerveza?"]},
        {"titulo": "Marcas y artesanal", "objetivo": "Percepción de lo artesanal frente a lo industrial",
         "minutos": 30, "repreguntas": ["¿Qué hace que una cerveza sea artesanal?"]},
        {"titulo": "Cierre", "objetivo": "Síntesis y recomendación", "minutos": 10},
    ]})
    ahora = ctx.ahora()
    fecha = (ahora + dt.timedelta(days=3)).astimezone(dt.timezone(dt.timedelta(hours=-3)))
    api("POST", "/cuali/sesiones", {
        "estudioId": e["id"], "nombre": "Grupo 1 — 25 a 44", "tipo": "grupo",
        "fecha": fecha.replace(hour=19, minute=0, tzinfo=None).isoformat(timespec="minutes"),
        "lugar": "Sala Equipos, Pocitos", "cupoObjetivo": 8, "ratioSobrerreclutamiento": 1.5,
        "regaloId": r1["id"], "cuotas": [
            {"dimension": "sexo", "categoria": "F", "objetivo": 4},
            {"dimension": "sexo", "categoria": "M", "objetivo": 4},
            {"dimension": "tramoEtario", "categoria": "25-34", "objetivo": 4},
            {"dimension": "tramoEtario", "categoria": "35-44", "objetivo": 4}]})
    e2 = api("POST", "/cuali/estudios", {"nombre": "Banca digital", "cliente": "Banco X",
                                         "categoria": "banca", "descripcion": "uso de la app del banco"})
    del e2
    # Memoria de fatiga: tres personas que ya estuvieron en un grupo de bebidas.
    api("POST", "/cuali/historico", {
        "categoria": "bebidas", "fecha": (ahora - dt.timedelta(days=60)).date().isoformat() + "T19:00",
        "etiqueta": "Grupo refrescos (importado)",
        "idPersonas": [fabrica.id_de(i) for i in (1, 4, 7)]})


class Manejador(http.server.SimpleHTTPRequestHandler):
    ctx = None

    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(RAIZ, "web", "public"), **k)

    def log_message(self, formato, *args):
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("%s\n" % (formato % args))

    def _json(self, status, cuerpo):
        datos = json.dumps(cuerpo, ensure_ascii=False,
                           default=lambda v: v.isoformat() if isinstance(v, dt.datetime) else str(v))
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(datos.encode("utf-8"))

    def _api(self, metodo):
        url = urllib.parse.urlparse(self.path)
        camino = url.path[len("/api"):]
        consulta = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        largo = int(self.headers.get("Content-Length") or 0)
        try:
            cuerpo = json.loads(self.rfile.read(largo) or b"{}") if largo else {}
        except json.JSONDecodeError:
            cuerpo = {}
        if metodo == "GET" and ruteo.normalizar(camino) == "/entorno":
            return self._json(200, {"sistema": "coloquio", "modo": "local", "whatsapp": True,
                                    "motorSemantico": "memoria",
                                    "usuariosLocales": [{"uid": k, **v} for k, v in USUARIOS.items()]})
        uid = self.headers.get("X-Usuario-Local")
        if ruteo.es_publica(metodo, camino):
            actor = auth.Actor(None)
        elif uid not in USUARIOS:
            return self._json(401, {"error": "no_autenticado", "mensaje": "Elegí un usuario de prueba."})
        else:
            u = USUARIOS[uid]
            actor = auth.Actor(uid, u["email"], u["roles"], u["nombre"], token="local")
        try:
            status, respuesta = ruteo.despachar(metodo, camino, cuerpo, consulta, actor, self.ctx)
            self._json(status, respuesta)
        except ErrorApi as error:
            self._json(error.status, error.como_dict())
        except Exception as error:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            self._json(500, {"error": "interno", "mensaje": str(error)})

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/api/"):
            return self._api("GET")
        if "." not in os.path.basename(urllib.parse.urlparse(self.path).path):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        self._api("POST")

    def do_PUT(self):  # noqa: N802
        self._api("PUT")

    def do_PATCH(self):  # noqa: N802
        self._api("PATCH")

    def do_DELETE(self):  # noqa: N802
        self._api("DELETE")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--puerto", type=int, default=8765)
    p.add_argument("--vacio", action="store_true", help="sin estudio de ejemplo")
    args = p.parse_args()
    ctx = fabrica.armar_contexto()
    ctx.reloj = lambda: dt.datetime.now(dt.timezone.utc)
    # La bóveda de prueba vence las declaraciones de convocatoria con el mismo reloj.
    ctx.bov.reloj = ctx.reloj
    ctx.padron = {k: {"nombre": v["nombre"], "email": v["email"], "rol": v["rol"]} for k, v in USUARIOS.items()}
    # Los roles de los usuarios de prueba, como si un administrador los hubiera asignado.
    for uid, u in USUARIOS.items():
        ctx.store.set(f"rolUsuario/{uid}", {"roles": u["roles"]})
    if not args.vacio:
        sembrar(ctx)
    Manejador.ctx = ctx
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", args.puerto), Manejador)
    print(f"COLOQUIO local en http://localhost:{args.puerto}  (Ctrl+C para salir)")
    servidor.serve_forever()


if __name__ == "__main__":
    main()
