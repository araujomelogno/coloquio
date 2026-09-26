"""Configuración por variables de entorno. Ningún secreto vive en el repo.

Lo que no es secreto (qué instancia, qué base, qué URL) va en
`functions/.env`, que Firebase carga en el deploy. Los secretos, en Secret
Manager, declarados en `SECRETOS` de `main.py`.
"""

import os

ZONA_HORARIA = "America/Montevideo"


def _secreto(e, clave):
    """Un secreto «vacío» en Secret Manager se carga como `-` (Secret Manager
    no admite un valor vacío). Se trata igual que si no estuviera."""
    valor = (e.get(clave) or "").strip()
    return "" if valor == "-" else valor


class Config:
    def __init__(self, entorno=None):
        e = os.environ if entorno is None else entorno
        self.proyecto = e.get("GCLOUD_PROJECT") or e.get("GOOGLE_CLOUD_PROJECT") or "gestion-paneles"
        # Base Firestore con nombre propio (SPEC §7.2 condición 1). La base por
        # defecto es de `paneles` y ahí solo vive su padrón de usuarios.
        self.base_firestore = e.get("COLOQUIO_FIRESTORE_DB", "coloquio")
        # Bóveda: en producción, conector + IAM. En local, un DSN.
        self.dsn_boveda = e.get("DSN_BOVEDA_COLOQUIO", "").strip() or None
        self.boveda_instancia = e.get(
            "BOVEDA_INSTANCIA", "gestion-paneles:southamerica-east1:paneles-boveda")
        self.boveda_usuario_iam = e.get("BOVEDA_USUARIO_IAM", "coloquio-app@gestion-paneles.iam")
        self.boveda_base = e.get("BOVEDA_BASE", "paneles_boveda")
        # Motor semántico de `paneles`, por su API (motor.py).
        self.paneles_api_url = e.get("PANELES_API_URL", "").strip()
        # WhatsApp Cloud API (Meta directo, sin intermediario — SPEC §9).
        self.wa_token = _secreto(e, "WHATSAPP_TOKEN")
        self.wa_phone_number_id = _secreto(e, "WHATSAPP_PHONE_NUMBER_ID")
        self.wa_app_secret = _secreto(e, "WHATSAPP_APP_SECRET")
        self.wa_verify_token = _secreto(e, "WHATSAPP_VERIFY_TOKEN")
        self.wa_prefijo_pais = e.get("WHATSAPP_PREFIJO_PAIS", "598").strip()

    @property
    def whatsapp_configurado(self):
        return bool(self.wa_token and self.wa_phone_number_id)


def cargar(entorno=None):
    return Config(entorno)
