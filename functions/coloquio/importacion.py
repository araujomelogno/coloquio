"""P1 (candidato a P0) — Importar sesiones históricas.

R1.3 arranca sin memoria: el filtro no sabe nada de los grupos que Equipos ya
hizo, así que en los primeros meses no excluye a nadie, justo cuando el
panelista profesional ya está en el panel (SPEC §13). Cargar a mano los grupos
realizados le da memoria desde el día uno.

Se carga por `id_persona` (sin PII): la lista sale de cruzar en `paneles` los
participantes del grupo histórico. Cada participación entra marcada
`importada: true`, con su propio id de sesión histórica, y cuenta para fatiga
e historial igual que una sesión corrida en COLOQUIO. También queda en el
índice de borrado: una baja la borra igual.
"""

from . import configuracion, historial, pii, util
from .errores import DatosInvalidos


def importar(ctx, actor, cuerpo):
    categoria = configuracion.exigir_categoria(ctx.store, util.slug(cuerpo.get("categoria")))
    fecha = util.parse_fecha(cuerpo.get("fecha"))
    if fecha > ctx.ahora():
        raise DatosInvalidos("Una sesión histórica no puede tener fecha futura.")
    tipo = cuerpo.get("tipo") or "grupo"
    etiqueta = str(cuerpo.get("etiqueta") or "").strip()
    pii.validar_texto_libre(etiqueta, "etiqueta")
    crudos = cuerpo.get("idPersonas") or []
    if isinstance(crudos, str):
        crudos = [x for x in crudos.replace(",", "\n").split() if x.strip()]
    ids = sorted({util.validar_id_persona(i) for i in crudos})
    if not ids:
        raise DatosInvalidos("Pegá al menos un id_persona.")
    if len(ids) > 200:
        raise DatosInvalidos("Una sesión histórica no puede tener más de 200 participantes.")
    sesion_id = "hist_" + util.nuevo_uuid()
    sesion = {"estudioId": None, "refEstudio": None, "categoria": categoria, "fecha": fecha,
              "modalidad": "presencial", "tipo": tipo}

    def tx_fn(tx):
        docs = tx.get_many([historial.ruta(i) for i in ids])
        for i in ids:
            doc = historial.registrar_participacion(docs[historial.ruta(i)], sesion_id, sesion)
            doc["sesiones"][-1].update({"importada": True, "etiqueta": etiqueta,
                                        "importadaPor": actor.uid})
            tx.set(historial.ruta(i), doc)
        return {"sesionHistoricaId": sesion_id, "participaciones": len(ids),
                "categoria": categoria}

    return ctx.store.transaccion(tx_fn)
