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
EDAD_DEL_TRAMO = {"18-24": 21, "25-34": 30, "35-44": 40, "45-54": 50}


def _cats(*pares, inactivas=()):
    return ([{"clave": c, "etiqueta": e, "orden": (n + 1) * 10} for n, (c, e) in enumerate(pares)]
            + [{"clave": c, "etiqueta": c, "orden": 900, "activo": False} for c in inactivas])


def catalogo():
    """El catálogo de la bóveda ficticia: un atributo de cada tipo, uno dado
    de baja, una categoría dada de baja y uno marcado especial. Las claves
    viven acá, en los datos de prueba, y en ningún lado del código de
    COLOQUIO."""
    return [
        {"clave": "sexo", "etiqueta": "Sexo", "tipo": "categorico", "orden": 10,
         "categorias": _cats(("F", "Femenino"), ("M", "Masculino"), ("X", "Otro / no binario"))},
        {"clave": "tramo_etario", "etiqueta": "Tramo etario", "tipo": "derivado", "orden": 20,
         "derivacion": "tramo_de_edad",
         "categorias": _cats(*[(t, t) for t in ("<18", "18-24", "25-34", "35-44", "45-54", "55-64", "65+")])},
        {"clave": "edad", "etiqueta": "Edad", "tipo": "derivado", "orden": 30,
         "derivacion": "edad_efectiva", "categorias": []},
        {"clave": "localidad", "etiqueta": "Localidad", "tipo": "categorico", "orden": 40,
         "categorias": _cats(*[(x, x) for x in ("Canelones", "Maldonado", "Montevideo", "Salto")])},
        {"clave": "nivel_educativo", "etiqueta": "Nivel educativo", "tipo": "categorico", "orden": 50,
         "categorias": _cats(("primaria", "Primaria"), ("secundaria", "Secundaria"),
                             ("terciario", "Terciario"), ("posgrado", "Posgrado"),
                             ("sin_dato", "Sin dato"), inactivas=("terciaria",))},
        {"clave": "hijos", "etiqueta": "Cantidad de hijos", "tipo": "numerico", "orden": 60,
         "categorias": []},
        {"clave": "ultima_compra", "etiqueta": "Última compra online", "tipo": "fecha", "orden": 70,
         "categorias": []},
        {"clave": "religion", "etiqueta": "Religión", "tipo": "categorico", "orden": 80,
         "es_especial": True,
         "categorias": _cats(("catolica", "Católica"), ("ninguna", "Ninguna"), ("otra", "Otra"))},
        {"clave": "nse_2019", "etiqueta": "NSE (2019)", "tipo": "categorico", "orden": 90,
         "activo": False, "categorias": _cats(("alto", "Alto"), ("bajo", "Bajo"))},
    ]


PANELES = {"panel-general": "Panel general", "panel-consumo": "Panel de consumo",
           "panel-salud": "Panel de salud"}
NOMBRES = ("Ana", "Bruno", "Carla", "Diego", "Elena", "Fabián", "Gimena", "Hugo")
APELLIDOS = ("Pereyra", "Silvera", "Olivera", "Techera", "Acosta", "Benítez")


def id_de(n):
    return str(uuid.uuid5(NS, f"persona-{n}"))


def nombre_de(n):
    return f"{NOMBRES[n % len(NOMBRES)]} {APELLIDOS[n % len(APELLIDOS)]} {n:02d}"


def panel(n=96):
    """`n` personas repartidas en sexo × tramo × localidad. Las múltiplos de
    17 no consintieron contacto: no deben aparecer nunca. Sí consintieron el
    uso semántico, así que siguen en `v_persona_convocable` (con otra
    finalidad), como en la bóveda real.

    La edad sale de tres fuentes, como en `f_atributo_persona()`: fecha de
    nacimiento (casi todas), edad declarada envejecida (i % 7 == 3) o, sin
    ninguna de las dos, el tramo cargado (i % 11 == 5: no tienen edad)."""
    personas = {}
    combinaciones = itertools.cycle(itertools.product(("F", "M"), TRAMOS, LOCALIDADES))
    for i in range(n):
        sexo, tramo, loc = next(combinaciones)
        edad = EDAD_DEL_TRAMO[tramo]
        atributos = {"sexo": sexo, "localidad": loc}
        p = {
            "consiente": i % 17 != 0,
            "finalidades": ["uso_semantico"],
            "estado": "activa",
            "enroladoEn": dt.datetime(2024, 1 + i % 12, 1, 9, 0, tzinfo=dt.timezone.utc),
            "paneles": ([{"panelId": "panel-general"}]
                        + ([{"panelId": "panel-consumo"}] if i % 2 == 0 else [])
                        + ([{"panelId": "panel-salud", "estado": "baja"}] if i % 9 == 0 else [])),
            "nombre": nombre_de(i),
            "celular": f"099 {100 + i:03d} {200 + i:03d}",
            "email": f"persona{i}@ejemplo.test",
        }
        if i % 11 == 5:
            atributos["tramo_etario"] = tramo
        elif i % 7 == 3:
            p["edadDeclarada"] = {"valor": edad - 1, "referencia": dt.date(2025, 10, 1)}
        else:
            p["fechaNacimiento"] = dt.date(2026 - edad, 3, 15)
        # Ausente (i % 4 == 0) no es lo mismo que «sin dato» declarado.
        if i % 4:
            atributos["nivel_educativo"] = ("secundaria", "terciario", "sin_dato")[i % 4 - 1]
        if i % 5:
            atributos["hijos"] = i % 3
        if i % 2 == 0:
            atributos["ultima_compra"] = dt.date(2025, 1 + i % 12, 10)
        if i % 6 in (0, 1):
            atributos["religion"] = ("catolica", "ninguna")[i % 6]
        p["atributos"] = atributos
        personas[id_de(i)] = p
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
    reloj = Reloj()
    bov = boveda.BovedaMemoria(personas, reloj=reloj, catalogo=catalogo(), paneles=dict(PANELES))
    mot = motor.MotorMemoria(corpus(personas))
    canal = CanalFalso()
    ctx = contexto.Contexto(st, boveda=bov, motor=mot, canal_wa=canal, reloj=reloj,
                            fabrica_boveda=lambda: bov)
    ctx._boveda = None  # perezosa, para poder comprobar que no se abrió
    ctx._fabrica_boveda = lambda: bov
    ctx.bov = bov
    return ctx


def actor(roles=("coordinador", "investigador", "administrador"), uid="u-coord",
          email="coordinadora@equipos.com.uy"):
    return auth.Actor(uid=uid, email=email, roles=roles, nombre="Coordinadora", token="tok")
