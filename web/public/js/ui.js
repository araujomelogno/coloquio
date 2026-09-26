/* Utilidades de interfaz: escape, toasts, modales, fechas y piezas repetidas. */

import * as api from './api.js';

export const TZ = window.APP_TZ || 'America/Montevideo';
export const $ = (sel, ctx = document) => ctx.querySelector(sel);
export const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export function toast(msg, tipo = '') {
  const w = document.getElementById('toast-wrap');
  while (w.children.length >= 3) w.firstChild.remove();
  const t = document.createElement('div');
  t.className = 'toast ' + tipo;
  t.innerHTML = `<span>${tipo === 'ok' ? '✅' : tipo === 'err' ? '⚠️' : 'ℹ️'}</span><span>${esc(msg)}</span>`;
  w.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'all .25s'; setTimeout(() => t.remove(), 260); }, 4200);
}

export function error(e) {
  console.error(e);
  toast(e?.message || String(e), 'err');
}

export function iniciales(nombre, email) {
  const src = (nombre || email || '?').trim();
  const partes = src.split(/\s+/);
  return (partes.length >= 2 ? partes[0][0] + partes[1][0] : src.slice(0, 2)).toUpperCase();
}

/* ── Fechas (siempre en hora de Montevideo) ── */
const aFecha = (v) => (v ? new Date(v) : null);
export function fecha(v) {
  const d = aFecha(v); if (!d) return '—';
  return new Intl.DateTimeFormat('es-UY', { timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric' }).format(d);
}
export function fechaHora(v) {
  const d = aFecha(v); if (!d) return '—';
  return new Intl.DateTimeFormat('es-UY', { timeZone: TZ, weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(d);
}
export function hora(v) {
  const d = aFecha(v); if (!d) return '—';
  return new Intl.DateTimeFormat('es-UY', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false }).format(d);
}
export function aInputLocal(v) {
  const d = aFecha(v); if (!d) return '';
  const p = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(d);
  const o = {}; p.forEach((x) => { o[x.type] = x.value; });
  return `${o.year}-${o.month}-${o.day}T${o.hour === '24' ? '00' : o.hour}:${o.minute}`;
}
export const pct = (x) => (x === null || x === undefined ? '—' : `${Math.round(x * 100)}%`);
export const plata = (x, moneda = 'UYU') => `${moneda === 'UYU' ? '$' : moneda + ' '}${Number(x || 0).toLocaleString('es-UY', { maximumFractionDigits: 0 })}`;

/* ── Piezas ── */
export const ETIQUETAS = {
  candidato: 'Candidato', invitado: 'Invitado', contactado: 'Contactado', acepto: 'Aceptó',
  confirmado: 'Confirmado', asistio: 'Asistió', no_contactable: 'No contactable', rechazo: 'Rechazó',
  se_cayo: 'Se cayó', no_show: 'No-show', reemplazado: 'Reemplazado',
  planificada: 'Planificada', convocando: 'Convocando', confirmada: 'Confirmada', realizada: 'Realizada', cancelada: 'Cancelada',
};
export const estado = (e) => `<span class="est est-${esc(e)}">${esc(ETIQUETAS[e] || e)}</span>`;
export const DIM = { sexo: 'Sexo', tramoEtario: 'Tramo etario', localidad: 'Localidad' };
export function segmento(s) {
  if (!s) return '—';
  return `<span class="seg-pill">${['sexo', 'tramoEtario', 'localidad'].filter((k) => s[k]).map((k) => `<span title="${DIM[k]}">${esc(s[k])}</span>`).join('')}</span>`;
}
export const codigo = (c) => `<span class="codigo">${esc(c)}</span>`;
export function histChip(h, idPersona) {
  const n = h?.total || 0;
  const clase = n === 0 ? 'cero' : n >= 2 ? 'alto' : '';
  const ult = h?.ultimaEn ? ` · últ. ${fecha(h.ultimaEn)}` : '';
  return `<button class="hist-chip ${clase}" data-historial="${esc(idPersona)}" title="Ver historial cualitativo">🗂 ${n}${ult}</button>`;
}
export function vacio(texto, icono = '📭') {
  return `<div class="empty-state"><span class="ei">${icono}</span>${esc(texto)}</div>`;
}
export function cargando() { return '<div class="empty-state"><div class="spinner"></div></div>'; }
export function encabezado(titulo, sub, acciones = '', miga = '') {
  return `<div class="page-header">${miga ? `<div class="breadcrumb">${miga}</div>` : ''}
    <div class="header-row"><div><div class="accent-bar"></div><h2>${titulo}</h2>${sub ? `<p>${sub}</p>` : ''}</div>
    <div class="toolbar">${acciones}</div></div></div>`;
}

/* ── Modal ── */
export function modal({ titulo, cuerpo, pie = '', ancho = false, alAbrir }) {
  const wrap = document.getElementById('modal-wrap');
  const el = document.createElement('div');
  el.className = 'modal-backdrop';
  el.innerHTML = `<div class="modal-box ${ancho ? 'wide' : ''}" role="dialog" aria-modal="true">
      <div class="modal-head"><div class="modal-title">${titulo}</div><button class="modal-close" aria-label="Cerrar">×</button></div>
      <div class="modal-body">${cuerpo}</div>${pie ? `<div class="modal-foot">${pie}</div>` : ''}</div>`;
  const cerrar = () => el.remove();
  el.addEventListener('click', (ev) => { if (ev.target === el) cerrar(); });
  el.querySelector('.modal-close').onclick = cerrar;
  wrap.appendChild(el);
  alAbrir?.(el, cerrar);
  return { el, cerrar };
}

/* Pide un motivo (anulaciones, reingresos). Resuelve con el texto o null. */
export function pedirMotivo({ titulo, explicacion, etiqueta = 'Motivo', boton = 'Registrar', peligro = false, detalle = '' }) {
  return new Promise((resolver) => {
    let hecho = false;
    const { el, cerrar } = modal({
      titulo,
      cuerpo: `<div class="alert alert-warn"><span>⚠️</span><span>${explicacion}</span></div>${detalle}
        <div class="form-group"><label>${esc(etiqueta)}</label><textarea id="motivo" rows="3" placeholder="Queda registrado con tu usuario y la hora."></textarea>
        <div class="field-hint">No escribas datos personales: nombres, teléfonos, emails ni documentos.</div></div>`,
      pie: `<button class="btn btn-outline" data-x>Cancelar</button><button class="btn ${peligro ? 'btn-danger' : 'btn-orange'}" data-ok>${esc(boton)}</button>`,
    });
    const fin = (v) => { if (!hecho) { hecho = true; resolver(v); } cerrar(); };
    el.querySelector('[data-x]').onclick = () => fin(null);
    el.querySelector('.modal-close').onclick = () => fin(null);
    el.querySelector('[data-ok]').onclick = () => {
      const v = el.querySelector('#motivo').value.trim();
      if (!v) { toast('El motivo es obligatorio.', 'err'); return; }
      fin(v);
    };
    setTimeout(() => el.querySelector('#motivo').focus(), 30);
  });
}

export function confirmar({ titulo, texto, boton = 'Confirmar', peligro = false }) {
  return new Promise((resolver) => {
    const { el, cerrar } = modal({
      titulo, cuerpo: `<p style="font-size:.88rem">${texto}</p>`,
      pie: `<button class="btn btn-outline" data-x>Cancelar</button><button class="btn ${peligro ? 'btn-danger' : 'btn-orange'}" data-ok>${esc(boton)}</button>`,
    });
    el.querySelector('[data-x]').onclick = () => { cerrar(); resolver(false); };
    el.querySelector('[data-ok]').onclick = () => { cerrar(); resolver(true); };
  });
}

/* R1.9 — historial cualitativo de una persona. */
export async function verHistorial(idPersona) {
  const { el } = modal({ titulo: 'Historial cualitativo', cuerpo: cargando(), ancho: true });
  const cuerpo = el.querySelector('.modal-body');
  try {
    const h = await api.personas.historial(idPersona);
    const porCat = Object.entries(h.porCategoria || {}).map(([c, v]) => `<span class="badge badge-orange" style="margin-right:.3rem">${esc(c)} · ${v.total}</span>`).join('');
    cuerpo.innerHTML = `
      <div class="stat-grid">
        <div class="stat s-total"><div class="stat-num">${h.total}</div><div class="stat-label">Participaciones</div></div>
        <div class="stat s-orange"><div class="stat-num" style="font-size:1.1rem">${fecha(h.ultimaEn)}</div><div class="stat-label">Última</div></div>
        <div class="stat s-free"><div class="stat-num">${h.convocatoriasActivas}</div><div class="stat-label">Embudos donde figura</div></div>
      </div>
      <p class="mb">${porCat || '<span class="muted">Sin participaciones por categoría.</span>'}</p>
      ${h.sesiones.length ? `<div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Estudio</th><th>Categoría</th><th>Tipo</th><th>Modalidad</th></tr></thead><tbody>
        ${h.sesiones.map((s) => `<tr><td>${fecha(s.fecha)}</td><td class="td-strong">${esc(s.estudioNombre || '—')}${s.importada ? ' <span class="badge badge-gray">importada</span>' : ''}</td><td>${esc(s.categoria)}</td><td>${s.tipo === 'idi' ? 'Entrevista' : 'Grupo'}</td><td>${esc(s.modalidad)}</td></tr>`).join('')}
      </tbody></table></div>` : vacio('Todavía no participó de ninguna sesión cualitativa.', '🆕')}
      <p class="field-hint mt">Id seudónimo: <span class="codigo">${esc(idPersona)}</span></p>`;
  } catch (e) {
    cuerpo.innerHTML = e.status === 404 ? vacio('Sin historial cualitativo: nunca participó ni fue convocada desde COLOQUIO.', '🆕') : `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

/* Delegación: cualquier chip de historial en la página abre el modal. */
document.addEventListener('click', (ev) => {
  const b = ev.target.closest('[data-historial]');
  if (b) { ev.preventDefault(); verHistorial(b.dataset.historial); }
});
