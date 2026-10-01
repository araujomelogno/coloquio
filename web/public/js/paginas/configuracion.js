/* Pantalla 7 — Configuración: regalos, umbrales de fatiga, categorías, guion,
   WhatsApp, roles y cumplimiento. */

import * as api from '../api.js';
import { S, puede } from '../app.js';
import { $, $$, esc, encabezado, cargando, plata, modal, toast, error, confirmar } from '../ui.js';

const ROLES = { coordinador: 'Coordinador de campo', investigador: 'Investigador', administrador: 'Administrador' };

export async function render() {
  const main = $('#main');
  main.innerHTML = encabezado('Configuración', 'Catálogos y umbrales: son datos, no constantes en el código.') + cargando();
  const c = await api.config.ver();
  const adm = puede('configurar');
  const dis = adm ? '' : 'disabled';
  main.innerHTML = encabezado('Configuración', 'Catálogos y umbrales: son datos, no constantes en el código.') + `
    <div class="grid-2">
      <div class="card">
        <div class="card-header"><span class="card-header-title">Filtro anti-panelista-profesional</span></div>
        <div class="card-body">
          <p class="small muted mb">Excluye a quien participó de una sesión cualitativa de la misma categoría dentro de la ventana, y a quien pasó el tope global. Corre contra el registro de COLOQUIO, no contra la fatiga de encuestas de <code>paneles</code>.</p>
          <div class="form-row">
            <div class="form-group"><label>Ventana por categoría (días)</label><input type="number" id="f-v" value="${c.fatiga.ventanaDias}" ${dis} /></div>
            <div class="form-group"><label>Participaciones que excluyen</label><input type="number" id="f-m" value="${c.fatiga.maxPorCategoria}" ${dis} /></div>
          </div>
          <div class="form-row">
            <div class="form-group"><label>Ventana del tope global (días)</label><input type="number" id="f-vg" value="${c.fatiga.ventanaGlobalDias}" ${dis} /></div>
            <div class="form-group"><label>Tope global</label><input type="number" id="f-mg" value="${c.fatiga.maxGlobal}" ${dis} /></div>
          </div>
          <div class="alert alert-warn"><span>⚠️</span><span>La ventana y la categorización son una definición metodológica de los investigadores. Estos valores son un punto de partida.</span></div>
          ${adm ? '<button class="btn btn-orange btn-sm" id="g-fatiga">Guardar umbrales</button>' : ''}
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-header-title">Catálogo de regalos</span>${adm ? '<button class="btn btn-outline btn-sm" id="n-regalo">+ Regalo</button>' : ''}</div>
        <div class="card-body tight"><div class="table-wrap"><table><thead><tr><th>Regalo</th><th>Valor</th><th>Estado</th><th></th></tr></thead><tbody>
          ${c.regalos.length ? c.regalos.map((r) => `<tr><td class="td-strong">${esc(r.nombre)}</td><td class="mono">${plata(r.valor, r.moneda)}</td><td><span class="badge ${r.activo !== false ? 'badge-green' : 'badge-gray'}">${r.activo !== false ? 'activo' : 'inactivo'}</span></td>
            <td>${adm ? `<button class="btn btn-ghost btn-xs" data-regalo="${esc(r.id)}">Editar</button>` : ''}</td></tr>`).join('') : '<tr><td colspan="4" class="td-muted">Sin regalos cargados.</td></tr>'}
        </tbody></table></div></div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-header-title">Categorías de estudio</span></div>
        <div class="card-body"><textarea id="cats" rows="6" ${dis}>${esc(c.categorias.map((x) => `${x.slug} | ${x.etiqueta}`).join('\n'))}</textarea>
          <p class="field-hint">Una por línea: <code>clave | etiqueta</code>. La clave es la que usa el filtro de fatiga: no la cambies si ya hay participaciones.</p>
          ${adm ? '<button class="btn btn-orange btn-sm mt" id="g-cats">Guardar categorías</button>' : ''}</div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-header-title">Guion general de convocatoria</span></div>
        <div class="card-body"><textarea id="guion" rows="6" ${dis}>${esc(c.guion)}</textarea>
          <p class="field-hint">Variables: {tema} {fecha} {lugar} {duracion} {incentivo} {codigo}. Cada estudio puede tener el suyo.</p>
          ${adm ? '<button class="btn btn-orange btn-sm mt" id="g-guion">Guardar guion</button>' : ''}</div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-header-title">WhatsApp · plantillas aprobadas por Meta</span><span class="badge ${S.entorno.whatsapp ? 'badge-green' : 'badge-amber'}">${S.entorno.whatsapp ? 'configurado' : 'sin credenciales'}</span></div>
        <div class="card-body">
          <div class="form-row"><div class="form-group"><label>Invitación</label><input type="text" id="w-inv" value="${esc(c.whatsapp.plantillaInvitacion)}" ${dis} /></div>
            <div class="form-group"><label>Idioma</label><input type="text" id="w-idioma" value="${esc(c.whatsapp.idioma)}" ${dis} /></div></div>
          <div class="form-row"><div class="form-group"><label>Recordatorio</label><input type="text" id="w-rec" value="${esc(c.whatsapp.plantillaRecordatorio)}" ${dis} /></div>
            <div class="form-group"><label>Confirmación</label><input type="text" id="w-conf" value="${esc(c.whatsapp.plantillaConfirmacion)}" ${dis} /></div></div>
          <p class="field-hint mb">Las plantillas llevan 5 variables ({{1}} tema, {{2}} fecha, {{3}} lugar, {{4}} incentivo, {{5}} código) y dos botones de respuesta rápida: «Sí, me interesa» y «No puedo». Que la invitación provoque respuesta abre la ventana de servicio de 24 h, y lo que sigue no se cobra.</p>
          ${adm ? '<button class="btn btn-orange btn-sm" id="g-wa">Guardar plantillas</button>' : ''}
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-header-title">Importar sesión histórica</span></div>
        <div class="card-body">
          <p class="small muted mb">Da memoria al filtro de fatiga desde el día uno: cargá los <code>id_persona</code> de un grupo ya realizado (se obtienen en <code>paneles</code>, sin datos personales).</p>
          <div class="form-row"><div class="form-group"><label>Categoría</label><select id="h-cat" ${puede('gestionar_estudios') ? '' : 'disabled'}>${c.categorias.map((x) => `<option value="${esc(x.slug)}">${esc(x.etiqueta)}</option>`).join('')}</select></div>
            <div class="form-group"><label>Fecha</label><input type="date" id="h-fecha" /></div></div>
          <div class="form-group"><label>Etiqueta</label><input type="text" id="h-et" placeholder="Ej.: Grupo cerveza — marzo 2026" /></div>
          <div class="form-group"><label>id_persona (uno por línea)</label><textarea id="h-ids" rows="4"></textarea></div>
          ${puede('gestionar_estudios') ? '<button class="btn btn-dark btn-sm" id="g-hist">Importar</button>' : ''}
        </div>
      </div>
    </div>
    ${puede('gestionar_roles') ? '<div class="card mt2" id="roles"><div class="card-header"><span class="card-header-title">Roles en COLOQUIO</span><span class="small muted">sobre el padrón de Gestión de paneles</span></div><div class="card-body tight">' + cargando() + '</div></div>' : ''}
    ${puede('cumplimiento') ? `<div class="card mt2"><div class="card-header"><span class="card-header-title">Cumplimiento</span></div><div class="card-body">
      <p class="small muted mb">La cascada de baja corre sola cada 30 minutos. Desde acá se puede forzar una pasada, y verificar (y reparar) los agregados y el historial por persona.</p>
      <div class="inline"><button class="btn btn-dark btn-sm" id="cascada">Correr cascada de baja</button>
      <button class="btn btn-outline btn-sm" id="consistencia">Verificar consistencia</button>
      <button class="btn btn-outline btn-sm" id="reparar">Verificar y reparar</button></div>
      <pre id="salida" class="small mt" style="white-space:pre-wrap;background:var(--gray-xlight);padding:.8rem;border-radius:4px;display:none"></pre></div></div>` : ''}`;

  const on = (sel, fn) => { const b = $(sel); if (b) b.onclick = async () => { b.disabled = true; try { await fn(); } catch (e) { error(e); } b.disabled = false; }; };
  on('#g-fatiga', async () => { await api.config.fatiga({ ventanaDias: $('#f-v').value, maxPorCategoria: $('#f-m').value, ventanaGlobalDias: $('#f-vg').value, maxGlobal: $('#f-mg').value }); toast('Umbrales guardados.', 'ok'); });
  on('#g-cats', async () => {
    const items = $('#cats').value.split('\n').map((l) => l.split('|')).filter((p) => p[0].trim()).map(([slug, et]) => ({ slug: slug.trim(), etiqueta: (et || slug).trim() }));
    await api.config.categorias({ items }); S.catalogos = await api.catalogos(); toast('Categorías guardadas.', 'ok');
  });
  on('#g-guion', async () => { await api.config.guion({ texto: $('#guion').value }); toast('Guion guardado.', 'ok'); });
  on('#g-wa', async () => { await api.config.whatsapp({ plantillaInvitacion: $('#w-inv').value, plantillaRecordatorio: $('#w-rec').value, plantillaConfirmacion: $('#w-conf').value, idioma: $('#w-idioma').value }); toast('Plantillas guardadas.', 'ok'); });
  on('#g-hist', async () => {
    const r = await api.personas.importar({ categoria: $('#h-cat').value, fecha: $('#h-fecha').value ? `${$('#h-fecha').value}T12:00` : '', etiqueta: $('#h-et').value, idPersonas: $('#h-ids').value });
    toast(`${r.participaciones} participaciones históricas importadas.`, 'ok'); $('#h-ids').value = '';
  });
  const nr = $('#n-regalo'); if (nr) nr.onclick = () => editarRegalo();
  $$('[data-regalo]').forEach((b) => { b.onclick = () => editarRegalo(c.regalos.find((r) => r.id === b.dataset.regalo)); });
  const mostrar = (x) => { const s = $('#salida'); s.style.display = 'block'; s.textContent = JSON.stringify(x, null, 2); };
  on('#cascada', async () => { const r = await api.config.cascada(); mostrar(r); toast(`Cascada: ${r.confirmados} confirmados, ${r.errores} errores.`, r.errores ? 'err' : 'ok'); });
  on('#consistencia', async () => { const r = await api.config.consistencia(false); mostrar(r); toast(r.consistente ? 'Todo consistente.' : `${r.hallazgos.length} diferencias.`, r.consistente ? 'ok' : 'err'); });
  on('#reparar', async () => {
    if (!(await confirmar({ titulo: 'Reparar', texto: 'Recalcula contadores, cuotas, valores comprometidos e historiales desde las sesiones y los reescribe.' }))) return;
    const r = await api.config.consistencia(true); mostrar(r); toast(r.reparado ? 'Reparado.' : 'No había nada que reparar.', 'ok');
  });
  if (puede('gestionar_roles')) pintarRoles();
}

function editarRegalo(r = {}) {
  const { el, cerrar } = modal({
    titulo: r.id ? 'Editar regalo' : 'Nuevo regalo',
    cuerpo: `<div class="form-group"><label>Nombre</label><input type="text" id="r-n" value="${esc(r.nombre || '')}" placeholder="Ej.: Orden de compra supermercado" /></div>
      <div class="form-row"><div class="form-group"><label>Valor</label><input type="number" id="r-v" value="${esc(r.valor ?? '')}" /></div>
      <div class="form-group"><label>Moneda</label><input type="text" id="r-m" value="${esc(r.moneda || 'UYU')}" /></div></div>
      <label class="check"><input type="checkbox" id="r-a" ${r.activo === false ? '' : 'checked'} /> Activo</label>`,
    pie: '<button class="btn btn-outline" data-x>Cancelar</button><button class="btn btn-orange" data-ok>Guardar</button>',
  });
  el.querySelector('[data-x]').onclick = cerrar;
  el.querySelector('[data-ok]').onclick = async () => {
    const cuerpo = { nombre: $('#r-n', el).value, valor: $('#r-v', el).value, moneda: $('#r-m', el).value, activo: $('#r-a', el).checked };
    try {
      if (r.id) await api.config.editarRegalo(r.id, cuerpo); else await api.config.crearRegalo(cuerpo);
      S.catalogos = await api.catalogos(); cerrar(); toast('Regalo guardado.', 'ok'); render();
    } catch (e) { error(e); }
  };
}

async function pintarRoles() {
  const cont = $('#roles .card-body');
  try {
    const { items } = await api.config.usuarios();
    cont.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Usuario</th><th>Rol en paneles</th>${Object.values(ROLES).map((r) => `<th>${r}</th>`).join('')}<th></th></tr></thead><tbody>
      ${items.map((u) => `<tr data-uid="${esc(u.uid)}"><td><div class="td-strong">${esc(u.nombre || '—')}</div><div class="small muted">${esc(u.email || u.uid)}</div>${u.activoEnPadron ? '' : '<span class="badge badge-gray">baja en padrón</span>'}</td>
        <td><span class="badge badge-gray">${esc(u.rolPaneles || '—')}</span></td>
        ${Object.keys(ROLES).map((r) => `<td><input type="checkbox" data-rol="${r}" ${u.roles.includes(r) ? 'checked' : ''} ${r === 'administrador' && u.adminPorPaneles ? 'disabled title="Admin de paneles: administrador por construcción"' : ''} style="width:16px;height:16px;accent-color:var(--orange)" /></td>`).join('')}
        <td><button class="btn btn-outline btn-xs" data-guardar>Guardar</button></td></tr>`).join('')}
      </tbody></table></div>`;
    cont.onclick = async (ev) => {
      const b = ev.target.closest('[data-guardar]'); if (!b) return;
      const tr = b.closest('tr');
      const roles = [...tr.querySelectorAll('[data-rol]:checked:not(:disabled)')].map((x) => x.dataset.rol);
      try { await api.config.roles(tr.dataset.uid, roles); toast('Roles actualizados.', 'ok'); } catch (e) { error(e); }
    };
  } catch (e) { cont.innerHTML = `<div class="alert alert-error"><span>⚠️</span><span>${esc(e.message)}</span></div>`; }
}
