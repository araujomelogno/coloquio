# Manual de usuario

`Manual_de_usuario.pdf` es el entregable. Es el paso a paso de cada tarea de la
Fase 1 de COLOQUIO, con capturas de la aplicación real: estudio y pauta, sesión,
selección, embudo, WhatsApp, reemplazo, recepción desde el teléfono, cierre,
incentivos, tablero, configuración y cumplimiento.

## Cómo se rehace

Las capturas se toman recorriendo la aplicación de verdad con
`scripts/servidor_local.py`, que usa la API y la interfaz de producción con
stores en memoria y un panel ficticio de 96 personas. No hay mockups.

```bash
npm install playwright-core pdf-lib      # en cualquier carpeta con node_modules a mano
pip install Pillow
```

### 1 · Capturar

```bash
node docs/manual/capturar.mjs            # levanta el servidor local en :8799 y deja 38 PNG en capturas/
```

El script hace tres retoques en el navegador, ninguno sobre el repo, y los
explica en su encabezado: oculta el cartel de «modo local», sirve la
tipografía desde `tipografia/` (sin red, la página cae a la de respaldo), y en
la captura de ingreso reemplaza el SDK de Firebase por uno que no inicia
sesión, para mostrar la pantalla de producción.

Los casos que no se pueden provocar desde la pantalla los arma por la API del
servidor local: la respuesta y la entrega fallida de WhatsApp (se simulan los
webhooks de Meta) y el mini-grupo de Maldonado donde se agota el segmento y no
hay reemplazo.

### 2 · Optimizar

Salen en PNG a 2×. En el PDF entran a ~1×, así que se pasan a JPEG:

```bash
python3 - <<'PY'
import pathlib
from PIL import Image
d = pathlib.Path('docs/manual/capturas')
for png in sorted(d.glob('*.png')):
    img = Image.open(png).convert('RGB')
    if img.width > 1700:
        img = img.resize((1700, round(img.height * 1700 / img.width)), Image.LANCZOS)
    img.save(png.with_suffix('.jpg'), 'JPEG', quality=88, optimize=True, progressive=True)
    png.unlink()
PY
```

### 3 · Generar el PDF

```bash
node docs/manual/generar_pdf.mjs
```

Portada y cuerpo se imprimen por separado —la portada va a sangre y el cuerpo
con márgenes y pie de página— y se pegan al final: Chromium aplica una sola
configuración de página por impresión. Es el mismo mecanismo que el manual de
`paneles`.

## Qué hay en esta carpeta

| Archivo | Qué es |
|---|---|
| `Manual_de_usuario.pdf` | El entregable |
| `portada.html` | La portada, a sangre |
| `manual.html` | El índice y las quince secciones |
| `estilo.css` | Los estilos, compartidos por los dos (base: el manual de `paneles`) |
| `capturas/` | Las 38 capturas |
| `tipografia/` | Montserrat local, para que el PDF salga igual sin red |
| `capturar.mjs` | Toma las capturas |
| `generar_pdf.mjs` | Maqueta el PDF |

## Detalles que conviene no deshacer

* **La ventana es de 1440 × 1000.** A 1280 px de ancho, con Montserrat, la
  columna de cuota del embudo se salía de la pantalla. Eso llevó a corregir la
  grilla (`.grid-2 > * { min-width: 0 }`), pero 1440 es el ancho de trabajo
  más común.
* **Los toasts se limpian antes de cada captura.** La única que es de un toast
  lo pide expresamente.
* **Las capturas de teléfono van de a dos** (`.par`): a ancho completo, una
  pantalla de teléfono ocupa tres páginas.
