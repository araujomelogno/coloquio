"""Rutas de la API, bajo `/api/cuali/**` (SPEC §8), con la convención de `paneles`.

Cada ruta declara el permiso que exige. Toda escritura pasa por acá: el
cliente no escribe en la base (R1.13) y las reglas de Firestore niegan todo.
"""

import re

from . import (
    canales, cascada, cierre, configuracion, consistencia, embudo, estudios, historial,
    importacion, incentivos, modelo, recepcion, reemplazo, seleccion, sesiones, tablero,
    usuarios, util,
)
from .errores import NoEncontrado

RUTAS = []
PREFIJO = "/cuali"


def ruta(metodo, patron, permiso):
    expresion = re.compile("^" + re.sub(r"<([a-zA-Z_]+)>", r"(?P<\1>[^/]+)", patron) + "$")

    def decorador(funcion):
        RUTAS.append((metodo.upper(), expresion, permiso, funcion, patron))
        return funcion

    return decorador


# Rutas públicas: el webhook de Meta (verifica su propia firma) y el entorno.
PUBLICAS = {("GET", "/webhooks/whatsapp"), ("POST", "/webhooks/whatsapp"), ("GET", "/entorno")}


def normalizar(camino):
    if camino.startswith(PREFIJO):
        camino = camino[len(PREFIJO):] or "/"
    return camino.rstrip("/") or "/"


def es_publica(metodo, camino):
    return (metodo.upper(), normalizar(camino)) in PUBLICAS


def resolver(metodo, camino):
    camino = normalizar(camino)
    for m, expresion, permiso, funcion, _ in RUTAS:
        if m != metodo.upper():
            continue
        coincide = expresion.match(camino)
        if coincide:
            return funcion, permiso, coincide.groupdict()
    raise NoEncontrado(f"No existe la ruta {metodo} /api{PREFIJO}{camino}.")


def despachar(metodo, camino, cuerpo, consulta, actor, ctx):
    funcion, permiso, params = resolver(metodo, camino)
    if permiso:
        actor.exigir(permiso)
    return funcion(ctx, actor, params, cuerpo or {}, consulta or {})


# ── Entorno y usuario ──────────────────────────────────────────────

@ruta("GET", "/entorno", None)
def entorno(ctx, actor, p, c, q):
    return 200, {"sistema": "coloquio", "fase": 1,
                 "whatsapp": ctx.canal_wa.configurado,
                 "motorSemantico": ctx.motor.nombre}


@ruta("GET", "/yo", "leer")
def yo(ctx, actor, p, c, q):
    return 200, actor.como_dict()


@ruta("GET", "/catalogos", "leer")
def catalogos(ctx, actor, p, c, q):
    return 200, {
        "categorias": configuracion.categorias(ctx.store),
        "regalos": configuracion.listar_regalos(ctx.store, solo_activos=True),
        "estados": [{"codigo": e, "etiqueta": modelo.ETIQUETAS[e]} for e in modelo.ESTADOS],
        "dimensiones": list(modelo.DIMENSIONES_CUOTA),
        "tramos": ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
        "sexos": ["F", "M"],
        "salidasSinReemplazo": modelo.SALIDAS_SIN_REEMPLAZO,
    }


@ruta("GET", "/tablero", "leer")
def ver_tablero(ctx, actor, p, c, q):
    return 200, tablero.resumen(ctx)


# ── R1.1 Estudios y pauta ──────────────────────────────────────────

@ruta("POST", "/estudios", "gestionar_estudios")
def crear_estudio(ctx, actor, p, c, q):
    return 201, estudios.crear(ctx, actor, c)


@ruta("GET", "/estudios", "leer")
def listar_estudios(ctx, actor, p, c, q):
    return 200, {"items": estudios.listar(ctx)}


@ruta("GET", "/estudios/<estudio_id>", "leer")
def ver_estudio(ctx, actor, p, c, q):
    return 200, estudios.ver(ctx, p["estudio_id"])


@ruta("PATCH", "/estudios/<estudio_id>", "gestionar_estudios")
def editar_estudio(ctx, actor, p, c, q):
    return 200, estudios.editar(ctx, actor, p["estudio_id"], c)


@ruta("POST", "/estudios/<estudio_id>/pauta", "gestionar_estudios")
def guardar_pauta(ctx, actor, p, c, q):
    return 201, estudios.guardar_pauta(ctx, actor, p["estudio_id"], c)


@ruta("GET", "/estudios/<estudio_id>/incentivos", "leer")
def incentivos_de_estudio(ctx, actor, p, c, q):
    return 200, incentivos.por_estudio(ctx, p["estudio_id"])


# ── R1.6 Sesiones ──────────────────────────────────────────────────

@ruta("POST", "/sesiones", "gestionar_sesiones")
def crear_sesion(ctx, actor, p, c, q):
    return 201, sesiones.crear(ctx, actor, c)


@ruta("GET", "/sesiones", "leer")
def listar_sesiones(ctx, actor, p, c, q):
    return 200, {"items": sesiones.listar(ctx, estado=q.get("estado"))}


@ruta("GET", "/sesiones/<sesion_id>", "leer")
def ver_sesion(ctx, actor, p, c, q):
    s = sesiones.exigir(ctx.store, p["sesion_id"])
    return 200, {"id": p["sesion_id"], **s}


@ruta("PATCH", "/sesiones/<sesion_id>", "gestionar_sesiones")
def editar_sesion(ctx, actor, p, c, q):
    return 200, sesiones.editar(ctx, actor, p["sesion_id"], c)


# ── R1.2 / R1.3 Selección ──────────────────────────────────────────

@ruta("POST", "/sesiones/<sesion_id>/candidatos", "seleccionar")
def seleccionar(ctx, actor, p, c, q):
    return 200, seleccion.seleccionar(ctx, actor, p["sesion_id"], c)


@ruta("POST", "/sesiones/<sesion_id>/convocatorias", "seleccionar")
def incorporar(ctx, actor, p, c, q):
    return 201, seleccion.incorporar(ctx, actor, p["sesion_id"], c)


@ruta("GET", "/sesiones/<sesion_id>/invitacion", "leer")
def proponer_invitacion(ctx, actor, p, c, q):
    return 200, seleccion.proponer_invitacion(ctx, p["sesion_id"])


@ruta("POST", "/sesiones/<sesion_id>/invitacion", "convocar")
def invitar(ctx, actor, p, c, q):
    return 200, embudo.invitar_propuestos(ctx, actor, p["sesion_id"], c)


# ── R1.4 / R1.5 Embudo y canal ─────────────────────────────────────

@ruta("GET", "/sesiones/<sesion_id>/embudo", "leer")
def ver_embudo(ctx, actor, p, c, q):
    return 200, embudo.vista(ctx, p["sesion_id"])


@ruta("PATCH", "/convocatorias/<sesion_id>/<id_persona>", "convocar")
def transicionar(ctx, actor, p, c, q):
    return 200, embudo.transicionar(ctx, actor, p["sesion_id"], p["id_persona"], c)


@ruta("POST", "/convocatorias/<sesion_id>/<id_persona>/intento", "convocar")
def intento(ctx, actor, p, c, q):
    return 200, embudo.registrar_intento(ctx, actor, p["sesion_id"], p["id_persona"], c)


@ruta("POST", "/convocatorias/<sesion_id>/<id_persona>/canal", "convocar")
def canal(ctx, actor, p, c, q):
    return 200, embudo.cambiar_canal(ctx, actor, p["sesion_id"], p["id_persona"], c)


@ruta("POST", "/convocatorias/<sesion_id>/<id_persona>/reingreso", "convocar")
def reingreso(ctx, actor, p, c, q):
    return 200, embudo.reingresar(ctx, actor, p["sesion_id"], p["id_persona"], c)


@ruta("DELETE", "/convocatorias/<sesion_id>/<id_persona>", "seleccionar")
def quitar(ctx, actor, p, c, q):
    return 200, embudo.quitar_candidato(ctx, actor, p["sesion_id"], p["id_persona"])


@ruta("GET", "/convocatorias/<sesion_id>/<id_persona>/contacto", "convocar")
def contacto(ctx, actor, p, c, q):
    return 200, canales.contacto(ctx, actor, p["sesion_id"], p["id_persona"],
                                 q.get("canal") or "celular")


@ruta("POST", "/convocatorias/<sesion_id>/<id_persona>/whatsapp", "convocar")
def whatsapp_enviar(ctx, actor, p, c, q):
    return 200, canales.enviar_whatsapp(ctx, actor, p["sesion_id"], p["id_persona"], c)


# ── R1.6 Reemplazo ─────────────────────────────────────────────────

@ruta("POST", "/sesiones/<sesion_id>/reemplazo", "convocar")
def proponer_reemplazo(ctx, actor, p, c, q):
    return 200, reemplazo.proponer(ctx, actor, p["sesion_id"], c)


@ruta("POST", "/sesiones/<sesion_id>/reemplazo/resolver", "convocar")
def resolver_reemplazo(ctx, actor, p, c, q):
    return 200, reemplazo.resolver(ctx, actor, p["sesion_id"], c)


# ── R1.7 Recepción ─────────────────────────────────────────────────

@ruta("GET", "/sesiones/<sesion_id>/recepcion", "recibir")
def ver_recepcion(ctx, actor, p, c, q):
    return 200, recepcion.lista(ctx, p["sesion_id"])


@ruta("POST", "/sesiones/<sesion_id>/asistencias", "recibir")
def check_in(ctx, actor, p, c, q):
    return 201, recepcion.registrar(ctx, actor, p["sesion_id"], c)


# ── R1.8 Cierre ────────────────────────────────────────────────────

@ruta("POST", "/sesiones/<sesion_id>/cerrar", "recibir")
def cerrar(ctx, actor, p, c, q):
    return 200, cierre.cerrar(ctx, actor, p["sesion_id"], c)


@ruta("POST", "/sesiones/<sesion_id>/cancelar", "gestionar_sesiones")
def cancelar(ctx, actor, p, c, q):
    return 200, cierre.cancelar(ctx, actor, p["sesion_id"], c)


# ── R1.9 Historial ─────────────────────────────────────────────────

@ruta("GET", "/personas/<id_persona>/historial", "ver_historial")
def ver_historial(ctx, actor, p, c, q):
    return 200, historial.ver(ctx, util.validar_id_persona(p["id_persona"]))


@ruta("POST", "/historico", "gestionar_estudios")
def importar_historico(ctx, actor, p, c, q):
    return 201, importacion.importar(ctx, actor, c)


# ── R1.10 Incentivos ───────────────────────────────────────────────

@ruta("GET", "/sesiones/<sesion_id>/incentivos", "leer")
def ver_incentivos(ctx, actor, p, c, q):
    return 200, incentivos.vista(ctx, p["sesion_id"])


@ruta("PATCH", "/incentivos/<sesion_id>/<id_persona>", "liquidar_incentivos")
def asignar_regalo(ctx, actor, p, c, q):
    return 200, incentivos.asignar(ctx, actor, p["sesion_id"], p["id_persona"], c)


@ruta("POST", "/incentivos/<sesion_id>/<id_persona>/entrega", "liquidar_incentivos")
def entregar_regalo(ctx, actor, p, c, q):
    return 200, incentivos.entregar(ctx, actor, p["sesion_id"], p["id_persona"])


# ── Configuración ──────────────────────────────────────────────────

@ruta("GET", "/config", "leer")
def ver_config(ctx, actor, p, c, q):
    return 200, {
        "fatiga": configuracion.fatiga(ctx.store),
        "categorias": configuracion.categorias(ctx.store),
        "whatsapp": configuracion.whatsapp(ctx.store),
        "guion": configuracion.guion(ctx.store),
        "regalos": configuracion.listar_regalos(ctx.store),
    }


@ruta("PUT", "/config/fatiga", "configurar")
def config_fatiga(ctx, actor, p, c, q):
    return 200, configuracion.guardar_fatiga(ctx, actor, c)


@ruta("PUT", "/config/categorias", "configurar")
def config_categorias(ctx, actor, p, c, q):
    return 200, {"items": configuracion.guardar_categorias(ctx, actor, c)}


@ruta("PUT", "/config/whatsapp", "configurar")
def config_whatsapp(ctx, actor, p, c, q):
    return 200, configuracion.guardar_whatsapp(ctx, actor, c)


@ruta("PUT", "/config/guion", "configurar")
def config_guion(ctx, actor, p, c, q):
    return 200, configuracion.guardar_guion(ctx, actor, c)


@ruta("POST", "/regalos", "configurar")
def crear_regalo(ctx, actor, p, c, q):
    return 201, configuracion.guardar_regalo(ctx, actor, c)


@ruta("PUT", "/regalos/<regalo_id>", "configurar")
def editar_regalo(ctx, actor, p, c, q):
    return 200, configuracion.guardar_regalo(ctx, actor, c, p["regalo_id"])


@ruta("GET", "/usuarios", "gestionar_roles")
def listar_usuarios(ctx, actor, p, c, q):
    return 200, {"items": usuarios.listar(ctx, getattr(ctx, "padron", None))}


@ruta("PUT", "/usuarios/<uid>/roles", "gestionar_roles")
def roles_usuario(ctx, actor, p, c, q):
    return 200, usuarios.asignar(ctx, actor, p["uid"], c, getattr(ctx, "padron", None))


# ── R1.11 Cumplimiento ─────────────────────────────────────────────

@ruta("POST", "/cumplimiento/cascada", "cumplimiento")
def correr_cascada(ctx, actor, p, c, q):
    return 200, cascada.procesar(ctx)


@ruta("POST", "/cumplimiento/consistencia", "cumplimiento")
def correr_consistencia(ctx, actor, p, c, q):
    return 200, consistencia.verificar(ctx, reparar=bool(c.get("reparar")))


# ── R1.5 Webhook de WhatsApp (público, con firma) ──────────────────

@ruta("GET", "/webhooks/whatsapp", None)
def webhook_verificar(ctx, actor, p, c, q):
    # Handshake de Meta: devuelve el challenge si el token coincide.
    if q.get("hub.mode") == "subscribe" and ctx.cfg.wa_verify_token and \
            q.get("hub.verify_token") == ctx.cfg.wa_verify_token:
        return 200, {"__texto__": q.get("hub.challenge", "")}
    return 403, {"error": "sin_permiso", "mensaje": "Token de verificación inválido."}


@ruta("POST", "/webhooks/whatsapp", None)
def webhook_recibir(ctx, actor, p, c, q):
    # La firma se valida en main.py, que es quien tiene el cuerpo crudo.
    return 200, canales.procesar_webhook(ctx, c)
