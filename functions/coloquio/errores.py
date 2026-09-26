"""Errores de dominio, con el código HTTP que les corresponde.

Misma convención que `panel_api.errores` de `paneles`: el frontend de los dos
sistemas lee `{error, mensaje, detalle}` y decide por `error`.
"""


class ErrorApi(Exception):
    """Error esperable: se traduce a una respuesta JSON con su status."""

    status = 400
    codigo = "error"

    def __init__(self, mensaje, detalle=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalle = detalle

    def como_dict(self):
        cuerpo = {"error": self.codigo, "mensaje": self.mensaje}
        if self.detalle is not None:
            cuerpo["detalle"] = self.detalle
        return cuerpo


class DatosInvalidos(ErrorApi):
    status = 400
    codigo = "datos_invalidos"


class NoAutenticado(ErrorApi):
    status = 401
    codigo = "no_autenticado"


class SinPermiso(ErrorApi):
    status = 403
    codigo = "sin_permiso"


class NoEncontrado(ErrorApi):
    status = 404
    codigo = "no_encontrado"


class Conflicto(ErrorApi):
    status = 409
    codigo = "conflicto"


class TransicionInvalida(ErrorApi):
    """R1.4 — el embudo no admite ese salto de estado."""

    status = 409
    codigo = "transicion_invalida"


class RequiereAnulacion(ErrorApi):
    """R1.3 / R1.7 — la regla se puede saltar, pero no en silencio.

    El cliente reintenta mandando `anulacion: {motivo}`; la anulación queda
    registrada con el usuario y la hora.
    """

    status = 409
    codigo = "requiere_anulacion"


class ContactoRechazado(ErrorApi):
    """La bóveda se negó a entregar un dato de contacto (R1.4 / Fase 5 R5.2).

    No es un error de COLOQUIO: el gate está en la base y no se puede saltear.
    """

    status = 403
    codigo = "contacto_rechazado"


class FugaDePII(ErrorApi):
    """R1.12: se intentó escribir PII en el store de COLOQUIO."""

    status = 500
    codigo = "fuga_de_pii"


class ServicioNoDisponible(ErrorApi):
    status = 503
    codigo = "servicio_no_disponible"
