/* Pantalla 1 — Estudios: lista y ficha, con la pauta y sus tópicos (R1.1). */

import * as api from '../api.js';
import { S, puede } from '../app.js';
import {
  $, $$, esc, encabezado, cargando, estado, fecha, fechaHora, plata, vacio, modal, toast, error,
} from '../ui.js';
import { formularioSesion } from './sesiones.js';

const catEtiqueta = (slug) => (S.catalogos.categorias.find((c) => c.slug === slug) || {}).etiqueta || slug;

export async function lista() {
  const main = $('#main');
  const acciones = puede('gestionar_estudios') ? '<button class="btn btn-orange" id="nuevo">+ Nuevo estudio</button>' : '';
  main.innerHTML = encabezado('Estudios', 'Cada estudio tiene su pauta y sus sesiones. El <code>refEstudio</code> es el mismo que usa <code>paneles</code>.', acciones) + cargando();
  const { items } = await api.estudios.listar();
  main.innerHTML = encabezado('Estudios', 'Cada estudio tiene su pauta y sus sesiones. El <code>refEstudio</code> es el mismo que usa <code>paneles</code>.', acciones) + `
    <div class="card"><div class="card-body tight">${items.length ? `<div class="table-wrap"><table>
      <thead><tr><th>Estudio</th><th>Cliente</th><th>Categoría</th><th>Pauta</th><th>Comprometido</th><th>Estado</th></tr></thead><tbody>
      ${items.map((e) => `<tr class="clickable" data-id="${e.id}"><td><div class="td-strong">${esc(e.nombre)}</div><div class="small muted">creado ${fecha(e.creadoEn)}</div></td>
        <td>${esc(e.cliente || '—')}</td><td><span class="badge badge-orange">${esc(catEtiqueta(e.categoria))}</span></td>
        <td>${e.pautaActivaVersion ? `v${e.pautaActivaVersion}` : '<span class="badge badge-amber">sin pauta</span>'}</td>
        <td class="mono">${plata(e.valorComprometido)}</td><td><span class="badge ${e.estado === 'activo' ? 'badge-green' : 'badge-gray'}">${esc(e.estado)}</span></td></tr>`).join('')}
      </tbody></table></div>` : vacio('Todavía no hay estudios. Creá el primero para cargar su pauta.', '🗂')}</div></div>`;
  $$('tr[data-id]').forEach((tr) => { tr.onclick = () => { location.hash = `#/estudios/${tr.dataset.id}`; }; });
  const b = $('#nuevo'); if (b) b.onclick = nuevoEstudio;
}

function nuevoEstudio() {
  const { el, cerrar } = modal({
    titulo: 'Nuevo estudio cualitativo',
    cuerpo: `
      <div class="form-group"><label>Nombre</label><input type="text" id="e-nombre" placeholder="Ej.: Cervezas artesanales 2026" /></div>
      <div class="form-row">
        <div class="form-group"><label>Cliente</label><input type="text" id="e-cliente" /></div>
        <div class="form-group"><label>Categoría</label><select id="e-cat">${S.catalogos.categorias.map((c) => `<option value="${esc(c.slug)}">${esc(c.etiqueta)}</option>`).join('')}</select>
          <div class="field-hint">La usa el filtro anti-panelista-profesional (R1.3).</div></div>
      </div>
      <div class="form-group"><label>Tema (se usa en el guion de convocatoria)</label><input type="text" id="e-desc" placeholder="Ej.: hábitos de consumo de cerveza" /></div>
      <div class="form-group"><label>refEstudio existente (opcional)</label><input type="text" id="e-ref" placeholder="uuid de la encuesta en paneles, si es un estudio mixto" />
        <div class="field-hint">Vacío = se emite uno nuevo. Un estudio mixto cuanti-cuali comparte el de su encuesta.</div></div>`,
    pie: '<button class="btn btn-outline" data-x>Cancelar</button><button class="btn btn-orange" data-ok>Crear estudio</button>',
  });
  el.querySelector('[data-x]').onclick = cerrar;
  el.querySelector('[data-ok]').onclick = async (ev) => {
    ev.target.disabled = true;
    try {
      const e = await api.estudios.crear({
        nombre: $('#e-nombre', el).value, cliente: $('#e-cliente', el).value, categoria: $('#e-cat', el).value,
        descripcion: $('#e-desc', el).value, refEstudio: $('#e-ref', el).value.trim() || undefined,
      });
      cerrar(); toast('Estudio creado. Ahora cargá su pauta.', 'ok');
      location.hash = `#/estudios/${e.id}`;
    } catch (e) { error(e); ev.target.disabled = false; }
  };
}

export async function ficha(id) {
  const main = $('#main');
  main.innerHTML = cargando();
  const e = await api.estudios.ver(id);
  const p = e.pautaActiva;
  const editar = puede('gestionar_estudios');
  main.innerHTML = encabezado(esc(e.nombre), `${esc(e.cliente || 'Sin cliente')} · <span class="badge badge-orange">${esc(catEtiqueta(e.categoria))}</span> · refEstudio <span class="codigo">${esc(e.refEstudio)}</span>`,
    puede('gestionar_sesiones') ? `<button class="btn btn-orange" id="nueva-sesion" ${p ? '' : 'disabled title="Primero cargá la pauta"'}>+ Nueva sesión</button>` : '',
    '<a href="#/estudios">Estudios</a> / ficha') + `
    ${p ? '' : '<div class="alert alert-warn"><span>⚠️</span><span>Este estudio no tiene pauta. <b>Una sesión no se puede abrir sin pauta activa</b>: la pauta es el instrumento.</span></div>'}
    <div class="grid-2">
      <div class="card">
        <div class="card-header"><span class="card-header-title">Pauta ${p ? `· v${p.version} · ${p.minutosTotales} min` : ''}</span>
          ${editar ? `<button class="btn btn-outline btn-sm" id="editar-pauta">${p ? 'Nueva versión' : 'Cargar pauta'}</button>` : ''}</div>
        <div class="card-body">${p ? `<ol class="pauta-ver">${p.topicos.map((t) => `<li><b>${esc(t.titulo)}</b> <span class="badge badge-gray">${t.minutos} min</span>
          ${t.objetivo ? `<div class="obj">🎯 ${esc(t.objetivo)}</div>` : ''}
          ${(t.repreguntas || []).map((r) => `<div class="rep">↳ ${esc(r)}</div>`).join('')}</li>`).join('')}</ol>
          ${e.versionesPauta.length > 1 ? `<p class="small muted">Versiones: ${e.versionesPauta.map((v) => `v${v.version}${v.activa ? ' (activa)' : ''}`).join(' · ')}</p>` : ''}`
          : vacio('Sin pauta cargada.', '📝')}</div>
      </div>
      <div>
        <div class="card">
          <div class="card-header"><span class="card-header-title">Sesiones</span><span class="small muted">${e.sesiones.length}</span></div>
          <div class="card-body tight">${e.sesiones.length ? `<div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Sesión</th><th>Cupo</th><th>Estado</th></tr></thead><tbody>
            ${e.sesiones.map((s) => `<tr class="clickable" data-sesion="${s.id}"><td class="nowrap">${fechaHora(s.fecha)}</td><td class="td-strong">${esc(s.nombre || 'Sesión')}<div class="small muted">${esc(s.lugar)}</div></td><td>${s.cupoObjetivo}</td><td>${estado(s.estado)}</td></tr>`).join('')}
          </tbody></table></div>` : vacio('Sin sesiones todavía.', '🗓')}</div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-header-title">Incentivos del estudio</span></div>
          <div class="card-body"><div class="stat s-orange" style="border:none;padding:0 0 0 .8rem"><div class="stat-num">${plata(e.valorComprometido)}</div><div class="stat-label">Valor comprometido total</div></div></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-header-title">Guion de convocatoria</span>${editar ? '<button class="btn btn-outline btn-sm" id="editar-guion">Editar</button>' : ''}</div>
          <div class="card-body"><div class="guion">${esc(e.guion || 'Usa el guion general de Configuración.')}</div>
          <p class="field-hint">Variables: {tema} {fecha} {lugar} {duracion} {incentivo} {codigo}</p></div>
        </div>
      </div>
    </div>`;
  $$('[data-sesion]').forEach((tr) => { tr.onclick = () => { location.hash = `#/sesiones/${tr.dataset.sesion}/embudo`; }; });
  const bp = $('#editar-pauta'); if (bp) bp.onclick = () => editorPauta(e);
  const bs = $('#nueva-sesion'); if (bs) bs.onclick = () => formularioSesion({ estudio: e });
  const bg = $('#editar-guion'); if (bg) bg.onclick = () => editarGuion(e);
}

function filaTopico(t = {}, i = 0) {
  return `<div class="topico" data-topico>
    <div class="topico-head"><div class="topico-num">${i + 1}</div>
      <input type="text" data-f="titulo" placeholder="Título del tópico" value="${esc(t.titulo || '')}" />
      <input type="number" data-f="minutos" min="1" style="max-width:110px" placeholder="min" value="${esc(t.minutos || 10)}" />
      <button class="btn btn-ghost" data-quitar title="Quitar">✕</button></div>
    <div class="form-group"><label>Objetivo</label><input type="text" data-f="objetivo" value="${esc(t.objetivo || '')}" placeholder="Qué se quiere saber con este tópico" /></div>
    <div><label>Repreguntas previstas (una por línea)</label><textarea data-f="repreguntas" rows="2">${esc((t.repreguntas || []).join('\n'))}</textarea></div>
  </div>`;
}

function editorPauta(e) {
  const base = e.pautaActiva?.topicos?.length ? e.pautaActiva.topicos : [{}];
  const { el, cerrar } = modal({
    titulo: `Pauta · ${esc(e.nombre)}`, ancho: true,
    cuerpo: `<p class="small muted mb">Guardar crea una versión nueva y desactiva la anterior. Las sesiones ya abiertas quedan con su versión.</p>
      <div id="topicos">${base.map(filaTopico).join('')}</div>
      <button class="btn btn-outline btn-sm" id="mas">+ Tópico</button> <span class="small muted" id="total"></span>`,
    pie: '<button class="btn btn-outline" data-x>Cancelar</button><button class="btn btn-orange" data-ok>Guardar versión</button>',
  });
  const cont = $('#topicos', el);
  const renumerar = () => {
    $$('[data-topico]', cont).forEach((d, i) => { d.querySelector('.topico-num').textContent = i + 1; });
    const total = $$('[data-f="minutos"]', cont).reduce((a, i) => a + (parseInt(i.value, 10) || 0), 0);
    $('#total', el).textContent = `Total: ${total} min`;
  };
  cont.addEventListener('click', (ev) => { if (ev.target.closest('[data-quitar]')) { ev.target.closest('[data-topico]').remove(); renumerar(); } });
  cont.addEventListener('input', renumerar);
  $('#mas', el).onclick = () => { cont.insertAdjacentHTML('beforeend', filaTopico({}, 99)); renumerar(); };
  renumerar();
  el.querySelector('[data-x]').onclick = cerrar;
  el.querySelector('[data-ok]').onclick = async (ev) => {
    const topicos = $$('[data-topico]', cont).map((d) => ({
      titulo: d.querySelector('[data-f="titulo"]').value,
      minutos: d.querySelector('[data-f="minutos"]').value,
      objetivo: d.querySelector('[data-f="objetivo"]').value,
      repreguntas: d.querySelector('[data-f="repreguntas"]').value.split('\n').map((x) => x.trim()).filter(Boolean),
    }));
    ev.target.disabled = true;
    try { const p = await api.estudios.guardarPauta(e.id, { topicos }); cerrar(); toast(`Pauta v${p.version} guardada.`, 'ok'); ficha(e.id); }
    catch (err) { error(err); ev.target.disabled = false; }
  };
}

function editarGuion(e) {
  const { el, cerrar } = modal({
    titulo: 'Guion de convocatoria del estudio',
    cuerpo: `<textarea id="g" rows="7">${esc(e.guion || '')}</textarea><p class="field-hint">Vacío = se usa el guion general. Variables: {tema} {fecha} {lugar} {duracion} {incentivo} {codigo}</p>`,
    pie: '<button class="btn btn-outline" data-x>Cancelar</button><button class="btn btn-orange" data-ok>Guardar</button>',
  });
  el.querySelector('[data-x]').onclick = cerrar;
  el.querySelector('[data-ok]').onclick = async () => {
    try { await api.estudios.editar(e.id, { guion: $('#g', el).value }); cerrar(); toast('Guion guardado.', 'ok'); ficha(e.id); } catch (err) { error(err); }
  };
}
