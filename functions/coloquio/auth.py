"""R1.13 — Firebase Auth con el padrón de `paneles`, roles propios de COLOQUIO.

**No hay un segundo directorio de personal.** Quién es empleado de Equipos lo
dice `usuarios/{uid}` en la base Firestore **por defecto** del proyecto, que es
de `paneles` y COLOQUIO solo lee. Si alguien está dado de baja ahí
(`activo = false`), tampoco entra acá.

**Los roles sí son de COLOQUIO** (HANDOFF §1: «el control de qué ve cada uno va
en los roles»), y viven en su base: `rolUsuario/{uid}.roles`. Un usuario puede
tener más de uno. El `admin` del padrón de `paneles` es administrador de
COLOQUIO por construcción: sin eso no habría quién asignar el primer rol.

    coordinador   convoca, recibe, liquida incentivos
    investigador  estudios, pautas, selección, historial
    administrador catálogos, umbrales, roles, cumplimiento (y todo lo demás)

En `rolUsuario` no se guarda nombre ni email: el validador de R1.12 no hace
distinción entre personal y panelistas, y no hace falta.
"""

from .errores import NoAutenticado, SinPermiso

ROLES = ("coordinador", "investigador", "administrador")

PERMISOS = {
    "leer": {"coordinador", "investigador", "administrador"},
    "gestionar_estudios": {"investigador", "administrador"},
    "gestionar_sesiones": {"investigador", "coordinador", "administrador"},
    "seleccionar": {"investigador", "coordinador", "administrador"},
    "ver_historial": {"investigador", "coordinador", "administrador"},
    # Saltar el filtro de fatiga con motivo. Lo pueden hacer quienes eligen a
    # quién llamar; queda registrado con usuario y motivo (R1.3).
    "anular_fatiga": {"investigador", "coordinador", "administrador"},
    "convocar": {"coordinador", "administrador"},
    "recibir": {"coordinador", "administrador"},
    "liquidar_incentivos": {"coordinador", "administrador"},
    "configurar": {"administrador"},
    "gestionar_roles": {"administrador"},
    "cumplimiento": {"administrador"},
}


class Actor:
    def __init__(self, uid, email=None, roles=(), nombre=None, token=None):
        self.uid = uid
        self.email = email
        self.roles = tuple(sorted(set(roles)))
        self.nombre = nombre
        # El ID token se conserva solo para reenviarlo al motor de `paneles`.
        self.token = token

    def puede(self, permiso):
        return any(r in PERMISOS.get(permiso, set()) for r in self.roles)

    def exigir(self, permiso):
        if not self.puede(permiso):
            raise SinPermiso(
                "Tus roles en COLOQUIO "
                f"({', '.join(self.roles) or 'ninguno'}) no permiten esta operación.",
                {"permiso": permiso},
            )
        return self

    def como_dict(self):
        return {"uid": self.uid, "email": self.email, "roles": list(self.roles),
                "nombre": self.nombre,
                "permisos": sorted(p for p in PERMISOS if self.puede(p))}


SISTEMA = Actor(uid="sistema", roles=ROLES, nombre="sistema")


def token_de(headers):
    autorizacion = headers.get("Authorization") or headers.get("authorization") or ""
    if not autorizacion.lower().startswith("bearer "):
        raise NoAutenticado("Falta el token de Firebase Auth (header Authorization).")
    return autorizacion.split(" ", 1)[1].strip()


def roles_de(usuario_padron, doc_roles):
    roles = set((doc_roles or {}).get("roles") or [])
    if (usuario_padron or {}).get("rol") == "admin":
        roles.add("administrador")
    return sorted(r for r in roles if r in ROLES)


def actor_de_request(headers, store, verificar_token=None, buscar_en_padron=None):
    """Resuelve el actor. Las dependencias se inyectan para probar sin Firebase."""
    if verificar_token is None or buscar_en_padron is None:
        from firebase_admin import auth as fb_auth, firestore

        def verificar_token(token):  # noqa: F811
            return fb_auth.verify_id_token(token)

        def buscar_en_padron(uid):  # noqa: F811
            # Base por defecto: el padrón es de `paneles`. Solo lectura.
            doc = firestore.client().collection("usuarios").document(uid).get()
            return doc.to_dict() if doc.exists else None

    token = token_de(headers)
    try:
        decodificado = verificar_token(token)
    except Exception as error:  # noqa: BLE001
        raise NoAutenticado(f"Token inválido: {error}")

    uid = decodificado.get("uid") or decodificado.get("user_id")
    usuario = buscar_en_padron(uid) or {}
    if not usuario or usuario.get("activo") is False:
        raise SinPermiso(
            "Tu usuario no está habilitado en el padrón de Equipos. Pedile el "
            "alta a un administrador de `paneles`.")
    roles = roles_de(usuario, store.get(f"rolUsuario/{uid}"))
    if not roles:
        raise SinPermiso(
            "Estás en el padrón, pero no tenés roles en COLOQUIO. Pedile a un "
            "administrador que te asigne coordinador, investigador o administrador.",
            {"uid": uid})
    return Actor(uid=uid, email=decodificado.get("email") or usuario.get("email"),
                 roles=roles, nombre=usuario.get("nombre"), token=token)
