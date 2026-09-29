/* Tablero: sesiones de la semana y métricas de la fase (SPEC §12). */

import * as api from '../api.js';
import { $, esc, encabezado, cargando, estado, fechaHora, fecha, pct, vacio } from '../ui.js';

export async function render() {
  const main = $('#main');
  main.innerHTML = encabezado('Tablero', 'Lo que está en campo y cómo viene funcionando la convocatoria.') + cargando();
  const t = await api.tablero();
  const tot = t.totales || {};
  const barras = (t.tendenciaShow || []).filter((x) => x.showRate !== null);
  main.innerHTML = encabezado('Tablero', 'Lo que está en campo y cómo viene funcionando la convocatoria.',
    '<a class="btn btn-orange" href="#/estudios">+ Nuevo estudio</a>') + `
    <div class="stat-grid">
      <div class="stat s-orange"><div class="stat-num">${t.semana.length}</div><div class="stat-label">Sesiones esta semana</div></div>
      <div class="stat s-free"><div class="stat-num">${t.enConvocatoria.length}</div><div class="stat-label">En convocatoria</div></div>
      <div class="stat s-ok"><div class="stat-num">${pct(t.showRatePromedio)}</div><div class="stat-label">Tasa de show promedio</div></div>
      <div class="stat s-total"><div class="stat-num">${t.sesionesConCuotaCompleta}<small> / ${t.sesionesRealizadas}</small></div><div class="stat-label">Realizadas con cuota completa</div></div>
      <div class="stat s-warn"><div class="stat-num">${tot.reconvocatoriasBloqueadas || 0}<small> · ${tot.anulacionesFatiga || 0} anuladas</small></div><div class="stat-label">Bloqueos por fatiga</div></div>
    </div>
    <div class="grid-2">
      <div class="card">
        <div class="card-header"><span class="card-header-title">Próximos 7 días</span><a class="btn btn-outline btn-sm" href="#/sesiones">Todas</a></div>
        <div class="card-body tight">${t.semana.length ? `<div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Sesión</th><th>Estado</th><th></th></tr></thead><tbody>
          ${t.semana.map((s) => `<tr><td class="nowrap">${fechaHora(s.fecha)}</td><td><div class="td-strong">${esc(s.nombre || 'Sesión')}</div><div class="small muted">${esc(s.estudioNombre || '')} · ${esc(s.lugar || '')}</div></td>
            <td>${estado(s.estado)}</td><td><a class="btn btn-outline btn-xs" href="#/sesiones/${s.id}/embudo">Embudo</a></td></tr>`).join('')}
        </tbody></table></div>` : vacio('No hay sesiones en los próximos siete días.', '🗓')}</div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-header-title">Tasa de show por sesión</span><span class="small muted">asistieron / confirmados</span></div>
        <div class="card-body">${barras.length ? `<div class="sparkline" style="margin-top:14px">${barras.map((b) => `<div class="b" style="height:${Math.max(4, b.showRate * 100)}%" title="${esc(b.nombre || '')} · ${fecha(b.fecha)}"><span>${pct(b.showRate)}</span></div>`).join('')}</div>
          <div class="table-wrap mt"><table><thead><tr><th>Sesión</th><th>Show</th><th>Ratio usado</th><th>Ratio necesario</th><th>Horas a cupo</th></tr></thead><tbody>
          ${barras.slice(-6).reverse().map((b) => `<tr><td>${esc(b.nombre || '—')}<div class="small muted">${fecha(b.fecha)}</div></td><td class="td-strong">${pct(b.showRate)}</td><td>${b.ratioConfigurado ?? '—'}</td><td>${b.ratioRealNecesario ?? '—'}</td><td>${b.horasDeConvocatoria ?? '—'}</td></tr>`).join('')}
          </tbody></table></div>` : vacio('Todavía no hay sesiones cerradas: la primera tasa de show aparece al cerrar una.', '📈')}</div>
      </div>
    </div>
    <div class="card mt2">
      <div class="card-header"><span class="card-header-title">Intentos de contacto por confirmación</span><span class="small muted">decide si WhatsApp vale la pena frente a la llamada</span></div>
      <div class="card-body"><div class="stat-grid" style="margin:0">
        <div class="stat s-total"><div class="stat-num">${t.intentosPorConfirmacion.manual ?? '—'}</div><div class="stat-label">Manual · ${tot.intentos_manual || 0} intentos</div></div>
        <div class="stat s-ok"><div class="stat-num">${t.intentosPorConfirmacion.whatsapp ?? '—'}</div><div class="stat-label">WhatsApp · ${tot.intentos_whatsapp || 0} envíos</div></div>
        <div class="stat s-orange"><div class="stat-num">${tot.plantillasWhatsapp || 0}<small> · ${tot.mensajesEnVentanaWhatsapp || 0} gratis</small></div><div class="stat-label">Plantillas pagas · en ventana</div></div>
      </div></div>
    </div>`;
}
