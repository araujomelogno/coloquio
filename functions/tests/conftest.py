import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fabrica  # noqa: E402
from coloquio import ruteo  # noqa: E402


def _store_emulador():
    """Con FIRESTORE_EMULATOR_HOST, las pruebas corren contra el emulador de
    Firestore (base con nombre `coloquio`), con la implementación real."""
    import urllib.request

    from coloquio import store

    host = os.environ["FIRESTORE_EMULATOR_HOST"]
    proyecto = "demo-coloquio"
    urllib.request.urlopen(urllib.request.Request(
        f"http://{host}/emulator/v1/projects/{proyecto}/databases/coloquio/documents",
        method="DELETE"))
    return store.StoreFirestore.conectar(proyecto, "coloquio")


@pytest.fixture
def ctx():
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        return fabrica.armar_contexto(st=_store_emulador())
    return fabrica.armar_contexto()


@pytest.fixture
def yo():
    return fabrica.actor()


class Api:
    def __init__(self, ctx, actor):
        self.ctx = ctx
        self.actor = actor

    def __call__(self, metodo, camino, cuerpo=None, consulta=None, actor=None):
        status, respuesta = ruteo.despachar(metodo, camino, cuerpo or {}, consulta or {},
                                            actor or self.actor, self.ctx)
        return respuesta


@pytest.fixture
def api(ctx, yo):
    return Api(ctx, yo)


CUOTAS = [
    {"dimension": "sexo", "categoria": "F", "objetivo": 4},
    {"dimension": "sexo", "categoria": "M", "objetivo": 4},
    {"dimension": "tramoEtario", "categoria": "25-34", "objetivo": 4},
    {"dimension": "tramoEtario", "categoria": "35-44", "objetivo": 4},
]


@pytest.fixture
def sesion(api, ctx):
    """Estudio de bebidas con pauta y una sesión de 8 con ratio 1.5 (12 invitados)."""
    regalo = api("POST", "/cuali/regalos", {"nombre": "Orden de compra $1500", "valor": 1500})
    estudio = api("POST", "/cuali/estudios", {"nombre": "Cervezas 2026", "cliente": "Cliente X",
                                              "categoria": "bebidas",
                                              "descripcion": "hábitos de consumo de cerveza"})
    api("POST", f"/cuali/estudios/{estudio['id']}/pauta", {"topicos": [
        {"titulo": "Caldeamiento", "objetivo": "Romper el hielo", "minutos": 10},
        {"titulo": "Ocasiones de consumo", "objetivo": "Mapear ocasiones", "minutos": 30,
         "repreguntas": ["¿Con quién?", "¿Dónde?"]},
    ]})
    s = api("POST", "/cuali/sesiones", {
        "estudioId": estudio["id"], "nombre": "Grupo 1", "tipo": "grupo",
        "fecha": "2026-10-08T19:00", "lugar": "Sala Equipos, Pocitos",
        "cupoObjetivo": 8, "ratioSobrerreclutamiento": 1.5, "cuotas": CUOTAS,
        "regaloId": regalo["id"]})
    s["estudio"] = estudio
    s["regalo"] = regalo
    return s
