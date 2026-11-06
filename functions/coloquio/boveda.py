"""Acceso a la bóveda de `paneles`, **solo por su superficie para COLOQUIO**.

COLOQUIO se conecta como `coloquio-app@gestion-paneles.iam` (miembro del rol
de grupo `coloquio_app`) con autenticación IAM de Cloud SQL. La base le
permite exactamente esto (HANDOFF §2; `boveda/0014`, `0016`, `0021`, `0034`):

    lectura    v_persona_convocable, v_fatiga_panelista, v_finalidad,
               v_texto_consentimiento_activo, v_atributo_catalogo
    ejecución  declarar_convocatoria(), contacto_para_convocatoria(),
               mis_borrados_pendientes(), confirmar_borrado(),
               reportar_error_de_borrado(), sistema_de_la_conexion(),
               f_persona_convocable_filtrada(), atributos_de_personas(),
               ficha_candidato(), identificar_candidatos()

Todo lo demás da `permission denied`, y es por diseño. Este módulo no intenta
leer `persona`, `consentimiento` ni `participacion`, y **no escribe** nada
fuera de lo que esas funciones hacen por su cuenta (DoD 11):
`declarar_convocatoria()` (R5.2.a) y la auditoría que escriben
`contacto_para_convocatoria()` e `identificar_candidatos()`.

Reglas que este módulo hace cumplir y que no conviene reimplementar en otro
lado:

* **El gate de consentimiento es la bóveda.** Toda lista de candidatos sale de
  `f_persona_convocable_filtrada('contacto_participacion', …)` o de
  `v_persona_convocable` con `= any(finalidades)`. No hay un `if` en Python
  que decida quién consintió (R1.2).
* **Ningún atributo tiene nombre acá** (R1.14). El vocabulario es
  `v_atributo_catalogo`; los filtros viajan como `{clave: condición}` y la
  bóveda los valida: una clave, un operador o una categoría desconocidos son
  error, nunca un filtro que no se aplicó.
* **`p_actor` es el email del usuario humano** que pidió el contacto o la
  identificación, siempre (HANDOFF §3). Sin él no se llama.
* **La PII no se guarda.** `contacto()` e `identificar()` la devuelven y
  listo; ni se loguea ni se cachea (R1.12, R1.17).
"""

import contextlib
import datetime as dt
import json
import threading

from .errores import (
    ContactoRechazado, ConvocatoriaRechazada, DatosInvalidos, NoEncontrado,
    ServicioNoDisponible,
)

FINALIDAD_CONTACTO = "contacto_participacion"
# R1.17 — el motivo de auditoría de la selección (`boveda/0034`): separa «lo
# miró para elegir» de «lo miró para llamar» (`convocatoria`).
MOTIVO_SELECCION = "seleccion_cuali"

# R5.2.a — la bóveda rechaza una declaración que venza a más de 60 días.
TOPE_DECLARACION_DIAS = 60
# `boveda/0034`: topes de cada función. Los repite acá solo para partir los
# pedidos que los superan; quien rechaza es la bóveda.
TOPE_ATRIBUTOS = 500
TOPE_IDENTIFICAR = 200
TOPE_FILTRADA = 5000

# SQLSTATE con que la superficie rechaza.
_INVALIDO, _TOPE, _NO_ENCONTRADO, _SIN_PRIVILEGIO = "22023", "54000", "P0002", "42501"


class ErrorSQL(Exception):
    """Lo que la bóveda contestó al rechazar: el SQLSTATE y su mensaje.

    `BovedaPostgres` lo arma desde el error del driver y `BovedaMemoria` lo
    levanta igual que la función real, así la traducción a errores de la API
    es una sola y la prueban los dos.
    """

    def __init__(self, sqlstate, mensaje):
        super().__init__(mensaje)
        self.sqlstate = sqlstate
        self.mensaje = mensaje


def _traducir(error, contexto):
    if error.sqlstate in (_INVALIDO, _TOPE):
        return DatosInvalidos(f"La bóveda rechazó {contexto}: {error.mensaje}")
    if error.sqlstate == _NO_ENCONTRADO:
        return NoEncontrado(error.mensaje)
    return error


def _fecha_iso(valor):
    if valor is None or isinstance(valor, str):
        return valor
    return valor.isoformat()


def _numero(valor):
    if valor is None:
        return None
    n = float(valor)
    return int(n) if n.is_integer() else n


class Boveda:
    """La interfaz que usa el dominio. Ver `BovedaPostgres` y `BovedaMemoria`.

    Cada objeto de la superficie es una primitiva (`_catalogo`, `_filtrada`,
    …) que devuelve las filas tal como las da la base; los métodos públicos
    validan, parten en lotes, traducen errores y pasan a la forma de la API.
    Así la conversión es una sola, y las pruebas la ejercitan con el doble.
    """

    nombre = "boveda"

    # ── primitivas: una por objeto de la superficie ──
    def _catalogo(self):
        raise NotImplementedError

    def _filtrada(self, finalidad, filtros, limite):
        raise NotImplementedError

    def _vigentes(self, ids):
        raise NotImplementedError

    def _atributos(self, ids, momento):
        raise NotImplementedError

    def _ficha(self, id_persona, momento):
        raise NotImplementedError

    def _identificar(self, ids, referencia, actor, motivo):
        raise NotImplementedError

    # ── R1.14 · el vocabulario ──
    def catalogo(self):
        """Atributos activos con sus categorías activas, en orden."""
        salida = []
        for f in self._catalogo():
            categorias = f.get("categorias") or []
            if isinstance(categorias, str):
                categorias = json.loads(categorias)
            salida.append({
                "clave": f["clave"], "etiqueta": f["etiqueta"], "tipo": f["tipo"],
                "orden": f.get("orden"), "esEspecial": bool(f.get("es_especial")),
                "categorias": [{"clave": c["clave"], "etiqueta": c.get("etiqueta") or c["clave"],
                                "orden": c.get("orden")} for c in categorias],
            })
        salida.sort(key=lambda a: (a["orden"] is None, a["orden"] or 0, a["clave"]))
        return salida

    # ── R1.14 · quiénes ──
    def convocables(self, filtros=None, limite=500):
        """Ids con `contacto_participacion` vigente que cumplen `filtros`.

        `filtros`: `{clave: {en: [...]} | {min, max} | {desde, hasta}}`, la
        forma de `f_persona_convocable_filtrada()`. Categorías del mismo
        atributo: o; atributos distintos: y.
        """
        try:
            filas = self._filtrada(FINALIDAD_CONTACTO, filtros or {}, int(limite))
        except ErrorSQL as error:
            raise _traducir(error, "el filtro") from None
        return [str(f["id_persona"]) for f in filas]

    def vigentes(self, ids):
        """De estos ids, cuáles siguen convocables (el gate, otra vez)."""
        ids = [str(i) for i in ids or []]
        if not ids:
            return set()
        return {str(f["id_persona"]) for f in self._vigentes(ids)}

    # ── R1.15 / R1.16 · los valores ──
    def atributos(self, ids, momento=None):
        """Los atributos de esas personas: solo las filas que existen.

        Un atributo ausente **no viene**: no se inventa un nulo, porque no
        saber algo es información distinta de un «sin dato» declarado.
        """
        ids = list(dict.fromkeys(str(i) for i in ids or []))
        salida = []
        for i in range(0, len(ids), TOPE_ATRIBUTOS):
            try:
                filas = self._atributos(ids[i:i + TOPE_ATRIBUTOS], momento)
            except ErrorSQL as error:
                raise _traducir(error, "el pedido de atributos") from None
            for f in filas:
                salida.append({
                    "idPersona": str(f["id_persona"]), "atributo": f["atributo"],
                    "valor": f["valor"], "etiquetaValor": f["etiqueta_valor"],
                    "valorNum": _numero(f["valor_num"]), "valorFecha": _fecha_iso(f["valor_fecha"]),
                    "procedencia": f["procedencia"],
                })
        return salida

    def ficha(self, id_persona, momento=None):
        """R1.16 — la ficha seudónima. No escribe en `reidentificacion`."""
        try:
            crudo = self._ficha(str(id_persona), momento)
        except ErrorSQL as error:
            raise _traducir(error, "la ficha") from None
        if isinstance(crudo, str):
            crudo = json.loads(crudo)
        return {
            "idPersona": str(crudo["id_persona"]),
            "estado": crudo.get("estado"),
            "enroladoEn": crudo.get("enrolado_en"),
            "atributos": [{
                "atributo": a["atributo"], "etiqueta": a.get("etiqueta"), "valor": a.get("valor"),
                "etiquetaValor": a.get("etiqueta_valor"), "procedencia": a.get("procedencia"),
                "esEspecial": bool(a.get("es_especial")),
            } for a in crudo.get("atributos") or []],
            # La bóveda los llama `nombre`, que es un campo de `pii.CAMPOS_PII`
            # aunque sea el nombre de un panel: acá van como `etiqueta`, así la
            # ficha no tiene un solo campo que el validador de R1.12 marque.
            "paneles": [{"id": p.get("id"), "etiqueta": p.get("nombre")}
                        for p in crudo.get("paneles") or []],
        }

    # ── R1.17 · quiénes son ──
    def identificar(self, ids, referencia, actor_email):
        """Nombre, email y celular de los tildados de una sesión.

        La bóveda escribe una fila de `reidentificacion` por persona devuelta,
        **antes** de devolverla, con motivo `seleccion_cuali` y la sesión como
        referencia. Lo que vuelve es PII: se entrega al navegador y no se
        guarda, no se loguea, no va a ningún evento (R1.12).
        """
        _exigir_actor(actor_email)
        _validar_referencia(referencia)
        ids = [str(i) for i in ids or []]
        try:
            filas = self._identificar(ids, str(referencia), actor_email, MOTIVO_SELECCION)
        except ErrorSQL as error:
            raise _traducir(error, "la identificación") from None
        return [{"idPersona": str(f["id_persona"]), "nombre": f["nombre"],
                 "email": f["email"], "celular": f["celular"]} for f in filas]

    # ── convocatoria y cascada ──
    def declarar_convocatoria(self, id_persona, referencia, vence_en):
        """R5.2.a — declara que COLOQUIO convocó a esta persona.

        `referencia` es el id de sesión de COLOQUIO (opaco para la bóveda).
        Volver a declarar la misma referencia actualiza el vencimiento: es lo
        que se hace al reprogramar. Reaplica el gate de consentimiento.
        """
        raise NotImplementedError

    def contacto(self, id_persona, canal, actor_email, motivo="convocatoria coloquio"):
        raise NotImplementedError

    def borrados_pendientes(self):
        raise NotImplementedError

    def confirmar_borrado(self, id_persona, alcance="total"):
        raise NotImplementedError

    def reportar_error_de_borrado(self, id_persona, error, alcance="total"):
        raise NotImplementedError

    def sistema(self):
        raise NotImplementedError

    def cerrar(self):
        pass


def _exigir_actor(actor_email):
    if not actor_email or "@" not in str(actor_email):
        raise DatosInvalidos(
            "Para pedir un dato de contacto o identificar a alguien hace falta el "
            "email del usuario que lo pide: la bóveda audita quién fue (HANDOFF §3)."
        )


def _validar_canal(canal):
    if canal not in ("email", "celular"):
        raise DatosInvalidos("El canal de contacto es `email` o `celular`, uno por vez.")


def _validar_referencia(referencia):
    if not str(referencia or "").strip():
        raise DatosInvalidos("Hace falta la referencia de la sesión.")


# ════════════════════════════════════════════════════════════════════
#  Postgres (Cloud SQL, IAM)
# ════════════════════════════════════════════════════════════════════

_CONECTOR = None
_CANDADO = threading.Lock()


def _conector():
    """Un solo `Connector` por instancia de la función: es caro de crear."""
    global _CONECTOR
    with _CANDADO:
        if _CONECTOR is None:
            from google.cloud.sql.connector import Connector, IPTypes

            _CONECTOR = Connector(ip_type=IPTypes.PRIVATE, refresh_strategy="lazy")
        return _CONECTOR


def _sqlstate(error):
    estado = getattr(error, "sqlstate", None)
    if estado:
        return estado
    args = getattr(error, "args", ())
    if args and isinstance(args[0], dict):
        return args[0].get("C")
    return None


def _mensaje_bd(error):
    diag = getattr(error, "diag", None)
    if diag is not None and getattr(diag, "message_primary", None):
        return diag.message_primary
    args = getattr(error, "args", ())
    if args and isinstance(args[0], dict):
        return args[0].get("M") or str(error)
    return str(error)


class BovedaPostgres(Boveda):
    """Conexión perezosa: una request que no toca la bóveda no la abre."""

    nombre = "postgres"

    def __init__(self, dsn=None, instancia=None, usuario_iam=None, base=None):
        self.dsn = dsn
        self.instancia = instancia
        self.usuario_iam = usuario_iam
        self.base = base
        self._conn = None

    def _conexion(self):
        if self._conn is not None:
            return self._conn
        try:
            if self.dsn:
                # Desarrollo y pruebas contra un cluster local o el Auth Proxy.
                import psycopg

                self._conn = psycopg.connect(self.dsn)
            else:
                # Producción: IP privada por el conector de VPC `paneles-conn`
                # y login IAM de la cuenta de servicio de la función.
                self._conn = _conector().connect(
                    self.instancia, "pg8000",
                    user=self.usuario_iam, db=self.base, enable_iam_auth=True,
                )
        except Exception as error:  # noqa: BLE001
            print(f"[boveda] no se pudo conectar: {error.__class__.__name__}")
            raise ServicioNoDisponible(
                "No se pudo conectar con la bóveda. La selección y el contacto "
                "dependen de ella; el resto de COLOQUIO sigue funcionando.")
        return self._conn

    def _filas(self, sql, params=()):
        conn = self._conexion()
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            columnas = [c[0] for c in cur.description] if cur.description else []
            filas = [dict(zip(columnas, f)) for f in cur.fetchall()] if columnas else []
            conn.commit()
            return filas
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def _superficie(self, sql, params=()):
        """Como `_filas`, pero un rechazo de la base vuelve como `ErrorSQL`."""
        try:
            return self._filas(sql, params)
        except ServicioNoDisponible:
            raise
        except Exception as error:  # noqa: BLE001
            estado = _sqlstate(error)
            if estado:
                raise ErrorSQL(estado, _mensaje_bd(error)) from None
            raise

    def _catalogo(self):
        return self._superficie(
            "select clave, etiqueta, tipo, orden, es_especial, categorias "
            "from v_atributo_catalogo order by orden, clave")

    def _filtrada(self, finalidad, filtros, limite):
        return self._superficie(
            "select id_persona::text as id_persona, finalidades "
            "from f_persona_convocable_filtrada(%s, %s::jsonb, %s)",
            (finalidad, json.dumps(filtros), limite))

    def _vigentes(self, ids):
        return self._superficie(
            "select id_persona::text as id_persona from v_persona_convocable "
            "where %s = any(finalidades) and id_persona = any(%s::uuid[])",
            (FINALIDAD_CONTACTO, ids))

    def _atributos(self, ids, momento):
        return self._superficie(
            "select id_persona::text as id_persona, atributo, valor, etiqueta_valor, "
            "valor_num, valor_fecha, procedencia "
            "from atributos_de_personas(%s::uuid[], coalesce(%s::timestamptz, now()))",
            (ids, momento))

    def _ficha(self, id_persona, momento):
        filas = self._superficie(
            "select ficha_candidato(%s::uuid, coalesce(%s::timestamptz, now())) as ficha",
            (id_persona, momento))
        return filas[0]["ficha"]

    def _identificar(self, ids, referencia, actor, motivo):
        return self._superficie(
            "select id_persona::text as id_persona, nombre, email, celular "
            "from identificar_candidatos(%s::uuid[], %s, %s, %s)",
            (ids, referencia, actor, motivo))

    def declarar_convocatoria(self, id_persona, referencia, vence_en):
        _validar_referencia(referencia)
        try:
            self._filas("select declarar_convocatoria(%s::uuid, %s, %s)",
                        (str(id_persona), str(referencia), vence_en))
        except ServicioNoDisponible:
            raise
        except Exception as error:  # noqa: BLE001
            estado = _sqlstate(error)
            if estado == "42501":
                raise ConvocatoriaRechazada(
                    "La bóveda no aceptó la convocatoria: " + _mensaje_bd(error))
            if estado == "22023":
                raise DatosInvalidos("La bóveda rechazó la declaración: " + _mensaje_bd(error))
            raise

    def contacto(self, id_persona, canal, actor_email, motivo="convocatoria coloquio"):
        _validar_canal(canal)
        _exigir_actor(actor_email)
        try:
            filas = self._filas(
                "select contacto_para_convocatoria(%s::uuid, %s, %s, %s) as dato",
                (str(id_persona), canal, motivo, actor_email),
            )
        except ServicioNoDisponible:
            raise
        except Exception as error:  # noqa: BLE001
            if _sqlstate(error) in ("42501", "22023"):
                raise ContactoRechazado(
                    "La bóveda no entregó el contacto: " + _mensaje_bd(error),
                    {"canal": canal})
            raise
        return (filas[0]["dato"] if filas else "") or ""

    def borrados_pendientes(self):
        filas = self._filas(
            "select id_persona::text as id_persona, alcance, finalidad, "
            "solicitado_en, intentos from mis_borrados_pendientes()")
        return [{"idPersona": f["id_persona"], "alcance": f["alcance"],
                 "finalidad": f["finalidad"], "solicitadoEn": f["solicitado_en"],
                 "intentos": f["intentos"]} for f in filas]

    def confirmar_borrado(self, id_persona, alcance="total"):
        self._filas("select confirmar_borrado(%s::uuid, %s)", (str(id_persona), alcance))

    def reportar_error_de_borrado(self, id_persona, error, alcance="total"):
        self._filas("select reportar_error_de_borrado(%s::uuid, %s, %s)",
                    (str(id_persona), str(error)[:500], alcance))

    def sistema(self):
        return self._filas("select sistema_de_la_conexion() as s")[0]["s"]

    def cerrar(self):
        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None


# ════════════════════════════════════════════════════════════════════
#  Memoria (pruebas, servidor local)
# ════════════════════════════════════════════════════════════════════

class BovedaMemoria(Boveda):
    """El doble de la bóveda: reproduce el SQL de la superficie, no lo aproxima.

    Cada primitiva sigue a su función de `paneles` —`boveda/0021`, `0016` y
    `0034`, y `f_atributo_persona()` de la `0010`—: las mismas validaciones,
    en el mismo orden, con el mismo SQLSTATE; el mismo gate; el mismo orden de
    filas. Si una prueba pasa contra el doble y falla contra la base, el doble
    está mal.

    `catalogo`: la tabla `atributo_demografico` con sus categorías
        `[{clave, etiqueta, tipo, orden, es_especial, activo,
           categorias: [{clave, etiqueta, orden, activo}], derivacion}]`.
        `derivacion` (`"edad_efectiva"` o `"tramo_de_edad"`) marca los dos derivados que el SQL
        de `paneles` calcula por nombre; el doble no nombra ninguno.
    `personas`: `{id: {...}}`
        `atributos`   `{clave: valor}` cargados. El valor es la clave de la
                      categoría, un número o una fecha; o una lista de
                      períodos `[{valor, desde, hasta}]` (vigencia de la 0010).
        `fechaNacimiento`, `edadDeclarada: {valor, referencia}` — las fuentes
                      de los derivados, con la precedencia de R3.14.g.
        `consiente`   `contacto_participacion` vigente (por defecto, sí).
        `refEstudio`  ese consentimiento es de ámbito estudio: no cuenta.
        `finalidades` otras finalidades vigentes de ámbito persona o panel.
        `estado`, `enroladoEn`, `paneles: [{panelId, estado}]`,
        `nombre`, `celular`, `email` — PII que vive acá y solo acá.
    `paneles`: `{panelId: nombre}`.

    `exigir_convocatoria_activa=False` apaga el chequeo de R5.2.a en
    `contacto()`, para probar partes que no tienen que ver con él.
    """

    nombre = "memoria"
    FINALIDADES = ("contacto_participacion", "uso_semantico", "grabacion_av",
                   "moderacion_automatizada", "difusion_verbatim")

    def __init__(self, personas=None, exigir_convocatoria_activa=True, reloj=None,
                 catalogo=None, paneles=None):
        self.personas = personas or {}
        self.catalogo_tabla = catalogo or []
        self.paneles = paneles or {}
        # La tabla `reidentificacion`: la escriben contacto e identificación.
        self.reidentificacion = []
        self.pendientes = {}
        self.confirmados = []
        self.errores = []
        self.exigir_convocatoria_activa = exigir_convocatoria_activa
        # {(id_persona, referencia): vence_en}
        self.declaraciones = {}
        self.llamadas_declarar = []
        self.llamadas = {"atributos": 0, "filtrada": 0, "ficha": 0, "identificar": 0}
        self.reloj = reloj or (lambda: dt.datetime.now(dt.timezone.utc))
        self.falla = None  # simular la bóveda caída

    @property
    def auditoria(self):
        """Las lecturas de contacto (`contacto_para_convocatoria`)."""
        return [r for r in self.reidentificacion if r["via"] == "contacto_para_convocatoria"]

    def _caida(self):
        if self.falla:
            raise ServicioNoDisponible(self.falla)

    # ── v_persona_convocable (0021) ──
    def _finalidades(self, p):
        """`finalidades` de la vista: vigentes, de ámbito persona o panel."""
        propias = set(p.get("finalidades") or [])
        if p.get("consiente", True) and not p.get("refEstudio"):
            propias.add(FINALIDAD_CONTACTO)
        return sorted(propias)

    def _vista(self):
        """{id_persona: finalidades}: activa, sin lápida, con alguna vigente."""
        return {pid: self._finalidades(p) for pid, p in self.personas.items()
                if p.get("estado", "activa") == "activa" and self._finalidades(p)}

    def _consiente(self, id_persona):
        return FINALIDAD_CONTACTO in self._vista().get(str(id_persona), ())

    # ── f_atributo_persona(momento) (0010) ──
    def _atributo(self, clave):
        return next((a for a in self.catalogo_tabla if a["clave"] == clave), None)

    def _derivado(self, tipo):
        return next((a for a in self.catalogo_tabla if a.get("derivacion") == tipo), None)

    @staticmethod
    def _vigente(valor, momento):
        """El valor a `momento`: `desde <= momento < hasta`."""
        if not isinstance(valor, list):
            return valor
        for periodo in valor:
            desde, hasta = periodo.get("desde"), periodo.get("hasta")
            if (desde is None or desde <= momento) and (hasta is None or momento < hasta):
                return periodo["valor"]
        return None

    @staticmethod
    def _anios(hasta, desde):
        """`date_part('year', age(hasta, desde))`: años cumplidos."""
        return hasta.year - desde.year - ((hasta.month, hasta.day) < (desde.month, desde.day))

    @staticmethod
    def _texto_num(n):
        n = float(n)
        return str(int(n)) if n.is_integer() else str(n)

    def _edad(self, p, momento):
        """Fecha de nacimiento > edad declarada envejecida (R3.14.g)."""
        hoy = momento.date()
        if p.get("fechaNacimiento"):
            return self._anios(hoy, p["fechaNacimiento"]), "derivado"
        dec = self._vigente(p.get("edadDeclarada"), momento) if isinstance(
            p.get("edadDeclarada"), list) else p.get("edadDeclarada")
        if dec and dec.get("valor") is not None:
            return int(round(dec["valor"] + self._anios(hoy, dec["referencia"]))), "envejecido"
        return None, None

    @staticmethod
    def _tramo(edad):
        for tope, tramo in ((18, "<18"), (25, "18-24"), (35, "25-34"), (45, "35-44"),
                            (55, "45-54"), (65, "55-64")):
            if edad < tope:
                return tramo
        return "65+"

    def _f_atributo_persona(self, momento):
        """Filas `(id_persona, atributo, valor, etiqueta_valor, valor_num,
        valor_fecha, procedencia)` de **todas** las personas: el gate lo pone
        quien la llama, igual que en la base."""
        filas = []
        a_edad, a_tramo = self._derivado("edad_efectiva"), self._derivado("tramo_de_edad")
        for pid, p in self.personas.items():
            # Valores cargados de atributos no derivados.
            for clave, crudo in (p.get("atributos") or {}).items():
                a = self._atributo(clave)
                if not a or a["tipo"] == "derivado":
                    continue
                v = self._vigente(crudo, momento)
                if v is None:
                    continue
                cat = next((c for c in a.get("categorias") or [] if c["clave"] == v), None)
                if a["tipo"] == "categorico":
                    if cat is None:
                        continue
                    fila = (v, cat.get("etiqueta") or v, None, None)
                elif a["tipo"] == "numerico":
                    fila = (self._texto_num(v), self._texto_num(v), v, None)
                else:  # fecha
                    fila = (v.isoformat(), v.isoformat(), None, v)
                filas.append({"id_persona": pid, "atributo": clave, "valor": fila[0],
                              "etiqueta_valor": fila[1], "valor_num": fila[2],
                              "valor_fecha": fila[3], "procedencia": "cargado"})
            edad, procedencia = self._edad(p, momento)
            if a_edad and edad is not None:
                filas.append({"id_persona": pid, "atributo": a_edad["clave"], "valor": str(edad),
                              "etiqueta_valor": str(edad), "valor_num": edad,
                              "valor_fecha": None, "procedencia": procedencia})
            if a_tramo:
                cargado = self._vigente((p.get("atributos") or {}).get(a_tramo["clave"]), momento)
                if edad is not None:
                    tramo = self._tramo(edad)
                elif cargado is not None:
                    tramo, procedencia = cargado, "cargado"
                else:
                    tramo = None
                if tramo is not None:
                    filas.append({"id_persona": pid, "atributo": a_tramo["clave"], "valor": tramo,
                                  "etiqueta_valor": tramo, "valor_num": None,
                                  "valor_fecha": None, "procedencia": procedencia})
        return filas

    # ── v_atributo_catalogo (0034 §1) ──
    def _catalogo(self):
        self._caida()
        filas = []
        for a in self.catalogo_tabla:
            if not a.get("activo", True):
                continue
            cats = sorted((c for c in a.get("categorias") or [] if c.get("activo", True)),
                          key=lambda c: (c.get("orden") or 0, c["clave"]))
            filas.append({"clave": a["clave"], "etiqueta": a["etiqueta"], "tipo": a["tipo"],
                          "orden": a.get("orden"), "es_especial": bool(a.get("es_especial")),
                          "categorias": [{"clave": c["clave"], "etiqueta": c.get("etiqueta") or c["clave"],
                                          "orden": c.get("orden")} for c in cats]})
        return sorted(filas, key=lambda f: (f["orden"] or 0, f["clave"]))

    # ── f_persona_convocable_filtrada() (0034 §3) ──
    @staticmethod
    def _arreglo(valores):
        return "{" + ",".join(str(v) for v in valores) + "}"

    def _filtrada(self, finalidad, filtros, limite):
        self._caida()
        self.llamadas["filtrada"] += 1
        if finalidad is None or finalidad not in self.FINALIDADES:
            raise ErrorSQL(_INVALIDO, f"Finalidad desconocida: {finalidad}.")
        if limite is None or limite < 1 or limite > TOPE_FILTRADA:
            raise ErrorSQL(_INVALIDO, f"El límite tiene que estar entre 1 y 5000 (vino {limite}).")
        filtros = {} if filtros is None else filtros
        if not isinstance(filtros, dict):
            raise ErrorSQL(_INVALIDO, "Los filtros van en un objeto {clave: condición}.")
        vista = self._vista()
        ids = [pid for pid, fin in vista.items() if finalidad in fin]
        ahora = self.reloj()
        derivados = None
        for clave in sorted(filtros):
            cond = filtros[clave]
            a = self._atributo(clave)
            if a is None:
                raise ErrorSQL(_INVALIDO, f"El atributo «{clave}» no está en el catálogo.")
            if not a.get("activo", True):
                raise ErrorSQL(_INVALIDO, f"El atributo «{clave}» está dado de baja: no se puede "
                                          "filtrar por él.")
            if not isinstance(cond, dict) or not cond:
                raise ErrorSQL(_INVALIDO, f"La condición de «{clave}» tiene que ser un objeto con un "
                                          "operador.")
            permitidos = {"categorico": ["en"], "numerico": ["min", "max"],
                          "fecha": ["desde", "hasta"], "derivado": ["en", "min", "max"]}[a["tipo"]]
            if not set(cond) <= set(permitidos):
                raise ErrorSQL(_INVALIDO, f"El atributo «{clave}» es {a['tipo']}: admite "
                                          f"{self._arreglo(permitidos)}, y vino {self._arreglo(cond)}.")
            try:
                en = None
                if "en" in cond:
                    if not isinstance(cond["en"], list) or not cond["en"]:
                        raise ValueError
                    en = [v if isinstance(v, str) else json.dumps(v) for v in cond["en"]]
                minimo = None if cond.get("min") is None else float(cond["min"])
                maximo = None if cond.get("max") is None else float(cond["max"])
                desde = None if cond.get("desde") is None else dt.date.fromisoformat(str(cond["desde"]))
                hasta = None if cond.get("hasta") is None else dt.date.fromisoformat(str(cond["hasta"]))
            except (TypeError, ValueError):
                raise ErrorSQL(_INVALIDO, f"La condición de «{clave}» no se puede leer: "
                                          f"{json.dumps(cond)}.") from None
            if en is not None:
                categorias = [c["clave"] for c in a.get("categorias") or [] if c.get("activo", True)]
                ajenas = [x for x in en if x not in categorias]
                if categorias and ajenas:
                    raise ErrorSQL(_INVALIDO, f"El atributo «{clave}» no tiene la(s) categoría(s) "
                                              f"{self._arreglo(ajenas)}.")
            if a["tipo"] == "derivado":
                if derivados is None:
                    derivados = self._f_atributo_persona(ahora)
                cumplen = {f["id_persona"] for f in derivados
                           if f["atributo"] == clave
                           and (en is None or f["valor"] in en)
                           and (minimo is None or (f["valor_num"] is not None and f["valor_num"] >= minimo))
                           and (maximo is None or (f["valor_num"] is not None and f["valor_num"] <= maximo))}
                ids = [i for i in ids if i in cumplen]
            else:
                def cumple(pid):
                    v = self._vigente((self.personas[pid].get("atributos") or {}).get(clave), ahora)
                    if v is None:
                        return False
                    es_cat = a["tipo"] == "categorico"
                    num = v if a["tipo"] == "numerico" else None
                    fecha = v if a["tipo"] == "fecha" else None
                    return ((en is None or (es_cat and v in en))
                            and (minimo is None or (num is not None and num >= minimo))
                            and (maximo is None or (num is not None and num <= maximo))
                            and (desde is None or (fecha is not None and fecha >= desde))
                            and (hasta is None or (fecha is not None and fecha <= hasta)))
                ids = [i for i in ids if cumple(i)]
            if not ids:
                break
        return [{"id_persona": i, "finalidades": vista[i]} for i in sorted(ids)[:limite]]

    def _vigentes(self, ids):
        self._caida()
        vista = self._vista()
        return [{"id_persona": i} for i in sorted(set(ids))
                if FINALIDAD_CONTACTO in vista.get(i, ())]

    # ── atributos_de_personas() (0034 §2) ──
    def _atributos(self, ids, momento):
        self._caida()
        self.llamadas["atributos"] += 1
        if ids is None:
            raise ErrorSQL(_INVALIDO, "Hace falta la lista de personas.")
        if len(ids) > TOPE_ATRIBUTOS:
            raise ErrorSQL(_TOPE, f"Se piden {len(ids)} personas y el tope es 500 por llamada.")
        vista = self._vista()
        pedidas = {i for i in ids if i in vista}
        orden = {a["clave"]: (a.get("orden") or 0, a["clave"]) for a in self.catalogo_tabla
                 if a.get("activo", True)}
        filas = [f for f in self._f_atributo_persona(momento or self.reloj())
                 if f["id_persona"] in pedidas and f["atributo"] in orden]
        return sorted(filas, key=lambda f: (f["id_persona"], orden[f["atributo"]]))

    # ── ficha_candidato() (0034 §4) ──
    def _ficha(self, id_persona, momento):
        self._caida()
        self.llamadas["ficha"] += 1
        if id_persona not in self._vista():
            raise ErrorSQL(_NO_ENCONTRADO, f"No hay un candidato {id_persona}.")
        p = self.personas[id_persona]
        activos = {a["clave"]: a for a in self.catalogo_tabla if a.get("activo", True)}
        filas = [f for f in self._f_atributo_persona(momento or self.reloj())
                 if f["id_persona"] == id_persona and f["atributo"] in activos]
        filas.sort(key=lambda f: (activos[f["atributo"]].get("orden") or 0, f["atributo"]))
        paneles = sorted(({"id": m["panelId"], "nombre": self.paneles.get(m["panelId"])}
                          for m in p.get("paneles") or [] if m.get("estado", "activo") == "activo"),
                         key=lambda x: str(x["nombre"]))
        enrolado = p.get("enroladoEn")
        return {
            "id_persona": id_persona,
            "estado": p.get("estado", "activa"),
            "enrolado_en": enrolado.isoformat() if enrolado else None,
            "atributos": [{"atributo": f["atributo"], "etiqueta": activos[f["atributo"]]["etiqueta"],
                           "valor": f["valor"], "etiqueta_valor": f["etiqueta_valor"],
                           "procedencia": f["procedencia"],
                           "es_especial": bool(activos[f["atributo"]].get("es_especial"))}
                          for f in filas],
            "paneles": paneles,
        }

    # ── identificar_candidatos() (0034 §5) ──
    def _identificar(self, ids, referencia, actor, motivo):
        self._caida()
        self.llamadas["identificar"] += 1
        if referencia is None or not referencia.strip():
            raise ErrorSQL(_INVALIDO, "Hace falta la referencia de la sesión: identificar es para "
                                      "los candidatos de una sesión concreta, no para traducir "
                                      "cualquier id.")
        if actor is None or not actor.strip():
            raise ErrorSQL(_INVALIDO, "Hace falta el actor: el email de la persona que lo pidió. Si "
                                      "no hay alguien detrás, no hay motivo para ver a nadie.")
        if ids is None:
            raise ErrorSQL(_INVALIDO, "Hace falta la lista de candidatos.")
        if len(ids) > TOPE_IDENTIFICAR:
            raise ErrorSQL(_TOPE, f"Se piden {len(ids)} personas y el tope es 200 por llamada: es "
                                  "una acción sobre los tildados, no una búsqueda.")
        vista = self._vista()
        devueltos = sorted({i for i in ids if FINALIDAD_CONTACTO in vista.get(i, ())})
        # Primero la auditoría, después la entrega.
        for i in devueltos:
            self.reidentificacion.append({
                "idPersona": i, "actor": actor, "actorEmail": actor,
                "motivo": (motivo or "").strip() or MOTIVO_SELECCION,
                "contexto": {"referencia": referencia, "via": "identificar_candidatos",
                             "pedidos": len(ids)},
                "via": "identificar_candidatos", "sistema": "coloquio"})
        filas = [{"id_persona": i, "nombre": self.personas[i].get("nombre"),
                  "email": self.personas[i].get("email"),
                  "celular": self.personas[i].get("celular")} for i in devueltos]
        return sorted(filas, key=lambda f: (f["nombre"] is None, f["nombre"] or "", f["id_persona"]))

    def declarar_convocatoria(self, id_persona, referencia, vence_en):
        if self.falla:
            raise ServicioNoDisponible(self.falla)
        _validar_referencia(referencia)
        ahora = self.reloj()
        if vence_en <= ahora:
            raise DatosInvalidos("La bóveda rechazó la declaración: la convocatoria vence en el pasado.")
        if vence_en > ahora + dt.timedelta(days=TOPE_DECLARACION_DIAS):
            raise DatosInvalidos("La bóveda rechazó la declaración: una convocatoria no puede "
                                 "declararse por más de 60 días.")
        if not self._consiente(id_persona):
            raise ConvocatoriaRechazada(
                f"La bóveda no aceptó la convocatoria: la persona {id_persona} no tiene "
                "consentimiento vigente de contacto_participacion, o ya no está activa.")
        self.declaraciones[(str(id_persona), str(referencia))] = vence_en
        self.llamadas_declarar.append((str(id_persona), str(referencia), vence_en))

    def tiene_declaracion(self, id_persona):
        ahora = self.reloj()
        return any(k[0] == str(id_persona) and v > ahora for k, v in self.declaraciones.items())

    def contacto(self, id_persona, canal, actor_email, motivo="convocatoria coloquio"):
        _validar_canal(canal)
        _exigir_actor(actor_email)
        if self.falla:
            raise ServicioNoDisponible(self.falla)
        p = self.personas.get(str(id_persona))
        if not self._consiente(id_persona):
            raise ContactoRechazado(
                f"La bóveda no entregó el contacto: la persona {id_persona} no "
                "tiene consentimiento vigente de contacto_participacion, o ya no "
                "está activa.", {"canal": canal})
        if self.exigir_convocatoria_activa and not self.tiene_declaracion(id_persona):
            raise ContactoRechazado(
                f"La bóveda no entregó el contacto: la persona {id_persona} no "
                "tiene una convocatoria activa en el sistema «coloquio»: no hay "
                "motivo para leer su contacto.", {"canal": canal})
        self.reidentificacion.append({
            "idPersona": str(id_persona), "actor": actor_email, "actorEmail": actor_email,
            "canal": canal, "motivo": motivo, "sistema": "coloquio",
            "contexto": {"canal": canal, "via": "contacto_para_convocatoria"},
            "via": "contacto_para_convocatoria"})
        return p.get(canal) or ""

    # ── cascada ──
    def dar_de_baja(self, id_persona, alcance="total"):
        """Lo que haría `paneles` al procesar una baja."""
        self.personas.pop(str(id_persona), None)
        # La FK con `on delete cascade` de la `0016` se lleva las declaraciones.
        self.declaraciones = {k: v for k, v in self.declaraciones.items() if k[0] != str(id_persona)}
        self.pendientes[(str(id_persona), alcance)] = {"intentos": 0, "ultimoError": None}

    def borrados_pendientes(self):
        return [{"idPersona": k[0], "alcance": k[1], "finalidad": None,
                 "solicitadoEn": None, "intentos": v["intentos"]}
                for k, v in self.pendientes.items()]

    def confirmar_borrado(self, id_persona, alcance="total"):
        clave = (str(id_persona), alcance)
        if clave not in self.pendientes:
            raise RuntimeError(f"No hay un borrado pendiente de {id_persona}.")
        del self.pendientes[clave]
        self.confirmados.append(clave)

    def reportar_error_de_borrado(self, id_persona, error, alcance="total"):
        clave = (str(id_persona), alcance)
        if clave in self.pendientes:
            self.pendientes[clave]["intentos"] += 1
            self.pendientes[clave]["ultimoError"] = str(error)[:500]
        self.errores.append((clave, str(error)))

    def sistema(self):
        return "coloquio"
 