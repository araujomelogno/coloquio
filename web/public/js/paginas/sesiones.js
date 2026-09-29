/* Pantalla 2 — Sesión: armado (fecha, lugar, cupo, cuotas, sobre-reclutamiento). */

import * as api from '../api.js';
import { S, puede, navSesion, tabsSesion } from '../app.js';
import {
  $, $$, esc, encabezado, cargando, estado, fechaHora, aInputLocal, vacio, modal, toast, error, DIM, pct,
} from '../ui.js';

export async function lista() {
  const main = $('#main');
  main.innerHTML = encabezado('Sesiones', 'Todas las sesiones, de todos los estudios.') + cargando();
  const { items } = await api.sesiones.listar();
  main.innerHTML = encabezado('Sesiones', 'Todas las sesiones, de todos los estudios.') + `
    <div class="card"><div class="card-body tight">${items.length ? `<div class="table-wrap"><table>
      <thead><tr><th>Fecha</th><th>Sesión</th><th>Estudio</th><th>Tipo</th><th>Cupo</th><th>Confirmados</th><th>Estado</th></tr></thead><tbody>
      ${items.map((s) => {
        const c = s.conteo || {};
        const conf = (c.confirmado || 0) + (c.asistio || 0);
        return `<tr class="clickable" data-id="${s.id}"><td class="nowrap">${fechaHora(s.fecha)}</td><td class="td-strong">${esc(s.nombre || 'Sesión')}<div class="small muted">${esc(s.lugar)}</div></td>
          <td>${esc(s.estudioNombre || '')}</td><td>${s.tipo === 'idi' ? 'Entrevista' : 'Grupo'}</td><td>${s.cupoObjetivo}</td>
          <td class="mono ${conf >= s.cupoObjetivo ? 'td-strong' : ''}">${conf} / ${s.cupoObjetivo}</td><td>${estado(s.estado)}</td></tr>`;
      }).join('')}</tbody></table></div>` : vacio('No hay sesiones. Se crean desde la ficha de un estudio con pauta.', '🗓')}</div></div>`;
  $$('tr[data-id]').forEach((tr) => { tr.onclick = () => { location.hash = `#/sesiones/${tr.dataset.id}/embudo`; }; });
}

function filaCuota(c = {}) {
  const opciones = (dim) => {
    if (dim === 'sexo') return S.catalogos.sexos;
    if (dim === 'tramoEtario') return S.catalogos.tramos;
    return null;
  };
  const dim = c.dimension || 'sexo';
  const ops = opciones(dim);
  return `<div class="form-row-4" data-cuota style="align-items:end;margin-bottom:.6rem">
    <div><select data-f="dimension">${Object.entries(DIM).map(([k, v]) => `<option value="${k}" ${k === dim ? 'selected' : ''}>${v}</option>`).join('')}</select></div>
    <div data-cat>${ops ? `<select data-f="categoria">${ops.map((o) => `<option ${o === c.categoria ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`
      : `<input type="text" data-f="categoria" value="${esc(c.categoria || '')}" placeholder="Ej.: Montevideo" />`}</div>
    <div><input type="number" data-f="objetivo" min="0" value="${esc(c.objetivo ?? 4)}" /></div>
    <div><button class="btn btn-ghost" data-quitar>✕ quitar</button></div></div>`;
}

function leerCuotas(el) {
  return $$('[data-cuota]', el).map((d) => ({
    dimension: d.querySelector('[data-f="dimension"]').value,
    categoria: d.querySelector('[data-f="categoria"]').value,
    objetivo: d.querySelector('[data-f="objetivo"]').value,
  }));
}

function camposSesion(s = {}) {
  const regalos = S.catalogos.regalos;
  return `
    <div class="form-row">
      <div class="form-group"><label>Nombre</label><input type="text" id="s-nombre" value="${esc(s.nombre || '')}" placeholder="Ej.: Grupo 1 — mujeres 25-44" /></div>
      <div class="form-group"><label>Tipo</label><select id="s-tipo"><option value="grupo" ${s.tipo !== 'idi' ? 'selected' : ''}>Focus group</option><option value="idi" ${s.tipo === 'idi' ? 'selected' : ''}>Entrevista en profundidad</option></select></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Fecha y hora</label><input type="datetime-local" id="s-fecha" value="${aInputLocal(s.fecha)}" /></div>
      <div class="form-group"><label>Lugar</label><input type="text" id="s-lugar" value="${esc(s.lugar || '')}" placeholder="Sala, dirección de la sala" /></div>
    </div>
    <div class="form-row-3">
      <div class="form-group"><label>Cupo objetivo</label><input type="number" id="s-cupo" min="1" value="${esc(s.cupoObjetivo || 8)}" /></div>
      <div class="form-group"><label>Ratio de sobre-reclutamiento</label><input type="number" id="s-ratio" min="1" step="0.05" value="${esc(s.ratioSobrerreclutamiento || 1.5)}" />
        <div class="field-hint" id="s-supuesto"></div></div>
      <div class="form-group"><label>Regalo por defecto</label><select id="s-regalo"><option value="">— sin regalo —</option>${regalos.map((r) => `<option value="${esc(r.id)}" ${r.id === s.regaloId ? 'selected' : ''}>${esc(r.nombre)} ($${r.valor})</option>`).join('')}</select></div>
    </div>
    <label>Cuotas de composición</label>
    <p class="field-hint mb">Cuántos de cada segmento querés <b>sentados</b>. El sistema sostiene la cuota durante toda la convocatoria.</p>
    <div class="form-row-4 small muted" style="margin-bottom:.3rem"><div>Dimensión</div><div>Categoría</div><div>Objetivo</div><div></div></div>
    <div id="cuotas">${(s.cuotas || [{ dimension: 'sexo', categoria: 'F', objetivo: 4 }, { dimension: 'sexo', categoria: 'M', objetivo: 4 }]).map(filaCuota).join('')}</div>
    <button class="btn btn-outline btn-sm" id="mas-cuota">+ Cuota</button>`;
}

function conectarCampos(el) {
  const cont = $('#cuotas', el);
  cont.addEventListener('click', (ev) => { if (ev.target.closest('[data-quitar]')) ev.target.closest('[data-cuota]').remove(); });
  cont.addEventListener('change', (ev) => {
    if (ev.target.matches('[data-f="dimension"]')) {
      const fila = ev.target.closest('[data-cuota]');
      fila.outerHTML = filaCuota({ dimension: ev.target.value, objetivo: fila.querySelector('[data-f="objetivo"]').value });
    }
  });
  $('#mas-cuota', el).onclick = () => cont.insertAdjacentHTML('beforeend', filaCuota({ dimension: 'tramoEtario', categoria: '25-34', objetivo: 2 }));
  const supuesto = () => {
    const cupo = parseInt($('#s-cupo', el).value, 10) || 0; const r = parseFloat($('#s-ratio', el).value) || 1;
    $('#s-supuesto', el).textContent = `Se invita a ${Math.ceil(cupo * r - 1e-9)} para sentar ${cupo}: se asume una caída del ${pct(1 - 1 / r)}.`;
  };
  $('#s-cupo', el).oninput = supuesto; $('#s-ratio', el).oninput = supuesto; supuesto();
}

const leerSesion = (el) => ({
  nombre: $('#s-nombre', el).value, tipo: $('#s-tipo', el).value, fecha: $('#s-fecha', el).value,
  lugar: $('#s-lugar', el).value, cupoObjetivo: $('#s-cupo', el).value,
  ratioSobrerreclutamiento: $('#s-ratio', el).value, regaloId: $('#s-regalo', el).value || null,
  cuotas: leerCuotas(el),
});

export function formularioSesion({ estudio }) {
  const { el, cerrar } = modal({
    titulo: `Nueva sesión · ${esc(estudio.nombre)}`, ancho: true,
    cuerpo: `<p class="small muted mb">Queda atada a la pauta v${estudio.pautaActiva?.version}. Modalidad presencial (la virtual llega en la Fase 2).</p>` + camposSesion(),
    pie: '<button class="btn btn-outline" data-x>Cancelar</button><button class="btn btn-orange" data-ok>Crear sesión</button>',
  });
  conectarCampos(el);
  el.querySelector('[data-x]').onclick = cerrar;
  el.querySelector('[data-ok]').onclick = async (ev) => {
    ev.target.disabled = true;
    try {
      const s = await api.sesiones.crear({ estudioId: estudio.id, ...leerSesion(el) });
      cerrar(); toast('Sesión creada. Siguiente paso: seleccionar candidatos.', 'ok');
      location.hash = `#/sesiones/${s.id}/seleccion`;
    } catch (e) { error(e); ev.target.disabled = false; }
  };
}

export async function cabeceraSesion(id, pestana) {
  const s = await api.sesiones.ver(id);
  navSesion(id, pestana, s.nombre || 'Sesión');
  const miga = `<a href="#/estudios/${s.estudioId}">Estudio</a> / <a href="#/sesiones">Sesiones</a>`;
  const html = encabezado(`${esc(s.nombre || 'Sesión')} ${estado(s.estado)}`,
    `${fechaHora(s.fecha)} · ${esc(s.lugar)} · ${s.tipo === 'idi' ? 'Entrevista' : 'Focus group'} presencial · cupo ${s.cupoObjetivo} · ratio ${s.ratioSobrerreclutamiento}`,
    '', miga) + tabsSesion(id, pestana);
  return { s, html };
}

export async function armado(id) {
  const main = $('#main');
  main.innerHTML = cargando();
  const { s, html } = await cabeceraSesion(id, 'armado');
  const abierta = ['planificada', 'convocando', 'confirmada'].includes(s.estado);
  const editable = abierta && puede('gestionar_sesiones');
  main.innerHTML = html + `
    <div class="grid-2">
      <div class="card"><div class="card-header"><span class="card-header-title">Datos de la sesión</span></div>
        <div class="card-body" id="form">${camposSesion(s)}
          ${editable ? '<div class="mt2"><button class="btn btn-orange" id="guardar">Guardar cambios</button></div>' : '<p class="field-hint mt">La sesión ya no admite cambios.</p>'}
        </div></div>
      <div>
        <div class="card"><div class="card-header"><span class="card-header-title">Decisiones de cuota registradas</span></div>
          <div class="card-body">${(s.decisionesCuota || []).length ? `<ul class="timeline">${s.decisionesCuota.map((d) => `<li><b>${esc(({ bajar_cupo: 'Bajó el cupo', correr_fecha: 'Corrió la fecha', aceptar_incompleta: 'Aceptó cuota incompleta', reemplazo_rompe_cuota: 'Reemplazo que rompe la cuota' })[d.salida] || d.salida)}</b>
            <div class="meta">${fechaHora(d.ts)} · segmento perdido: ${esc(Object.values(d.perdido?.segmento || {}).join(' · '))}</div></li>`).join('')}</ul>` : '<p class="small muted">Ninguna todavía. Cuando un segmento no se pueda restituir, la salida elegida queda acá.</p>'}</div></div>
        ${s.cancelacion ? `<div class="card"><div class="card-header"><span class="card-header-title">Cancelación</span></div><div class="card-body"><p><b>Motivo:</b> ${esc(s.cancelacion.motivo)}</p><p class="small muted">${esc(s.cancelacion.resolucionIncentivos || '')}</p></div></div>` : ''}
        ${s.notasSesion ? `<div class="card"><div class="card-header"><span class="card-header-title">Notas de la sesión</span></div><div class="card-body"><p>${esc(s.notasSesion)}</p></div></div>` : ''}
        ${abierta && puede('gestionar_sesiones') ? `<div class="card"><div class="card-header"><span class="card-header-title">Cancelar la sesión</span></div><div class="card-body">
          <p class="small muted mb">Con gente ya confirmada, la sesión pasa a estado propio y los incentivos que se decidan compensar quedan registrados.</p>
          <button class="btn btn-danger btn-sm" id="cancelar">Cancelar sesión</button></div></div>` : ''}
      </div>
    </div>`;
  const form = $('#form');
  conectarCampos(form);
  if (!editable) $$('input,select,button', form).forEach((x) => { if (x.id !== 'guardar') x.disabled = true; });
  const g = $('#guardar');
  if (g) g.onclick = async () => {
    g.disabled = true;
    try { await api.sesiones.editar(id, leerSesion(form)); toast('Sesión actualizada.', 'ok'); armado(id); } catch (e) { error(e); g.disabled = false; }
  };
  const c = $('#cancelar');
  if (c) c.onclick = () => cancelar(id);
}

async function cancelar(id) {
  const e = await api.sesiones.embudo(id);
  const confirmados = e.convocatorias.filter((x) => ['acepto', 'confirmado'].includes(x.estado));
  const { el, cerrar } = modal({
    titulo: 'Cancelar sesión',
    cuerpo: `<div class="form-group"><label>Motivo</label><textarea id="c-motivo" rows="2"></textarea></div>
      ${confirmados.length ? `<label>Compensar a quienes ya habían confirmado</label>
        <div class="mb">${confirmados.map((x) => `<label class="check" style="margin:.2rem 1rem .2rem 0"><input type="checkbox" value="${x.idPersona}" data-comp /> <span class="codigo">${x.codigo}</span></label>`).join('')}</div>
        <div class="form-group"><label>Regalo de compensación</label><select id="c-regalo"><option value="">—</option>${S.catalogos.regalos.map((r) => `<option value="${r.id}">${esc(r.nombre)}</option>`).join('')}</select></div>` : ''}
      <div class="form-group"><label>Cómo se resolvieron los incentivos</label><textarea id="c-res" rows="2" placeholder="Ej.: se compensa con la mitad del regalo a quienes confirmaron"></textarea>
      <div class="field-hint">No escribas datos personales.</div></div>`,
    pie: '<button class="btn btn-outline" data-x>Volver</button><button class="btn btn-danger" data-ok>Cancelar sesión</button>',
  });
  el.querySelector('[data-x]').onclick = cerrar;
  el.querySelector('[data-ok]').onclick = async () => {
    try {
      await api.sesiones.cancelar(id, {
        motivo: $('#c-motivo', el).value, resolucionIncentivos: $('#c-res', el).value,
        compensar: $$('[data-comp]:checked', el).map((x) => x.value), regaloId: $('#c-regalo', el)?.value,
      });
      cerrar(); toast('Sesión cancelada.', 'ok'); armado(id);
    } catch (e) { error(e); }
  };
}
