/* Pantalla 3 — Selección de candidatos (R1.2, R1.3, R1.9, R1.18).

   Demográfica, semántica o mixta; resultados con segmento, evidencia de por
   qué entró cada uno y su historial cualitativo en la misma pantalla.

   R1.18: cada criterio semántico puede ser duro (filtra) o no (ordena), y la
   consulta corre en modo laxo (por defecto) o estricto. La lista dice qué
   modo se usó, cuántos dejó afuera el motor y por qué, y marca a simple vista
   al candidato penalizado o de confianza baja. `peso` y `umbral_distancia`
   no se exponen: son calibración del motor de `paneles`. */

import * as api from '../api.js';
import { S, puede } from '../app.js';
import {
  $, $$, esc, cargando, segmento, codigo, histChip, vacio, modal, toast, error, pedirMotivo, DIM,
} from '../ui.js';
import { cabeceraSesion } from './sesiones.js';
import { panelCuota } from './embudo.js';

let ultima = null;

export async function render(id) {
  const main = $('#main');
  main.innerHTML = cargando();
  const { s, html } = await cabeceraSesion(id, 'seleccion');
  const chips = (nombre, valores) => `<div class="seg">${valores.map((v) => `<label><input type="checkbox" name="${nombre}" value="${esc(v)}" /><span>${esc(v)}</span></label>`).join('')}</div>`;
  main.innerHTML = html + `
    <div class="card">
      <div class="card-header"><span class="card-header-title">Consulta contra el panel</span>
        <div class="seg" id="modo">
          <label><input type="radio" name="modo" value="demografica" checked /><span>Demográfica</span></label>
          <label><input type="radio" name="modo" value="semantica" /><span>Semántica</span></label>
          <label><input type="radio" name="modo" value="mixta" /><span>Mixta</span></label>
        </div></div>
      <div class="card-body">
        <div id="bloque-demo">
          <div class="form-row">
            <div class="form-group"><label>Sexo</label>${chips('sexo', S.catalogos.sexos)}</div>
            <div class="form-group"><label>Tramo etario</label>${chips('tramoEtario', S.catalogos.tramos)}</div>
          </div>
          <div class="form-row-3">
            <div class="form-group"><label>Localidad</label><input type="text" id="f-loc" placeholder="Montevideo, Canelones" /></div>
            <div class="form-group"><label>Edad mínima</label><input type="number" id="f-min" /></div>
            <div class="form-group"><label>Edad máxima</label><input type="number" id="f-max" /></div>
          </div>
        </div>
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
        <div class="inline"><button class="btn btn-orange" id="buscar">Buscar candidatos</button>
          <span class="small muted">Nadie sin consentimiento vigente de contacto aparece: lo garantiza la vista de la bóveda, no este filtro.</span></div>
      </div>
    </div>
    <div id="resultado" class="mt2"></div>`;

  const sincronizar = () => {
    const modo = $('input[name=modo]:checked').value;
    $('#bloque-demo').classList.toggle('hidden', modo === 'semantica');
    $('#bloque-sem').classList.toggle('hidden', modo === 'demografica');
  };
  $$('input[name=modo]').forEach((r) => { r.onchange = sincronizar; });
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

function leerConsulta() {
  const valores = (n) => $$(`input[name=${n}]:checked`).map((x) => x.value);
  return {
    modo: $('input[name=modo]:checked').value,
    filtros: {
      sexo: valores('sexo'), tramoEtario: valores('tramoEtario'),
      localidad: $('#f-loc').value.split(',').map((x) => x.trim()).filter(Boolean),
      edadMin: $('#f-min').value, edadMax: $('#f-max').value,
    },
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

function fila(c, excluido = false) {
  const bloqueado = c.enEstaSesion || c.enOtraSesionDelEstudio;
  const marca = c.enEstaSesion ? '<span class="badge badge-blue">ya en la sesión</span>'
    : c.enOtraSesionDelEstudio ? '<span class="badge badge-gray">en otra sesión del estudio</span>' : '';
  return `<tr class="${esFlojo(c) ? (c.penalizado || !c.verificacionIncompleta ? 'floja' : 'incompleta') : ''}">
    <td><input type="checkbox" data-sel="${c.idPersona}" data-excluido="${excluido ? 1 : 0}" ${bloqueado ? 'disabled' : ''} style="width:16px;height:16px;accent-color:var(--orange)" /></td>
    <td>${codigo(c.codigo)}</td>
    <td>${segmento(c.segmento)}${c.edad ? `<div class="small muted">${c.edad} años</div>` : ''}</td>
    <td class="mono">${c.rango ? `#${c.rango} · ${Math.round((c.puntaje || 0) * 100)}` : '—'}${marcas(c) ? `<div class="marcas">${marcas(c)}</div>` : ''}</td>
    <td style="min-width:240px;max-width:400px">${evidencia(c)}</td>
    <td>${histChip(c.historial, c.idPersona)}</td>
    <td>${excluido ? `<span class="badge badge-amber" title="${esc(c.fatiga.motivos.map((m) => m.mensaje).join(' '))}">fatiga</span><div class="small muted" style="max-width:220px">${esc(c.fatiga.motivos[0]?.mensaje || '')}</div>` : marca}</td>
  </tr>`;
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

function pintar(id, s, r) {
  const cont = $('#resultado');
  const deg = (r.degradaciones || []).map((d) => `<div class="alert alert-warn"><span>⚠️</span><span><b>${esc(d.etapa || 'Degradación')}:</b> ${esc(d.motivo)} ${esc(d.consecuencia || '')}</span></div>`).join('');
  const avisos = (r.avisosCuota || []).map((a) => `<div class="alert alert-error"><span>⛔</span><span>${esc(a.mensaje)}</span></div>`).join('');
  const cabecera = `<tr><th></th><th>Código</th><th>Segmento</th><th>Ranking</th><th>Evidencia</th><th>Historial</th><th></th></tr>`;
  cont.innerHTML = `${deg}${avisoExcluidos(r)}${avisos}
    <div class="grid-2 ancha">
      <div class="card">
        <div class="card-header"><span class="card-header-title">${esc(resumen(r))}</span>
          <div class="toolbar"><button class="btn btn-outline btn-sm" id="todos">Seleccionar todos</button>
          ${puede('seleccionar') ? '<button class="btn btn-orange btn-sm" id="agregar">Agregar a la lista de espera</button>' : ''}</div></div>
        <div class="card-body tight">${r.candidatos.length ? `<div class="table-wrap"><table><thead>${cabecera}</thead><tbody>${r.candidatos.map((c) => fila(c)).join('')}</tbody></table></div>` : vacio('Ningún candidato cumple el criterio.', '🔍')}
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
      <div class="card-body tight"><div class="table-wrap"><table><thead>${cabecera}</thead><tbody>${r.excluidosPorFatiga.map((c) => fila(c, true)).join('')}</tbody></table></div></div></div>` : ''}`;

  $('#todos').onclick = () => $$('[data-sel][data-excluido="0"]:not(:disabled)').forEach((x) => { x.checked = true; });
  const ag = $('#agregar'); if (ag) ag.onclick = () => agregar(id, s);
  $('#proponer').onclick = () => proponer(id);
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
        ${p.deficitRestante.length ? `<div class="alert alert-error"><span>⛔</span><span>La lista de espera no alcanza para: ${p.deficitRestante.map((d) => `${DIM[d.dimension]} ${esc(d.categoria)} (faltan ${d.faltan})`).join(', ')}. Ampliá la selección antes de convocar.</span></div>` : ''}
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
