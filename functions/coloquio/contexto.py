"""Contexto de una request: el store, la bóveda, el motor, el canal y el reloj.

La bóveda se abre en forma perezosa: la mayoría de las rutas (embudo,
recepción, incentivos) no la tocan, y cada conexión de más es superficie de
exposición que no hace falta abrir.
"""

import datetime as dt

from . import boveda as mod_boveda, config as mod_config, motor as mod_motor, whatsapp


def ahora_utc():
    return dt.datetime.now(dt.timezone.utc)


class Contexto:
    def __init__(self, store, boveda=None, motor=None, canal_wa=None, cfg=None,
                 reloj=None, fabrica_boveda=None):
        self.store = store
        self.cfg = cfg or mod_config.cargar({})
        self._boveda = boveda
        self._fabrica_boveda = fabrica_boveda
        self.motor = motor or mod_motor.crear(self.cfg.paneles_api_url)
        self.canal_wa = canal_wa or whatsapp.ClienteWhatsApp.desde_config(self.cfg)
        self.reloj = reloj or ahora_utc

    @property
    def boveda(self):
        if self._boveda is None:
            if self._fabrica_boveda:
                self._boveda = self._fabrica_boveda()
            else:
                c = self.cfg
                self._boveda = mod_boveda.BovedaPostgres(
                    dsn=c.dsn_boveda, instancia=c.boveda_instancia,
                    usuario_iam=c.boveda_usuario_iam, base=c.boveda_base)
        return self._boveda

    @property
    def abrio_boveda(self):
        return self._boveda is not None

    def ahora(self):
        return self.reloj()

    def cerrar(self):
        if self._boveda is not None and self._fabrica_boveda is None:
            self._boveda.cerrar()
