/* Cliente de la API de COLOQUIO (`/api/cuali/**`).

   En producción manda el ID token de Firebase Auth; el backend resuelve los
   roles contra el padrón de `paneles` + los roles propios de COLOQUIO.
   En modo local (scripts/servidor_local.py) manda el usuario de prueba
   elegido en la pantalla de ingreso. El cliente nunca escribe en la base. */

const BASE = (window.API_BASE || '/api').replace(/\/$/, '') + '/cuali';

export const estado = {
  local: false,
  usuarioLocal: null,
  obtenerToken: async () => null,
};

export class ErrorApi extends Error {
  constructor(mensaje, status, cuerpo) {
    super(mensaje);
    this.status = status;
    this.cuerpo = cuerpo || {};
    this.codigo = this.cuerpo.error || 'error';
    this.detalle = this.cuerpo.detalle;
  }
}

async function pedir(metodo, camino, { cuerpo, consulta } = {}) {
  const url = new URL(BASE + camino, window.location.origin);
  Object.entries(consulta || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
  });
  const headers = { 'Content-Type': 'application/json' };
  if (estado.local) {
    if (estado.usuarioLocal) headers['X-Usuario-Local'] = estado.usuarioLocal;
  } else {
    const token = await estado.obtenerToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  let respuesta;
  try {
    respuesta = await fetch(url, { method: metodo, headers, body: cuerpo ? JSON.stringify(cuerpo) : undefined });
  } catch (e) {
    throw new ErrorApi('No se pudo conectar con el servidor. Revisá la conexión.', 0, { error: 'red' });
  }
  let datos = {};
  try { datos = await respuesta.json(); } catch { /* sin cuerpo */ }
  if (!respuesta.ok) throw new ErrorApi(datos.mensaje || `Error ${respuesta.status}`, respuesta.status, datos);
  return datos;
}

const GET = (c, q) => pedir('GET', c, { consulta: q });
const POST = (c, b) => pedir('POST', c, { cuerpo: b || {} });
const PUT = (c, b) => pedir('PUT', c, { cuerpo: b || {} });
const PATCH = (c, b) => pedir('PATCH', c, { cuerpo: b || {} });
const DELETE = (c) => pedir('DELETE', c);

export const entorno = () => GET('/entorno');
export const yo = () => GET('/yo');
export const catalogos = () => GET('/catalogos');
export const tablero = () => GET('/tablero');

export const estudios = {
  listar: () => GET('/estudios'),
  ver: (id) => GET(`/estudios/${id}`),
  crear: (b) => POST('/estudios', b),
  editar: (id, b) => PATCH(`/estudios/${id}`, b),
  guardarPauta: (id, b) => POST(`/estudios/${id}/pauta`, b),
  incentivos: (id) => GET(`/estudios/${id}/incentivos`),
};

export const sesiones = {
  listar: (q) => GET('/sesiones', q),
  ver: (id) => GET(`/sesiones/${id}`),
  crear: (b) => POST('/sesiones', b),
  editar: (id, b) => PATCH(`/sesiones/${id}`, b),
  seleccionar: (id, b) => POST(`/sesiones/${id}/candidatos`, b),
  incorporar: (id, b) => POST(`/sesiones/${id}/convocatorias`, b),
  propuestaInvitacion: (id) => GET(`/sesiones/${id}/invitacion`),
  invitar: (id, b) => POST(`/sesiones/${id}/invitacion`, b),
  embudo: (id) => GET(`/sesiones/${id}/embudo`),
  proponerReemplazo: (id, b) => POST(`/sesiones/${id}/reemplazo`, b),
  resolverReemplazo: (id, b) => POST(`/sesiones/${id}/reemplazo/resolver`, b),
  recepcion: (id) => GET(`/sesiones/${id}/recepcion`),
  checkIn: (id, b) => POST(`/sesiones/${id}/asistencias`, b),
  cerrar: (id, b) => POST(`/sesiones/${id}/cerrar`, b),
  cancelar: (id, b) => POST(`/sesiones/${id}/cancelar`, b),
  incentivos: (id) => GET(`/sesiones/${id}/incentivos`),
};

export const convocatorias = {
  transicion: (s, p, b) => PATCH(`/convocatorias/${s}/${p}`, b),
  intento: (s, p, b) => POST(`/convocatorias/${s}/${p}/intento`, b),
  canal: (s, p, canal) => POST(`/convocatorias/${s}/${p}/canal`, { canal }),
  reingreso: (s, p, motivo) => POST(`/convocatorias/${s}/${p}/reingreso`, { motivo }),
  quitar: (s, p) => DELETE(`/convocatorias/${s}/${p}`),
  contacto: (s, p, canal) => GET(`/convocatorias/${s}/${p}/contacto`, { canal }),
  whatsapp: (s, p, tipo) => POST(`/convocatorias/${s}/${p}/whatsapp`, { tipo }),
};

export const incentivos = {
  asignar: (s, p, regaloId) => PATCH(`/incentivos/${s}/${p}`, { regaloId }),
  entregar: (s, p) => POST(`/incentivos/${s}/${p}/entrega`),
};

export const personas = {
  historial: (id) => GET(`/personas/${id}/historial`),
  importar: (b) => POST('/historico', b),
};

export const config = {
  ver: () => GET('/config'),
  fatiga: (b) => PUT('/config/fatiga', b),
  categorias: (b) => PUT('/config/categorias', b),
  whatsapp: (b) => PUT('/config/whatsapp', b),
  guion: (b) => PUT('/config/guion', b),
  crearRegalo: (b) => POST('/regalos', b),
  editarRegalo: (id, b) => PUT(`/regalos/${id}`, b),
  usuarios: () => GET('/usuarios'),
  roles: (uid, roles) => PUT(`/usuarios/${uid}/roles`, { roles }),
  cascada: () => POST('/cumplimiento/cascada'),
  consistencia: (reparar) => POST('/cumplimiento/consistencia', { reparar }),
};
