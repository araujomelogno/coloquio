"""Constantes del modelo (SPEC §6) y la máquina de estados del embudo (R1.4).

```
candidato → invitado → contactado → aceptó → confirmado → asistió
                ↓           ↓          ↓          ↓
            no contactable  rechazó   se cayó   no-show
                                          ↓
                                     reemplazado
```
"""

import math

# ── Embudo ──
CANDIDATO = "candidato"
INVITADO = "invitado"
CONTACTADO = "contactado"
ACEPTO = "acepto"
CONFIRMADO = "confirmado"
ASISTIO = "asistio"
NO_CONTACTABLE = "no_contactable"
RECHAZO = "rechazo"
SE_CAYO = "se_cayo"
NO_SHOW = "no_show"
REEMPLAZADO = "reemplazado"

ESTADOS = (CANDIDATO, INVITADO, CONTACTADO, ACEPTO, CONFIRMADO, ASISTIO,
           NO_CONTACTABLE, RECHAZO, SE_CAYO, NO_SHOW, REEMPLAZADO)

ETIQUETAS = {
    CANDIDATO: "Candidato", INVITADO: "Invitado", CONTACTADO: "Contactado",
    ACEPTO: "Aceptó", CONFIRMADO: "Confirmado", ASISTIO: "Asistió",
    NO_CONTACTABLE: "No contactable", RECHAZO: "Rechazó", SE_CAYO: "Se cayó",
    NO_SHOW: "No-show", REEMPLAZADO: "Reemplazado",
}

# Transiciones directas permitidas.
TRANSICIONES = {
    CANDIDATO: {INVITADO},
    INVITADO: {CONTACTADO, NO_CONTACTABLE},
    CONTACTADO: {ACEPTO, RECHAZO},
    ACEPTO: {CONFIRMADO, SE_CAYO},
    # Una baja de último momento de alguien confirmado también es «se cayó».
    CONFIRMADO: {ASISTIO, NO_SHOW, SE_CAYO},
    SE_CAYO: {REEMPLAZADO},
    NO_SHOW: {REEMPLAZADO},
}

# Atajos de un clic (R1.5: «registrar el resultado es un clic por estado»).
# Si el coordinador marca «aceptó» sobre alguien invitado, el contacto
# existió: se registran los dos eventos, en orden, no se saltea ninguno.
ATAJOS = {
    (INVITADO, ACEPTO): (CONTACTADO, ACEPTO),
    (INVITADO, RECHAZO): (CONTACTADO, RECHAZO),
    (CONTACTADO, CONFIRMADO): (ACEPTO, CONFIRMADO),
    (INVITADO, CONFIRMADO): (CONTACTADO, ACEPTO, CONFIRMADO),
}

# Sacan a la persona del embudo de la sesión. Volver requiere acción
# explícita (`reingresar`), con motivo.
TERMINALES_REINGRESABLES = {RECHAZO, NO_CONTACTABLE, NO_SHOW}
TERMINALES = TERMINALES_REINGRESABLES | {SE_CAYO, REEMPLAZADO, ASISTIO}

# Los que ocupan un lugar en la cuota: dijeron que sí y siguen.
CUBREN_CUOTA = {ACEPTO, CONFIRMADO, ASISTIO}
# Los que siguen en juego en la sesión.
ACTIVOS = {CANDIDATO, INVITADO, CONTACTADO, ACEPTO, CONFIRMADO}
# Los que ocupan un lugar de invitación (para el sobre-reclutamiento).
EN_INVITACION = {INVITADO, CONTACTADO, ACEPTO, CONFIRMADO, ASISTIO}

# ── Sesión ──
PLANIFICADA = "planificada"
CONVOCANDO = "convocando"
CONFIRMADA = "confirmada"
REALIZADA = "realizada"
CANCELADA = "cancelada"
ESTADOS_SESION = (PLANIFICADA, CONVOCANDO, CONFIRMADA, REALIZADA, CANCELADA)
SESION_ABIERTA = {PLANIFICADA, CONVOCANDO, CONFIRMADA}

TIPOS_SESION = ("grupo", "idi")
DIMENSIONES_CUOTA = ("sexo", "tramoEtario", "localidad")

CANALES = ("manual", "whatsapp")

# ── Incentivo ──
COMPROMETIDO = "comprometido"
ENTREGADO = "entregado"

# ── Salidas cuando no hay reemplazo (R1.6) ──
SALIDAS_SIN_REEMPLAZO = {
    "bajar_cupo": "Bajar el cupo",
    "correr_fecha": "Correr la fecha",
    "aceptar_incompleta": "Aceptar la sesión con la cuota incompleta",
}

# ── Configuración por defecto ──
# La ventana y la categorización son una definición metodológica de los
# investigadores (SPEC §10, bloqueante de producto). Estos valores son un punto
# de partida editable desde Configuración, no una decisión.
FATIGA_POR_DEFECTO = {
    "ventanaDias": 180,        # ventana por categoría
    "maxPorCategoria": 1,      # participaciones en la ventana que excluyen
    "ventanaGlobalDias": 365,  # ventana del tope global
    "maxGlobal": 3,            # tope global, cualquier categoría
}

CATEGORIAS_POR_DEFECTO = [
    {"slug": "bebidas", "etiqueta": "Bebidas"},
    {"slug": "alimentos", "etiqueta": "Alimentos"},
    {"slug": "banca", "etiqueta": "Banca y finanzas"},
    {"slug": "telecomunicaciones", "etiqueta": "Telecomunicaciones"},
    {"slug": "politica", "etiqueta": "Política y opinión pública"},
    {"slug": "salud", "etiqueta": "Salud"},
    {"slug": "retail", "etiqueta": "Retail"},
    {"slug": "automotor", "etiqueta": "Automotor"},
    {"slug": "otros", "etiqueta": "Otros"},
]

WHATSAPP_POR_DEFECTO = {
    "plantillaInvitacion": "coloquio_invitacion",
    "plantillaRecordatorio": "coloquio_recordatorio",
    "plantillaConfirmacion": "coloquio_confirmacion",
    "idioma": "es",
}

GUION_POR_DEFECTO = (
    "Hola, te hablamos de Equipos Consultores. Estamos organizando un "
    "encuentro de conversación sobre {tema} el {fecha} en {lugar}, de "
    "aproximadamente {duracion} minutos. Por participar te llevás {incentivo}. "
    "¿Te interesaría participar? Tu código de convocatoria es {codigo}."
)


def meta_invitacion(objetivo, ratio):
    """Cuántos invitar para sentar `objetivo`, con el ratio de sobre-reclutamiento."""
    return int(math.ceil(objetivo * ratio - 1e-9))


def tasa_caida_supuesta(ratio):
    return round(1 - 1 / ratio, 4) if ratio and ratio > 0 else 0.0
