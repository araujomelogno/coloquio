/* Pantalla 4 — Embudo: estados, cuota contra objetivo, quién falta, reemplazo.

   Registrar un resultado es un clic por estado (R1.5): si registrar cuesta más
   que la llamada, no se registra y el embudo miente. */

import * as api from '../api.js';
import { puede } from '../app.js';
import {
  $, $$, esc, cargando, estado, segmento, codigo, fechaHora, hora, vacio, modal, toast, error,
  pedirMotivo, confirmar, DIM, pct, ETIQUETAS,
} from '../ui.js';
import { cabeceraSesion } from './sesiones.js';

const PASOS = ['candidato', 'invitado', 'contactado', 'acepto', 'confirmado', 'asistio'];
const SALIDAS = ['no_contactable', 'rechazo', 'se_cayo', 'no_show', 'reemplazado'];
const BOTON = {
  invitado: ['Invitar', 'btn-outline'], contactado: ['Contactado', 'btn-outline'], acepto: ['Aceptó', 'btn-green'],
  confirmado: ['Confirmó', 'btn-green'], asistio: ['Asistió', 'btn-green'], no_contactable: ['No contactable', 'btn-outline'],
  rechazo: ['Rechazó', 'btn-outline'], se_cayo: ['Se cayó', 'btn-outline'], no_show: ['No vino', 'btn-outline'],
};
// Atajos de un clic que el backend completa con los pasos intermedios.
const ATAJOS = { invitado: ['acepto', 'rechazo'], contactado: ['confirmado'] };
const FILTROS = {
  curso: ['invitado', 'contactado', 'acepto', 'confirmado'],
  espera: ['candidato'],
  cerrados: ['asistio', ...SALIDAS],
  todos: null,
};
let filtro = 'curso';

export function panelCuota(c) {
  if (!c) return '';
  const filas = (c.cuotas || []).map((q) => {
    const pctCub = q.objetivo ? Math.min(100, (q.cubierto / q.objetivo) * 100) : 100;
    const pctInv = q.metaInvitacion ? Math.min(100, (q.enInvitacion / q.metaInvitacion) * 100) : 0;
    return `<div class="cuota-row"><div class="cuota-name">${esc(q.categoria)}<small>${DIM[q.dimension] || q.dimension}</small></div>
      <div class="bar" title="Invitados ${q.enInvitacion}/${q.metaInvitacion} · aceptaron ${q.cubierto}/${q.objetivo}"><div class="fill inv" style="width:${pctInv}%"></div><div class="fill ${q.faltan ? 'warn' : ''}" style="width:${pctCub}%"></div></div>
      <div class="cuota-num ${q.faltan ? 'falta' : 'ok'}">${q.cubierto}/${q.objetivo} ${q.faltan ? `· faltan ${q.faltan}` : '✓'}<div class="small muted">inv. ${q.enInvitacion}/${q.metaInvitacion} · espera ${q.enEspera}</div></div></div>`;
  }).join('');
  return `${filas || '<p class="small muted">La sesión no declara cuotas: cualquier candidato restituye el cupo.</p>'}
    <p class="field-hint mt">Barra verde: aceptaron/confirmaron contra el objetivo. Celeste: invitados contra la meta con ratio ${c.ratio} (caída supuesta ${pct(c.tasaCaidaSupuesta)}).</p>`;
}

export async function render(id) {
  const main = $('#main');
  main.innerHTML = cargando();
  const { html } = await cabeceraSesion(id, 'embudo');
  const e = await api.sesiones.embudo(id);
  const abierta = ['planificada', 'convocando', 'confirmada'].includes(e.sesion.estado);
  const c = e.cuota;
  const m = e.metricas;

  const avisos = [];
  if (c.cupoAlcanzado && abierta) avisos.push(`<div class="alert alert-success"><span>🎯</span><span><b>Cupo alcanzado:</b> ${c.confirmados} confirmados para ${c.cupoObjetivo} lugares.${m.cupoConfirmadoEn && m.invitadoPrimeroEn ? ` Tiempo de convocatoria: ${Math.round((new Date(m.cupoConfirmadoEn) - new Date(m.invitadoPrimeroEn)) / 36e5)} h.` : ''}</span></div>`);
  e.alertasBaja.forEach((a) => avisos.push(`<div class="alert alert-error"><span>🚪</span><span><b>Baja del panel:</b> una persona ${ETIQUETAS[a.estadoPrevio]?.toLowerCase() || ''} se dio de baja (${fechaHora(a.ts)}). Segmento perdido: ${segmento(a.segmento)}</span>
    <span class="alert-actions">${puede('convocar') && abierta ? `<button class="btn btn-danger btn-xs" data-reemplazo-alerta="${a.id}">Buscar reemplazo</button>` : ''}</span></div>`));
  e.pendientesDeReemplazo.forEach((p) => avisos.push(`<div class="alert alert-warn"><span>🔁</span><span>${codigo(p.codigo)} ${ETIQUETAS[p.estado].toLowerCase()} — segmento ${segmento(p.segmento)} sin restituir.</span>
    <span class="alert-actions">${puede('convocar') && abierta ? `<button class="btn btn-orange btn-xs" data-reemplazo="${p.idPersona}">Reemplazar</button>` : ''}</span></div>`));

  main.innerHTML = html + avisos.join('') + `
    <div class="funnel">${PASOS.map((p) => `<div class="funnel-step ${p === 'confirmado' ? 'hl' : ''}"><div class="n">${e.conteo[p] || 0}</div><div class="l">${ETIQUETAS[p]}</div></div>`).join('')}</div>
    <div class="funnel-exits">${SALIDAS.map((s) => `${estado(s)} <b class="small">${e.conteo[s] || 0}</b>`).join('&nbsp;&nbsp;')}</div>
    <div class="grid-2 ancha">
      <div class="card">
        <div class="card-header"><div class="seg" id="filtros">${Object.entries({ curso: 'En curso', espera: 'Lista de espera', cerrados: 'Cerrados', todos: 'Todos' }).map(([k, v]) => `<label><input type="radio" name="filtro" value="${k}" ${k === filtro ? 'checked' : ''}/><span>${v}</span></label>`).join('')}</div>
          <div class="toolbar"><a class="btn btn-outline btn-sm" href="#/sesiones/${id}/seleccion">+ Candidatos</a><button class="btn btn-outline btn-sm" id="exportar">Exportar CSV</button></div></div>
        <div class="card-body tight" id="tabla"></div>
      </div>
      <div>
        <div class="card"><div class="card-header"><span class="card-header-title">Cuota · ${c.confirmados}/${c.cupoObjetivo} confirmados</span></div><div class="card-body">${panelCuota(c)}</div></div>
        <div class="card"><div class="card-header"><span class="card-header-title">Métricas</span></div><div class="card-body">
          <div class="stat-grid" style="grid-template-columns:1fr 1fr;margin:0">
            <div class="stat s-free"><div class="stat-num">${c.invitados}<small>/${c.metaInvitacionTotal}</small></div><div class="stat-label">Invitados / meta</div></div>
            <div class="stat s-ok"><div class="stat-num">${m.intentosPorConfirmacion.manual ?? '—'}</div><div class="stat-label">Intentos x conf. manual</div></div>
            <div class="stat s-ok"><div class="stat-num">${m.intentosPorConfirmacion.whatsapp ?? '—'}</div><div class="stat-label">Intentos x conf. WhatsApp</div></div>
            <div class="stat s-warn"><div class="stat-num">${m.anulacionesFatiga || 0}</div><div class="stat-label">Anulaciones de fatiga</div></div>
            ${m.showRate !== undefined ? `<div class="stat s-total"><div class="stat-num">${pct(m.showRate)}</div><div class="stat-label">Tasa de show</div></div>` : ''}
          </div></div></div>
      </div>
    </div>`;

  const pintarTabla = () => {
    const estados = FILTROS[filtro];
    const items = e.convocatorias.filter((x) => !estados || estados.includes(x.estado));
    $('#tabla').innerHTML = items.length ? `<div class="table-wrap"><table><thead><tr><th>Código</th><th>Segmento</th><th>Estado</th><th>Canal</th><th>Registrar</th><th></th></tr></thead><tbody>
      ${items.map((x) => filaConvocatoria(x, abierta)).join('')}</tbody></table></div>` : vacio('No hay nadie en este tramo del embudo.', '·');
  };
  pintarTabla();
  $$('input[name=filtro]').forEach((r) => { r.onchange = () => { filtro = r.value; pintarTabla(); }; });
  $('#exportar').onclick = () => exportar(e);

  main.onclick = async (ev) => {
    const t = ev.target.closest('button, select');
    if (!t || t.tagName === 'SELECT') return;
    const pid = t.dataset.pid;
    try {
      if (t.dataset.a) {
        t.disabled = true;
        const r = await api.convocatorias.transicion(id, pid, { a: t.dataset.a });
        toast(`${r.convocatoria.idPersona.replace(/-/g, '').slice(0, 6).toUpperCase()} → ${ETIQUETAS[r.convocatoria.estado]}${r.pasos.length > 1 ? ' (con pasos intermedios registrados)' : ''}`, 'ok');
        if (r.cupoRecienAlcanzado) toast('🎯 ¡Cupo alcanzado!', 'ok');
        render(id);
      } else if (t.dataset.contacto) {
        verContacto(id, pid, t.dataset.contacto);
      } else if (t.dataset.wa) {
        t.disabled = true;
        const r = await api.convocatorias.whatsapp(id, pid, t.dataset.wa);
        if (r.enviado) toast(`WhatsApp enviado${r.pago ? ' (plantilla)' : ' dentro de la ventana de servicio: sin costo'}.`, 'ok');
        else toast(`No salió por WhatsApp: ${r.motivo}. La convocatoria pasó a canal manual, sin perder su estado.`, 'err');
        render(id);
      } else if (t.dataset.intento !== undefined && pid) {
        await api.convocatorias.intento(id, pid, { resultado: 'sin_respuesta' });
        toast('Intento registrado.', 'ok'); render(id);
      } else if (t.dataset.reingreso !== undefined && pid) {
        const motivo = await pedirMotivo({ titulo: 'Volver a meter al embudo', explicacion: 'Esta persona había salido del embudo. Volver requiere una acción explícita con motivo.' });
        if (motivo) { await api.convocatorias.reingreso(id, pid, motivo); toast('Reingresó como invitado.', 'ok'); render(id); }
      } else if (t.dataset.quitar !== undefined && pid) {
        if (await confirmar({ titulo: 'Quitar de la lista de espera', texto: 'Nunca fue invitado, así que se puede quitar sin dejar registro en el embudo.' })) {
          await api.convocatorias.quitar(id, pid); render(id);
        }
      } else if (t.dataset.eventos !== undefined && pid) {
        verEventos(e.convocatorias.find((x) => x.idPersona === pid));
      } else if (t.dataset.reemplazo) {
        reemplazo(id, { idPersona: t.dataset.reemplazo });
      } else if (t.dataset.reemplazoAlerta) {
        reemplazo(id, { alertaId: t.dataset.reemplazoAlerta });
      }
    } catch (err) { error(err); t.disabled = false; }
  };
  main.onchange = async (ev) => {
    const sel = ev.target.closest('select[data-canal]');
    if (!sel) return;
    try { await api.convocatorias.canal(id, sel.dataset.canal, sel.value); toast(`Canal: ${sel.value}.`, 'ok'); render(id); } catch (err) { error(err); }
  };
}

function filaConvocatoria(x, abierta) {
  const pid = x.idPersona;
  const conv = puede('convocar') && abierta;
  const destinos = [...x.siguientes, ...(ATAJOS[x.estado] || [])].filter((d) => BOTON[d] && !(x.estado === 'confirmado' && d === 'asistio'));
  const unicos = [...new Set(destinos)];
  const botones = conv ? unicos.map((d) => `<button class="btn ${BOTON[d][1]} btn-xs" data-a="${d}" data-pid="${pid}">${BOTON[d][0]}</button>`).join('') : '';
  const enCurso = ['invitado', 'contactado', 'acepto', 'confirmado'].includes(x.estado);
  const wa = conv && x.canal === 'whatsapp' ? (
    ['candidato', 'invitado'].includes(x.estado) ? `<button class="btn btn-dark btn-xs" data-wa="invitacion" data-pid="${pid}">WA invitación</button>`
      : x.estado === 'acepto' ? `<button class="btn btn-dark btn-xs" data-wa="confirmacion" data-pid="${pid}">WA confirmar</button>`
        : x.estado === 'confirmado' ? `<button class="btn btn-dark btn-xs" data-wa="recordatorio" data-pid="${pid}">WA recordar</button>` : '') : '';
  const marcas = [
    x.anulacion ? `<span class="badge badge-amber" title="${esc(x.anulacion.motivo)}">anuló fatiga</span>` : '',
    x.degradacion ? `<span class="badge badge-red" title="${esc(x.degradacion.motivo)}">WA falló → manual</span>` : '',
    x.respuestaPendienteRevision ? '<span class="badge badge-purple">respondió por WA: revisar</span>' : '',
    x.esReemplazoDe ? '<span class="badge badge-blue">reemplazo</span>' : '',
    x.ventanaServicioHasta && new Date(x.ventanaServicioHasta) > new Date() ? `<span class="badge badge-green" title="Hasta ${hora(x.ventanaServicioHasta)}">ventana WA abierta</span>` : '',
  ].join(' ');
  return `<tr>
    <td>${codigo(x.codigo)}</td>
    <td>${segmento(x.segmento)}</td>
    <td>${estado(x.estado)}<div style="margin-top:.2rem">${marcas}</div></td>
    <td>${conv && (x.estado === 'candidato' || enCurso) ? `<select data-canal="${pid}" style="padding:.3rem .5rem;font-size:.75rem;width:auto"><option value="manual" ${x.canal === 'manual' ? 'selected' : ''}>Manual</option><option value="whatsapp" ${x.canal === 'whatsapp' ? 'selected' : ''}>WhatsApp</option></select>` : `<span class="small">${esc(x.canal)}</span>`}</td>
    <td><div class="td-actions" style="max-width:230px">${botones}${wa}</div></td>
    <td><div class="td-actions">
      ${conv && enCurso ? `<button class="btn btn-ghost btn-xs" data-contacto="celular" data-pid="${pid}" title="Ver celular (auditado)">📞</button><button class="btn btn-ghost btn-xs" data-contacto="email" data-pid="${pid}" title="Ver email (auditado)">✉️</button>` : ''}
      ${conv && ['invitado', 'contactado', 'acepto'].includes(x.estado) && x.canal === 'manual' ? `<button class="btn btn-ghost btn-xs" data-intento data-pid="${pid}" title="Llamé y no atendió: registrar un intento">↻</button>` : ''}
      ${conv && ['se_cayo', 'no_show'].includes(x.estado) && x.requiereReemplazo ? `<button class="btn btn-orange btn-xs" data-reemplazo="${pid}">Reemplazar</button>` : ''}
      ${conv && ['rechazo', 'no_contactable', 'no_show'].includes(x.estado) ? `<button class="btn btn-ghost btn-xs" data-reingreso data-pid="${pid}">Reingresar</button>` : ''}
      ${puede('seleccionar') && abierta && x.estado === 'candidato' ? `<button class="btn btn-ghost btn-xs" data-quitar data-pid="${pid}">Quitar</button>` : ''}
      <button class="btn btn-ghost btn-xs" data-historial="${pid}" title="Historial cualitativo">🗂</button>
      <button class="btn btn-ghost btn-xs" data-eventos data-pid="${pid}" title="Eventos">≡</button>
    </div></td></tr>`;
}

async function verContacto(sesionId, pid, canal) {
  const { el } = modal({ titulo: `Contacto · ${canal}`, cuerpo: cargando() });
  const cuerpo = el.querySelector('.modal-body');
  try {
    const c = await api.convocatorias.contacto(sesionId, pid, canal);
    cuerpo.innerHTML = `<div class="alert alert-warn"><span>🔐</span><span>${esc(c.aviso)}</span></div>
      <div class="contacto-dato">${c.vacio ? '<span class="muted" style="font-size:.9rem">La persona no tiene ' + esc(canal) + ' cargado</span>' : esc(c.dato)}</div>
      <label>Guion sugerido</label><div class="guion">${esc(c.guion)}</div>
      <p class="field-hint mt">Código de convocatoria para darle: ${codigo(c.codigo)} — lo dice al llegar.</p>`;
  } catch (e) {
    cuerpo.innerHTML = `<div class="alert alert-error"><span>⛔</span><span>${esc(e.message)}</span></div>`;
  }
}

function verEventos(x) {
  modal({
    titulo: `Eventos · ${x.codigo}`,
    cuerpo: `<ul class="timeline">${(x.eventos || []).slice().reverse().map((ev) => `<li><b>${ev.de ? `${ETIQUETAS[ev.de] || ev.de} → ` : ''}${ETIQUETAS[ev.a] || ev.a}</b>
      <div class="meta">${fechaHora(ev.ts)} · ${esc(ev.canal)} · ${esc(ev.resultado || '')} · ${esc(String(ev.actor || '').startsWith('sistema') ? ev.actor : 'usuario ' + String(ev.actor).slice(0, 8))}</div>
      ${ev.motivo ? `<div class="small">Motivo: ${esc(ev.motivo)}</div>` : ''}</li>`).join('')}</ul>
      ${x.anulacion ? `<div class="alert alert-warn mt"><span>⚠️</span><span>Entró anulando el filtro de fatiga: “${esc(x.anulacion.motivo)}” (${fechaHora(x.anulacion.ts)})</span></div>` : ''}`,
  });
}

async function reemplazo(sesionId, cuerpoPerdido) {
  const { el, cerrar } = modal({ titulo: 'Reemplazo con revalidación de cuota', cuerpo: cargando(), ancho: true });
  const cuerpo = el.querySelector('.modal-body');
  let p;
  try { p = await api.sesiones.proponerReemplazo(sesionId, cuerpoPerdido); } catch (e) {
    cuerpo.innerHTML = `<div class="alert alert-error"><span>⚠️</span><span>${esc(e.message)}</span></div>`; return;
  }
  const filaCand = (c, parcial) => `<tr><td>${codigo(c.codigo)}</td><td>${segmento(c.segmento)}</td>
    <td>${c.origen === 'panel' ? '<span class="badge badge-blue">del panel</span>' : '<span class="badge badge-gray">lista de espera</span>'}</td>
    <td>${parcial ? `<span class="badge badge-red">rompe ${esc(c.rompe.map((d) => DIM[d]).join(', '))}</span>` : '<span class="badge badge-green">restituye</span>'}</td>
    <td><button class="btn ${parcial ? 'btn-outline' : 'btn-orange'} btn-xs" data-elegir="${c.idPersona}" data-parcial="${parcial ? 1 : 0}">Elegir</button></td></tr>`;
  cuerpo.innerHTML = `
    <p class="mb">Se perdió: ${codigo(p.perdido.codigo)} ${segmento(p.perdido.segmento)} · dimensiones con cuota: ${p.dimensionesConCuota.map((d) => DIM[d]).join(', ') || 'ninguna'}</p>
    <div class="alert ${p.sinReemplazo ? 'alert-error' : 'alert-success'}"><span>${p.sinReemplazo ? '⛔' : '✅'}</span><span>${esc(p.mensaje)}</span></div>
    ${p.propuestos.length ? `<div class="table-wrap"><table><thead><tr><th>Código</th><th>Segmento</th><th>Origen</th><th>Cuota</th><th></th></tr></thead><tbody>${p.propuestos.map((c) => filaCand(c, false)).join('')}</tbody></table></div>` : ''}
    ${p.sinReemplazo ? `<h4 class="mt2 mb">Elegí una salida (queda registrada)</h4>
      <div class="inline">${p.opciones.map((o) => `<button class="btn btn-dark btn-sm" data-salida="${o.salida}">${esc(o.etiqueta)}</button>`).join('')}</div>
      <div id="nueva-fecha" class="hidden mt"><label>Nueva fecha</label><div class="inline"><input type="datetime-local" id="nf" style="max-width:260px" /><button class="btn btn-orange btn-sm" id="nf-ok">Correr la fecha</button></div></div>` : ''}
    ${p.parciales.length ? `<details class="mt2"><summary class="small" style="cursor:pointer;font-weight:700">Candidatos que NO restituyen el segmento (${p.parciales.length}) — usarlos exige aceptar la cuota incompleta</summary>
      <div class="table-wrap mt"><table><tbody>${p.parciales.map((c) => filaCand(c, true)).join('')}</tbody></table></div></details>` : ''}`;
  cuerpo.onclick = async (ev) => {
    const b = ev.target.closest('button');
    if (!b) return;
    try {
      if (b.dataset.elegir) {
        const parcial = b.dataset.parcial === '1';
        if (parcial && !(await confirmar({ titulo: 'Reemplazo que rompe la cuota', texto: 'Este candidato no restituye el segmento perdido. Si seguís, la sesión queda con la cuota incompleta en esa dimensión y la decisión se registra con tu usuario.', boton: 'Aceptar cuota incompleta', peligro: true }))) return;
        await api.sesiones.resolverReemplazo(sesionId, { accion: 'reemplazar', ...cuerpoPerdido, reemplazo: b.dataset.elegir, aceptarCuotaIncompleta: parcial });
        cerrar(); toast('Reemplazo invitado. Contactalo desde el embudo.', 'ok'); render(sesionId);
      } else if (b.dataset.salida === 'correr_fecha') {
        $('#nueva-fecha', el).classList.remove('hidden');
      } else if (b.dataset.salida) {
        await api.sesiones.resolverReemplazo(sesionId, { accion: 'sin_reemplazo', ...cuerpoPerdido, salida: b.dataset.salida });
        cerrar(); toast('Salida registrada.', 'ok'); render(sesionId);
      } else if (b.id === 'nf-ok') {
        await api.sesiones.resolverReemplazo(sesionId, { accion: 'sin_reemplazo', ...cuerpoPerdido, salida: 'correr_fecha', nuevaFecha: $('#nf', el).value });
        cerrar(); toast('Fecha corrida y registrada.', 'ok'); render(sesionId);
      }
    } catch (e) { error(e); }
  };
}

function exportar(e) {
  const filas = [['codigo', 'sexo', 'tramo_etario', 'localidad', 'estado', 'canal', 'es_reemplazo', 'anulo_fatiga']];
  e.convocatorias.forEach((x) => filas.push([x.codigo, x.segmento.sexo, x.segmento.tramoEtario, x.segmento.localidad, x.estado, x.canal, x.esReemplazoDe ? 'si' : '', x.anulacion ? 'si' : '']));
  const csv = filas.map((f) => f.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  a.download = `embudo-${(e.sesion.nombre || 'sesion').replace(/\W+/g, '-')}.csv`;
  a.click();
}
