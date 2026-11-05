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

# R1.18 — el modo de la consulta. `paneles` usa `estricto` por defecto;
# COLOQUIO usa `laxo`, al revés (addendum R1.18): acá un humano filtra después
# por teléfono, y un dudoso que no entra a la lista puede costar el grupo.
ESTRICTO, LAXO = "estricto", "laxo"
MODOS = (LAXO, ESTRICTO)
MODO_POR_DEFECTO = LAXO

# Veredictos por criterio, con los nombres de `paneles` (`verificacion.py`).
CUMPLE, NO_CUMPLE, DUDOSO = "cumple", "no_cumple", "dudoso"
SIN_VERIFICAR, SIN_EVIDENCIA, IRRELEVANTE = "sin_verificar", "sin_evidencia", "irrelevante"

# Motivos de exclusión que se informan (R1.18). `paneles` distingue además
# `irrelevante` y `sin_evidencia_pertinente`; para quien decide son ausencia
# de evidencia —su propio `_combinar()` los trata igual—, así que se cuentan
# como `sin_evidencia`.
MOTIVOS_EXCLUSION = (NO_CUMPLE, DUDOSO, SIN_EVIDENCIA)
_MOTIVO_INFORMADO = {
    NO_CUMPLE: NO_CUMPLE, DUDOSO: DUDOSO, SIN_EVIDENCIA: SIN_EVIDENCIA,
    IRRELEVANTE: SIN_EVIDENCIA, "sin_evidencia_pertinente": SIN_EVIDENCIA,
}


def normalizar_criterio(crudo):
    """Un criterio semántico como lo manda la interfaz: un texto suelto o
    `{texto, duro}`. `peso` y `umbral_distancia` no se aceptan: quedan con
    los valores de `paneles` (R1.18, calibración)."""
    if isinstance(crudo, dict):
        texto, duro = str(crudo.get("texto") or "").strip(), bool(crudo.get("duro"))
    else:
        texto, duro = str(crudo or "").strip(), False
    return {"texto": texto, "duro": duro} if texto else None


def normalizar_criterios(crudos):
    return [c for c in (normalizar_criterio(x) for x in (crudos or [])) if c]


def criterios_para_paneles(filtros, criterios):
    """Arma la lista de criterios de `POST /api/consultas`.

    Cada criterio semántico lleva su `duro`: uno duro **filtra** (quien no lo
    cumple queda afuera en los dos modos); uno no duro **ordena**.
    """
    salida = []
    for dim, dim_paneles in _DIMENSION_PANELES.items():
        valores = [v for v in ((filtros or {}).get(dim) or []) if v]
        if valores:
            salida.append({"tipo": "demografico", "dimension": dim_paneles,
                           "operador": "in", "valor": valores})
    for c in normalizar_criterios(criterios):
        salida.append({"tipo": "semantico", "texto": c["texto"], "duro": c["duro"]})
    return salida


def _detalle(item):
    # `paneles` manda el detalle como `criterios` (y, por compatibilidad,
    # también como `detalle`).
    return item.get("criterios") or item.get("detalle") or []


def _evidencias(item):
    """Por criterio semántico: veredicto, razón y evidencia. Se conservan
    todos los veredictos —también `sin_evidencia` y `sin_verificar`—: lo que
    distingue a un buen candidato de uno que entró de rebote está acá."""
    salida = []
    for d in _detalle(item):
        if d.get("tipo") != "semantico":
            continue
        ev = d.get("evidencia") or {}
        salida.append({
            "criterio": d.get("criterio"),
            "veredicto": d.get("veredicto"),
            "estado": d.get("estado"),
            "razon": d.get("razon"),
            "respuesta": ev.get("valor_texto"),
            "pregunta": ev.get("pregunta_texto"),
            "estudio": ev.get("estudio"),
            "fechaCampo": ev.get("fecha_campo"),
        })
    return salida


def _marcas(item, evidencias):
    """`penalizado`, `verificacionIncompleta` y `confianzaBaja` del candidato.

    Si `paneles` no manda una marca, se deduce de los veredictos, y la duda
    nunca se resuelve a favor: un campo ausente se lee «no se sabe», no
    «todo bien» (contrato v2 de `paneles`).
    """
    veredictos = {e["veredicto"] for e in evidencias}
    penalizado = item.get("penalizado")
    if penalizado is None:
        penalizado = bool(veredictos & {DUDOSO, SIN_EVIDENCIA, IRRELEVANTE})
    incompleta = item.get("verificacion_incompleta")
    if incompleta is None:
        incompleta = SIN_VERIFICAR in veredictos
    confianza_baja = item.get("confianza_baja")
    if confianza_baja is None:
        confianza_baja = item.get("confianza") != "alta"
    confianza_baja = bool(confianza_baja or penalizado or incompleta)
    return bool(penalizado), bool(incompleta), confianza_baja


def resumen_excluidos(crudos):
    """Cuántos dejó afuera el motor y por qué. Solo conteos: los ids de los
    excluidos no le sirven a nadie en la pantalla."""
    por_motivo = {m: 0 for m in MOTIVOS_EXCLUSION}
    otros = 0
    for e in crudos or []:
        motivo = _MOTIVO_INFORMADO.get(e.get("motivo"))
        if motivo:
            por_motivo[motivo] += 1
        else:
            otros += 1
    salida = {"total": len(crudos or []), "porMotivo": por_motivo}
    if otros:
        salida["otros"] = otros
    return salida


def normalizar_resultado(crudo, modo=None):
    """Respuesta de `paneles` → lo que usa COLOQUIO. Solo `id_persona` y
    evidencia: no viaja PII (el motor tampoco la devuelve)."""
    items = []
    for i, item in enumerate(crudo.get("items") or []):
        evidencias = _evidencias(item)
        penalizado, incompleta, confianza_baja = _marcas(item, evidencias)
        items.append({
            "idPersona": str(item.get("id_persona")),
            "puntaje": item.get("puntaje"),
            "confianza": item.get("confianza"),
            "estado": item.get("estado"),
            "rango": i + 1,
            "evidencia": evidencias,
            "penalizado": penalizado,
            "verificacionIncompleta": incompleta,
            "confianzaBaja": confianza_baja,
        })
    return {
        "items": items,
        "modo": crudo.get("modo") or modo,
        "excluidos": resumen_excluidos(crudo.get("excluidos")),
        "degradaciones": crudo.get("degradaciones") or [],
        "puente": crudo.get("puente"),
    }


class MotorSemantico:
    nombre = "motor"
    disponible = False
    motivo = ""

    def consultar(self, filtros, criterios, token, limite=100, modo=MODO_POR_DEFECTO):
        raise NotImplementedError


class MotorNoConfigurado(MotorSemantico):
    nombre = "sin_motor"
    motivo = ("No está configurada la URL de la API de `paneles` "
              "(PANELES_API_URL).")

    def consultar(self, filtros, criterios, token, limite=100, modo=MODO_POR_DEFECTO):
        raise ErrorMotor(self.motivo)


class ErrorMotor(RuntimeError):
    pass


class MotorPanelesHttp(MotorSemantico):
    nombre = "paneles"
    disponible = True

    def __init__(self, url_base, timeout=90):
        self.url = url_base.rstrip("/") + "/consultas"
        self.timeout = timeout

    def consultar(self, filtros, criterios, token, limite=100, modo=MODO_POR_DEFECTO):
        cuerpo = {
            "criterios": criterios_para_paneles(filtros, criterios),
            # Siempre explícito: si no se manda, `paneles` aplica su default
            # (estricto) y descarta a los dudosos sin que nadie se entere.
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
                return normalizar_resultado(json.loads(r.read().decode("utf-8")), modo)
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
    en común: no pretende ser un motor, solo respetar el contrato. Y el
    contrato incluye la combinación: arma la respuesta **cruda** de `paneles`
    —`items` con `criterios`, `penalizado`, `verificacion_incompleta`,
    `confianza`, y `excluidos` con su `motivo`— aplicando las reglas de
    `consultas._combinar()`, y la pasa por `normalizar_resultado()`, igual que
    `MotorPanelesHttp`. Un doble que devolviera ya normalizado probaría un
    camino que producción no recorre.

    Perillas de prueba:
      `veredictos`  {id_persona: veredicto} — fuerza el juicio del verificador
                    (`cumple`, `no_cumple`, `dudoso`) para esa persona.
      `verificacion_caida`  el verificador no respondió: toda evidencia queda
                    `sin_verificar` («verificación incompleta», nunca `dudoso`).
    """

    nombre = "memoria"
    disponible = True

    def __init__(self, corpus=None, falla=None, veredictos=None, verificacion_caida=False):
        self.corpus = corpus or {}
        self.falla = falla
        self.veredictos = veredictos or {}
        self.verificacion_caida = verificacion_caida
        self.llamadas = 0
        self.ultima = None  # el cuerpo que habría ido a `POST /api/consultas`

    @staticmethod
    def _palabras(texto):
        return {p.lower().strip(".,;:¿?¡!") for p in texto.split()}

    def _hallazgo(self, id_persona, texto):
        """La mejor respuesta de la persona para un criterio, o None."""
        buscadas = {p for p in self._palabras(texto) if len(p) > 3}
        mejor, evidencia = 0.0, None
        for r in self.corpus.get(id_persona) or []:
            puntaje = len(buscadas & self._palabras(r["texto"])) / max(len(buscadas), 1)
            if puntaje > mejor:
                mejor, evidencia = puntaje, r
        if mejor <= 0:
            return None
        if self.verificacion_caida:
            veredicto, razon = SIN_VERIFICAR, "El verificador no respondió (motor de prueba)."
        else:
            veredicto = self.veredictos.get(id_persona) or (CUMPLE if mejor >= 0.5 else DUDOSO)
            razon = "Coincidencia de términos (motor de prueba)."
        return {"puntaje": round(mejor, 4), "veredicto": veredicto, "razon": razon,
                "evidencia": {"valor_texto": evidencia["texto"],
                              "pregunta_texto": evidencia.get("pregunta"),
                              "estudio": evidencia.get("estudio"),
                              "fecha_campo": evidencia.get("fecha")}}

    def _combinar(self, criterios, modo):
        """Las reglas de `paneles` (`consultas._combinar`), en chico."""
        estricto = modo == ESTRICTO
        items, excluidos = [], []
        for id_persona in sorted(self.corpus):
            hallazgos = [(c, self._hallazgo(id_persona, c["texto"])) for c in criterios]
            if not any(h for _, h in hallazgos):
                continue  # el recall ni la encontró: no está en el universo
            detalle, excluir = [], None
            for c, h in hallazgos:
                if h is None:
                    detalle.append({"criterio": c["texto"], "tipo": "semantico", "puntaje": 0.0,
                                    "veredicto": SIN_EVIDENCIA, "evidencia": None,
                                    "razon": "No hay ninguna respuesta suya cerca de este criterio."})
                    if c["duro"] or estricto:
                        excluir = excluir or {"criterio": c["texto"], "motivo": SIN_EVIDENCIA}
                    continue
                v = h["veredicto"]
                if v == NO_CUMPLE:
                    h["puntaje"] = 0.0
                    excluir = excluir or {"criterio": c["texto"], "motivo": NO_CUMPLE}
                elif v == DUDOSO and (c["duro"] or estricto):
                    excluir = excluir or {"criterio": c["texto"], "motivo": DUDOSO}
                detalle.append({"criterio": c["texto"], "tipo": "semantico",
                                "puntaje": h["puntaje"], "veredicto": v, "razon": h["razon"],
                                "pendientes_de_verificar": 1 if v == SIN_VERIFICAR else 0,
                                "evidencia": h["evidencia"]})
            if excluir:
                excluidos.append({"id_persona": id_persona, "estado": "descartada", **excluir})
                continue
            penalizado = any(d["veredicto"] in (SIN_EVIDENCIA, DUDOSO) for d in detalle)
            incompleta = any(d.get("pendientes_de_verificar") for d in detalle)
            puntaje = sum(d["puntaje"] for d in detalle) / len(detalle)
            items.append({
                "id_persona": id_persona,
                "estado": "pendiente" if incompleta else "posible" if penalizado else "confirmada",
                "puntaje": round(puntaje, 4),
                "confianza": "baja" if (penalizado or incompleta or puntaje < 0.5) else "alta",
                "penalizado": penalizado,
                "verificacion_incompleta": incompleta,
                "criterios": detalle,
            })
        items.sort(key=lambda i: (-i["puntaje"], i["id_persona"]))
        return items, excluidos

    def consultar(self, filtros, criterios, token, limite=100, modo=MODO_POR_DEFECTO):
        self.llamadas += 1
        self.ultima = {"criterios": criterios_para_paneles(filtros, criterios), "modo": modo,
                       "limite": int(limite)}
        if self.falla:
            raise ErrorMotor(self.falla)
        if modo not in MODOS:
            raise ErrorMotor(f"Modo desconocido: {modo!r}.")
        items, excluidos = self._combinar(normalizar_criterios(criterios), modo)
        crudo = {"modo": modo, "items": items[:limite], "excluidos": excluidos,
                 "degradaciones": [], "puente": None}
        return normalizar_resultado(crudo, modo)


def crear(url_base):
    return MotorPanelesHttp(url_base) if url_base else MotorNoConfigurado()
