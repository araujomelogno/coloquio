"""Cloud Functions for Firebase — COLOQUIO · Fase 1.

Dos funciones, en el codebase `coloquio` (firebase.json), en el mismo proyecto
que `paneles` (`gestion-paneles`). Los nombres llevan prefijo porque el
proyecto es compartido y tienen que ser únicos (HANDOFF §1):

* `coloquio_api` — HTTP. Hosting reescribe `/api/**` del sitio de COLOQUIO
  hacia acá.
* `coloquio_cascada` — programada. Atiende los borrados pendientes de la
  bóveda (R1.11).

Las dos corren como la cuenta de servicio `coloquio-app@…`, que es la que tiene
usuario IAM en la bóveda, y salen por el conector de VPC existente
`paneles-conn` (no se crea otro: ~US$ 10–15/mes al pedo, HANDOFF §8).
"""

import datetime as dt
import json
import os
import traceback

import firebase_admin
from firebase_functions import https_fn, options, scheduler_fn

from coloquio import auth, cascada, config, contexto, ruteo, store as mod_store, whatsapp
from coloquio.errores import ErrorApi, NoAutenticado

if not firebase_admin._apps:
    firebase_admin.initialize_app()

# Si cambia, cambiar también la región del rewrite en firebase.json.
REGION = "southamerica-east1"

# Conector de VPC de `paneles`. Se lee del entorno del deploy:
# `export VPC_CONNECTOR=paneles-conn` antes de `firebase deploy`.
VPC_CONNECTOR = os.environ.get("VPC_CONNECTOR") or None

# La identidad con la que la función se conecta a la bóveda (login IAM).
CUENTA_DE_SERVICIO = os.environ.get(
    "COLOQUIO_SERVICE_ACCOUNT", "coloquio-app@gestion-paneles.iam.gserviceaccount.com")

# Secretos montados desde Secret Manager. `firebase deploy` solo monta los
# declarados acá: uno que falta hace que el sistema se comporte como si la
# credencial no existiera (lección aprendida en `paneles`). Todos tienen que
# existir en Secret Manager, aunque sea vacíos.
SECRETOS = [
    "WHATSAPP_TOKEN",            # token de la app de Meta
    "WHATSAPP_PHONE_NUMBER_ID",  # número emisor
    "WHATSAPP_APP_SECRET",       # firma de los webhooks entrantes
    "WHATSAPP_VERIFY_TOKEN",     # handshake de suscripción del webhook
]

PREFIJO = "/api"

_STORE = None


def _store():
    global _STORE
    if _STORE is None:
        cfg = config.cargar()
        _STORE = mod_store.StoreFirestore.conectar(cfg.proyecto, cfg.base_firestore)
    return _STORE


def _serializar(valor):
    if isinstance(valor, dt.datetime):
        return valor.isoformat()
    return str(valor)


def _json(status, cuerpo):
    if isinstance(cuerpo, dict) and "__texto__" in cuerpo:
        return https_fn.Response(str(cuerpo["__texto__"]), status=status,
                                 headers={"Content-Type": "text/plain"})
    return https_fn.Response(
        json.dumps(cuerpo, ensure_ascii=False, default=_serializar),
        status=status, headers={"Content-Type": "application/json; charset=utf-8"})


def _camino_de(req):
    camino = req.path or "/"
    if camino.startswith(PREFIJO):
        camino = camino[len(PREFIJO):] or "/"
    return camino


def _opciones_comunes():
    return dict(
        region=REGION,
        secrets=SECRETOS,
        service_account=CUENTA_DE_SERVICIO,
        vpc_connector=VPC_CONNECTOR,
        vpc_connector_egress_settings=(
            options.VpcEgressSetting.PRIVATE_RANGES_ONLY if VPC_CONNECTOR else None),
        memory=options.MemoryOption.MB_512,
        timeout_sec=120,
    )


@https_fn.on_request(
    cors=options.CorsOptions(cors_origins=["*"],
                             cors_methods=["get", "post", "put", "patch", "delete", "options"]),
    **_opciones_comunes(),
)
def coloquio_api(req: https_fn.Request) -> https_fn.Response:
    if req.method == "OPTIONS":
        return https_fn.Response("", status=204)

    camino = _camino_de(req)
    cfg = config.cargar()
    st = _store()

    if ruteo.es_publica(req.method, camino):
        actor = auth.Actor(uid=None, roles=(), nombre="público")
        # El webhook de Meta se autentica con su firma sobre el cuerpo crudo.
        if req.method == "POST" and ruteo.normalizar(camino) == "/webhooks/whatsapp":
            if not whatsapp.firma_valida(req.get_data(), req.headers.get("X-Hub-Signature-256"),
                                         cfg.wa_app_secret):
                return _json(401, NoAutenticado("Firma de webhook inválida.").como_dict())
    else:
        try:
            actor = auth.actor_de_request(req.headers, st)
        except ErrorApi as error:
            return _json(error.status, error.como_dict())

    try:
        cuerpo = req.get_json(silent=True) or {}
    except Exception:  # noqa: BLE001
        cuerpo = {}
    consulta = dict(req.args or {})

    ctx = contexto.Contexto(st, cfg=cfg)
    try:
        status, respuesta = ruteo.despachar(req.method, camino, cuerpo, consulta, actor, ctx)
        return _json(status, respuesta)
    except ErrorApi as error:
        return _json(error.status, error.como_dict())
    except Exception as error:  # noqa: BLE001
        # `format_exc()` imprime código, no valores: no lleva PII al log.
        print(f"[coloquio_api] error no manejado: {error!r}\n{traceback.format_exc()}")
        return _json(500, {"error": "interno", "mensaje": "Error interno del servidor."})
    finally:
        ctx.cerrar()


@scheduler_fn.on_schedule(
    schedule="every 30 minutes",
    timezone=scheduler_fn.Timezone("America/Montevideo"),
    **_opciones_comunes(),
)
def coloquio_cascada(event: scheduler_fn.ScheduledEvent) -> None:
    """R1.11 — pasada periódica sobre `mis_borrados_pendientes()`."""
    ctx = contexto.Contexto(_store(), cfg=config.cargar())
    try:
        resultado = cascada.procesar(ctx)
        print(f"[coloquio_cascada] pendientes={resultado['pendientes']} "
              f"confirmados={resultado['confirmados']} errores={resultado['errores']}")
    finally:
        ctx.cerrar()
