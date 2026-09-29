/* Toma las capturas del manual recorriendo la aplicación real.
 *
 *   npm install playwright-core
 *   node docs/manual/capturar.mjs            # deja las PNG en docs/manual/capturas
 *
 * Levanta `scripts/servidor_local.py`: la API y la interfaz son las de
 * producción, con stores en memoria y un panel ficticio de 96 personas. No hay
 * mockups: lo que se ve en el manual es lo que hace la aplicación.
 *
 * Tres retoques, todos en el navegador y ninguno sobre el repo:
 *   · se oculta el cartel de «modo local», que existe solo porque la copia no
 *     tiene Firebase;
 *   · la tipografía se sirve desde docs/manual/tipografia, porque sin red la
 *     página cae a la de respaldo;
 *   · para la captura de ingreso, el SDK de Firebase se reemplaza por uno que
 *     no inicia sesión, así se ve la pantalla de producción.
 */
import { chromium } from 'playwright-core';
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const RAIZ = path.resolve(AQUI, '..', '..');
const SALIDA = path.resolve(process.argv[2] || path.join(AQUI, 'capturas'));
const PUERTO = 8799;
const BASE = `http://127.0.0.1:${PUERTO}`;
const EJECUTABLE = process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

await fs.mkdir(SALIDA, { recursive: true });

// ── Servidor local ──
const servidor = spawn('python3', [path.join(RAIZ, 'scripts', 'servidor_local.py'), '--puerto', String(PUERTO)], { stdio: 'ignore' });
for (let i = 0; i < 50; i++) {
  try { await fetch(`${BASE}/api/cuali/entorno`); break; } catch { await new Promise((r) => setTimeout(r, 200)); }
}

async function api(metodo, camino, cuerpo, usuario = 'u-admin') {
  const r = await fetch(`${BASE}/api/cuali${camino}`, {
    method: metodo,
    headers: { 'Content-Type': 'application/json', 'X-Usuario-Local': usuario },
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  const datos = await r.json();
  if (!r.ok) throw new Error(`${metodo} ${camino}: ${datos.mensaje}`);
  return datos;
}

// ── Tipografía local ──
const PESOS = [400, 500, 600, 700, 800];
const cssFuentes = PESOS.flatMap((p) => ['latin', 'latin-ext'].map((s) => `
@font-face { font-family: 'Montserrat'; font-style: normal; font-weight: ${p};
  src: url(https://fuentes.local/montserrat-${p}-${s}.woff2) format('woff2'); }`)).join('\n')
  + "\n@font-face { font-family: 'Montserrat'; font-weight: 900; src: url(https://fuentes.local/montserrat-800-latin.woff2) format('woff2'); }";

async function prepararContexto(ctx) {
  await ctx.route('https://fonts.googleapis.com/**', (r) => r.fulfill({ contentType: 'text/css', body: cssFuentes }));
  await ctx.route('https://fonts.gstatic.com/**', (r) => r.abort());
  await ctx.route('https://fuentes.local/**', (r) => r.fulfill({
    path: path.join(AQUI, 'tipografia', path.basename(new URL(r.request().url()).pathname)),
    contentType: 'font/woff2',
  }));
  await ctx.addInitScript(() => {
    const s = document.createElement('style');
    s.textContent = '.demo-banner{display:none!important}';
    document.addEventListener('DOMContentLoaded', () => document.head.appendChild(s));
  });
}

const nav = await chromium.launch({ executablePath: EJECUTABLE, args: ['--no-sandbox'], env: { ...process.env, LANG: 'es_UY.UTF-8' } });

async function limpiar(p) {
  await p.evaluate(() => {
    document.getElementById('toast-wrap')?.replaceChildren();
    document.activeElement?.blur?.();
  });
  await p.waitForTimeout(150);
}
let n = 0;
const nombre = (clave) => `${String(++n).padStart(2, '0')}-${clave}.png`;
async function captura(p, clave, { modal = false, elemento = null, completa = false, toast = false } = {}) {
  if (!toast) await limpiar(p);
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(250);
  const archivo = path.join(SALIDA, nombre(clave));
  if (modal) await p.locator('.modal-box').last().screenshot({ path: archivo });
  else if (elemento) await p.locator(elemento).first().screenshot({ path: archivo });
  else await p.screenshot({ path: archivo, fullPage: completa });
  console.log('  ✓', path.basename(archivo));
}
const cerrarModal = async (p) => { await p.locator('.modal-close').last().click(); await p.waitForTimeout(150); };
const esperar = (p, ms = 450) => p.waitForTimeout(ms);
// Ir a una pantalla releyendo los datos: con la misma URL, `goto` solo cambia
// el hash y la app no vuelve a pedir nada.
const irA = async (p, ruta) => { await p.goto(`${BASE}/#${ruta}`); await p.reload(); };

// ════════════════ 1 · Ingreso (pantalla de producción) ════════════════
{
  const ctx = await nav.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2, locale: 'es-UY' });
  await prepararContexto(ctx);
  await ctx.route('**/api/cuali/entorno', (r) => r.fulfill({ contentType: 'application/json', body: '{"sistema":"coloquio"}' }));
  await ctx.route('https://www.gstatic.com/firebasejs/**/firebase-app.js', (r) => r.fulfill({ contentType: 'text/javascript', body: 'export function initializeApp(){return {}}' }));
  await ctx.route('https://www.gstatic.com/firebasejs/**/firebase-auth.js', (r) => r.fulfill({
    contentType: 'text/javascript',
    body: `export function getAuth(){return {currentUser:null}}
      export function onAuthStateChanged(a, cb){ setTimeout(() => cb(null), 0); }
      export async function signInWithEmailAndPassword(){ throw new Error('x'); }
      export async function sendPasswordResetEmail(){}
      export async function signOut(){}`,
  }));
  const p = await ctx.newPage();
  await p.goto(BASE); await p.waitForSelector('#login-form');
  await p.fill('#email', 'coordinacion@equipos.com.uy'); await p.fill('#clave', 'contraseña');
  await captura(p, 'ingreso');
  await ctx.close();
}

// ════════════════ Escritorio ════════════════
const ctx = await nav.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 2, locale: 'es-UY' });
await prepararContexto(ctx);
await ctx.addInitScript(() => sessionStorage.setItem('coloquio-local', 'u-admin'));
const p = await ctx.newPage();
p.on('pageerror', (e) => console.error('pageerror', e.message));

await p.goto(BASE); await p.waitForSelector('text=Próximos 7 días'); await esperar(p);
await captura(p, 'tablero-inicio');

// ── 3 · Estudios ──
await p.goto(`${BASE}/#/estudios`); await p.waitForSelector('text=Cervezas artesanales 2026');
await captura(p, 'estudios');
await p.click('#nuevo'); await p.waitForSelector('#e-nombre');
await p.fill('#e-nombre', 'Aguas saborizadas 2026'); await p.fill('#e-cliente', 'Bebidas del Plata');
await p.selectOption('#e-cat', 'bebidas'); await p.fill('#e-desc', 'consumo de aguas saborizadas');
await captura(p, 'estudio-nuevo', { modal: true });
await p.click('.modal-box [data-ok]'); await p.waitForSelector('text=no tiene pauta');
await captura(p, 'estudio-sin-pauta');
await p.click('#editar-pauta'); await p.waitForSelector('[data-topico]');
const topicos = [
  ['Caldeamiento', 10, 'Presentación y rutina de hidratación', ''],
  ['Momentos de consumo', 25, 'Cuándo y por qué se elige un agua saborizada', '¿Qué la reemplaza?\n¿En qué momento del día?'],
  ['Evaluación de concepto', 35, 'Reacción espontánea al concepto nuevo', '¿Qué es lo primero que te llama la atención?'],
];
for (let i = 0; i < topicos.length; i++) {
  if (i > 0) await p.click('#mas');
  const t = p.locator('[data-topico]').nth(i);
  await t.locator('[data-f="titulo"]').fill(topicos[i][0]);
  await t.locator('[data-f="minutos"]').fill(String(topicos[i][1]));
  await t.locator('[data-f="objetivo"]').fill(topicos[i][2]);
  await t.locator('[data-f="repreguntas"]').fill(topicos[i][3]);
}
await captura(p, 'pauta-editor', { modal: true });
await p.click('.modal-box [data-ok]'); await esperar(p);

const estudios = (await api('GET', '/estudios')).items;
const cervezas = estudios.find((e) => e.nombre.startsWith('Cervezas'));
const banca = estudios.find((e) => e.nombre.startsWith('Banca'));
await p.goto(`${BASE}/#/estudios/${cervezas.id}`); await p.waitForSelector('text=Ocasiones de consumo');
await captura(p, 'estudio-ficha');
await p.click('#nueva-sesion'); await p.waitForSelector('#s-nombre');
await p.fill('#s-nombre', 'Grupo 2 — 45 a 64'); await p.fill('#s-lugar', 'Sala Equipos, Pocitos');
await p.fill('#s-cupo', '8'); await p.fill('#s-ratio', '1.5');
await captura(p, 'sesion-nueva', { modal: true });
await cerrarModal(p);

const sesion = (await api('GET', '/sesiones')).items.find((s) => s.estudioId === cervezas.id);
const S = sesion.id;
await p.goto(`${BASE}/#/sesiones/${S}/armado`); await p.waitForSelector('#form');
await captura(p, 'sesion-armado');

// ── 5 · Selección ──
await p.goto(`${BASE}/#/sesiones/${S}/seleccion`); await p.waitForSelector('#buscar');
await p.click('#modo label:has(input[value=mixta])');
await p.click('.seg label:has(input[name=tramoEtario][value="25-34"])');
await p.click('.seg label:has(input[name=tramoEtario][value="35-44"])');
await p.fill('#f-crit', 'toma cerveza artesanal con amigos');
await captura(p, 'seleccion-consulta', { elemento: '.card' });
await p.click('#buscar'); await p.waitForSelector('text=ranking semántico'); await esperar(p);
await captura(p, 'seleccion-mixta');
await p.click('#modo label:has(input[value=demografica])');
await p.click('#buscar'); await p.waitForSelector('text=demográfica pura'); await esperar(p);
await p.locator('text=Excluidos por el filtro anti-panelista-profesional').scrollIntoViewIfNeeded();
await captura(p, 'seleccion-excluidos', { elemento: '.card.mt2' });
await p.locator('.card.mt2 [data-historial]').first().click(); await p.waitForSelector('.modal-box >> text=Participaciones'); await esperar(p);
await captura(p, 'historial', { modal: true });
await cerrarModal(p);
await p.evaluate(() => window.scrollTo(0, 0));
await p.click('#todos');
await p.locator('[data-sel][data-excluido="1"]').first().check();
await p.click('#agregar'); await p.waitForSelector('#motivo');
await p.fill('#motivo', 'Perfil de consumo artesanal muy difícil de conseguir en Maldonado');
await captura(p, 'anulacion-fatiga', { modal: true });
await p.click('.modal-box [data-ok]'); await p.waitForSelector('.toast.ok'); await esperar(p, 900);
await p.click('#proponer'); await p.waitForSelector('text=Lista de invitación propuesta'); await esperar(p);
await captura(p, 'invitacion-propuesta', { modal: true });
await p.click('.modal-box [data-ok]'); await p.waitForSelector('.funnel'); await esperar(p);

// ── 6 · Embudo ──
await captura(p, 'embudo');
const conv0 = (await api('GET', `/sesiones/${S}/embudo`)).convocatorias.filter((c) => c.estado === 'invitado');
await p.locator(`[data-contacto=celular][data-pid="${conv0[0].idPersona}"]`).click(); await p.waitForSelector('.contacto-dato'); await esperar(p);
await captura(p, 'contacto', { modal: true });
await cerrarModal(p);
await p.locator(`[data-intento][data-pid="${conv0[1].idPersona}"]`).click(); await esperar(p, 700);
// Ocho confirmados, con el atajo de un clic.
for (let i = 0; i < 8; i++) {
  await p.locator(`[data-a=acepto][data-pid="${conv0[i].idPersona}"]`).click(); await esperar(p, 500);
}
for (let i = 0; i < 7; i++) {
  await p.locator(`[data-a=confirmado][data-pid="${conv0[i].idPersona}"]`).click(); await esperar(p, 500);
}
// WhatsApp: dos por ese canal; uno responde, al otro no le llega.
const wa1 = conv0[8].idPersona; const wa2 = conv0[9].idPersona;
for (const pid of [wa1, wa2]) {
  await p.locator(`select[data-canal="${pid}"]`).selectOption('whatsapp'); await esperar(p, 600);
  await p.locator(`[data-wa=invitacion][data-pid="${pid}"]`).click(); await esperar(p, 700);
}
await api('POST', '/webhooks/whatsapp', { entry: [{ changes: [{ value: { messages: [
  { type: 'button', context: { id: 'wamid.PRUEBA0001' }, button: { payload: `c1|${S}|${wa1}|si` } }] } }] }] });
await api('POST', '/webhooks/whatsapp', { entry: [{ changes: [{ value: { statuses: [
  { id: 'wamid.PRUEBA0002', status: 'failed', errors: [{ title: 'Número no registrado en WhatsApp' }] }] } }] }] });
await irA(p, `/sesiones/${S}/embudo`); await p.waitForSelector('.funnel'); await esperar(p);
const filaWa = async (pid) => p.locator('tr', { has: p.locator(`select[data-canal="${pid}"], [data-eventos][data-pid="${pid}"]`) }).first();
await (await filaWa(wa1)).scrollIntoViewIfNeeded();
await (await filaWa(wa1)).screenshot({ path: path.join(SALIDA, nombre('whatsapp-respondio')) }); console.log('  ✓ whatsapp-respondio');
await (await filaWa(wa2)).screenshot({ path: path.join(SALIDA, nombre('whatsapp-degradado')) }); console.log('  ✓ whatsapp-degradado');
// La confirmación por WhatsApp de quien respondió: dentro de la ventana, gratis.
await p.locator(`[data-wa=confirmacion][data-pid="${wa1}"]`).click(); await p.waitForSelector('.toast'); await esperar(p, 300);
await captura(p, 'whatsapp-en-ventana', { elemento: '#toast-wrap', toast: true });
await api('POST', '/webhooks/whatsapp', { entry: [{ changes: [{ value: { messages: [
  { type: 'interactive', interactive: { button_reply: { id: `c1|${S}|${wa1}|si` } } }] } }] }] });
await irA(p, `/sesiones/${S}/embudo`); await p.waitForSelector('text=Cupo alcanzado'); await esperar(p);
await p.evaluate(() => window.scrollTo(0, 0));
await captura(p, 'cupo-alcanzado');
await p.locator(`[data-eventos][data-pid="${wa1}"]`).click(); await p.waitForSelector('.timeline');
await captura(p, 'eventos', { modal: true });
await cerrarModal(p);

// ── 8 · Reemplazo ──
const caido = conv0[2].idPersona;
await p.locator(`[data-a=se_cayo][data-pid="${caido}"]`).click(); await p.waitForSelector('text=sin restituir'); await esperar(p);
await p.evaluate(() => window.scrollTo(0, 0));
await captura(p, 'se-cayo', { elemento: '.alert-warn' });
await p.locator(`[data-reemplazo="${caido}"]`).first().click(); await p.waitForSelector('text=Reemplazo con revalidación'); await esperar(p);
await p.locator('.modal-box details summary').click().catch(() => {});
await captura(p, 'reemplazo', { modal: true });
await p.locator('.modal-box [data-elegir][data-parcial="0"]').first().click(); await esperar(p, 800);

// Caso sin candidatos: un mini-grupo en Maldonado donde el segmento se agota.
await api('POST', `/estudios/${banca.id}/pauta`, { topicos: [{ titulo: 'Uso de la app', minutos: 45 }] });
const mini = await api('POST', '/sesiones', {
  estudioId: banca.id, nombre: 'Mini-grupo Maldonado', tipo: 'grupo', fecha: new Date(Date.now() + 5 * 864e5).toISOString().slice(0, 16),
  lugar: 'Hotel Conrad, Punta del Este', cupoObjetivo: 4, ratioSobrerreclutamiento: 1,
  cuotas: [{ dimension: 'sexo', categoria: 'F', objetivo: 4 }, { dimension: 'tramoEtario', categoria: '45-54', objetivo: 4 },
    { dimension: 'localidad', categoria: 'Maldonado', objetivo: 4 }],
});
const selMini = await api('POST', `/sesiones/${mini.id}/candidatos`, { modo: 'demografica', filtros: { sexo: ['F'], tramoEtario: ['45-54'], localidad: ['Maldonado'] } });
const idsMini = selMini.candidatos.map((c) => c.idPersona);
await api('POST', `/sesiones/${mini.id}/convocatorias`, { candidatos: idsMini });
await api('POST', `/sesiones/${mini.id}/invitacion`, { ids: idsMini });
for (const pid of idsMini) await api('PATCH', `/convocatorias/${mini.id}/${pid}`, { a: 'confirmado' });
await api('PATCH', `/convocatorias/${mini.id}/${idsMini[0]}`, { a: 'se_cayo' });
await irA(p, `/sesiones/${mini.id}/embudo`); await p.waitForSelector('text=sin restituir');
await p.locator(`[data-reemplazo="${idsMini[0]}"]`).first().click(); await p.waitForSelector('text=Ningún candidato'); await esperar(p);
await captura(p, 'sin-reemplazo', { modal: true });
await cerrarModal(p);

// Uno que aceptó pero no confirmó, para la recepción.
const noConf = conv0[7].idPersona;

// ════════════════ Teléfono: recepción ════════════════
const movil = await nav.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: 'es-UY' });
await prepararContexto(movil);
await movil.addInitScript(() => sessionStorage.setItem('coloquio-local', 'u-coord'));
const m = await movil.newPage();
await m.goto(`${BASE}/#/sesiones/${S}/recepcion`); await m.waitForSelector('.recep-hero'); await esperar(m);
await captura(m, 'recepcion-movil');
const confirmados = (await api('GET', `/sesiones/${S}/recepcion`)).items.filter((i) => i.confirmado);
for (const c of confirmados.slice(0, 7)) { await m.locator(`[data-llego="${c.idPersona}"]`).click(); await esperar(m, 550); }
const codNoConf = noConf.replace(/-/g, '').slice(0, 6).toUpperCase();
await m.fill('#buscar', codNoConf); await esperar(m, 300);
await captura(m, 'recepcion-busqueda');
await m.locator(`[data-llego="${noConf}"]`).click(); await m.waitForSelector('#motivo');
await m.fill('#motivo', 'Trae la invitación de WhatsApp; confirmó por teléfono esta mañana');
await captura(m, 'recepcion-no-confirmado', { modal: true });
await m.click('.modal-box [data-ok]'); await esperar(m, 700);
await m.fill('#buscar', 'ZZ9'); await esperar(m, 300);
await captura(m, 'recepcion-codigo-ajeno');
await m.fill('#buscar', ''); await esperar(m, 300);
await captura(m, 'recepcion-presentes', { completa: true });
await m.fill('#notas', 'Buena dinámica; se cubrieron los cuatro tópicos en 85 minutos.');
await m.click('#cerrar'); await m.waitForSelector('.modal-box [data-ok]');
await captura(m, 'cerrar-sesion', { modal: true });
await m.click('.modal-box [data-ok]'); await m.waitForSelector('text=Regalo por participante'); await esperar(m);
await movil.close();

// ── 10 · Incentivos ──
await p.goto(`${BASE}/#/sesiones/${S}/incentivos`); await p.waitForSelector('text=Regalo por participante'); await esperar(p);
const inc = await api('GET', `/sesiones/${S}/incentivos`);
const canasta = inc.catalogo.find((r) => r.nombre.startsWith('Canasta'));
await p.locator(`select[data-regalo="${inc.items[0].idPersona}"]`).selectOption(canasta.id); await esperar(p, 700);
for (const i of inc.items.slice(1, 4)) { await p.locator(`[data-entregar="${i.idPersona}"]`).click(); await esperar(p, 600); }
await captura(p, 'incentivos');
const presente = inc.items[1].idPersona;
await irA(p, `/sesiones/${S}/embudo`); await p.waitForSelector('.funnel');
await p.click('#filtros label:has(input[value=cerrados])'); await esperar(p, 300);
await p.locator(`[data-historial="${presente}"]`).first().click(); await p.waitForSelector('.modal-box >> text=Participaciones'); await esperar(p);
await captura(p, 'historial-despues', { modal: true });
await cerrarModal(p);

// ── 11 · Tablero ──
await p.goto(`${BASE}/#/`); await p.waitForSelector('text=Tasa de show por sesión'); await esperar(p, 700);
await captura(p, 'tablero', { completa: true });

// ── 12 y 13 · Configuración ──
await p.goto(`${BASE}/#/configuracion`); await p.waitForSelector('text=Roles en COLOQUIO'); await esperar(p, 700);
await captura(p, 'configuracion');
await p.locator('.card', { hasText: 'Importar sesión histórica' }).scrollIntoViewIfNeeded();
await p.fill('#h-fecha', '2026-03-12'); await p.fill('#h-et', 'Grupo cerveza — marzo 2026');
await p.fill('#h-ids', '7b0f1a52-3c11-4f5e-9e21-3f6f2d0a9b11\n0c4d9e2a-8b7f-4a1c-b3d5-6e2f1a9c7d40');
await captura(p, 'importar-historico', { elemento: '.card:has-text("Importar sesión histórica")' });
await p.locator('#roles').scrollIntoViewIfNeeded(); await esperar(p);
await captura(p, 'roles', { elemento: '#roles' });
await p.click('#consistencia'); await esperar(p, 800);
await captura(p, 'cumplimiento', { elemento: '.card:has-text("Cumplimiento")' });

await nav.close();
servidor.kill();
console.log(`\n${n} capturas en ${SALIDA}`);
