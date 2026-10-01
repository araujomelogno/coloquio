/* COLOQUIO — arranque, ingreso y navegación.

   HTML + módulos ES, sin paso de build (SPEC §7.1). Auth con Firebase del
   proyecto `gestion-paneles`: mismo padrón que `paneles`. */

import * as api from './api.js';
import { $, esc, iniciales, toast, error } from './ui.js';
import * as tablero from './paginas/tablero.js';
import * as estudios from './paginas/estudios.js';
import * as sesiones from './paginas/sesiones.js';
import * as seleccion from './paginas/seleccion.js';
import * as embudo from './paginas/embudo.js';
import * as recepcion from './paginas/recepcion.js';
import * as incentivos from './paginas/incentivos.js';
import * as configuracion from './paginas/configuracion.js';

const LOGO_BLANCO = 'assets/logo-equipos-horizontal-blanco.png';
const LOGO_E = 'assets/logo-equipos-e.png';
const app$ = () => document.getElementById('app');

export const S = { yo: null, entorno: null, catalogos: null };
let auth = null;
let fb = null;

const ROLES = { coordinador: 'Coordinación de campo', investigador: 'Investigación', administrador: 'Administración' };
export const puede = (permiso) => (S.yo?.permisos || []).includes(permiso);

/* ── Ingreso ─────────────────────────────────────────────────────── */

function pantallaLogin(contenido) {
  app$().innerHTML = `
    <div class="login-wrap">
      <div class="login-brand"><div class="login-brand-inner">
        <div class="login-brand-logo"><img src="${LOGO_E}" alt="Equipos Consultores" /></div>
        <div class="tagline">COLOQUIO<em>investigación cualitativa</em></div>
        <div class="tagline-sub">Estudios, pautas, convocatoria, recepción e incentivos.<br/>Sobre el panel de Equipos, sin datos personales fuera de la bóveda.</div>
      </div></div>
      <div class="login-form-panel"><div class="login-form-inner">${contenido}</div></div>
    </div>`;
}

function loginFirebase() {
  pantallaLogin(`
    <h1>Ingresar</h1>
    <p class="login-sub">Con tu usuario de Equipos — el mismo de Gestión de paneles.</p>
    <div id="login-msg"></div>
    <form id="login-form">
      <div class="form-group"><label>Email</label><input type="email" id="email" autocomplete="username" required /></div>
      <div class="form-group"><label>Contraseña</label><input type="password" id="clave" autocomplete="current-password" required /></div>
      <button class="btn btn-orange btn-full" type="submit">Ingresar</button>
    </form>
    <div class="login-forgot"><a id="olvide">¿Olvidaste tu contraseña?</a></div>`);
  $('#login-form').onsubmit = async (ev) => {
    ev.preventDefault();
    const b = ev.submitter; b.disabled = true;
    try { await fb.signInWithEmailAndPassword(auth, $('#email').value.trim(), $('#clave').value); }
    catch (e) { $('#login-msg').innerHTML = `<div class="alert alert-error"><span>⚠️</span><span>Email o contraseña incorrectos.</span></div>`; b.disabled = false; }
  };
  $('#olvide').onclick = async () => {
    const email = $('#email').value.trim();
    if (!email) { toast('Escribí tu email primero.', 'err'); return; }
    try { await fb.sendPasswordResetEmail(auth, email); toast('Te mandamos un email para restablecerla.', 'ok'); }
    catch (e) { error(e); }
  };
}

function loginLocal() {
  const usuarios = S.entorno.usuariosLocales || [];
  pantallaLogin(`
    <h1>Modo local</h1>
    <p class="login-sub">Servidor de desarrollo con datos ficticios en memoria. Elegí con qué rol entrar.</p>
    ${usuarios.map((u) => `<button class="btn btn-outline btn-full mb" data-u="${esc(u.uid)}" style="justify-content:flex-start;text-transform:none;letter-spacing:0">
       <span class="user-avatar" style="width:30px;height:30px;font-size:.75rem">${esc(iniciales(u.nombre))}</span>
       <span style="text-align:left"><b>${esc(u.nombre)}</b><br/><span class="small muted">${u.roles.map((r) => ROLES[r]).join(' · ')}</span></span></button>`).join('')}`);
  document.querySelectorAll('[data-u]').forEach((b) => {
    b.onclick = () => { api.estado.usuarioLocal = b.dataset.u; sessionStorage.setItem('coloquio-local', b.dataset.u); entrar(); };
  });
}

async function entrar() {
  app$().innerHTML = '<div class="center-screen"><div class="spinner"></div></div>';
  try {
    S.yo = await api.yo();
    S.catalogos = await api.catalogos();
  } catch (e) {
    app$().innerHTML = `<div class="center-screen"><div class="info-card"><div class="ic-icon">🔒</div>
      <h2>Sin acceso a COLOQUIO</h2><p>${esc(e.message)}</p><button class="btn btn-dark" id="salir">Salir</button></div></div>`;
    $('#salir').onclick = salir;
    return;
  }
  layout();
  window.removeEventListener('hashchange', rutear);
  window.addEventListener('hashchange', rutear);
  rutear();
}

async function salir() {
  if (api.estado.local) { sessionStorage.removeItem('coloquio-local'); api.estado.usuarioLocal = null; loginLocal(); return; }
  try { await fb.signOut(auth); } catch { /* nada */ }
}

/* ── Layout ──────────────────────────────────────────────────────── */

function layout() {
  const yo = S.yo;
  app$().innerHTML = `
    ${api.estado.local ? '<div class="demo-banner">Modo local · datos ficticios en memoria · nada de esto toca la bóveda ni Firestore</div>' : ''}
    <div class="app">
      <aside class="sidebar">
        <div class="sidebar-top"><img class="logo-horizontal-white" src="${LOGO_BLANCO}" alt="Equipos Consultores" /><div class="brand-name">Coloquio</div></div>
        <div class="sidebar-section-label">Campo cualitativo</div>
        <a class="nav-item" href="#/" data-nav="tablero"><span class="nav-icon">◧</span>Tablero</a>
        <a class="nav-item" href="#/estudios" data-nav="estudios"><span class="nav-icon">▤</span>Estudios</a>
        <a class="nav-item" href="#/sesiones" data-nav="sesiones"><span class="nav-icon">◷</span>Sesiones</a>
        <div id="nav-sesion"></div>
        ${puede('configurar') || puede('leer') ? `<div class="sidebar-section-label">Administración</div>
        <a class="nav-item" href="#/configuracion" data-nav="configuracion"><span class="nav-icon">⚙</span>Configuración</a>` : ''}
        <div class="sidebar-footer">
          <div class="user-pill"><div class="user-avatar">${esc(iniciales(yo.nombre, yo.email))}</div>
            <div class="user-info-wrap"><div class="user-email">${esc(yo.nombre || yo.email || yo.uid)}</div>
            <div class="user-role">${yo.roles.map((r) => ROLES[r] || r).join(' · ')}</div></div></div>
          <button class="btn btn-dark btn-full btn-sm" id="salir" style="background:rgba(255,255,255,.08)">Cerrar sesión</button>
        </div>
      </aside>
      <main class="main" id="main"></main>
    </div>`;
  $('#salir').onclick = salir;
}

export function navSesion(sesionId, actual, nombre) {
  const nav = $('#nav-sesion');
  if (!nav) return;
  if (!sesionId) { nav.innerHTML = ''; return; }
  const items = [
    ['armado', 'Armado'], ['seleccion', 'Selección'], ['embudo', 'Embudo'],
    ['recepcion', 'Recepción'], ['incentivos', 'Incentivos'],
  ];
  nav.innerHTML = `<div class="sidebar-section-label" style="padding-top:.6rem">${esc(nombre || 'Sesión')}</div>` +
    items.map(([k, l]) => `<a class="nav-item nav-sub ${k === actual ? 'active' : ''}" href="#/sesiones/${sesionId}/${k}">${l}</a>`).join('');
}

export function tabsSesion(sesionId, actual) {
  const items = [
    ['armado', 'Armado'], ['seleccion', 'Selección'], ['embudo', 'Embudo'],
    ['recepcion', 'Recepción'], ['incentivos', 'Incentivos'],
  ];
  return `<nav class="tabs">${items.map(([k, l]) => `<a class="tab ${k === actual ? 'active' : ''}" href="#/sesiones/${sesionId}/${k}">${l}</a>`).join('')}</nav>`;
}

/* ── Router ──────────────────────────────────────────────────────── */

const RUTAS = [
  [/^\/?$/, 'tablero', () => tablero.render()],
  [/^\/estudios$/, 'estudios', () => estudios.lista()],
  [/^\/estudios\/([^/]+)$/, 'estudios', (m) => estudios.ficha(m[1])],
  [/^\/sesiones$/, 'sesiones', () => sesiones.lista()],
  [/^\/sesiones\/([^/]+)(?:\/armado)?$/, 'sesiones', (m) => sesiones.armado(m[1])],
  [/^\/sesiones\/([^/]+)\/seleccion$/, 'sesiones', (m) => seleccion.render(m[1])],
  [/^\/sesiones\/([^/]+)\/embudo$/, 'sesiones', (m) => embudo.render(m[1])],
  [/^\/sesiones\/([^/]+)\/recepcion$/, 'sesiones', (m) => recepcion.render(m[1])],
  [/^\/sesiones\/([^/]+)\/incentivos$/, 'sesiones', (m) => incentivos.render(m[1])],
  [/^\/configuracion$/, 'configuracion', () => configuracion.render()],
];

async function rutear() {
  const camino = (location.hash || '#/').slice(1);
  const main = $('#main');
  if (!main) return;
  for (const [re, nav, fn] of RUTAS) {
    const m = camino.match(re);
    if (m) {
      document.querySelectorAll('[data-nav]').forEach((a) => a.classList.toggle('active', a.dataset.nav === nav));
      if (!camino.startsWith('/sesiones/')) navSesion(null);
      main.onclick = null; main.onchange = null;
      window.scrollTo(0, 0);
      try { await fn(m); } catch (e) {
        main.innerHTML = `<div class="alert alert-error"><span>⚠️</span><span>${esc(e.message)}</span></div>`;
        console.error(e);
      }
      return;
    }
  }
  main.innerHTML = '<div class="empty-state"><span class="ei">🧭</span>No existe esa pantalla.</div>';
}

/* ── Arranque ────────────────────────────────────────────────────── */

async function arrancar() {
  try { S.entorno = await api.entorno(); } catch (e) { S.entorno = {}; }
  if (S.entorno.modo === 'local') {
    api.estado.local = true;
    const guardado = sessionStorage.getItem('coloquio-local');
    if (guardado) { api.estado.usuarioLocal = guardado; entrar(); } else loginLocal();
    return;
  }
  const cfg = window.firebaseConfig || {};
  if (!cfg.apiKey) {
    app$().innerHTML = '<div class="center-screen"><div class="info-card"><div class="ic-icon">⚙️</div><h2>Falta configurar Firebase</h2><p>Completá <code>window.firebaseConfig</code> en index.html.</p></div></div>';
    return;
  }
  const [{ initializeApp }, fbAuth] = await Promise.all([
    import('https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js'),
    import('https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js'),
  ]);
  fb = fbAuth;
  auth = fbAuth.getAuth(initializeApp(cfg));
  api.estado.obtenerToken = async () => (auth.currentUser ? auth.currentUser.getIdToken() : null);
  fbAuth.onAuthStateChanged(auth, (u) => { if (u) entrar(); else loginFirebase(); });
}

arrancar();
