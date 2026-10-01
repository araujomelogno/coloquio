# Decisiones de diseño

**Sistema:** COLOQUIO · investigación cualitativa · Equipos Consultores
**Alcance:** Fase 1 — estudio cualitativo y embudo de convocatoria
**Última actualización:** 2026-09-30

---

## Qué es este documento y cómo leerlo

Un registro de las decisiones que no son obvias: las que alguien que lea el código
podría querer revertir sin saber qué se rompe si lo hace. No documenta *qué*
hace el sistema —para eso están el PRD y la SPEC— sino **por qué está hecho así
y qué se descartó en el camino**.

Tiene la misma forma que `paneles/docs/decisiones.md`, y la numeración es
propia: una `D7` de acá no es la `D7` de `paneles`.

Cada decisión tiene la misma estructura:

- **El problema**: qué había que resolver.
- **La decisión**: qué se hizo.
- **Alternativas descartadas**: qué más se consideró y por qué no.
- **Consecuencias**: qué se gana, qué se paga y qué queda condicionado.
- **Dónde vive**: el archivo donde está, para ir a mirarlo.

Muchas tienen además **Cómo se verifica**: la prueba automatizada que falla si
alguien revierte la decisión sin querer. Cuando existe es la parte más
importante de la entrada, porque es lo que convierte una decisión en una
restricción real del sistema. Las pruebas están en `functions/tests/`.

> **Una decisión revertible no es un error.** Varias de las que están acá se
> pueden cambiar con buenos motivos. Lo que este documento evita es que se
> cambien **sin** motivos, por no saber qué sostenían.

### Índice

| | Decisión | Bloque |
|---|---|---|
| [D1](#d1) | Mismo proyecto que `paneles`, con codebase, sitio y base propios | A · Dónde vive |
| [D2](#d2) | Firestore con nombre propio, y no Cloud SQL, para el store cualitativo | A |
| [D3](#d3) | El store se envuelve: nadie escribe en Firestore directo | A |
| [D4](#d4) | Todo pasa por la API; las reglas niegan todo | A |
| [D5](#d5) | Roles propios sobre el padrón de `paneles` | A |
| [D6](#d6) | Cero PII se hace valer en cada escritura, por nombre y por contenido | B · Privacidad |
| [D7](#d7) | No hay notas libres sobre personas | B |
| [D8](#d8) | El contacto se pide en el momento, con el email humano, y se descarta | B |
| [D9](#d9) | La bóveda se lee solo por la superficie de la Fase 5 | B |
| [D10](#d10) | El segmento lo pone la bóveda, no el cliente | B |
| [D11](#d11) | El motor semántico es el de `paneles`, por su API y con el token del usuario | C · Selección |
| [D12](#d12) | Si el motor no responde, la selección degrada y lo dice | C |
| [D13](#d13) | El gate de contacto se aplica después del ranking, contra la vista | C |
| [D14](#d14) | La fatiga cualitativa es propia y cuenta participación, no convocatoria | C |
| [D15](#d15) | La fatiga se puede saltar, pero no en silencio | C |
| [D16](#d16) | La importación histórica se adelantó de P1 | C |
| [D17](#d17) | El id del documento de convocatoria es el `id_persona` | D · Modelo |
| [D18](#d18) | Un estudio por persona, garantizado en la misma transacción | D |
| [D19](#d19) | `participacionCuali`: un documento, tres requisitos | D |
| [D20](#d20) | Los agregados se mantienen al escribir, y hay una verificación que repara | D |
| [D21](#d21) | Una sola definición de qué hace una transición | D |
| [D22](#d22) | Nada de efectos externos adentro de una transacción | D |
| [D23](#d23) | Un store en memoria que hace cumplir las reglas de Firestore, y el emulador | D |
| [D24](#d24) | Los atajos de un clic registran los pasos intermedios | E · Embudo |
| [D25](#d25) | Volver desde un terminal exige motivo; quitar, solo antes de invitar | E |
| [D26](#d26) | Un intento sin respuesta es un evento, no un estado | E |
| [D27](#d27) | El estado de la sesión se deriva del embudo | E |
| [D28](#d28) | La meta de invitación es por segmento, y el supuesto se muestra | F · Cuota |
| [D29](#d29) | La lista de invitación no se completa con cualquiera | F |
| [D30](#d30) | Restituir el segmento es coincidir en todas las dimensiones con cuota | F |
| [D31](#d31) | Sin reemplazo hay tres salidas, y la elegida queda registrada | F |
| [D32](#d32) | Una baja en un embudo activo deja el segmento, no la persona | F |
| [D33](#d33) | El canal es por persona, y el manual se construyó primero | G · Canal |
| [D34](#d34) | La invitación provoca respuesta; lo que sigue va en la ventana gratis | G |
| [D35](#d35) | El botón de WhatsApp lleva el `id_persona`, no el teléfono | G |
| [D36](#d36) | Si WhatsApp falla, la convocatoria pasa a manual y no pierde su estado | G |
| [D37](#d37) | En la puerta, la identidad es un código de convocatoria | H · Día de sesión |
| [D38](#d38) | El compromiso de incentivo nace con la asistencia | H |
| [D39](#d39) | El cierre es una sola transacción | H |
| [D40](#d40) | Cancelar es un estado propio, con compensación explícita | H |
| [D41](#d41) | Borrar, verificar, y recién después confirmar | I · Cascada |
| [D42](#d42) | Con la persona se va su código y toda referencia cruzada | I |
| [D43](#d43) | Qué alcances de baja borran en la Fase 1 | I |
| [D44](#d44) | La convocatoria se declara en la bóveda al invitar, antes de la transacción | J · Convocatoria declarada |
| [D46](#d46) | El vencimiento es la sesión más dos días, con el tope de la bóveda | J |
| [D47](#d47) | Si la declaración venció, se repone al leer el contacto, una vez | J |
| [D45](#d45) | Los umbrales de fatiga son un punto de partida, no una definición | K · Abierto |

---

# Bloque A · Dónde vive COLOQUIO

<a id="d1"></a>
## D1 · Mismo proyecto que `paneles`, con codebase, sitio y base propios

**El problema.** COLOQUIO necesita llegar a la bóveda de `paneles`, que vive en
una VPC privada del proyecto `gestion-paneles`, y a la vez poder desplegarse sin
tocar `paneles`.

**La decisión.** El mismo proyecto GCP (HANDOFF §1), pero con todo lo que se
despliega separado:

- funciones en un **codebase propio** (`coloquio` en `firebase.json`) y con
  **prefijo** en el nombre (`coloquio_api`, `coloquio_cascada`), porque en un
  proyecto compartido los nombres tienen que ser únicos;
- un **sitio de Hosting propio** (`coloquio-equipos`, target `coloquio`);
- una **base Firestore con nombre propio** (D2);
- el **conector de VPC existente** (`paneles-conn`), no uno nuevo.

**Alternativas descartadas.**

- *Proyecto propio con Shared VPC.* Era la recomendación de la Fase 0 de
  `paneles`. Se descartó por la cuota de facturación y por la complejidad. Además
  obliga a tener un conector propio (~US$ 10–15/mes).
- *Meter COLOQUIO adentro de `paneles`.* Lo descarta el PRD: un sistema que hace
  todo deja de tener invariantes que valga la pena defender.

**Consecuencias.** La separación que importa, la de **privilegios de base**, se
mantiene: COLOQUIO entra a la bóveda con su propio rol y solo ve la superficie
de la Fase 5 (D9). La separación de proyectos era comodidad operativa. El costo
incremental de infraestructura es prácticamente cero.

**Dónde vive.** `firebase.json`, `.firebaserc`, `functions/main.py`,
`scripts/verificar_region.py`.

---

<a id="d2"></a>
## D2 · Firestore con nombre propio, y no Cloud SQL, para el store cualitativo

**El problema.** El PRD pensaba el store cualitativo como un Cloud SQL con
régimen de bóveda, porque en las fases siguientes va a tener transcripciones y
grabaciones, que son PII por definición. Pero `firestore.rules` de `paneles`
dice que Firestore en ese proyecto guarda **una sola cosa**, el padrón, y que
nada de PII de panelistas puede ir ahí.

**La decisión.** Para la Fase 1, Firestore, con dos condiciones que la hacen
admisible (SPEC §7.2):

1. **Una base con nombre propio** (`coloquio`), separada de la base por defecto.
   Tiene reglas, índices y respaldo propios. La invariante de `paneles` sobre su
   base queda intacta.
2. **Una base sin PII por diseño** (D6). Guarda `id_persona`, estados,
   timestamps y segmentos: tokens opacos y una máquina de estados.

**Alternativas descartadas.**

- *Cloud SQL dedicada.* ~US$ 10/mes, un pool de conexiones que duele cuando la
  función escala, y ningún listener en tiempo real, que es lo que va a necesitar
  el tablero de sala de la Fase 2.
- *Un esquema aparte en la bóveda.* Pondría el store cualitativo del lado de la
  PII sin tener PII, y le daría a COLOQUIO privilegios de escritura en la
  bóveda, que es justo lo que la Fase 5 existe para evitar.
- *Colecciones con prefijo en la base por defecto.* El HANDOFF lo admitía, pero
  mezcla dos regímenes en una misma base, con las mismas reglas.

**Consecuencias.** Se paga lo que Firestore no tiene: no hay `group by` (D20),
no hay índices únicos (D17), no hay `join` con la bóveda (el cruce se hace en
memoria sobre conjuntos chicos), y la cláusula `in` está topeada (el filtro de
fatiga se resuelve con lecturas puntuales, no con una consulta).

> **A revisar en la Fase 2.** Cuando lleguen grabaciones y transcripciones, que
> sí son PII, esas **no** pueden ir a esta base. La decisión de la Fase 1 se
> sostiene porque lo que se guarda no tiene PII, y deja de sostenerse para ese
> contenido.

**Dónde vive.** `firestore.rules`, `firebase.json` (`"database": "coloquio"`),
`coloquio/config.py` (`COLOQUIO_FIRESTORE_DB`).

---

<a id="d3"></a>
## D3 · El store se envuelve: nadie escribe en Firestore directo

**El problema.** Si el código de dominio usara el cliente de Firestore
directamente, la validación de PII (D6) dependería de que cada módulo se acuerde
de llamarla. Además la lógica de dominio no se podría probar sin Firestore.

**La decisión.** Una interfaz propia, `Store` (`get`, `get_many`, `set`,
`update`, `delete`, `listar`, `grupo`, `transaccion`), con dos
implementaciones: `StoreFirestore` y `StoreMemoria`. Las dos validan **toda**
escritura, dentro y fuera de transacción. No hay otro camino para escribir.

**Alternativas descartadas.**

- *Validar en cada módulo.* Es la forma más directa de que alguien se olvide.
- *Un ORM.* No existe uno razonable para Firestore en Python, y agrega una capa
  que no aporta a lo que había que garantizar.

**Consecuencias.** Todo el dominio se prueba en memoria en segundos y, sin
cambiar una línea, contra el emulador (D23).

**Dónde vive.** `coloquio/store.py`.

**Cómo se verifica.** `test_el_store_rechaza_pii` (escritura directa y en
transacción).

---

<a id="d4"></a>
## D4 · Todo pasa por la API; las reglas niegan todo

**El problema.** Firestore invita a que el navegador lea y escriba directo.

**La decisión.** `firestore.rules` niega todo desde el cliente. Las escrituras
entran por `coloquio_api` con el Admin SDK, que no pasa por las reglas. Es el
mismo modelo que usa `paneles`.

**Alternativas descartadas.** *Lectura directa desde el navegador para el
tablero.* Sería más rápido de hacer, pero las reglas tendrían que replicar los
roles y la lógica de qué puede ver cada uno. Se reconsidera en la Fase 2 para
los listeners de la sala.

**Consecuencias.** Hay una sola puerta, con permisos declarados por ruta. Las
únicas rutas públicas son el webhook de Meta, que verifica su firma, y el
entorno.

**Dónde vive.** `firestore.rules`, `coloquio/ruteo.py` (`PUBLICAS`).

**Cómo se verifica.** `test_solo_el_webhook_y_el_entorno_son_publicos`.

---

<a id="d5"></a>
## D5 · Roles propios sobre el padrón de `paneles`

**El problema.** La SPEC pide el mismo padrón de personal que `paneles`, sin un
segundo directorio, pero con roles de COLOQUIO: coordinador, investigador y
administrador, y más de uno por usuario.

**La decisión.**

- **Quién es empleado** lo dice `usuarios/{uid}` en la base **por defecto**, que
  es de `paneles`. COLOQUIO solo la lee. Quien está desactivado ahí no entra.
- **Qué puede hacer** lo dice `rolUsuario/{uid}.roles` en la base de COLOQUIO.
- El `admin` de `paneles` es administrador de COLOQUIO **por construcción**: sin
  eso no habría quién asignar el primer rol.
- En `rolUsuario` no se guarda ni nombre ni email. El validador de PII no
  distingue entre personal y panelistas, y no hace falta que lo haga.

**Alternativas descartadas.**

- *Agregar campos en `usuarios` de `paneles`.* Sería escribir en la base de otro
  sistema.
- *Reusar los roles de `paneles`.* No se corresponden: «analista» no es
  «investigador», y en `paneles` un usuario tiene un solo rol.

**Consecuencias.** Para la búsqueda **semántica** hace falta además permiso en
`paneles` (D11). Está dicho en el manual de despliegue.

**Dónde vive.** `coloquio/auth.py`, `coloquio/usuarios.py`.

**Cómo se verifica.** `test_actor_desde_padron`, `test_roles_y_permisos`.

---

# Bloque B · Privacidad

<a id="d6"></a>
## D6 · Cero PII se hace valer en cada escritura, por nombre y por contenido

**El problema.** R1.12 es el invariante que hace admisible usar Firestore (D2).
Si se rompe, la decisión de store deja de sostenerse.

**La decisión.** Dos controles, dentro de `Store`:

- **Por nombre de campo.** La misma lista que `pii.CAMPOS_PII` de `panel_api`,
  normalizando camelCase (`fechaNacimiento` → `fecha_nacimiento`), porque
  Firestore invita a esa forma. `nombre` está permitido solo donde nombra una
  cosa: estudio, sesión, regalo, configuración.
- **Por contenido, en los campos de texto libre.** Emails, teléfonos y cédulas
  con formato. Solo en los pocos campos declarados como texto libre, porque
  aplicarlo a todo daría falsos positivos con ids y fechas.

**Alternativas descartadas.** *Solo por nombre, como en `paneles`.* En el store
semántico alcanza, porque ahí el texto ya viene despersonalizado. Acá el riesgo
es un coordinador escribiendo «cel 099…» en una nota.

**Consecuencias.** Una categoría de estudio no puede llamarse como un campo de
PII, porque es clave de un mapa en `participacionCuali`. Se valida al guardarla.
El control por contenido **no detecta nombres propios**: no tienen patrón. Es
un riesgo residual declarado (SPEC §13), que se mitiga con diseño de formulario
y avisos en la interfaz.

**Dónde vive.** `coloquio/pii.py`, `coloquio/store.py`, `coloquio/configuracion.py`.

**Cómo se verifica.** `test_lista_de_pii_es_espejo_de_paneles` (si `paneles`
cambia su lista, esto tiene que cambiar a mano), `test_claves_pii_en_camelcase`,
`test_texto_libre_con_pii`, `test_auditoria_del_store_sin_pii`, y
`scripts/auditar_store.py` contra producción.

---

<a id="d7"></a>
## D7 · No hay notas libres sobre personas

**El problema.** La vía de fuga de PII más probable es un campo de
observaciones sobre un participante.

**La decisión.** No existe. Ningún documento de `convocatoria`, `asistencia`,
`incentivo` o `participacionCuali` tiene un campo de texto libre. Hay texto
libre solo donde lo exige un requisito, y es de la **sesión**: notas de cierre,
motivos de anulación, cancelación. Todo eso pasa por el control de contenido.

Una respuesta de WhatsApp en texto libre **no se guarda**: se marca la
convocatoria con «respondió, revisar en el teléfono».

**Alternativas descartadas.** *Permitirlas con una advertencia.* Una advertencia
no es un control.

**Dónde vive.** `coloquio/pii.py` (`TEXTO_LIBRE_POR_COLECCION`),
`coloquio/canales.py` (`_marcar_revision`).

**Cómo se verifica.** `test_notas_de_sesion_no_admiten_pii`,
`test_webhook_no_expone_remitente`.

---

<a id="d8"></a>
## D8 · El contacto se pide en el momento, con el email humano, y se descarta

**El problema.** Convocar exige un celular o un email, que es PII. Si se guarda
una vez, la base deja de estar libre de PII.

**La decisión.**

- Se pide con `contacto_para_convocatoria()` **en el momento de usarlo**, un
  canal por vez.
- `p_actor` es **siempre el email del usuario humano** que lo pide (HANDOFF §3).
  `Boveda.contacto()` se niega a llamar sin él: si una operación no tiene una
  persona detrás, no debería estar pidiendo un contacto.
- El dato se devuelve al navegador y listo. No va al evento del embudo, ni al
  documento, ni al log. En el envío por WhatsApp vive en una variable local y se
  borra con `del` después de usarse.

**Alternativas descartadas.** *Cachearlo durante la convocatoria para no pedirlo
dos veces.* Cada lectura queda auditada en la bóveda, y eso es parte del valor:
se sabe quién miró qué contacto y cuándo.

**Consecuencias.** Cada «📞» en el embudo es una fila en `reidentificacion` a
nombre de quien la pidió. El modal lo dice.

**Dónde vive.** `coloquio/boveda.py` (`_exigir_actor`), `coloquio/canales.py`.

**Cómo se verifica.** `test_contacto_exige_actor_humano`; en
`test_embudo_manual_y_whatsapp`, que el dato no aparezca en el store y que la
auditoría registre el email.

---

<a id="d9"></a>
## D9 · La bóveda se lee solo por la superficie de la Fase 5

**El problema.** Con dos consumidores, un gate de consentimiento escrito en
Python se vuelve una promesa repetida en dos bases de código.

**La decisión.** COLOQUIO usa únicamente `v_persona_convocable`,
`declarar_convocatoria()`, `contacto_para_convocatoria()`,
`mis_borrados_pendientes()`, `confirmar_borrado()`,
`reportar_error_de_borrado()` y `sistema_de_la_conexion()`. **El gate es la
vista**: no hay un `if` en COLOQUIO que decida quién consintió. La única
escritura es `declarar_convocatoria()` (R5.2.a, D44), y es una función de la
superficie, no una tabla.

Se conecta como `coloquio-app@…` con login IAM, por IP privada, con el Cloud SQL
Connector.

**Alternativas descartadas.** *`v_fatiga_panelista`* estaba disponible y no se
usa: mide otra cosa (D14).

**Consecuencias.** La base hace cumplir el contrato: si COLOQUIO intentara leer
`persona`, recibiría `permission denied`.

**Dónde vive.** `coloquio/boveda.py`.

**Cómo se verifica.** `test_boveda_solo_superficie_fase5` lee el SQL de
`BovedaPostgres` y falla si aparece una relación o una función fuera de la
lista, o un `insert`/`update`/`delete`. Del lado de `paneles`, `scripts/verificar_coloquio.py`
controla los privilegios efectivos.

---

<a id="d10"></a>
## D10 · El segmento lo pone la bóveda, no el cliente

**El problema.** Al incorporar candidatos al embudo, el navegador ya tiene el
segmento de cada uno (lo vio en la selección). Sería cómodo mandarlo.

**La decisión.** No se acepta. `incorporar()` recibe solo ids, y el segmento se
**relee de la vista**. Así, además, el gate de consentimiento se reaplica en el
momento de incorporar: quien retiró el consentimiento entre la búsqueda y el
clic no entra.

**Alternativas descartadas.** *Confiar en el cliente.* Un segmento falso rompe la
cuota en silencio, que es exactamente lo que R1.6 prohíbe.

**Dónde vive.** `coloquio/seleccion.py` (`incorporar`).

**Cómo se verifica.** `test_nadie_sin_consentimiento_aparece_ni_entra` fuerza la
incorporación de ids sin consentimiento y verifica que quedan en
`sinConsentimientoVigente`.

---

# Bloque C · Selección de candidatos

<a id="d11"></a>
## D11 · El motor semántico es el de `paneles`, por su API y con el token del usuario

**El problema.** R1.2 pide selección semántica con evidencia, «igual que la
consulta de `paneles`». El PRD es explícito: COLOQUIO no reimplementa el motor.
Pero COLOQUIO no tiene rol en el store semántico, y el motor depende de la
bóveda con los privilegios de `paneles`.

**La decisión.** `POST /api/consultas` de `paneles`, reenviando **el mismo ID
token** del usuario. Como el padrón es el mismo, `paneles` resuelve el rol y
aplica su propio permiso `consultar`. Nadie escala privilegios a través de
COLOQUIO.

**Alternativas descartadas.**

- *Copiar el motor.* Duplica embeddings, recall, reranking, verificación y su
  calibración. La primera diferencia sería silenciosa.
- *Darle a COLOQUIO un rol en el store semántico.* Habría que replicar el gate
  de `uso_semantico` y la resolución demográfica, que es el problema que la
  Fase 5 resolvió llevándolo a la base.

**Consecuencias.** El PRD prefería no acoplar la disponibilidad de COLOQUIO a la
de `paneles`. Acá el acople existe, pero está acotado a la parte semántica y
degrada (D12). Convocar, recibir y cerrar no dependen de `paneles`.

**Dónde vive.** `coloquio/motor.py`.

---

<a id="d12"></a>
## D12 · Si el motor no responde, la selección degrada y lo dice

**El problema.** El motor puede fallar: `paneles` caído, sin permiso, sin
configurar. Y para segmentos poco encuestados no hay contenido embebido, así
que el ranking sería ruido (SPEC §13).

**La decisión.** La selección no se cae: se resuelve **demográfica pura** y la
respuesta trae `degradaciones` con el motivo y la consecuencia. La pantalla lo
muestra arriba de los resultados. Lo mismo cuando el motor responde vacío.

Y el caso inverso: una consulta demográfica **no llama al motor**
(`abrioSemantica: false`), como pide R1.2.

**Dónde vive.** `coloquio/seleccion.py`, `coloquio/motor.py`.

**Cómo se verifica.** `test_motor_caido_degrada_y_lo_dice`,
`test_demografica_no_toca_el_motor`.

---

<a id="d13"></a>
## D13 · El gate de contacto se aplica después del ranking, contra la vista

**El problema.** `paneles` filtra el ranking por `uso_semantico`. Para
convocar a un grupo hace falta además `contacto_participacion`, y son
finalidades distintas.

**La decisión.** Los ids del ranking se cruzan contra `v_persona_convocable`
con `finalidad = 'contacto_participacion'`. Quien no está en la vista no
aparece, aunque el motor lo haya puesto primero. La respuesta informa cuántos
cayeron (`descartadosPorGate`), sin decir quiénes.

**Consecuencias.** «Ninguna persona sin consentimiento aparece» lo garantiza la
base, no COLOQUIO (DoD 3).

**Dónde vive.** `coloquio/seleccion.py`.

**Cómo se verifica.** `test_nadie_sin_consentimiento_aparece_ni_entra`.

---

<a id="d14"></a>
## D14 · La fatiga cualitativa es propia y cuenta participación, no convocatoria

**El problema.** La bóveda expone `v_fatiga_panelista`, pero cuenta
**convocatorias a encuestas**, por panel. El problema del cualitativo es otro:
el panelista profesional que se sienta en todos los grupos.

**La decisión.** El filtro corre contra el registro propio de COLOQUIO
(`participacionCuali`) y cuenta **participación efectiva en sesión**, por
categoría de estudio, dentro de una ventana, más un tope global. Los umbrales
son datos (`config/fatigaCuali`), no constantes.

**Alternativas descartadas.** *Unificar con `umbral_fatiga`.* Mezcla dos
mecanismos que se diseñaron separados: uno evita sobreconvocar a encuestas, el
otro evita al profesional. La fatiga unificada es P2.

**Consecuencias.** Asumida y documentada: el muestreo de `paneles` no ve estas
participaciones. Para `paneles`, alguien que fue a tres grupos sigue descansado
(SPEC §13).

**Dónde vive.** `coloquio/historial.py` (`evaluar_fatiga`), `coloquio/configuracion.py`.

**Cómo se verifica.** `test_fatiga_excluye_y_la_anulacion_queda_registrada`,
`test_umbral_de_fatiga_configurable`, y el final de `test_recepcion_y_cierre`
(quien asistió queda excluido en la próxima sesión de la misma categoría).

---

<a id="d15"></a>
## D15 · La fatiga se puede saltar, pero no en silencio

**El problema.** Hay perfiles difíciles de conseguir, y a veces hay que volver a
sentar a alguien. Una regla sin salida termina esquivándose por fuera del sistema.

**La decisión.** Los excluidos se muestran aparte, con el motivo. Incorporarlos
exige `anulacion: {motivo}` y el permiso `anular_fatiga`, y la anulación queda
en la convocatoria con usuario, hora y los motivos de fatiga que se saltearon.

El intento bloqueado **se cuenta** (`reconvocatoriasBloqueadas`) aunque la
operación aborte, en una transacción aparte. Es la métrica de la SPEC §12: si
todas las anulaciones se aprueban, el umbral está mal puesto.

**Dónde vive.** `coloquio/seleccion.py` (`_incorporar_tx`, `_contar_bloqueo`).

**Cómo se verifica.** `test_fatiga_excluye_y_la_anulacion_queda_registrada`.

---

<a id="d16"></a>
## D16 · La importación histórica se adelantó de P1

**El problema.** El filtro de fatiga arranca sin memoria: durante los primeros
meses no excluye a nadie, justo cuando el panelista profesional ya está en el
panel (SPEC §13).

**La decisión.** Se implementó en la Fase 1: se pegan los `id_persona` de un
grupo ya realizado, con categoría y fecha. Cada participación entra marcada
`importada: true` y cuenta igual para fatiga e historial. También entra al
índice de borrado.

**Consecuencias.** La verificación de consistencia **conserva** las importadas
al reconstruir, porque no salen de ninguna sesión de COLOQUIO.

**Dónde vive.** `coloquio/importacion.py`, `coloquio/consistencia.py`.

---

# Bloque D · Modelo y consistencia

<a id="d17"></a>
## D17 · El id del documento de convocatoria es el `id_persona`

**El problema.** «Una persona no puede estar dos veces en la misma sesión», y
Firestore no tiene índices únicos.

**La decisión.** `sesion/{s}/convocatoria/{idPersona}`: la unicidad es una
propiedad del store y no una validación que alguien puede olvidar. Lo mismo para
`asistencia` e `incentivo`.

**Consecuencias.** Los documentos llevan además `idPersona` como campo, para las
consultas de grupo de colección que usa la cascada (D41).

**Dónde vive.** `coloquio/embudo.py` (`ruta`).

---

<a id="d18"></a>
## D18 · Un estudio por persona, garantizado en la misma transacción

**El problema.** «Una persona no puede estar en dos sesiones del mismo estudio»
cruza documentos de distintas sesiones.

**La decisión.** `participacionCuali/{id}.convocadoEn[]` lista las sesiones
(con su estudio) donde la persona está o estuvo en el embudo. La incorporación
lo **lee y lo escribe en la misma transacción** que crea la convocatoria. Dos
altas concurrentes del mismo id en dos sesiones chocan en ese documento, y
Firestore serializa.

**Alternativas descartadas.** *Consultar todas las sesiones del estudio.* Es una
consulta de grupo por cada candidato y no es atómica.

**Dónde vive.** `coloquio/seleccion.py`, `coloquio/historial.py`.

**Cómo se verifica.** `test_dos_sesiones_del_mismo_estudio_no`.

---

<a id="d19"></a>
## D19 · `participacionCuali`: un documento, tres requisitos

**El problema.** Fatiga (R1.3), historial (R1.9) e índice de borrado (R1.11)
necesitan lo mismo: todo lo de una persona en un solo lugar.

**La decisión.** Un documento por persona con `sesiones[]` (donde participó,
escrito al cerrar) y `convocadoEn[]` (donde estuvo en el embudo, escrito al
incorporar). La SPEC lo pedía con `sesiones[]`. `convocadoEn[]` se agregó
porque, sin él, alguien que está en un embudo y todavía no participó no figura
en el índice, y la cascada no lo encontraría sin un barrido.

**Consecuencias.** Es una dependencia concentrada: si se desincroniza, se
rompen los tres requisitos a la vez. Por eso tiene reconstrucción (D20) y la
cascada tiene una red de seguridad independiente (D41).

**Dónde vive.** `coloquio/historial.py`.

---

<a id="d20"></a>
## D20 · Los agregados se mantienen al escribir, y hay una verificación que repara

**El problema.** Tasa de show, convocados por estado, cuota cubierta y valor
comprometido son agregados, y Firestore no hace `group by`.

**La decisión.** Se mantienen **en la misma transacción** que cambia el estado:
`conteo`, `cuotas[].cubierto`, `metricas`, `valorComprometido` de sesión y de
estudio, y `participacionCuali`. Y hay una verificación que los **recalcula
desde la fuente** (convocatorias, asistencias, incentivos) y, si se le pide,
los reescribe (Configuración → Cumplimiento).

**Alternativas descartadas.**

- *Calcular siempre al leer.* Para una sesión es barato, y de hecho la vista
  del embudo recalcula la cuota. Pero el tablero y los totales por estudio
  necesitarían leer todas las sesiones en cada vista.
- *`firestore.Increment`.* No es portable al store en memoria, y no resuelve
  los agregados que no son sumas.
- *Una verificación que solo avisa.* La SPEC §13 pide explícitamente que repare.

**Dónde vive.** `coloquio/embudo.py` (`contar_alta`, `contar_baja`),
`coloquio/consistencia.py`.

**Cómo se verifica.** `test_consistencia_repara_contadores` rompe un contador,
borra un historial y verifica la reparación. `test_recepcion_y_cierre` y
`test_baja_en_cascada_borra_todo_y_confirma` terminan pidiendo que todo esté
consistente.

---

<a id="d21"></a>
## D21 · Una sola definición de qué hace una transición

**El problema.** El estado de una convocatoria lo cambian seis lugares: el
coordinador, la recepción, el cierre, el reemplazo, el webhook de WhatsApp y la
cascada. Si cada uno ajustara los contadores a su manera, se desincronizarían.

**La decisión.** `embudo.aplicar()` es una función pura sobre los diccionarios
de sesión y convocatoria. Valida la transición, registra el evento (de, a,
canal, resultado, hora, actor), ajusta contadores y cuota, actualiza métricas y
deriva el estado de la sesión. Todos los lugares la llaman.

**Dónde vive.** `coloquio/embudo.py`.

---

<a id="d22"></a>
## D22 · Nada de efectos externos adentro de una transacción

**El problema.** Firestore reintenta la función de transacción cuando hay
contención. Un WhatsApp o una lectura de contacto adentro se ejecutaría dos
veces: dos mensajes pagos o dos filas de auditoría.

**La decisión.** Los efectos externos van **antes** de la transacción y la
transacción solo registra el resultado. En el envío de WhatsApp: se pide el
contacto, se envía, y después, en la transacción, se registra el evento y el
`wamid`. Si el envío falla, una transacción aparte degrada a manual (D36).

**Dónde vive.** `coloquio/canales.py` (`enviar_whatsapp`).

---

<a id="d23"></a>
## D23 · Un store en memoria que hace cumplir las reglas de Firestore, y el emulador

**El problema.** Las pruebas de dominio tienen que ser rápidas. Pero un doble
que no se comporta como Firestore esconde bugs que aparecen recién en
producción.

**La decisión.**

- `StoreMemoria` **imita las dos reglas que más muerden**: en una transacción
  todas las lecturas van antes que las escrituras (si no, lanza
  `LecturaDespuesDeEscritura`), y las escrituras se aplican juntas al final.
- La misma suite corre **contra el emulador de Firestore** con la
  implementación real, poniendo `FIRESTORE_EMULATOR_HOST`.

**Consecuencias.** El emulador encontró un bug que la memoria no veía: dentro de
una transacción, `transaction.get()` no acepta una colección, solo una consulta.
Se corrigió en `StoreFirestore` antes de desplegar.

**Dónde vive.** `coloquio/store.py`, `functions/tests/conftest.py`.

**Cómo se verifica.** `test_lectura_despues_de_escritura_falla`, y la suite
completa con el emulador.

---

# Bloque E · Embudo

<a id="d24"></a>
## D24 · Los atajos de un clic registran los pasos intermedios

**El problema.** R1.5: «si registrar cuesta más que la llamada, no se registra y
el embudo miente». Pero la máquina de estados de la SPEC exige pasar por
`contactado` antes de `aceptó`.

**La decisión.** Botones de un clic que admiten atajos (`invitado → aceptó`,
`invitado → rechazó`, `contactado → confirmado`, `invitado → confirmado`). El
sistema **registra cada paso intermedio** como evento propio, marcado
`implícito`. El grafo de la SPEC se respeta y el coordinador no paga clics de
más.

**Dónde vive.** `coloquio/modelo.py` (`ATAJOS`), `coloquio/embudo.py` (`camino`).

**Cómo se verifica.** `test_embudo_manual_y_whatsapp` (seis confirmaciones por
atajo), `test_transiciones_invalidas_y_terminales`.

---

<a id="d25"></a>
## D25 · Volver desde un terminal exige motivo; quitar, solo antes de invitar

**El problema.** Los terminales (`rechazó`, `no contactable`, `no-show`) sacan a
la persona del embudo, pero la gente cambia de idea.

**La decisión.** `reingresar` vuelve a `invitado` y exige un motivo, que queda
en el evento. Y **quitar** a alguien del embudo solo se puede mientras es
`candidato`, es decir, antes de que exista cualquier contacto. Lo demás queda
registrado.

**Dónde vive.** `coloquio/embudo.py` (`reingresar`, `quitar_candidato`).

---

<a id="d26"></a>
## D26 · Un intento sin respuesta es un evento, no un estado

**El problema.** La SPEC §12 mide «intentos de contacto por confirmación, por
canal». Una llamada que nadie atiende no cambia el estado, pero es un intento.

**La decisión.** «↻ sin respuesta» registra un evento sin cambio de estado y
suma `intentos_manual`. Cada envío de WhatsApp suma `intentos_whatsapp`. Las
confirmaciones suman por el canal de la convocatoria.

**Alternativas descartadas.** *Un estado `no atendió`.* Agrega un estado que no
lleva a ningún lado y complica el grafo.

**Dónde vive.** `coloquio/embudo.py` (`registrar_intento`), `coloquio/tablero.py`.

---

<a id="d27"></a>
## D27 · El estado de la sesión se deriva del embudo

**El problema.** `planificada → convocando → confirmada` depende de lo que pasa
en el embudo, y un estado manual se desactualiza.

**La decisión.** La primera invitación pasa la sesión a `convocando`. Llegar al
cupo de confirmados la pasa a `confirmada`, y registra `cupoConfirmadoEn`, que
da el tiempo de convocatoria. Si alguien se cae y ya no alcanza, **vuelve** a
`convocando`. `realizada` y `cancelada` son acciones explícitas.

**Dónde vive.** `coloquio/embudo.py` (`_paso`).

**Cómo se verifica.** `test_cupo_alcanzado_avisa`,
`test_baja_en_embudo_activo_dispara_reemplazo`.

---

# Bloque F · Sobre-reclutamiento y reemplazo

<a id="d28"></a>
## D28 · La meta de invitación es por segmento, y el supuesto se muestra

**El problema.** «Convocar doce para sentar ocho» es un supuesto sobre la tasa
de caída, y si no se ve no se puede corregir.

**La decisión.** La meta de invitación de cada cuota es `ceil(objetivo × ratio)`,
y la total, `ceil(cupo × ratio)`. El supuesto (`caída = 1 − 1/ratio`) se
muestra al armar, en la propuesta de invitación y en el embudo. Al cerrar se
registra el `ratioRealNecesario` (invitados / presentes), que con el tiempo
reemplaza a la intuición.

**Dónde vive.** `coloquio/modelo.py` (`meta_invitacion`), `coloquio/sesiones.py`,
`coloquio/cierre.py`.

**Cómo se verifica.** `test_meta_de_invitacion`.

---

<a id="d29"></a>
## D29 · La lista de invitación no se completa con cualquiera

**El problema.** Si la lista de espera no alcanza para un segmento, completar
la meta total con gente de otros segmentos da un número redondo y una cuota
rota.

**La decisión.** Una elección greedy sobre la lista de espera, que prioriza a
quien cubre los segmentos con más déficit y penaliza a quien suma a uno ya
cubierto. **Corta** cuando nadie aporta a un segmento con déficit, y devuelve
el déficit restante para que se amplíe la selección.

**Alternativas descartadas.** *Un solver.* `paneles` tiene uno para muestreo.
Para doce personas con dos o tres dimensiones, el greedy es explicable, que es
lo que el coordinador necesita.

**Dónde vive.** `coloquio/sesiones.py` (`proponer_invitacion`).

**Cómo se verifica.** `test_propuesta_de_invitacion_respeta_la_cuota`.

---

<a id="d30"></a>
## D30 · Restituir el segmento es coincidir en todas las dimensiones con cuota

**El problema.** R1.6 pide candidatos que «restituyen el segmento perdido», y
hay que definir qué es restituir.

**La decisión.** Coincidir con quien se fue en **todas** las dimensiones que
tienen cuota en esa sesión. Se busca primero en la lista de espera y, si no
alcanza, en el panel, con el mismo gate, la misma fatiga y la misma regla de un
estudio por persona. Los que no coinciden se muestran aparte, con la dimensión
que rompen.

**Alternativas descartadas.** *Coincidir en al menos una dimensión.* Deja
reemplazar a una mujer de 25-34 por un hombre de 25-34 y llamarlo reemplazo.

**Dónde vive.** `coloquio/reemplazo.py` (`proponer`).

**Cómo se verifica.** `test_reemplazo_restituye_el_segmento`.

---

<a id="d31"></a>
## D31 · Sin reemplazo hay tres salidas, y la elegida queda registrada

**El problema.** Cuando nadie restituye el segmento, el sistema podría proponer
lo más parecido. Eso es romper la cuota en silencio.

**La decisión.** Se informa explícitamente y se ofrecen las tres salidas de la
SPEC: **bajar el cupo** (también baja el objetivo de los segmentos afectados),
**correr la fecha**, o **aceptar la cuota incompleta**. La elegida queda en
`decisionesCuota` con usuario y hora. Usar igual un candidato que no restituye
exige `aceptarCuotaIncompleta` y se registra como `reemplazo_rompe_cuota`.

**Dónde vive.** `coloquio/reemplazo.py`.

**Cómo se verifica.** `test_sin_candidatos_lo_informa_y_registra_la_salida`,
`test_reemplazo_que_rompe_la_cuota_exige_aceptarlo`.

---

<a id="d32"></a>
## D32 · Una baja en un embudo activo deja el segmento, no la persona

**El problema.** Si alguien que aceptó se da de baja del panel, hay que sacarlo
del embudo (R1.11) y disparar el reemplazo (R1.6). Pero después del borrado su
id no puede quedar en COLOQUIO.

**La decisión.** La cascada deja en la sesión una **alerta de baja** con el
segmento perdido y el estado que tenía, sin id. El reemplazo acepta
`{alertaId}` además de `{idPersona}`.

**Dónde vive.** `coloquio/cascada.py`, `coloquio/reemplazo.py`.

**Cómo se verifica.** `test_baja_en_embudo_activo_dispara_reemplazo`.

---

# Bloque G · Canal de convocatoria

<a id="d33"></a>
## D33 · El canal es por persona, y el manual se construyó primero

**El problema.** A algunos se los llama y a otros se les escribe. Y el canal de
WhatsApp depende de plazos de Meta que nadie controla.

**La decisión.** El canal es una propiedad de cada convocatoria, y se cambia con
un selector en la fila. El canal manual es completo sin WhatsApp: contacto
auditado, guion con las variables del caso y el código de convocatoria, y
registro del resultado con un clic.

**Consecuencias.** La fase se puede entregar aunque Meta demore la aprobación de
las plantillas.

**Dónde vive.** `coloquio/canales.py`, `coloquio/embudo.py` (`cambiar_canal`).

---

<a id="d34"></a>
## D34 · La invitación provoca respuesta; lo que sigue va en la ventana gratis

**El problema.** Meta cobra por plantilla entregada. Cuando la persona responde,
se abre una ventana de servicio de 24 h en la que los mensajes no se cobran
(SPEC §9).

**La decisión.** La plantilla de invitación lleva dos botones de respuesta
rápida. La respuesta abre la ventana (`ventanaServicioHasta`). La confirmación y
el recordatorio **salen como mensaje libre** si la ventana está abierta, y como
plantilla solo si está cerrada. Se cuentan por separado las plantillas pagas y
los mensajes gratis.

**Dónde vive.** `coloquio/canales.py`, `coloquio/whatsapp.py`.

**Cómo se verifica.** En `test_embudo_manual_y_whatsapp`: la confirmación dentro
de la ventana sale con `pago: false`.

---

<a id="d35"></a>
## D35 · El botón de WhatsApp lleva el `id_persona`, no el teléfono

**El problema.** El webhook tiene que saber a qué convocatoria corresponde una
respuesta, y el único dato que Meta trae del remitente es su número, que es PII.

**La decisión.** Cada botón lleva el payload `c1|<sesionId>|<idPersona>|si|no`.
El webhook ubica la convocatoria por ahí, y **no lee** el número ni el nombre de
perfil. Para las respuestas de texto y los estados de entrega se guarda
`mensajeWa/{wamid}` → sesión e id. El `wamid` no es PII, y entra al índice de
borrado.

El webhook es público y se autentica con la firma `X-Hub-Signature-256`.

**Dónde vive.** `coloquio/whatsapp.py`, `coloquio/canales.py`, `functions/main.py`.

**Cómo se verifica.** `test_webhook_no_expone_remitente`,
`test_firma_del_webhook`, y en `test_embudo_manual_y_whatsapp`, que ni el número
ni el nombre de perfil aparezcan en el store.

---

<a id="d36"></a>
## D36 · Si WhatsApp falla, la convocatoria pasa a manual y no pierde su estado

**El problema.** Plantilla rechazada, número bloqueado, entrega fallida,
credenciales sin cargar.

**La decisión.** La convocatoria pasa a canal `manual` con `degradacion:
{motivo, hora}` y un evento. **El estado no cambia.** El embudo lo marca con
«WA falló → manual». Pasa igual si la bóveda rechaza el contacto.

**Dónde vive.** `coloquio/canales.py` (`_degradar`).

**Cómo se verifica.** `test_embudo_manual_y_whatsapp` cubre la entrega fallida y
la plantilla rechazada.

---

# Bloque H · El día de la sesión

<a id="d37"></a>
## D37 · En la puerta, la identidad es un código de convocatoria

**El problema.** R1.7 pide verificar la identidad en la recepción. Pero COLOQUIO
no tiene nombres: no hay contra qué comparar.

**La decisión.** Cada convocado tiene un **código de convocatoria**: los seis
primeros caracteres de su `id_persona`. Se le da al invitarlo (el guion y los
mensajes de WhatsApp lo incluyen) y lo dice al llegar. La recepción busca por
código. Un código que no es de la sesión se muestra con «no dejes pasar a nadie
sin verificar». Si hace falta más, el coordinador puede pedir el celular a la
bóveda, que queda auditado.

**Alternativas descartadas.** *Traer el nombre de la bóveda para la recepción.*
La superficie de la Fase 5 no lo expone, a propósito.

**Consecuencias.** El código es un fragmento del seudónimo. Sin la bóveda no
identifica a nadie, pero igual se borra con la persona (D42).

**Dónde vive.** `coloquio/util.py` (`codigo_de`), `coloquio/recepcion.py`.

**Cómo se verifica.** `test_recepcion_y_cierre` (ocho llegadas por código).

---

<a id="d38"></a>
## D38 · El compromiso de incentivo nace con la asistencia

**El problema.** La SPEC ubica el compromiso de incentivo al cerrar la sesión,
pero el regalo se entrega en la puerta, antes de cerrar.

**La decisión.** El check-in crea la asistencia **y** el compromiso, con el
regalo por defecto de la sesión, en la misma transacción. El cierre completa los
que falten. Se puede reasignar el regalo mientras esté `comprometido`.

**Dónde vive.** `coloquio/recepcion.py`, `coloquio/incentivos.py`, `coloquio/cierre.py`.

---

<a id="d39"></a>
## D39 · El cierre es una sola transacción

**El problema.** Cerrar toca los no-show, la participación de cada presente, los
incentivos, las métricas de la sesión y el valor del estudio. Un cierre a medias
deja la fatiga y el historial mal.

**La decisión.** Todo en una transacción (unos 60 documentos para un grupo de
12, lejos del límite de 500). Quien estaba confirmado y no llegó pasa a
`no-show`. La tasa de show se mide sobre **los que llegaron confirmados al
día** (presentes + no-show). Cerrar sin asistencias exige confirmarlo.

**Dónde vive.** `coloquio/cierre.py`.

**Cómo se verifica.** `test_recepcion_y_cierre`.

---

<a id="d40"></a>
## D40 · Cancelar es un estado propio, con compensación explícita

**El problema.** Una sesión cancelada con gente confirmada tiene incentivos que
se resuelven a mano (caso borde de la SPEC).

**La decisión.** Estado `cancelada` con motivo y resolución, y la opción de
compensar a quienes habían aceptado o confirmado. Esa opción crea compromisos
con `motivoCompromiso: cancelacion`. Todo el texto pasa por el control de PII.

**Dónde vive.** `coloquio/cierre.py` (`cancelar`).

---

# Bloque I · Cascada de baja

<a id="d41"></a>
## D41 · Borrar, verificar, y recién después confirmar

**El problema.** La bóveda confía en la confirmación: un pendiente confirmado
sale del tablero del DPO. Confirmar un borrado que no ocurrió es un
incumplimiento que nadie ve.

**La decisión.** Por cada pendiente:

1. el índice (`participacionCuali`) **más** consultas de grupo de colección por
   `idPersona`, que son la red de seguridad si el índice se desincronizó;
2. los borrados, sesión por sesión, en transacción, ajustando contadores;
3. una **verificación independiente** (`rastro()`) de que no quedó nada;
4. recién entonces `confirmar_borrado()`. Ante cualquier error,
   `reportar_error_de_borrado()` y el pendiente queda abierto.

**Consecuencias.** Hasta que se construyan los índices de grupo de colección
después del deploy, la cascada falla y reporta. Es el comportamiento correcto.

**Dónde vive.** `coloquio/cascada.py`, `firestore.indexes.json`.

**Cómo se verifica.** `test_baja_en_cascada_borra_todo_y_confirma`,
`test_borrado_fallido_no_se_confirma`.

---

<a id="d42"></a>
## D42 · Con la persona se va su código y toda referencia cruzada

**El problema.** Borrar sus documentos no alcanza. El id aparece también en la
convocatoria de quien la reemplazó (`esReemplazoDe`, `reemplazadoPor`), en
`mensajeWa`, y su código en las decisiones de cuota de la sesión.

**La decisión.** Todo eso se limpia. Las referencias se reemplazan por `baja` o
`BAJA`, y los mensajes se borran. La verificación busca también ahí.

**Dónde vive.** `coloquio/cascada.py` (`REFERENCIAS`, `_borrar_de_sesion`).

**Cómo se verifica.** `test_baja_en_cascada_borra_todo_y_confirma` busca el id
**y** el código en todo el store.

---

<a id="d43"></a>
## D43 · Qué alcances de baja borran en la Fase 1

**El problema.** La bóveda genera pendientes por baja total y por retiro de una
finalidad. COLOQUIO declara cinco finalidades (contacto, grabación, moderación
automatizada, uso semántico cuali, difusión), y en la Fase 1 solo tiene datos
por la primera.

**La decisión.** Baja total y retiro de `contacto_participacion` borran todo:
los datos de COLOQUIO existen porque la persona participó. Los retiros de las
otras finalidades se confirman sin borrar, porque en esta fase no hay datos que
dependan de ellas, y se cuentan aparte (`sinDatosEnFase1`).

> **A revisar en la Fase 2**, cuando haya grabaciones: un retiro de
> `grabacion_av` va a tener qué borrar.

**Dónde vive.** `coloquio/cascada.py` (`ALCANCES_QUE_BORRAN`).

---

# Bloque J · La convocatoria declarada (R5.2.a)

<a id="d44"></a>
## D44 · La convocatoria se declara en la bóveda al invitar, antes de la transacción

**El problema.** `contacto_para_convocatoria()` exige una convocatoria activa en
el sistema que llama. La `0014` la verificaba solo contra las encuestas de
`paneles`, y rechazaba a COLOQUIO. Desde la `boveda/0016` (R5.2.a) el consumidor
la **declara** con `declarar_convocatoria(id_persona, referencia, vence_en)`. La
función reaplica el gate de consentimiento, tiene un tope de 60 días y, con la
misma referencia, actualiza en vez de duplicar.

**La decisión.** Se declara en cada paso que deja a alguien **invitado**:

- la lista de invitación, el botón de la fila, el reemplazo y la invitación por
  WhatsApp (`candidato → invitado`);
- el **reingreso** desde un terminal, porque vuelve a estar invitado;
- la **reprogramación** de la sesión, desde Armado o desde «correr la fecha».
  En ese caso se redeclara a todos los que siguen en curso, con la misma
  referencia y la fecha nueva.

La referencia es el **id de sesión de COLOQUIO**. La declaración va **fuera de
la transacción de Firestore y antes de ella**. Si la bóveda la rechaza (retiró
el consentimiento) o no responde, la persona queda como candidato. En la lista
de invitación, los rechazados se informan uno por uno (`noDeclarados`) y el
resto se invita igual.

**Alternativas descartadas.**

- *Declarar después de la transacción.* Si la bóveda fallaba, quedaba en
  COLOQUIO alguien «invitado» cuyo contacto la bóveda no iba a entregar, y el
  coordinador se enteraba al intentar llamarlo.
- *Declarar adentro de la transacción.* Firestore puede reintentarla (D22), y la
  bóveda no participa de ella.
- *Declarar al leer el contacto.* Haría de «leer un contacto» la forma de
  convocar, y el contrato pide lo contrario: el motivo va primero. Leer el
  contacto de un candidato que nunca se invitó ahora se rechaza del lado de
  COLOQUIO.

**Consecuencias.** Si la transacción falla después de declarar (una carrera),
queda una declaración sin invitación. No abre nada que no estuviera ya: la
persona consintió y está en la sesión. Vence sola y la bóveda la purga. Reprogramar
no falla si la bóveda no responde, porque la reprogramación ya ocurrió en
COLOQUIO: la pantalla lo avisa, y D47 lo repone.

**Dónde vive.** `coloquio/declaracion.py`, y sus llamadas en `embudo.py`
(`transicionar`, `reingresar`, `invitar_propuestos`), `canales.py`,
`reemplazo.py` y `sesiones.py` (`editar`).

**Cómo se verifica.** `tests/test_declaracion.py`, en particular
`test_se_declara_antes_de_la_transaccion` (con la bóveda caída nadie queda
invitado), `test_si_la_boveda_rechaza_no_queda_invitado`,
`test_reprogramar_actualiza_no_duplica` y
`test_el_candidato_no_invitado_no_tiene_contacto`.

---

<a id="d46"></a>
## D46 · El vencimiento es la sesión más dos días, con el tope de la bóveda

**El problema.** El contrato pide `fecha_sesion + 2 días`, y la bóveda rechaza
más de 60. Una sesión que se arma con más de 58 días de anticipación rompe la
cuenta.

**La decisión.** `min(fecha + 2 días, ahora + 59 días)`, con un día de margen
bajo el tope para no rozarlo por diferencias de reloj entre la función y la
base. Si la sesión ya pasó hace más de dos días, no se declara, y el error lo
explica.

**Alternativas descartadas.** *Dejar que la bóveda rechace.* No se podría
convocar para una sesión lejana hasta que falten menos de 58 días, sin ningún
motivo de privacidad para esa espera.

**Consecuencias.** En una sesión muy lejana, la declaración vence antes que la
sesión. Se renueva al reprogramar o al leer un contacto (D47).

**Dónde vive.** `coloquio/declaracion.py` (`vencimiento`).

**Cómo se verifica.** `test_tope_de_sesenta_dias`,
`test_vencimiento_rechaza_sesiones_pasadas`.

---

<a id="d47"></a>
## D47 · Si la declaración venció, se repone al leer el contacto, una vez

**El problema.** Una declaración puede vencer mientras la convocatoria sigue
viva: una sesión lejana (D46), una reprogramación con la bóveda caída, o una
invitación hecha antes de R5.2.a.

**La decisión.** Si la bóveda rechaza la lectura de contacto de alguien **en
curso** (invitado, contactado, aceptó o confirmado), COLOQUIO vuelve a declarar
y reintenta **una sola vez**. Si la causa era el consentimiento, la declaración
también falla, y ese es el error que se muestra.

**Alternativas descartadas.** *Distinguir la causa por el texto del error de la
bóveda.* Sería frágil. Redeclarar es idempotente, y la declaración ya separa el
caso del consentimiento por su cuenta.

**Consecuencias.** `p_actor` sigue siendo siempre el email del usuario humano
en las dos lecturas (D8).

**Dónde vive.** `coloquio/canales.py` (`leer_contacto`).

**Cómo se verifica.** `test_declaracion_vencida_se_repone_al_leer_el_contacto`.

---

# Bloque K · Lo que quedó abierto

<a id="d45"></a>
## D45 · Los umbrales de fatiga son un punto de partida, no una definición

**El problema.** La ventana y la categorización del filtro anti-panelista
profesional son una definición metodológica de los investigadores (SPEC §10,
bloqueante de producto), y no estaba tomada.

**La decisión.** Valores por defecto editables desde Configuración: 180 días
por categoría, una participación excluye, y un tope global de 3 en 365 días.
Nueve categorías iniciales, también editables. La interfaz dice que son un
punto de partida.

**Consecuencias.** Cuando los investigadores fijen la regla se cambia desde la
pantalla, sin deploy. Si la categoría de un estudio se renombra con
participaciones ya registradas, se rompe la continuidad del filtro. La pantalla
lo advierte.

**Dónde vive.** `coloquio/modelo.py` (`FATIGA_POR_DEFECTO`,
`CATEGORIAS_POR_DEFECTO`), `coloquio/configuracion.py`.
