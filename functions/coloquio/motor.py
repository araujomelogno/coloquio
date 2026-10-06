"""R1.2 — el criterio semántico usa **el motor de consulta de `paneles`**.

COLOQUIO no reimplementa embeddings, recall, reranking ni verificación: eso
vive en `panel_api/consultas.py`, con su calibración (PRD §5). Y tampoco se
conecta al store semántico: no tiene rol ahí, y no le hace falta.

La vía es la API de `paneles` (`POST /api/consultas`), reenviando el **mismo
ID token** del usuario de COLOQUIO. Como el padrón de Firebase Auth es el
mismo (HANDOFF §1), `paneles` resuelve el rol del usuario y aplica su propio
permiso `consultar`: un usuario que no puede consultar en `paneles` tampoco
puede hacerlo desde acá. Nadie escala privilegios a través de COLOQUIO.

**Degradación explícita.** Si `paneles` no responde, no está configurado o el
usuario no tiene permiso allá, la selección no se cae: se resuelve
demográfica pura y la respuesta lo dice (`degradaciones`). Lo mismo cuando el
segmento no tiene contenido embebido (SPEC §13, riesgo de datos): la
interfaz tiene que decirlo en vez de mostrar un ranking de ruido. La
selección nunca depende de que `paneles` esté corriendo para poder convocar.

**El gate de COLOQUIO se aplica después, y no se delega.** `paneles` filtra
por `uso_semantico`; COLOQUIO además exige `contacto_participacion`, y lo hace
cruzando los ids del ranking contra `v_persona_convocable` (seleccion.py).
"""

import json
import urllib.error
import urllib.request

# Tramo etario y sexo se mandan al motor con los nombres de `paneles`.
_DIMENSION_PANELES = {"sexo": "sexo", "tramoEtario": "tramo_etario", "localidad": "localidad"}


def criterios_para_paneles(filtros, textos):
    """Arma la lista de criterios de `POST /api/consultas`."""
    criterios = []
    for dim, dim_paneles in _DIMENSION_PANELES.items():
        valores = [v for v in ((filtros or {}).get(dim) or []) if v]
        if valores:
            criterios.append({"tipo": "demografico", "dimension": dim_paneles,
                              "operador": "in", "valor": valores})
    for texto in textos:
        texto = (texto or "").strip()
        if texto:
            criterios.append({"tipo": "semantico", "texto": texto})
    return criterios


def _evidencias(item):
    salida = []
    for d in item.get("criterios") or []:
        if d.get("tipo") != "semantico":
            continue
        ev = d.get("evidencia") or {}
        salida.append({
            "criterio": d.get("criterio"),
            "veredicto": d.get("veredicto"),
            "razon": d.get("razon"),
            "respuesta": ev.get("valor_texto"),
            "pregunta": ev.get("pregunta_texto"),
            "estudio": ev.get("estudio"),
            "fechaCampo": ev.get("fecha_campo"),
        })
    return salida


def normalizar_resultado(crudo):
    """Respuesta de `paneles` → lo que usa COLOQUIO. Solo `id_persona` y
    evidencia: no viaja PII (el motor tampoco la devuelve)."""
    items = []
    for i, item in enumerate(crudo.get("items") or []):
        items.append({
            "idPersona": str(item.get("id_persona")),
            "puntaje": item.get("puntaje"),
            "confianza": item.get("confianza"),
            "rango": i + 1,
            "evidencia": _evidencias(item),
             "verificacionIncompleta": item.get("verificacion_incompleta"),

        })
    return {
        "items": items,
        "degradaciones": crudo.get("degradaciones") or [],
        "puente": crudo.get("puente"),
    }


class MotorSemantico:
    nombre = "motor"
    disponible = False
    motivo = ""

    def consultar(self, filtros, textos, token, limite=100, modo="laxo"):
        raise NotImplementedError


class MotorNoConfigurado(MotorSemantico):
    nombre = "sin_motor"
    motivo = ("No está configurada la URL de la API de `paneles` "
              "(PANELES_API_URL).")

    def consultar(self, filtros, textos, token, limite=100, modo="laxo"):
        raise ErrorMotor(self.motivo)


class ErrorMotor(RuntimeError):
    pass


class MotorPanelesHttp(MotorSemantico):
    nombre = "paneles"
    disponible = True

    def __init__(self, url_base, timeout=90):
        self.url = url_base.rstrip("/") + "/consultas"
        self.timeout = timeout

    def consultar(self, filtros, textos, token, limite=100, modo="laxo"):
        cuerpo = {
            "criterios": criterios_para_paneles(filtros, textos),
            "modo": modo,
            "limite": int(limite),
            "top_k": min(int(limite), 100),
        }
        pedido = urllib.request.Request(
            self.url, data=json.dumps(cuerpo).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(pedido, timeout=self.timeout) as r:
                return normalizar_resultado(json.loads(r.read().decode("utf-8")))
        except urllib.error.HTTPError as error:
            try:
                detalle = json.loads(error.read().decode("utf-8"))
                mensaje = detalle.get("mensaje") or str(error)
            except Exception:  # noqa: BLE001
                mensaje = str(error)
            if error.code in (401, 403):
                mensaje = ("`paneles` no te habilita a correr consultas "
                           f"semánticas ({mensaje}).")
            raise ErrorMotor(mensaje)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ErrorMotor(f"No se pudo llegar al motor de `paneles`: {error}")


class MotorMemoria(MotorSemantico):
    """Para pruebas y el servidor local.

    `corpus`: {id_persona: [{texto, estudio, pregunta}]}. Rankea por palabras
    en común: no pretende ser un motor, solo respetar el contrato.
    """

    nombre = "memoria"
    disponible = True

    def __init__(self, corpus=None, falla=None):
        self.corpus = corpus or {}
        self.falla = falla
        self.llamadas = 0

    def consultar(self, filtros, textos, token, limite=100, modo="laxo"):
        self.llamadas += 1
        if self.falla:
            raise ErrorMotor(self.falla)
        palabras = {p.lower().strip(".,;:¿?¡!") for t in textos for p in t.split() if len(p) > 3}
        items = []
        for id_persona, respuestas in self.corpus.items():
            mejor, evidencia = 0.0, None
            for r in respuestas:
                propias = {p.lower().strip(".,;:¿?¡!") for p in r["texto"].split()}
                comun = len(palabras & propias)
                puntaje = comun / max(len(palabras), 1)
                if puntaje > mejor:
                    mejor, evidencia = puntaje, r
            if mejor > 0:
                items.append({
                    "idPersona": id_persona,
                    "puntaje": round(mejor, 4),
                    "confianza": "alta" if mejor >= 0.5 else "baja",
                    "evidencia": [{
                        "criterio": " / ".join(textos),
                        "veredicto": "cumple" if mejor >= 0.5 else "dudoso",
                        "razon": "Coincidencia de términos (motor de prueba).",
                        "respuesta": evidencia["texto"],
                        "pregunta": evidencia.get("pregunta"),
                        "estudio": evidencia.get("estudio"),
                        "fechaCampo": evidencia.get("fecha"),
                    }],
                })
        items.sort(key=lambda i: -i["puntaje"])
        for i, item in enumerate(items):
            item["rango"] = i + 1
        return {"items": items[:limite], "degradaciones": [], "puente": None}


def crear(url_base):
    return MotorPanelesHttp(url_base) if url_base else MotorNoConfigurado()
