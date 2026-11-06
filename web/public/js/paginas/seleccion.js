/* Pantalla 3 — Selección de candidatos (R1.2, R1.3, R1.9, R1.14 a R1.18).

   Demográfica, semántica o mixta; resultados con segmento, evidencia de por
   qué entró cada uno y su historial cualitativo en la misma pantalla.

   R1.14: el formulario se arma con el catálogo de atributos de la bóveda.
   Ningún atributo tiene nombre en este archivo: un atributo nuevo en `paneles`
   aparece al recargar. Categorías del mismo atributo: o; atributos: y.

   R1.15: columnas elegibles, recordadas por usuario. Agregar una columna no
   vuelve a buscar: pide los valores de los ids que la lista ya tiene. Un
   atributo ausente se ve distinto de uno declarado «sin dato».

   R1.16: «Ficha» abre la ficha seudónima, con el historial cualitativo.

   R1.17: «Identificar» actúa sobre los tildados y solo si el usuario tiene el
   permiso. Nombre, email y celular viven en `IDENTIDADES`, en memoria de esta
   pantalla: no se guardan en el navegador, no se mandan a ningún lado y se
   borran al salir de la pantalla o al buscar de nuevo.

   R1.18: cada criterio semántico puede ser duro (filtra) o no (ordena), y la
   consulta corre en modo laxo (por defecto) o estricto. La lista dice qué
   modo se usó, cuántos dejó afuera el motor y por qué, y marca a simple vista
   al candidato penalizado o de confianza baja. `peso` y `umbral_distancia`
   no se exponen: son calibración del motor de `paneles`. */

import * as api from '../api.js';
import { puede } from '../app.js';
import {
  $, $$, esc, cargando, segmento, codigo, histChip, vacio, modal, toast, error, pedirMotivo, DIM,
  cargarAtributos, fecha, confirmar,
} from '../ui.js';
import { cabeceraSesion } from './sesiones.js';
import { panelCuota } from './embudo.js';

let ultima = null;
let CATALOGO = [];
let COLUMNAS = [];                 // claves elegidas, en el orden del catálogo
const VALORES = new Map();         // idPersona → {clave: fila de atributos_de_personas}
const IDENTIDADES = new Map();     // idPersona → {nombre, email, celular} (R1.17, solo en memoria)
const TOPE_IDENTIFICAR = 200;

const conCategorias = (a) => (a.categorias || []).length > 0;
const tipoControl = (a) => (conCategorias(a) ? 'combo' : a.tipo === 'fecha' ? 'fechas' : 'rango');

function control(a) {
  if (tipoControl(a) === 'combo') {
    return `<details class="combo" data-attr="${esc(a.clave)}"><summary><span class="combo-tit">${esc(a.etiqueta)}</span><span class="combo-sel">cualquiera</span></summary>
      <div class="combo-lista">${a.categorias.map((c) => `<label><input type="checkbox" value="${esc(c.clave)}" /><span>${esc(c.etiqueta)}</span></label>`).join('')}</div></details>`;
  }
  const [op1, op2, tipo] = tipoControl(a) === 'fechas' ? ['desde', 'hasta', 'date'] : ['min', 'max', 'number'];
  return `<div class="rango" data-attr="${esc(a.clave)}"><span class="rango-tit">${esc(a.etiqueta)}</span>
    <input type="${tipo}" data-op="${op1}" placeholder="${tipo === 'number' ? 'desde' : ''}" aria-label="${esc(a.etiqueta)} ${op1}" />
    <span class="muted">a</span>
    <input type="${tipo}" data-op="${op2}" placeholder="${tipo === 'number' ? 'hasta' : ''}" aria-label="${esc(a.etiqueta)} ${op2}" /></div>`;
}

function formularioDemografico() {
  if (!CATALOGO.length) {
    return '<div class="alert alert-warn"><span>⚠️</span><span>No se pudo leer el catálogo de atributos de la bóveda. Se puede buscar sin filtros demográficos.</span></div>';
  }
  return `<div class="filtros-grid">${CATALOGO.map(control).join('')}</div>
    <div class="field-hint">Varias categorías del mismo atributo se suman (o); atributos distintos se cruzan (y). Los atributos salen del catálogo de <code>paneles</code>: uno nuevo aparece al recargar.</div>`;
}

export async function render(id) {
  const main = $('#main');
  main.innerHTML = cargando();
  IDENTIDADES.clear();   // R1.17: la identidad no sobrevive a la pantalla
  const [{ s, html }, catalogo, prefs] = await Promise.all([
    cabeceraSesion(id, 'seleccion'), cargarAtributos(),
    api.preferencias.ver().catch(() => ({ columnasSeleccion: [] }))]);
  CATALOGO = catalogo;
  // R1.15: un atributo dado de baja desaparece de las columnas, sin error.
  COLUMNAS = CATALOGO.map((a) => a.clave).filter((k) => (prefs.columnasSeleccion || []).includes(k));
  main.innerHTML = html + `
    <div class="card">
      <div class="card-header"><span class="card-header-title">Consulta contra el panel</span>
        <div class="seg" id="modo">
          <label><input type="radio" name="modo" value="demografica" checked /><span>Demográfica</span></label>
          <label><input type="radio" name="modo" value="semantica" /><span>Semántica</span></label>
          <label><input type="radio" name="modo" value="mixta" /><span>Mixta</span></label>
        </div></div>
      <div class="card-body">
        <div id="bloque-demo">${formularioDemografico()}</div>
        <div id="bloque-sem" class="hidden">
          <div class="form-group"><label>Qué dijo la gente en estudios anteriores</label>
            <div id="crits"></div>
            <button type="button" class="btn btn-outline btn-xs" id="mas-crit">+ agregar criterio</button>
            <div class="field-hint">Usa el motor de consulta de <code>paneles</code>: devuelve la respuesta y el estudio de donde salió cada candidato. Un criterio <b>duro</b> filtra: quien no lo cumple queda afuera en cualquier modo. Sin marcar, ordena.</div></div>
          <div class="form-group"><label>Modo</label>
            <div class="seg" id="modo-sem">
              <label><input type="radio" name="modoSemantico" value="laxo" checked /><span>Laxo</span></label>
              <label><input type="radio" name="modoSemantico" value="estricto" /><span>Estricto</span></label>
            </div>
            <div class="field-hint"><b>Laxo</b>: quien tiene evidencia dudosa o ninguna entra a la lista, marcado ⚠; el filtro fino lo hacés vos al llamar. <b>Estricto</b>: quedan afuera, y se informa cuántos y por qué.</div></div>
        </div>
        <div class="inline mt"><button class="btn btn-orange" id="buscar">Buscar candidatos</button>
          <span class="small muted">Nadie sin consentimiento vigente de contacto aparece: lo garantiza la bóveda, no este filtro.</span></div>
      </div>
    </div>
    <div id="resultado" class="mt2"></div>`;

  const sincronizar = () => {
    const modo = $('input[name=modo]:checked').value;
    $('#bloque-demo').classList.toggle('hidden', modo === 'semantica');
    $('#bloque-sem').classList.toggle('hidden', modo === 'demografica');
  };
  $$('input[name=modo]').forEach((r) => { r.onchange = sincronizar; });
  $$('details.combo').forEach((d) => d.addEventListener('change', () => {
    const n = $$('input:checked', d).length;
    $('.combo-sel', d).textContent = n ? `${n} elegida${n > 1 ? 's' : ''}` : 'cualquiera';
    d.classList.toggle('activo', n > 0);
  }));
  $('#mas-crit').onclick = () => agregarCriterio();
  agregarCriterio();
  $('#buscar').onclick = () => buscar(id, s);
  if (ultima?.sesion === id) pintar(id, s, ultima.r);
}

function agregarCriterio(texto = '', duro = false) {
  const div = document.createElement('div');
  div.className = 'crit-fila';
  div.innerHTML = `<input type="text" class="crit-texto" placeholder="Ej.: toma cerveza artesanal con amigos" value="${esc(texto)}" />
    <label class="crit-duro" title="Un criterio duro filtra: quien no lo cumple queda afuera, en laxo o en estricto."><input type="checkbox" ${duro ? 'checked' : ''} /><span>duro</span></label>
    <button type="button" class="btn btn-outline btn-xs" title="Quitar criterio">✕</button>`;
  div.querySelector('button').onclick = () => { if ($$('.crit-fila').length > 1) div.remove(); else div.querySelector('.crit-texto').value = ''; };
  $('#crits').appendChild(div);
}

// R1.14 — `{clave: {en: [...]} | {min, max} | {desde, hasta}}`, la forma de la bóveda.
function leerFiltros() {
  const filtros = {};
  $$('details.combo').forEach((d) => {
    const en = $$('input:checked', d).map((x) => x.value);
    if (en.length) filtros[d.dataset.attr] = { en };
  });
  $$('.rango').forEach((r) => {
    const cond = {};
    $$('input[data-op]', r).forEach((i) => { if (i.value !== '') cond[i.dataset.op] = i.value; });
    if (Object.keys(cond).length) filtros[r.dataset.attr] = cond;
  });
  return filtros;
}

function leerConsulta() {
  return {
    modo: $('input[name=modo]:checked').value,
    filtros: leerFiltros(),
    criterios: $$('.crit-fila').map((f) => ({
      texto: f.querySelector('.crit-texto').value.trim(),
      duro: f.querySelector('.crit-duro input').checked,
    })).filter((c) => c.texto),
    modoSemantico: $('input[name=modoSemantico]:checked').value,
    limite: 200,
  };
}

async function buscar(id, s, q = null) {
  const b = $('#buscar'); b.disabled = true;
  $('#resultado').innerHTML = cargando();
  q = q || leerConsulta();
  try {
    const r = await api.sesiones.seleccionar(id, q);
    ultima = { sesion: id, r, q };
    IDENTIDADES.clear();
    VALORES.clear();
    pintar(id, s, r);
  } catch (e) { $('#resultado').innerHTML = `<div class="alert alert-error"><span>⚠️</span><span>${esc(e.message)}</span></div>`; }
  b.disabled = false;
}

// R1.18 — `sin_verificar` no es `dudoso`: nadie juzgó la evidencia, que no es
// lo mismo que haberla juzgado y dudado. Por eso tienen color y texto propios.
const VEREDICTO = {
  cumple: ['badge-green', 'cumple'],
  no_cumple: ['badge-red', 'no cumple'],
  dudoso: ['badge-amber', '⚠ dudoso'],
  sin_verificar: ['badge-blue', 'sin verificar'],
  sin_evidencia: ['badge-gray', 'sin evidencia'],
  irrelevante: ['badge-gray', 'sin evidencia'],
};

function veredicto(v) {
  if (!v) return '';
  const [clase, texto] = VEREDICTO[v] || ['badge-gray', v];
  return `<span class="badge ${clase}">${esc(texto)}</span>`;
}

function evidencia(c) {
  if (!c.evidencia?.length) return '<span class="small muted">—</span>';
  const varios = c.evidencia.length > 1;
  const titulo = (e) => (varios ? `<b>${esc(e.criterio || '')}</b> ` : '');
  return c.evidencia.map((e) => (e.respuesta
    ? `<div class="evid evid-${esc(e.veredicto || 'nd')}">${varios ? `<div>${titulo(e)}</div>` : ''}“${esc(e.respuesta)}”
      <small>${veredicto(e.veredicto)} ${esc(e.razon || '')}</small>
      <small>${esc(e.estudio || '')}${e.pregunta ? ' · ' + esc(e.pregunta) : ''}</small></div>`
    // Sin respuesta cercana: una línea, no un bloque vacío.
    : `<div class="evid evid-${esc(e.veredicto || 'nd')}">${titulo(e)}${veredicto(e.veredicto)}<small>${esc(e.razon || 'Sin una respuesta suya cerca de este criterio.')}</small></div>`)).join('');
}

// Marcas del candidato: con qué calidad de evidencia entró.
function marcas(c) {
  const salida = [];
  if (c.penalizado) salida.push('<span class="badge badge-amber" title="Entró por la tolerancia del modo laxo: alguna evidencia es dudosa o falta.">⚠ penalizado</span>');
  else if (c.confianzaBaja && !c.verificacionIncompleta) salida.push('<span class="badge badge-amber" title="La evidencia está lejos del criterio.">⚠ confianza baja</span>');
  if (c.verificacionIncompleta) salida.push('<span class="badge badge-blue" title="El verificador no juzgó parte de su evidencia. No es lo mismo que dudoso.">verificación incompleta</span>');
  return salida.join(' ');
}

const esFlojo = (c) => !!(c.penalizado || c.confianzaBaja);

// R1.15 — presente, vacío y ausente se ven distintos. Ausente: la bóveda no
// devolvió la fila (no se cargó nunca); vacío: vino, pero sin texto.
function celdaAtributo(pid, clave) {
  const f = VALORES.get(pid)?.[clave];
  if (!VALORES.get(pid)?.[`__${clave}`]) return '<span class="muted small">…</span>';   // todavía no se pidió
  if (!f) return '<span class="ausente" title="Sin dato en el panel: este atributo no está cargado para esta persona">∅ no consta</span>';
  if (f.valor === '' || f.etiquetaValor === '') return '<span class="vacio-val" title="Cargado sin valor">(vacío)</span>';
  return `<span title="${esc(f.procedencia || '')}">${esc(f.etiquetaValor ?? f.valor)}</span>`;
}

function identidad(pid) {
  const i = IDENTIDADES.get(pid);
  if (!i) return '<span class="muted small">—</span>';
  return `<div class="identidad"><b>${esc(i.nombre || '(sin nombre)')}</b><small>${esc(i.celular || '')}${i.celular && i.email ? ' · ' : ''}${esc(i.email || '')}</small></div>`;
}

function fila(c, semantica, excluido = false) {
  const bloqueado = c.enEstaSesion || c.enOtraSesionDelEstudio;
  const marca = c.enEstaSesion ? '<span class="badge badge-blue">ya en la sesión</span>'
    : c.enOtraSesionDelEstudio ? '<span class="badge badge-gray">en otra sesión del estudio</span>' : '';
  return `<tr class="${esFlojo(c) ? (c.penalizado || !c.verificacionIncompleta ? 'floja' : 'incompleta') : ''}">
    <td><input type="checkbox" data-sel="${c.idPersona}" data-excluido="${excluido ? 1 : 0}" ${bloqueado ? 'disabled' : ''} style="width:16px;height:16px;accent-color:var(--orange)" /></td>
    <td>${codigo(c.codigo)}</td>
    <td>${histChip(c.historial, c.idPersona)}</td>
    ${IDENTIDADES.size ? `<td>${identidad(c.idPersona)}</td>` : ''}
    <td>${segmento(c.segmento)}</td>
    ${semantica ? `<td class="mono">${c.rango ? `#${c.rango} · ${Math.round((c.puntaje || 0) * 100)}` : '—'}${marcas(c) ? `<div class="marcas">${marcas(c)}</div>` : ''}</td>
    <td style="min-width:240px;max-width:400px">${evidencia(c)}</td>` : ''}
    ${COLUMNAS.map((k) => `<td>${celdaAtributo(c.idPersona, k)}</td>`).join('')}
    <td><button class="btn btn-ghost btn-xs" data-ficha="${c.idPersona}">Ficha</button></td>
    <td>${excluido ? `<span class="badge badge-amber" title="${esc(c.fatiga.motivos.map((m) => m.mensaje).join(' '))}">fatiga</span><div class="small muted" style="max-width:220px">${esc(c.fatiga.motivos[0]?.mensaje || '')}</div>` : marca}</td>
  </tr>`;
}

function cabecera(semantica) {
  return `<tr><th></th><th>Código</th><th>Historial</th>${IDENTIDADES.size ? '<th>Identidad</th>' : ''}<th>Cuota</th>
    ${semantica ? '<th>Ranking</th><th>Evidencia</th>' : ''}
    ${COLUMNAS.map((k) => `<th>${esc(DIM[k])}</th>`).join('')}<th></th><th></th></tr>`;
}

const MOTIVO = { no_cumple: 'no cumplen', dudoso: 'dudosos', sin_evidencia: 'sin evidencia' };

// «modo laxo · 187 candidatos · 23 penalizados · 4 sin verificar»: un número
// de candidatos sin el modo al lado no es interpretable.
function resumen(r) {
  if (!r.modoSemantico) return `${r.total} candidatos · ${r.abrioSemantica ? 'demográfica pura (sin ranking semántico)' : 'demográfica pura'}`;
  const partes = [`modo ${r.modoSemantico}`, `${r.total} candidatos`];
  if (r.calidad?.penalizados) partes.push(`${r.calidad.penalizados} penalizados`);
  if (r.calidad?.sinVerificar) partes.push(`${r.calidad.sinVerificar} sin verificar`);
  return partes.join(' · ');
}

function avisoExcluidos(r) {
  const ex = r.excluidosSemanticos;
  if (!r.modoSemantico || !ex) return '';
  if (!ex.total) return r.modoSemantico === 'estricto' ? '<div class="alert alert-info"><span>ℹ️</span><span>Modo estricto: el motor no dejó a nadie afuera.</span></div>' : '';
  const detalle = Object.entries(ex.porMotivo).filter(([, n]) => n).map(([m, n]) => `${n} ${MOTIVO[m] || m}`);
  if (ex.otros) detalle.push(`${ex.otros} por otros motivos`);
  return `<div class="alert ${r.modoSemantico === 'estricto' ? 'alert-warn' : 'alert-info'}"><span>${r.modoSemantico === 'estricto' ? '⚠️' : 'ℹ️'}</span><span>Modo ${esc(r.modoSemantico)}: el motor dejó afuera a <b>${ex.total}</b> persona(s) — ${detalle.join(' · ')}.${r.modoSemantico === 'estricto' && (ex.porMotivo.dudoso || ex.porMotivo.sin_evidencia) ? ' En modo laxo, los dudosos y sin evidencia entrarían marcados.' : ''}</span></div>`;
}

function selectorColumnas() {
  return `<details class="columnas" id="columnas"><summary class="btn btn-outline btn-sm">Columnas ▾${COLUMNAS.length ? ` (${COLUMNAS.length})` : ''}</summary>
    <div class="columnas-lista"><div class="small muted mb">Código e historial están siempre. Tu elección se recuerda.</div>
    ${CATALOGO.map((a) => `<label><input type="checkbox" value="${esc(a.clave)}" ${COLUMNAS.includes(a.clave) ? 'checked' : ''} /><span>${esc(a.etiqueta)}</span></label>`).join('')}</div></details>`;
}

// Las tablas se re-pintan sin volver a buscar (columnas, identidades),
// conservando los tildados.
function pintarTablas(r) {
  const tildados = new Set($$('[data-sel]:checked').map((x) => x.dataset.sel));
  const sem = !!r.abrioSemantica;
  const t1 = $('#tabla-candidatos');
  if (t1) t1.innerHTML = r.candidatos.length ? `<div class="table-wrap"><table><thead>${cabecera(sem)}</thead><tbody>${r.candidatos.map((c) => fila(c, sem)).join('')}</tbody></table></div>` : vacio('Ningún candidato cumple el criterio.', '🔍');
  const t2 = $('#tabla-excluidos');
  if (t2) t2.innerHTML = `<div class="table-wrap"><table><thead>${cabecera(sem)}</thead><tbody>${r.excluidosPorFatiga.map((c) => fila(c, sem, true)).join('')}</tbody></table></div>`;
  $$('[data-sel]').forEach((x) => { if (tildados.has(x.dataset.sel)) x.checked = true; });
  actualizarIdentificar();
}

const idsDeLaLista = (r) => [...r.candidatos, ...r.excluidosPorFatiga].map((c) => c.idPersona);

// R1.15 — una sola llamada en lote sobre los ids que la lista ya tiene.
async function completarValores(r, claves) {
  const pedida = (pid, k) => VALORES.get(pid)?.[`__${k}`];
  const ids = idsDeLaLista(r).filter((pid) => claves.some((k) => !pedida(pid, k)));
  const faltan = claves.filter((k) => ids.some((pid) => !pedida(pid, k)));
  if (!ids.length || !faltan.length) return;
  for (let i = 0; i < ids.length; i += 500) {
    const lote = ids.slice(i, i + 500);
    const { filas } = await api.atributos.valores(lote, faltan);
    lote.forEach((pid) => {
      const v = VALORES.get(pid) || {};
      faltan.forEach((k) => { v[`__${k}`] = true; });   // pedida: lo que no vino es ausente
      VALORES.set(pid, v);
    });
    filas.forEach((f) => { VALORES.get(f.idPersona)[f.atributo] = f; });
  }
}

function actualizarIdentificar() {
  const b = $('#identificar');
  if (!b) return;
  const n = $$('[data-sel]:checked').length;
  b.textContent = `Identificar (${n})`;
  b.disabled = n === 0;
}

function pintar(id, s, r) {
  const cont = $('#resultado');
  const deg = (r.degradaciones || []).map((d) => `<div class="alert alert-warn"><span>⚠️</span><span><b>${esc(d.etapa || 'Degradación')}:</b> ${esc(d.motivo)} ${esc(d.consecuencia || '')}</span></div>`).join('');
  const avisos = (r.avisosCuota || []).map((a) => `<div class="alert alert-error"><span>⛔</span><span>${esc(a.mensaje)}</span></div>`).join('');
  cont.innerHTML = `${deg}${avisoExcluidos(r)}${avisos}
    <div class="grid-2 ancha">
      <div class="card">
        <div class="card-header"><span class="card-header-title">${esc(resumen(r))}</span>
          <div class="toolbar">${selectorColumnas()}<button class="btn btn-outline btn-sm" id="todos">Seleccionar todos</button>
          ${puede('identificar') ? '<button class="btn btn-dark btn-sm" id="identificar" disabled>Identificar (0)</button>' : ''}
          ${puede('seleccionar') ? '<button class="btn btn-orange btn-sm" id="agregar">Agregar a la lista de espera</button>' : ''}</div></div>
        <div class="card-body tight"><div id="tabla-candidatos"></div>
          ${r.modoSemantico ? `<div class="pie-lista small muted">${esc(resumen(r))}<br><span class="badge badge-amber">⚠</span> evidencia dudosa, ausente o de confianza baja · <span class="badge badge-blue">verificación incompleta</span> nadie juzgó la evidencia (no es dudoso).</div>` : ''}</div>
      </div>
      <div>
        <div class="card"><div class="card-header"><span class="card-header-title">Cuota de la sesión</span></div><div class="card-body">${panelCuota(r.cuota)}</div></div>
        <div class="card"><div class="card-header"><span class="card-header-title">Siguiente paso</span></div><div class="card-body">
          <p class="small muted mb">Con la lista de espera armada, el sistema propone a quién invitar para cumplir la cuota asumiendo la caída.</p>
          <button class="btn btn-dark btn-full" id="proponer">Proponer lista de invitación</button></div></div>
        ${r.excluidosPorFatiga.length ? `<div class="card"><div class="card-header"><span class="card-header-title">Excluidos por fatiga · ${r.excluidosPorFatiga.length}</span></div>
          <div class="card-body small muted">Ventana ${r.configFatiga.ventanaDias} días por categoría · tope ${r.configFatiga.maxGlobal} en ${r.configFatiga.ventanaGlobalDias} días. Se puede saltar la regla con motivo registrado.</div></div>` : ''}
      </div>
    </div>
    ${r.excluidosPorFatiga.length ? `<div class="card mt2"><div class="card-header"><span class="card-header-title">Excluidos por el filtro anti-panelista-profesional</span></div>
      <div class="card-body tight" id="tabla-excluidos"></div></div>` : ''}`;

  pintarTablas(r);
  if (COLUMNAS.length) completarValores(r, COLUMNAS).then(() => pintarTablas(r)).catch(error);

  $('#todos').onclick = () => { $$('[data-sel][data-excluido="0"]:not(:disabled)').forEach((x) => { x.checked = true; }); actualizarIdentificar(); };
  // Asignados, no sumados: `#resultado` sobrevive entre búsquedas.
  cont.onchange = (ev) => { if (ev.target.matches('[data-sel]')) actualizarIdentificar(); };
  cont.onclick = (ev) => {
    const b = ev.target.closest('[data-ficha]');
    if (b) verFicha(b.dataset.ficha);
  };
  $('#columnas').addEventListener('change', async () => {
    const elegidas = $$('#columnas input:checked').map((x) => x.value);
    COLUMNAS = CATALOGO.map((a) => a.clave).filter((k) => elegidas.includes(k));
    $('#columnas summary').textContent = `Columnas ▾${COLUMNAS.length ? ` (${COLUMNAS.length})` : ''}`;
    api.preferencias.guardar({ columnasSeleccion: COLUMNAS }).catch(error);
    pintarTablas(r);
    try { await completarValores(r, COLUMNAS); pintarTablas(r); } catch (e) { error(e); }
  });
  const ag = $('#agregar'); if (ag) ag.onclick = () => agregar(id, s);
  const idf = $('#identificar'); if (idf) idf.onclick = () => identificar(id, r);
  $('#proponer').onclick = () => proponer(id);
}

// R1.16 — ficha seudónima: lo que la búsqueda ya sabía, de a una persona, más
// su historial cualitativo. Sin nombre ni contacto, y sin registro.
async function verFicha(pid) {
  const { el } = modal({ titulo: 'Ficha del candidato', cuerpo: cargando(), ancho: true });
  const cuerpo = el.querySelector('.modal-body');
  try {
    const f = await api.candidatos.ficha(pid);
    const h = f.historial || { sesiones: [] };
    cuerpo.innerHTML = `
      <p class="mb">${codigo(f.codigo)} · ${esc(f.estado)} · en el panel desde ${fecha(f.enroladoEn)}
        ${f.paneles.length ? ` · ${f.paneles.map((p) => `<span class="badge badge-gray">${esc(p.etiqueta)}</span>`).join(' ')}` : ''}</p>
      <h4 class="mb">Atributos</h4>
      ${f.atributos.length ? `<div class="table-wrap"><table><thead><tr><th>Atributo</th><th>Valor</th><th>Procedencia</th></tr></thead><tbody>
        ${f.atributos.map((a) => `<tr><td>${esc(a.etiqueta || a.atributo)}</td><td class="td-strong">${esc(a.etiquetaValor ?? a.valor)}</td><td class="small muted">${esc(a.procedencia || '')}</td></tr>`).join('')}</tbody></table></div>`
        : vacio('No tiene atributos cargados.', '🗒')}
      <h4 class="mt2 mb">Historial cualitativo · ${h.total || 0}</h4>
      ${(h.sesiones || []).length ? `<div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Estudio</th><th>Categoría</th><th>Tipo</th><th>Modalidad</th></tr></thead><tbody>
        ${h.sesiones.map((x) => `<tr><td>${fecha(x.fecha)}</td><td class="td-strong">${esc(x.estudioNombre || '—')}${x.importada ? ' <span class="badge badge-gray">importada</span>' : ''}</td><td>${esc(x.categoria)}</td><td>${x.tipo === 'idi' ? 'Entrevista' : 'Grupo'}</td><td>${esc(x.modalidad)}</td></tr>`).join('')}</tbody></table></div>`
        : '<p class="small muted">Nunca participó de una sesión cualitativa.</p>'}
      <p class="small muted mt">Ficha seudónima: sin nombre ni contacto, y abrirla no queda registrado como reidentificación.</p>`;
  } catch (e) { cuerpo.innerHTML = `<div class="alert alert-error"><span>⚠️</span><span>${esc(e.message)}</span></div>`; }
}

// R1.17 — una acción sobre los tildados, nunca la carga de la página. La
// bóveda registra una fila de auditoría por persona antes de devolverla.
async function identificar(id, r) {
  const ids = $$('[data-sel]:checked').map((x) => x.dataset.sel);
  if (!ids.length) return;
  if (ids.length > TOPE_IDENTIFICAR) { toast(`Se pueden identificar hasta ${TOPE_IDENTIFICAR} por vez.`, 'err'); return; }
  const ok = await confirmar({
    titulo: `Identificar a ${ids.length} candidato${ids.length > 1 ? 's' : ''}`,
    texto: 'Vas a ver nombre, celular y email. La bóveda lo registra con tu usuario, una vez por persona, como selección cualitativa de esta sesión. No se guarda en COLOQUIO: desaparece al salir de la pantalla.',
    boton: 'Identificar',
  });
  if (!ok) return;
  try {
    const res = await api.candidatos.identificar(id, ids);
    res.identificados.forEach((i) => IDENTIDADES.set(i.idPersona, { nombre: i.nombre, email: i.email, celular: i.celular }));
    pintarTablas(r);
    toast(`${res.identificados.length} identificado${res.identificados.length === 1 ? '' : 's'}${res.noIdentificados ? ` · ${res.noIdentificados} sin consentimiento de contacto vigente` : ''}.`, 'ok');
  } catch (e) { error(e); }
}

async function agregar(id, s, anulacion) {
  const sel = $$('[data-sel]:checked');
  if (!sel.length) { toast('Marcá al menos un candidato.', 'err'); return; }
  // R1.18 — con cada candidato viaja con qué calidad de evidencia entró: la
  // propuesta de invitación no completa cuota con penalizados si hay verificados.
  const porId = Object.fromEntries([...(ultima?.r?.candidatos || []), ...(ultima?.r?.excluidosPorFatiga || [])].map((c) => [c.idPersona, c]));
  const ids = sel.map((x) => x.dataset.sel);
  const candidatos = ids.map((pid) => {
    const c = porId[pid] || {};
    return { idPersona: pid, puntaje: c.puntaje, penalizado: !!c.penalizado, verificacionIncompleta: !!c.verificacionIncompleta, confianzaBaja: !!c.confianzaBaja };
  });
  const hayExcluidos = sel.some((x) => x.dataset.excluido === '1');
  if (hayExcluidos && !anulacion) {
    const motivo = await pedirMotivo({
      titulo: 'Anular el filtro de fatiga',
      explicacion: 'Hay personas excluidas por participación cualitativa reciente. Se puede saltar la regla, pero no en silencio: el motivo queda registrado con tu usuario.',
      boton: 'Anular y agregar',
    });
    if (!motivo) return;
    anulacion = { motivo };
  }
  try {
    const r = await api.sesiones.incorporar(id, { candidatos, anulacion });
    const extra = [];
    if (r.yaEstaban.length) extra.push(`${r.yaEstaban.length} ya estaban`);
    if (r.enOtraSesionDelEstudio.length) extra.push(`${r.enOtraSesionDelEstudio.length} en otra sesión del estudio`);
    if (r.sinConsentimientoVigente.length) extra.push(`${r.sinConsentimientoVigente.length} sin consentimiento vigente`);
    toast(`${r.incorporados.length} agregados a la lista de espera${extra.length ? ' · ' + extra.join(' · ') : ''}.`, 'ok');
    buscar(id, s, ultima?.q);
  } catch (e) {
    if (e.codigo === 'requiere_anulacion') {
      const motivo = await pedirMotivo({ titulo: 'Anular el filtro de fatiga', explicacion: esc(e.message), boton: 'Anular y agregar' });
      if (motivo) agregar(id, s, { motivo });
    } else error(e);
  }
}

async function proponer(id) {
  try {
    const p = await api.sesiones.propuestaInvitacion(id);
    const e = await api.sesiones.embudo(id);
    const porId = Object.fromEntries(e.convocatorias.map((c) => [c.idPersona, c]));
    const { el, cerrar } = modal({
      titulo: 'Lista de invitación propuesta', ancho: true,
      cuerpo: `<div class="alert alert-info"><span>ℹ️</span><span>${esc(p.supuesto)} Ya hay ${p.yaInvitados} invitados.</span></div>
        ${(p.avisos || []).map((a) => `<div class="alert alert-warn"><span>⚠️</span><span>${esc(a.mensaje)}</span></div>`).join('')}
        ${p.deficitRestante.length ? `<div class="alert alert-error"><span>⛔</span><span>La lista de espera no alcanza para: ${p.deficitRestante.map((d) => `${esc(DIM[d.dimension])} ${esc(d.categoria)} (faltan ${d.faltan})`).join(', ')}. Ampliá la selección antes de convocar.</span></div>` : ''}
        ${p.propuestos.length ? `<div class="table-wrap"><table><thead><tr><th>Código</th><th>Segmento</th><th>Evidencia</th></tr></thead><tbody>
          ${p.propuestos.map((pid) => `<tr class="${(p.conEvidenciaFloja || []).includes(pid) ? 'floja' : ''}"><td>${codigo(porId[pid]?.codigo)}</td><td>${segmento(porId[pid]?.segmento)}</td><td>${(p.conEvidenciaFloja || []).includes(pid) ? '<span class="badge badge-amber">⚠ evidencia floja</span>' : ''}</td></tr>`).join('')}</tbody></table></div>`
          : vacio('No hay nadie más para invitar desde la lista de espera.', '✅')}
        <div class="form-group mt"><label>Canal inicial</label><select id="canal"><option value="manual">Manual (llamo o escribo yo)</option><option value="whatsapp">WhatsApp</option></select>
        <div class="field-hint">Se puede cambiar persona por persona desde el embudo.</div></div>`,
      pie: `<button class="btn btn-outline" data-x>Cerrar</button>${puede('convocar') && p.propuestos.length ? `<button class="btn btn-orange" data-ok>Invitar a ${p.propuestos.length}</button>` : ''}`,
    });
    el.querySelector('[data-x]').onclick = cerrar;
    const ok = el.querySelector('[data-ok]');
    if (ok) ok.onclick = async () => {
      try {
        const r = await api.sesiones.invitar(id, { ids: p.propuestos, canal: $('#canal', el).value });
        cerrar(); toast(`${r.invitados.length} invitados. Seguí la convocatoria desde el embudo.`, 'ok');
        // R5.2.a — la bóveda no aceptó la convocatoria (retiró el consentimiento): quedan en espera.
        if (r.noDeclarados?.length) toast(`${r.noDeclarados.length} no se pudieron invitar: la bóveda no aceptó la convocatoria (sin consentimiento vigente). Quedan en la lista de espera.`, 'err');
        location.hash = `#/sesiones/${id}/embudo`;
      } catch (err) { error(err); }
    };
  } catch (e) { error(e); }
}
