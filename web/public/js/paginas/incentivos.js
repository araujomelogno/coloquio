/* Pantalla 6 — Incentivos: asignación y entrega, con el total comprometido (R1.10).
   No son puntos ni pasan por el ledger de `paneles`: un regalo por sesión. */

import * as api from '../api.js';
import { puede } from '../app.js';
import { $, esc, cargando, codigo, fechaHora, plata, vacio, toast, error } from '../ui.js';
import { cabeceraSesion } from './sesiones.js';

export async function render(id) {
  const main = $('#main');
  main.innerHTML = cargando();
  const { html } = await cabeceraSesion(id, 'incentivos');
  const v = await api.sesiones.incentivos(id);
  const liquida = puede('liquidar_incentivos');
  main.innerHTML = html + `
    <div class="stat-grid">
      <div class="stat s-orange"><div class="stat-num">${plata(v.totales.comprometido)}</div><div class="stat-label">Comprometido en la sesión</div></div>
      <div class="stat s-ok"><div class="stat-num">${plata(v.totales.entregado)}</div><div class="stat-label">Entregado</div></div>
      <div class="stat s-warn"><div class="stat-num">${v.totales.pendientes}</div><div class="stat-label">Pendientes de entrega</div></div>
      <div class="stat s-total"><div class="stat-num">${plata(v.estudio.valorComprometido)}</div><div class="stat-label">Comprometido en el estudio</div></div>
    </div>
    <div class="alert alert-info"><span>ℹ️</span><span>COLOQUIO registra el compromiso y la entrega del regalo. No ejecuta pagos ni resuelve su tratamiento fiscal.</span></div>
    <div class="card"><div class="card-header"><span class="card-header-title">Regalo por participante</span></div>
      <div class="card-body tight">${v.items.length ? `<div class="table-wrap"><table><thead><tr><th>Código</th><th>Regalo</th><th>Valor</th><th>Estado</th><th></th></tr></thead><tbody>
      ${v.items.map((i) => `<tr><td>${codigo(i.codigo)}${i.motivoCompromiso === 'cancelacion' ? ' <span class="badge badge-gray">compensación</span>' : ''}</td>
        <td>${liquida && i.estado === 'comprometido' ? `<select data-regalo="${i.idPersona}" style="padding:.35rem .5rem;font-size:.78rem">
            <option value="">— elegir —</option>${v.catalogo.map((r) => `<option value="${esc(r.id)}" ${r.id === i.regaloId ? 'selected' : ''}>${esc(r.nombre)}</option>`).join('')}</select>` : esc(i.regaloNombre || '—')}</td>
        <td class="mono">${plata(i.valor, i.moneda)}</td>
        <td>${i.estado === 'entregado' ? `<span class="est est-confirmado">Entregado</span><div class="small muted">${fechaHora(i.entregadoEn)}</div>` : '<span class="est est-acepto">Comprometido</span>'}</td>
        <td>${liquida && i.estado === 'comprometido' ? `<button class="btn btn-green btn-xs" data-entregar="${i.idPersona}" ${i.regaloId ? '' : 'disabled title="Asigná un regalo primero"'}>Marcar entregado</button>` : ''}</td></tr>`).join('')}
      </tbody></table></div>` : vacio('Todavía no hay compromisos: se crean al registrar la llegada de cada participante.', '🎁')}</div></div>`;

  main.onchange = async (ev) => {
    const s = ev.target.closest('select[data-regalo]');
    if (!s || !s.value) return;
    try { await api.incentivos.asignar(id, s.dataset.regalo, s.value); toast('Regalo asignado.', 'ok'); render(id); } catch (e) { error(e); }
  };
  main.onclick = async (ev) => {
    const b = ev.target.closest('[data-entregar]');
    if (!b) return;
    b.disabled = true;
    try { await api.incentivos.entregar(id, b.dataset.entregar); toast('Entrega registrada.', 'ok'); render(id); } catch (e) { error(e); b.disabled = false; }
  };
}
