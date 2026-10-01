"""Roles de COLOQUIO sobre el padrón de `paneles` (R1.13).

El padrón (quién es empleado, nombre, email) se **lee** de `usuarios` en la
base por defecto; COLOQUIO no lo escribe. Lo único que COLOQUIO guarda es
`rolUsuario/{uid}.roles`, en su propia base.
"""

from . import auth
from .errores import DatosInvalidos, NoEncontrado


def leer_padron():
    from firebase_admin import firestore

    return {d.id: d.to_dict() for d in firestore.client().collection("usuarios").stream()}


def listar(ctx, padron=None):
    padron = padron if padron is not None else leer_padron()
    roles = dict(ctx.store.listar("rolUsuario"))
    items = []
    for uid, u in padron.items():
        items.append({
            "uid": uid,
            "nombre": u.get("nombre"),
            "email": u.get("email"),
            "activoEnPadron": u.get("activo", True) is not False,
            "rolPaneles": u.get("rol"),
            "roles": auth.roles_de(u, roles.get(uid)),
            "adminPorPaneles": u.get("rol") == "admin",
        })
    items.sort(key=lambda i: (not i["activoEnPadron"], (i["nombre"] or i["email"] or "").lower()))
    return items


def asignar(ctx, actor, uid, cuerpo, padron=None):
    padron = padron if padron is not None else leer_padron()
    if uid not in padron:
        raise NoEncontrado("Ese usuario no está en el padrón de Equipos.")
    roles = sorted(set(cuerpo.get("roles") or []))
    invalidos = [r for r in roles if r not in auth.ROLES]
    if invalidos:
        raise DatosInvalidos(f"Roles inválidos: {invalidos}.", {"validos": list(auth.ROLES)})
    ctx.store.set(f"rolUsuario/{uid}", {"roles": roles, "actualizadoPor": actor.uid,
                                        "actualizadoEn": ctx.ahora()})
    return {"uid": uid, "roles": auth.roles_de(padron[uid], {"roles": roles})}
