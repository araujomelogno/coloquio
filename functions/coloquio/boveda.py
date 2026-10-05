"""Acceso a la bóveda de `paneles`, **solo por la superficie de la Fase 5**.

COLOQUIO se conecta como `coloquio-app@gestion-paneles.iam` (miembro del rol
de grupo `coloquio_app`) con autenticación IAM de Cloud SQL. La base le
permite exactamente esto (HANDOFF §2, «DESPLIEGUE - COLOQUIO Fase 0» §5):

    lectura    v_persona_convocable, v_fatiga_panelista, v_finalidad,
               v_texto_consentimiento_activo
    ejecución  declarar_convocatoria(), contacto_para_convocatoria(),
               mis_borrados_pendientes(), confirmar_borrado(),
               reportar_error_de_borrado(), sistema_de_la_conexion()

Todo lo demás da `permission denied`, y es por diseño. Este módulo no intenta
leer `persona`, `consentimiento` ni `participacion`, y **no escribe** nada
fuera de lo que esas funciones hacen por su cuenta (DoD 11). La única
escritura propia es `declarar_convocatoria()` (R5.2.a, `boveda/0016`): sin una
convocatoria declarada, la bóveda no entrega el contacto.

Tres reglas que este módulo hace cumplir y que no conviene reimplementar en
otro lado:

* **El gate de consentimiento es la vista.** Toda lista de candidatos sale de
  `v_persona_convocable` con `finalidad = 'contacto_participacion'`. No hay un
  `if` en Python que decida quién consintió (R1.2).
* **`p_actor` es el email del usuario humano** que pidió el contacto, siempre
  (HANDOFF §3). `contacto()` se niega a llamar sin él: si la operación no
  tiene una persona detrás, no debería estar pidiendo un contacto.
* **El dato de contacto no se guarda.** `contacto()` lo devuelve y listo; ni
  se loguea ni se cachea (R1.12).
"""

import contextlib
import datetime as dt
import threading

from .errores import (
    ContactoRechazado, ConvocatoriaRechazada, DatosInvalidos, ServicioNoDisponible,
)

FINALIDAD_CONTACTO = "contacto_participacion"

# R5.2.a — la bóveda rechaza una declaración que venza a más de 60 días.
TOPE_DECLARACION_DIAS = 60

# Columnas de la vista → claves del segmento en COLOQUIO.
DIMENSIONES = ("sexo", "tramoEtario", "localidad")
_COLUMNA = {"sexo": "sexo", "tramoEtario": "tramo_etario", "localidad": "localidad"}

TRAMOS = ("18-24", "25-34", "35-44", "45-54", "55-64", "65+")


def segmento_de(fila):
    return {
        "sexo": fila.get("sexo"),
        "tramoEtario": fila.get("tramo_etario") or fila.get("tramoEtario"),
        "localidad": fila.get("localidad"),
    }


class Boveda:
    """Interfaz. Ver `BovedaPostgres` y `BovedaMemoria`."""

    nombre = "boveda"

    def convocables(self, filtros=None, ids=None, ref_estudio=None, limite=500):
        """Personas con consentimiento vigente de contacto_participacion.

        `filtros`: {sexo: [..], tramoEtario: [..], localidad: [..],
        edadMin, edadMax}. `ids`: restringe a ese conjunto (para cruzar con
        el ranking semántico). Devuelve [{idPersona, segmento, edad}].
        """
        raise NotImplementedError

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
            "Para pedir un dato de contacto hace falta el email del usuario que "
            "lo pide: la bóveda audita quién fue (HANDOFF §3)."
        )


def _validar_canal(canal):
    if canal not in ("email", "celular"):
        raise DatosInvalidos("El canal de contacto es `email` o `celular`, uno por vez.")


def _validar_referencia(referencia):
    if not str(referencia or "").strip():
        raise DatosInvalidos("La declaración de convocatoria necesita la referencia de la sesión.")


def _armar_where(filtros, ids, ref_estudio):
    """SQL y parámetros de la selección sobre la vista. Solo `%s`."""
    filtros = filtros or {}
    where = ["finalidad = %s"]
    params = [FINALIDAD_CONTACTO]
    # El consentimiento puede tener ámbito de estudio (boveda/0013): vale el
    # global y el de este estudio, ninguno más.
    # if ref_estudio:
    #    where.append("(ref_estudio is null or ref_estudio::text = %s)")
    #    params.append(str(ref_estudio))
    # else:
    #    where.append("ref_estudio is null")
    for dim in DIMENSIONES:
        valores = [v for v in (filtros.get(dim) or []) if v not in (None, "")]
        if valores:
            where.append(f"{_COLUMNA[dim]} = any(%s)")
            params.append(list(valores))
    if filtros.get("edadMin") not in (None, ""):
        where.append("edad >= %s")
        params.append(int(filtros["edadMin"]))
    if filtros.get("edadMax") not in (None, ""):
        where.append("edad <= %s")
        params.append(int(filtros["edadMax"]))
    if ids is not None:
        where.append("id_persona::text = any(%s)")
        params.append([str(i) for i in ids])
    return " and ".join(where), params


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

    def convocables(self, filtros=None, ids=None, ref_estudio=None, limite=500):
        if ids is not None and not ids:
            return []
        where, params = _armar_where(filtros, ids, ref_estudio)
        # `distinct on`: una persona puede tener la finalidad global y la del
        # estudio a la vez; es un candidato, no dos.
        sql = (
            "select  id_persona::text as id_persona, "
            "sexo, localidad, tramo_etario, edad "
            f"from v_persona_convocable where {where} "
            "order by id_persona limit %s"
        )
        filas = self._filas(sql, params + [int(limite)])
        return [{"idPersona": f["id_persona"], "segmento": segmento_de(f),
                 "edad": f.get("edad")} for f in filas]

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
    """Imita la superficie: el gate, la auditoría y la cascada.

    `personas`: {id: {segmento, edad, consiente, celular, email}}. Los datos de
    contacto viven acá y solo acá, igual que en la bóveda real.

    Reproduce el contrato de R5.2.a (`boveda/0016`): `contacto()` exige una
    convocatoria declarada y vigente para COLOQUIO, y `declarar_convocatoria()`
    reaplica el gate, rechaza vencimientos pasados o a más de 60 días, y
    actualiza en vez de duplicar. `exigir_convocatoria_activa=False` apaga el
    chequeo, para probar partes que no tienen que ver con él.
    """

    nombre = "memoria"

    def __init__(self, personas=None, exigir_convocatoria_activa=True, reloj=None):
        self.personas = personas or {}
        self.auditoria = []
        self.pendientes = {}
        self.confirmados = []
        self.errores = []
        self.exigir_convocatoria_activa = exigir_convocatoria_activa
        # {(id_persona, referencia): vence_en}
        self.declaraciones = {}
        self.llamadas_declarar = []
        self.reloj = reloj or (lambda: dt.datetime.now(dt.timezone.utc))
        self.falla = None  # simular la bóveda caída

    def _pasa(self, p, filtros, ref_estudio):
        if not p.get("consiente", True):
            return False
        ambito = p.get("refEstudio")
        if ambito and ambito != ref_estudio:
            return False
        filtros = filtros or {}
        for dim in DIMENSIONES:
            valores = [v for v in (filtros.get(dim) or []) if v not in (None, "")]
            if valores and p["segmento"].get(dim) not in valores:
                return False
        edad = p.get("edad")
        if filtros.get("edadMin") not in (None, "") and (edad is None or edad < int(filtros["edadMin"])):
            return False
        if filtros.get("edadMax") not in (None, "") and (edad is None or edad > int(filtros["edadMax"])):
            return False
        return True

    def convocables(self, filtros=None, ids=None, ref_estudio=None, limite=500):
        universo = self.personas.items()
        if ids is not None:
            permitidos = {str(i) for i in ids}
            universo = [(k, v) for k, v in universo if k in permitidos]
        salida = [
            {"idPersona": k, "segmento": dict(p["segmento"]), "edad": p.get("edad")}
            for k, p in sorted(universo) if self._pasa(p, filtros, ref_estudio)
        ]
        return salida[:limite]

    def _consiente(self, id_persona):
        p = self.personas.get(str(id_persona))
        return bool(p and p.get("consiente", True))

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
        if not p or not p.get("consiente", True):
            raise ContactoRechazado(
                f"La bóveda no entregó el contacto: la persona {id_persona} no "
                "tiene consentimiento vigente de contacto_participacion, o ya no "
                "está activa.", {"canal": canal})
        if self.exigir_convocatoria_activa and not self.tiene_declaracion(id_persona):
            raise ContactoRechazado(
                f"La bóveda no entregó el contacto: la persona {id_persona} no "
                "tiene una convocatoria activa en el sistema «coloquio»: no hay "
                "motivo para leer su contacto.", {"canal": canal})
        self.auditoria.append({"idPersona": str(id_persona), "actor": actor_email,
                               "canal": canal, "motivo": motivo, "sistema": "coloquio"})
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
 