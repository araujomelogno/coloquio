"""Datos de prueba: un panel chico, un corpus semántico y un canal falso.

Lo usan las pruebas y el servidor local (`scripts/servidor_local.py`). Los
datos de contacto son ficticios y viven solo en la `BovedaMemoria`, como en la
bóveda real: nunca en el store de COLOQUIO.
"""

import datetime as dt
import itertools
import uuid

from coloquio import auth, boveda, contexto, motor, store

NS = uuid.UUID("7b1e0c1a-2f4e-4c55-9a51-000000c01001")
LOCALIDADES = ("Montevideo", "Canelones", "Maldonado")
TRAMOS = ("18-24", "25-34", "35-44", "45-54")


def id_de(n):
    return str(uuid.uuid5(NS, f"persona-{n}"))


def panel(n=96):
    """`n` personas repartidas en sexo × tramo × localidad. Las múltiplos de
    17 no consintieron contacto: no deben aparecer nunca."""
    personas = {}
    combinaciones = itertools.cycle(itertools.product(("F", "M"), TRAMOS, LOCALIDADES))
    for i in range(n):
        sexo, tramo, loc = next(combinaciones)
        personas[id_de(i)] = {
            "segmento": {"sexo": sexo, "tramoEtario": tramo, "localidad": loc},
            "edad": {"18-24": 21, "25-34": 30, "35-44": 40, "45-54": 50}[tramo],
            "consiente": i % 17 != 0,
            "celular": f"099 {100 + i:03d} {200 + i:03d}",
            "email": f"persona{i}@ejemplo.test",
        }
    return personas


def corpus(personas):
    """Respuestas abiertas de encuestas anteriores (lo que el motor rankea)."""
    frases = [
        "Tomo cerveza artesanal los fines de semana con amigos",
        "Prefiero el vino tinto en las comidas",
        "Dejé las bebidas azucaradas por salud",
        "Compro cerveza industrial en el supermercado",
        "El mate es lo único que tomo todos los días",
    ]
    salida = {}
    for i, pid in enumerate(personas):
        salida[pid] = [{"texto": frases[i % len(frases)], "estudio": "Hábitos de consumo 2025",
                        "pregunta": "¿Qué bebidas consumís habitualmente?", "fecha": "2025-11-01"}]
    return salida


class CanalFalso:
    """Imita la Cloud API: registra envíos, puede fallar a pedido."""

    configurado = True

    def __init__(self):
        self.enviados = []
        self.falla = None
        self._n = 0

    def _wamid(self):
        self._n += 1
        return f"wamid.PRUEBA{self._n:04d}"

    def enviar_plantilla(self, celular, plantilla, idioma, variables, botones=()):
        from coloquio.whatsapp import ErrorCanal

        if self.falla:
            raise ErrorCanal(self.falla)
        wamid = self._wamid()
        self.enviados.append({"tipo": "plantilla", "plantilla": plantilla, "botones": list(botones),
                              "wamid": wamid, "variables": list(variables)})
        return wamid

    def enviar_texto_con_botones(self, celular, texto, botones):
        from coloquio.whatsapp import ErrorCanal

        if self.falla:
            raise ErrorCanal(self.falla)
        wamid = self._wamid()
        self.enviados.append({"tipo": "texto", "botones": [b[1] for b in botones], "wamid": wamid})
        return wamid


class Reloj:
    def __init__(self, inicio=None):
        self.t = inicio or dt.datetime(2026, 10, 1, 12, 0, tzinfo=dt.timezone.utc)

    def __call__(self):
        return self.t

    def avanzar(self, **kw):
        self.t = self.t + dt.timedelta(**kw)


def armar_contexto(n=96, personas=None, st=None):
    personas = personas or panel(n)
    st = st or store.StoreMemoria()
    bov = boveda.BovedaMemoria(personas)
    mot = motor.MotorMemoria(corpus(personas))
    canal = CanalFalso()
    reloj = Reloj()
    ctx = contexto.Contexto(st, boveda=bov, motor=mot, canal_wa=canal, reloj=reloj,
                            fabrica_boveda=lambda: bov)
    ctx._boveda = None  # perezosa, para poder comprobar que no se abrió
    ctx._fabrica_boveda = lambda: bov
    ctx.bov = bov
    return ctx


def actor(roles=("coordinador", "investigador", "administrador"), uid="u-coord",
          email="coordinadora@equipos.com.uy"):
    return auth.Actor(uid=uid, email=email, roles=roles, nombre="Coordinadora", token="tok")
