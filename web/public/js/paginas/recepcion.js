/* Pantalla 5 — Recepción, pensada para teléfono (R1.7).

   El coordinador está parado en una puerta: código grande, un botón grande,
   el contador de presentes arriba. Quien no está confirmado se señala antes
   de dejarlo entrar, y aceptarlo requiere una anulación con motivo. */

import * as api from '../api.js';
import { puede } from '../app.js';
import { $, esc, cargando, segmento, hora, toast, error, pedirMotivo, confirmar, ETIQUETAS } from '../ui.js';
import { cabeceraSesion } from './sesiones.js';

export async function render(id) {
  const main = $('#main');
  main.innerHTML = cargando();
  const { html } = await cabeceraSesion(id, 'recepcion');
  const r = await api.sesiones.recepcion(id);
  const abierta = ['planificada', 'convocando', 'confirmada'].includes(r.sesion.estado);
  main.innerHTML = html + `
    <div class="recep">
      <div class="recep-hero"><div class="t">Presentes</div>
        <div class="n" id="presentes">${r.presentes}<small> / ${r.cupoObjetivo}</small></div>
        <div class="s">${r.confirmados} confirmados · ${esc(r.sesion.lugar || '')} · ${hora(r.sesion.fecha)}</div></div>
      ${abierta ? '' : `<div class="alert alert-info"><span>ℹ️</span><span>La sesión está ${esc(r.sesion.estado)}: no admite check-in.</span></div>`}
      <div class="recep-buscar"><input type="search" id="buscar" placeholder="CÓDIGO" maxlength="8" autocomplete="off" inputmode="text" /></div>
      <div id="lista"></div>
      ${abierta && puede('recibir') ? `<div class="card mt2"><div class="card-header"><span class="card-header-title">Cerrar la sesión</span></div><div class="card-body">
        <p class="small muted mb">Al cerrar: quien estaba confirmado y no llegó pasa a no-show, se escribe la participación de cada presente y quedan comprometidos los incentivos.</p>
        <div class="form-group"><label>Notas de la sesión (opcional)</label><textarea id="notas" rows="2" placeholder="Cómo fue la sesión. Nada que identifique a una persona."></textarea>
        <div class="field-hint">Las observaciones son de la sesión, no de los participantes: no escribas nombres, teléfonos, emails ni documentos.</div></div>
        <button class="btn btn-dark btn-full" id="cerrar">Cerrar sesión</button></div></div>` : ''}
    </div>`;

  const pintar = () => {
    const q = $('#buscar').value.trim().toUpperCase().replace(/-/g, '');
    const items = r.items.filter((i) => (q ? i.codigo.startsWith(q) : i.esperado || i.estado === 'asistio'));
    $('#lista').innerHTML = items.length ? items.map((i) => {
      const llego = i.estado === 'asistio';
      const noConf = !llego && !i.confirmado;
      return `<div class="recep-item ${llego ? 'llego' : ''} ${noConf ? 'no-conf' : ''}">
        <div class="info"><div><span class="codigo">${esc(i.codigo)}</span> ${segmento(i.segmento)}</div>
          <div class="small ${noConf ? '' : 'muted'}" style="${noConf ? 'color:var(--amber);font-weight:700' : ''}">${llego ? `✓ llegó ${hora(i.llegoEn)}` : noConf ? `⚠ no confirmado (${esc(ETIQUETAS[i.estado])})` : 'confirmado'}</div></div>
        ${abierta && !llego && puede('recibir') ? `<button class="btn ${noConf ? 'btn-outline' : 'btn-green'} big" data-llego="${i.idPersona}" data-noconf="${noConf ? 1 : 0}">Llegó</button>` : ''}
      </div>`;
    }).join('') : `<div class="empty-state">${q ? `El código <b>${esc(q)}</b> no está en esta sesión. No dejes pasar a nadie sin verificar.` : 'Nadie confirmado todavía.'}</div>`;
  };
  pintar();
  $('#buscar').oninput = pintar;
  $('#buscar').onkeydown = (ev) => {
    if (ev.key === 'Enter') { const b = $('#lista [data-llego]'); if (b && $$lista().length === 1) b.click(); }
  };
  const $$lista = () => [...document.querySelectorAll('#lista [data-llego]')];

  main.onclick = async (ev) => {
    const b = ev.target.closest('[data-llego]');
    if (b) {
      let anulacion;
      if (b.dataset.noconf === '1') {
        const motivo = await pedirMotivo({
          titulo: 'Persona no confirmada',
          explicacion: 'Esta persona no está confirmada para esta sesión. Para dejarla entrar hay que registrar una anulación con motivo.',
          boton: 'Dejar entrar', peligro: true,
        });
        if (!motivo) return;
        anulacion = { motivo };
      }
      b.disabled = true;
      try {
        const res = await api.sesiones.checkIn(id, { idPersona: b.dataset.llego, anulacion });
        toast(`${res.codigo} presente (${res.presentes}/${res.cupoObjetivo}).`, 'ok');
        render(id);
      } catch (e) { error(e); b.disabled = false; }
    }
    if (ev.target.id === 'cerrar') {
      if (!(await confirmar({ titulo: 'Cerrar la sesión', texto: `Hay ${r.presentes} presentes. Los confirmados que no llegaron pasan a no-show. ¿Cerrar?`, boton: 'Cerrar sesión' }))) return;
      try {
        const res = await api.sesiones.cerrar(id, { notasSesion: $('#notas').value, confirmarSinAsistentes: r.presentes === 0 });
        toast(`Sesión cerrada · tasa de show ${res.showRate === null ? '—' : Math.round(res.showRate * 100) + '%'} · ${res.participacionesEscritas} participaciones registradas.`, 'ok');
        location.hash = `#/sesiones/${id}/incentivos`;
      } catch (e) { error(e); }
    }
  };
}
