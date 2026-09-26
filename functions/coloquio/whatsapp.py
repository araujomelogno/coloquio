"""R1.5 — canal WhatsApp: Cloud API de Meta, directo (SPEC §9).

Tres decisiones que gobiernan este módulo:

**La invitación provoca respuesta.** La plantilla de invitación lleva dos
botones de respuesta rápida («Sí, me interesa» / «No puedo»). Cuando la
persona toca uno, se abre la **ventana de servicio de 24 h** y todo lo que
sigue —confirmación, recordatorio, dudas— viaja como mensaje libre, que no se
cobra. Mandar tres plantillas sueltas sería pagar tres veces (SPEC §9, R1.5).

**El payload del botón es el `id_persona`, no el teléfono.** Cada botón vuelve
con `c1|<sesionId>|<idPersona>|si|no`. Así el webhook sabe a qué convocatoria
corresponde la respuesta sin guardar el número: el celular se pide a la bóveda
al enviar y se descarta (R1.12). El webhook de Meta trae el número y el
nombre de perfil del remitente; **no se leen, no se loguean, no se guardan**.

**Si el canal falla, degrada a manual.** Plantilla rechazada, número
bloqueado, entrega fallida: la convocatoria conserva su estado y pasa a canal
manual con el motivo. El embudo nunca se pierde por un problema de mensajería.
"""

import hashlib
import hmac
import json
import re
import urllib.error
import urllib.request

API = "https://graph.facebook.com/v21.0"
PREFIJO_PAYLOAD = "c1"
VENTANA_SERVICIO_HORAS = 24


class ErrorCanal(RuntimeError):
    """El envío no salió. No es un error del usuario: degrada a manual."""


def normalizar_celular(numero, prefijo_pais="598"):
    """A formato E.164 sin `+`, como lo pide la Cloud API.

    Uruguay: `099 123 456` → `59899123456`; `99123456` → `59899123456`.
    Un número que ya trae código de país se respeta.
    """
    digitos = re.sub(r"\D", "", str(numero or ""))
    if not digitos:
        raise ErrorCanal("La persona no tiene celular cargado en la bóveda.")
    if str(numero).strip().startswith("+") or digitos.startswith(prefijo_pais) and len(digitos) > 9:
        return digitos
    if digitos.startswith("0"):
        digitos = digitos[1:]
    if len(digitos) < 8:
        raise ErrorCanal("El celular cargado en la bóveda no tiene un formato válido.")
    return prefijo_pais + digitos


def payload(sesion_id, id_persona, respuesta):
    return f"{PREFIJO_PAYLOAD}|{sesion_id}|{id_persona}|{respuesta}"


def leer_payload(texto):
    partes = str(texto or "").split("|")
    if len(partes) != 4 or partes[0] != PREFIJO_PAYLOAD:
        return None
    return {"sesionId": partes[1], "idPersona": partes[2], "respuesta": partes[3]}


def firma_valida(cuerpo_bytes, firma_header, app_secret):
    """`X-Hub-Signature-256` = HMAC-SHA256 del cuerpo con el app secret."""
    if not app_secret or not firma_header or not firma_header.startswith("sha256="):
        return False
    esperada = hmac.new(app_secret.encode(), cuerpo_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, firma_header.split("=", 1)[1])


def interpretar_webhook(cuerpo):
    """Eventos relevantes del webhook, **sin** datos del remitente.

    Devuelve una lista de:
      {"tipo": "respuesta", "payload": {...}, "contextoId": wamid|None}
      {"tipo": "texto", "contextoId": wamid|None, "afirmativo": bool|None}
      {"tipo": "estado", "wamid": ..., "estado": "failed|delivered|...", "error": str|None}
    """
    eventos = []
    for entrada in (cuerpo or {}).get("entry") or []:
        for cambio in entrada.get("changes") or []:
            valor = cambio.get("value") or {}
            for m in valor.get("messages") or []:
                contexto = (m.get("context") or {}).get("id")
                tipo = m.get("type")
                datos = None
                if tipo == "button":
                    datos = leer_payload((m.get("button") or {}).get("payload"))
                elif tipo == "interactive":
                    datos = leer_payload(
                        ((m.get("interactive") or {}).get("button_reply") or {}).get("id"))
                if datos:
                    eventos.append({"tipo": "respuesta", "payload": datos,
                                    "contextoId": contexto})
                elif tipo == "text":
                    texto = ((m.get("text") or {}).get("body") or "").strip().lower()
                    afirmativo = None
                    if re.fullmatch(r"(s[ií]|dale|confirmo|ok|voy)[.!]*", texto):
                        afirmativo = True
                    elif re.fullmatch(r"(no|no puedo|no voy)[.!]*", texto):
                        afirmativo = False
                    # El texto en sí no sale de acá: puede traer cualquier cosa.
                    eventos.append({"tipo": "texto", "contextoId": contexto,
                                    "afirmativo": afirmativo})
            for s in valor.get("statuses") or []:
                errores = s.get("errors") or []
                eventos.append({
                    "tipo": "estado", "wamid": s.get("id"), "estado": s.get("status"),
                    "error": (errores[0].get("title") or errores[0].get("message"))
                    if errores else None,
                })
    return eventos


class ClienteWhatsApp:
    def __init__(self, token="", phone_number_id="", prefijo_pais="598", pedir=None):
        self.token = token
        self.phone_number_id = phone_number_id
        self.prefijo_pais = prefijo_pais
        self._pedir = pedir or self._pedir_http

    @classmethod
    def desde_config(cls, cfg):
        return cls(cfg.wa_token, cfg.wa_phone_number_id, cfg.wa_prefijo_pais)

    @property
    def configurado(self):
        return bool(self.token and self.phone_number_id)

    def _pedir_http(self, url, datos):
        pedido = urllib.request.Request(
            url, data=json.dumps(datos).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(pedido, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                detalle = json.loads(error.read().decode("utf-8")).get("error", {})
                mensaje = detalle.get("error_user_msg") or detalle.get("message") or str(error)
            except Exception:  # noqa: BLE001
                mensaje = str(error)
            raise ErrorCanal(f"Meta rechazó el envío: {mensaje}")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ErrorCanal(f"No se pudo llegar a la API de WhatsApp: {error}")

    def _enviar(self, datos):
        if not self.configurado:
            raise ErrorCanal("WhatsApp no está configurado (falta el token o el número emisor).")
        respuesta = self._pedir(f"{API}/{self.phone_number_id}/messages", datos)
        mensajes = respuesta.get("messages") or []
        if not mensajes or not mensajes[0].get("id"):
            raise ErrorCanal("Meta no devolvió el id del mensaje.")
        return mensajes[0]["id"]

    def enviar_plantilla(self, celular, plantilla, idioma, variables, botones=()):
        """Plantilla aprobada, con variables del cuerpo y payloads de botones."""
        componentes = []
        if variables:
            componentes.append({"type": "body", "parameters": [
                {"type": "text", "text": str(v)} for v in variables]})
        for indice, carga in enumerate(botones):
            componentes.append({"type": "button", "sub_type": "quick_reply",
                                "index": str(indice),
                                "parameters": [{"type": "payload", "payload": carga}]})
        return self._enviar({
            "messaging_product": "whatsapp",
            "to": normalizar_celular(celular, self.prefijo_pais),
            "type": "template",
            "template": {"name": plantilla, "language": {"code": idioma},
                         "components": componentes},
        })

    def enviar_texto_con_botones(self, celular, texto, botones):
        """Mensaje libre dentro de la ventana de servicio: no se cobra."""
        return self._enviar({
            "messaging_product": "whatsapp",
            "to": normalizar_celular(celular, self.prefijo_pais),
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": texto[:1024]},
                "action": {"buttons": [
                    {"type": "reply", "reply": {"id": carga, "title": titulo[:20]}}
                    for titulo, carga in botones][:3]},
            },
        })
