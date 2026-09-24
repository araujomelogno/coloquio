# SPEC — COLOQUIO · Fase 0: la bóveda como plataforma compartida

**Sistema:** COLOQUIO · investigación cualitativa · Equipos Consultores
**PRD de referencia:** `PRD_coloquio_detallado.md` (Fase 0)
**Dónde se implementa:** repo `paneles` — migraciones `db/boveda/0007…0009`, `db/semantica/0004`, y los cambios mínimos en `panel_api` para que la aplicación siga usando lo mismo que expone a terceros
**Estado:** Borrador para desarrollo · primer sprint del proyecto
**Precondición:** Fases 1 a 3 de `paneles` desplegadas (es el estado actual)
**Última actualización:** 2026-09-22

---

## 1. Problem Statement

`paneles` fue construido con un supuesto que hoy deja de ser cierto: que hay **un solo** programa hablándole a la bóveda. Bajo ese supuesto fue razonable que las tres invariantes de cumplimiento vivieran en Python. El gate de consentimiento es `consentimiento.exigir()`. El umbral de fatiga es una lista de constantes y un `if` en `muestreo._motivo_de_exclusion()`. La prohibición de PII del lado semántico es `pii.validar_sin_pii()` más una auditoría, `semantica.auditar_columnas()`, que solo encuentra el problema si alguien la ejecuta.

COLOQUIO va a ser el segundo programa. Va a consultar candidatos, leer contactos para convocar y escribir verbatims. Si se conecta a la bóveda tal como está hoy, las tres invariantes pasan a ser **promesas repetidas en dos bases de código**, y la primera que se rompa lo va a hacer en silencio: una persona sin consentimiento vigente convocada a un focus group, o una baja que deja la grabación de esa persona viva en Cloud Storage porque la cascada de `bajas.py` no sabe que COLOQUIO existe.

El costo de no resolverlo no es deuda técnica. Es que el derecho de supresión deje de cumplirse sin que nadie se entere, en un sistema que guarda PII identificada de forma permanente bajo URCDP. Y por separado: el modelo de consentimiento actual **no admite** las finalidades que el cualitativo necesita —grabar audio y video, conducir la sesión automáticamente, indexar el verbatim, difundirlo al cliente—, porque el dominio está cerrado con un `check (finalidad in ('contacto_participacion','uso_semantico'))` en dos tablas. Hoy no se puede ni registrar el consentimiento de grabación, aunque alguien lo firme.

## 2. Goals

- **Que la bóveda haga valer sus propias reglas.** Que un consumidor nuevo no pueda obtener una persona sin consentimiento vigente aunque escriba la consulta a mano y aunque su código tenga un bug.
- **Que la baja llegue a todos lados.** Que el retiro de consentimiento arrastre artefactos de sistemas que `paneles` no conoce, y que quede rastro verificable de lo que se borró y de lo que falta borrar.
- **Que el consentimiento deje de ser un enum en el DDL.** Que agregar una finalidad sea cargar una fila, no migrar dos tablas, y que el cualitativo tenga las cuatro que le faltan.
- **Que el acceso sea mínimo y auditado.** Que COLOQUIO pueda leer lo que necesita —y nada más— y que cada lectura de dato de contacto quede registrada con quién la pidió y para qué.
- **Que nada de lo anterior rompa `paneles`.** Las 409 pruebas existentes siguen verdes y la aplicación sigue funcionando durante y después de la migración.

## 3. Non-Goals

- **No se refactoriza `panel_api`.** Se lo apunta a las vistas nuevas donde corresponde para que no queden dos implementaciones del mismo gate, y nada más. Reescribir el muestreo no es de esta fase.
- **No se define la política de retención de medios.** Es una definición legal que bloquea la Fase 2 de COLOQUIO, no ésta. Acá solo se deja el mecanismo por donde va a pasar el borrado.
- **No se redactan los textos de consentimiento.** Esta fase habilita el dominio y el versionado; los cuerpos los escribe quien corresponda. Un texto faltante bloquea *usar* la finalidad, no implementarla.
- **No se construye nada de COLOQUIO.** Ni esquema cuali, ni API, ni interfaz. Esta fase termina con la bóveda lista para que COLOQUIO empiece, y con un cliente de prueba que demuestra que está lista.
- **No se resuelve la fatiga unificada entre cuali y cuanti.** Queda como pregunta abierta del PRD. Acá se exponen los hechos de fatiga; quién los suma es otra discusión.
- **No se migra el borrado semántico existente al mecanismo nuevo.** El `persona_borrada.borrado_semantica_en` que hoy usa `bajas.py` queda como está. El mecanismo nuevo es aditivo y convive.

## 4. User Stories

**DPO / cumplimiento**

- Como DPO, quiero que la baja de una persona arrastre sus grabaciones y transcripciones aunque las haya creado un sistema que `paneles` no conoce, para que el derecho de supresión se cumpla de verdad y no por convención entre equipos.
- Como DPO, quiero poder listar en cualquier momento las bajas cuyo borrado todavía no confirmó algún sistema, para saber si tengo un incumplimiento abierto en vez de suponer que todo salió bien.
- Como DPO, quiero poder registrar el consentimiento de grabación audiovisual y el de difusión de verbatim como finalidades separadas, con su texto versionado, para que el cualitativo tenga base legal antes de encender una cámara.
- Como DPO, quiero ver quién accedió al dato de contacto de una persona y con qué motivo, incluido cuando el que accedió fue otro sistema.

**Responsable de la plataforma**

- Como responsable de la plataforma, quiero que un sistema consumidor no pueda escribir sobre `persona`, `consentimiento` ni `participacion`, para que el acceso directo a la base no sea un agujero abierto.
- Como responsable de la plataforma, quiero que la consulta de candidatos pase obligatoriamente por una superficie que ya aplica el gate, para no depender de que cada consumidor se acuerde de aplicarlo.
- Como responsable de la plataforma, quiero saber qué sistema originó cada escritura, para poder investigar un dato raro sin adivinar.

**Desarrollador de COLOQUIO**

- Como desarrollador de COLOQUIO, quiero una superficie de lectura estable y documentada contra la bóveda, para no acoplarme a tablas que `paneles` puede cambiar en su próxima migración.
- Como desarrollador de COLOQUIO, quiero obtener el dato de contacto de alguien que voy a convocar sin tener permiso de leer la tabla `persona` entera.
- Como desarrollador de COLOQUIO, quiero un contrato claro de qué tengo que borrar cuando me avisan de una baja, y cómo confirmo que lo hice.

**Responsable de panel (no debe notar nada)**

- Como responsable de panel, quiero que el muestreo, la composición y las bajas sigan comportándose exactamente igual después de la migración.

**Casos borde**

- Persona con consentimiento otorgado y después retirado → no aparece en la superficie de convocables, aunque la fila de otorgamiento siga existiendo (el historial no se pisa).
- Persona en estado `pendiente_consentimiento` (creada por ingesta sin base legal) → nunca aparece, para ninguna finalidad.
- Persona ya dada de baja, cuya lápida existe pero cuyo `id_persona` alguien todavía tiene guardado → la superficie no devuelve nada y la función de contacto falla explícitamente.
- Consumidor que pide contacto de alguien que no tiene convocatoria activa → se rechaza.
- Borrado en un consumidor que falla → la baja en la bóveda se completa igual, queda pendiente y reintentable. **Nunca se demora el retiro esperando a un consumidor.**
- Finalidad nueva sin texto activo cargado → se puede definir, no se puede otorgar.
- Consumidor dado de alta en el registro de sistemas *después* de una baja ya ocurrida → no se le puede exigir retroactivamente; el alta deja constancia de desde cuándo es responsable.

---

## 5. Requirements

### Must-Have (P0)

---

#### R0.1 — Superficie de convocables: el gate de consentimiento, en la base

El gate deja de ser `consentimiento.exigir()` y pasa a ser la única puerta de lectura de candidatos.

**Decisión de diseño, y es la que ordena todo el requisito: se separa el *gate legal* de la *política de negocio*.**

El consentimiento vigente es un **invariante legal**: no es negociable, no admite parámetros y no puede quedar del lado del consumidor. Va en una vista de la que es imposible salirse.

La fatiga es una **política de negocio**: sus umbrales son por panel (`umbral_fatiga`), su ventana es un parámetro, y en el código actual el cálculo excluye la encuesta en curso (`pa.encuesta_id <> %s`), que es contexto del llamador y no se puede expresar en una vista sin parámetros. Además, COLOQUIO tiene su propia noción de fatiga cualitativa (R1.3 del PRD) que no es ésta. Así que la fatiga se expone como **hechos**, y cada consumidor aplica el umbral que le corresponde.

**`v_persona_convocable`** — una fila por `(id_persona, finalidad)` de toda persona que hoy puede ser usada para esa finalidad.

- Incluye únicamente personas con `consentimiento.estado = 'vigente'` para esa finalidad.
- Excluye a quien tenga `persona.estado <> 'activa'` (hoy: `pendiente_consentimiento`).
- Excluye a quien tenga lápida en `persona_borrada`.
- Expone `id_persona`, `finalidad`, y los segmentadores de `v_demografia` (`sexo`, `localidad`, `tramo_etario`, `edad`).
- **No expone** `nombre`, `documento`, `email`, `celular`, `contacto`, `observaciones` ni `fecha_nacimiento`.

**`v_fatiga_panelista`** — una fila por `(id_persona, panel_id)` con los hechos: convocatorias en ventana, convocatorias acumuladas, fecha de última convocatoria, respondidas. Cuenta **solo** `participacion.origen = 'convocatoria'`, con el mismo criterio que hoy usa `muestreo._candidatos()`: la fatiga mide cuánto se molestó a alguien, no cuántas veces respondió.

**Criterios de aceptación**

- Dada una persona con consentimiento vigente para `contacto_participacion`, cuando se consulta `v_persona_convocable` con esa finalidad, entonces aparece.
- Dada una persona cuyo consentimiento para esa finalidad está `retirado`, entonces **no aparece**, bajo ninguna combinación de filtros, aunque su fila de otorgamiento siga en `consentimiento`.
- Dada una persona con `estado = 'pendiente_consentimiento'`, entonces no aparece para ninguna finalidad.
- Dada una persona con lápida en `persona_borrada`, entonces no aparece.
- Dado un `select *` sobre la vista, entonces el conjunto de columnas no interseca con `pii.CAMPOS_PII`.
- Dada una persona con tres convocatorias en los últimos noventa días y dos participaciones de origen `importacion`, entonces `v_fatiga_panelista` informa tres, no cinco.
- **Prueba de no regresión:** para un panel y una encuesta dados, el conjunto de elegibles que devuelve `muestreo` apoyado en las vistas nuevas es idéntico al que devolvía antes, sobre el mismo set de prueba.

---

#### R0.2 — Contacto acotado y auditado: una función, no una vista

Convocar exige leer un canal de contacto, que es PII. Y esa lectura tiene que quedar auditada — cosa que **una vista no puede hacer**, porque no tiene efectos. Por eso el contacto se sirve por función.

La tabla de auditoría ya existe: `reidentificacion`, con `motivo` que contempla `'convocatoria'`. Esta fase la reutiliza y le agrega de qué sistema vino.

**`contacto_para_convocatoria(id_persona uuid, canal text, motivo text, actor text, sistema text)`**, `security definer`.

- Devuelve **un solo canal** (`email` o `celular`), el pedido, y nada más. No devuelve nombre, ni documento, ni la fila.
- Verifica consentimiento vigente de `contacto_participacion` antes de devolver nada.
- Exige que la persona tenga una convocatoria activa en el sistema que llama (ver R0.4: el registro de consumidores declara cómo se verifica eso para cada uno).
- Escribe una fila en `reidentificacion` en la misma transacción en que devuelve el dato. Si la auditoría no se puede escribir, no se devuelve el dato.

**Criterios de aceptación**

- Dado un `id_persona` con consentimiento vigente y convocatoria activa, cuando se pide su celular, entonces se devuelve el celular y aparece una fila nueva en `reidentificacion` con el `id_persona`, el actor, el motivo y el sistema.
- Dado un `id_persona` sin consentimiento vigente, entonces la función falla y **no** se registra acceso a un dato que no se entregó.
- Dado un `id_persona` sin convocatoria activa para el sistema que llama, entonces la función falla.
- Dado un rol de consumidor, cuando intenta `select email from persona`, entonces la base lo rechaza (R0.4). La función es la única vía.
- Dado un canal que no existe para esa persona, entonces devuelve vacío explícito, no error, y registra el intento.

---

#### R0.3 — Cascada de baja extensible

Hoy `bajas.py` borra la PII, da de baja las membresías y llama al store semántico. El borrado semántico ya está bien resuelto: **no es transaccional, no bloquea la baja, y deja rastro para reintentar** — la lápida `persona_borrada` guarda `borrado_semantica_en` en null hasta que se confirma, y `pendientes_de_borrado_semantica()` las lista. Esta fase **generaliza ese patrón a N consumidores** en vez de inventar uno nuevo.

**`borrado_pendiente(id_persona, sistema, solicitado_en, confirmado_en, intentos, ultimo_error)`**, con PK `(id_persona, sistema)`.

- Dada una baja que dispara cascada, se inserta una fila por cada sistema **activo** del registro de R0.4, con `confirmado_en` en null.
- El consumidor consulta sus pendientes, borra lo suyo y confirma.
- `v_borrados_sin_confirmar` lista todo lo abierto, con antigüedad. Es el tablero del DPO.
- La lápida `persona_borrada` sigue siendo la prueba de que el retiro se atendió y **no se toca**: `bajas.py` conserva su columna y su flujo actual.

**Criterios de aceptación**

- Dada una baja total de una persona, cuando se completa en la bóveda, entonces existe una fila en `borrado_pendiente` por cada sistema activo registrado.
- Dado un consumidor que confirma su borrado, entonces su fila queda con `confirmado_en` y desaparece de `v_borrados_sin_confirmar`.
- Dado un consumidor caído, entonces la baja en la bóveda se completa igual y la fila queda pendiente con su contador de intentos. **La baja nunca espera al consumidor.**
- Dado un retiro parcial de `uso_semantico` (que hoy no borra la PII), entonces se generan pendientes solo para los sistemas cuyo alcance declarado incluye esa finalidad, no para todos.
- Dada una baja anterior al alta de un consumidor, entonces ese consumidor no recibe pendientes retroactivos, y su fecha de alta lo justifica.
- Las pruebas existentes de la cascada de `bajas.py` siguen pasando sin cambios.

---

#### R0.4 — Registro de sistemas y roles de Postgres con privilegio mínimo

**`sistema_consumidor(codigo, nombre, alta_en, activo, alcance_finalidades text[], contacto_tecnico)`** — quién consume la bóveda, desde cuándo, y de qué se hace responsable ante una baja. Es lo que hace determinista a R0.3.

**Roles.** Hoy la aplicación se conecta con un rol que es dueño de las tablas. Se agrega:

- `coloquio_app`: `select` sobre `v_persona_convocable`, `v_fatiga_panelista` y las vistas de catálogo; `execute` sobre `contacto_para_convocatoria` y las funciones de confirmación de borrado; `select`/`update` sobre sus propias filas de `borrado_pendiente`. **Cero privilegio sobre `persona`, `consentimiento`, `participacion`, `membresia` y `encuesta`.**
- `plataforma_ro`: solo lectura de auditoría y de las vistas de cumplimiento, para el DPO y para los chequeos automáticos.

**Detalle de implementación que hay que hacer bien, porque de él depende que la vista sea realmente la única puerta:** las tablas ya tienen `row level security` **habilitada y sin políticas**, lo que para un rol que no es el dueño significa cero filas. Eso juega a favor. Y una vista en Postgres se ejecuta con los privilegios de **su dueño**, no del que la consulta, salvo que se cree con `security_invoker = true`. Por lo tanto: **las vistas de R0.1 se crean con el dueño actual y sin `security_invoker`**, y a `coloquio_app` no se le otorga nada sobre las tablas base. La vista pasa; la consulta directa no. Si alguien creara las vistas con `security_invoker = true`, devolverían cero filas y el requisito quedaría roto de una forma difícil de diagnosticar: va como comentario en la migración.

**Criterios de aceptación**

- Conectado como `coloquio_app`: `select from v_persona_convocable` funciona.
- Conectado como `coloquio_app`: `select from persona`, `insert into persona`, `update consentimiento` y `delete from participacion` fallan, todos, en la base.
- Conectado como `coloquio_app`: `select from consentimiento` falla, pero el efecto del gate se obtiene igual por la vista.
- Dado un sistema marcado como `activo = false`, entonces deja de recibir pendientes de borrado nuevos, y los que ya tenía siguen abiertos.
- Existe una prueba que enumera los privilegios efectivos del rol y falla si aparece uno que no está en la lista blanca. La lista blanca vive en el repo, no en la cabeza de alguien.

---

#### R0.5 — Prohibición de PII del lado semántico, con dientes

`auditar_columnas()` compara nombres de columna contra `pii.CAMPOS_PII` recorriendo `information_schema`. Es correcto, pero **solo detecta cuando alguien la ejecuta**. Con dos sistemas escribiendo, eso no alcanza.

Un `check` no sirve acá: la regla es sobre **nombres de columna**, no sobre valores. El mecanismo que corresponde es un **event trigger** en `ddl_command_end` que inspeccione `create table`, `alter table … add column` y `alter table … rename column`, y aborte si el nombre cae en la lista de PII, con la excepción ya prevista de `nombre` en `cuestionario` y `pregunta`.

**Hay una incógnita real de plataforma:** Cloud SQL restringe la creación de event triggers a roles con privilegio de superusuario, y hay que confirmar si el rol administrativo disponible los permite (ver §11). Por eso el requisito tiene dos niveles y el primero es el que se entrega sí o sí:

- **P0 — gate de despliegue.** `scripts/verificar_esquema.py` incorpora el chequeo de PII y sale con código distinto de cero si encuentra una columna prohibida. Se corre en CI sobre el esquema de migraciones **y** contra la base antes de cada deploy. Una columna con nombre de PII del lado semántico impide desplegar.
- **P1 — event trigger.** Si la plataforma lo permite, el rechazo ocurre en el momento del `alter table`, y el gate de despliegue queda como segunda línea.

Y la lista de PII deja de estar solo en Python: se materializa en la base como tabla de catálogo, de modo que el chequeo del lado semántico y el de la bóveda usen la misma fuente. Hoy `pii.CAMPOS_PII` es un `frozenset` en el repo y el chequeo se hace contra `information_schema` desde la aplicación; el día que COLOQUIO escriba embeddings va a necesitar la misma lista sin importar el módulo de Python.

**Criterios de aceptación**

- Dado un intento de agregar `email` a una tabla del store semántico, entonces el chequeo de esquema falla y el deploy no procede (P0); y si el event trigger está activo, el `alter table` falla en el momento (P1).
- Dado `nombre` en `cuestionario` o en `pregunta`, entonces no se reporta: sigue siendo la excepción legítima.
- Dado el store semántico actual tal como está hoy, entonces el chequeo pasa limpio. Si no pasa, hay un hallazgo previo que reportar antes de seguir.
- La lista de campos PII es una sola y está en la base; `pii.CAMPOS_PII` la lee o la espeja, y existe una prueba que falla si divergen.

---

#### R0.6 — Auditoría con origen

Toda escritura auditada registra qué sistema la originó. Hoy `usuario_auditoria` y `reidentificacion` guardan `actor_uid` y `actor_email`, que asumen una persona logueada en la app de administración. Con dos sistemas eso ya no identifica al autor.

- `reidentificacion` y `usuario_auditoria` incorporan `sistema text` con FK a `sistema_consumidor`, con default `'paneles'` para no romper lo existente.
- El valor lo fija la conexión, no el llamador: se deriva del rol de base de datos, de modo que un consumidor no pueda declararse otro.

**Criterios de aceptación**

- Dada una lectura de contacto hecha por COLOQUIO, entonces la fila de `reidentificacion` dice `coloquio`.
- Dada una acción de la app de administración, entonces dice `paneles`, y las filas históricas también.
- Dado un intento de pasar un `sistema` distinto del que corresponde al rol conectado, entonces se ignora el valor pasado y se registra el real.

---

#### R0.7 — Reformulación del modelo de consentimiento

Es la mitad legal de la fase y la que desbloquea todo el cualitativo.

**7.a — El dominio de finalidades pasa de `check` a catálogo.**

Hoy `consentimiento.finalidad` y `texto_consentimiento.finalidad` tienen cada una un `check (finalidad in ('contacto_participacion','uso_semantico'))`. Agregar una finalidad significa migrar dos tablas; y ya sabemos que van a ser más de cuatro con el tiempo (video, paneles de terceros, transferencias). Se reemplaza por:

**`finalidad_consentimiento(codigo, descripcion, requiere_texto, ambito, activa)`**, con FK desde `consentimiento.finalidad` y desde `texto_consentimiento.finalidad`.

Sigue siendo la base la que rechaza una finalidad inventada — cambia el mecanismo, no la garantía. `inscripcion.finalidades` es un `text[]` y no admite FK: se valida con trigger contra el catálogo.

**7.b — Las cuatro finalidades del cualitativo.**

| Código | Qué habilita | Ámbito |
|---|---|---|
| `grabacion_av` | Grabar audio y video de la sesión | Por estudio/sesión |
| `moderacion_automatizada` | Que la sesión la conduzca un sistema | Por estudio/sesión |
| `uso_semantico_cuali` | Indexar el verbatim despersonalizado en el corpus consultable entre estudios | Persona |
| `difusion_verbatim` | Entregar al cliente un clip o cita identificable | Por estudio/sesión |

`uso_semantico_cuali` es **distinta** de `uso_semantico`: una autoriza indexar respuestas de encuesta, la otra lo que alguien dijo hablando. Mezclarlas sería exactamente el error de limitación de finalidad que el diseño original evitó al separar `contacto_participacion` de `uso_semantico`.

`difusion_verbatim` es la más delicada de las cuatro y merece su propia fila porque **es la única en la que el dato sale de Equipos**. Grabar es tratamiento interno; entregarle al cliente el video de la cara de alguien diciendo una frase es otra cosa.

**7.c — Consentimiento con alcance de estudio.**

`consentimiento` tiene hoy un `panel_id` nullable: el consentimiento puede ser a nivel persona o a nivel panel. El cualitativo necesita un tercer alcance: **por estudio**. Que alguien haya aceptado que lo graben en un grupo de marzo no autoriza a grabarlo en uno de agosto.

Se agrega `ref_estudio uuid` nullable a `consentimiento`, alineado con el `ref_estudio` que ya comparten `encuesta` (bóveda) y `cuestionario` (semántico). El catálogo declara qué ámbito corresponde a cada finalidad y la base lo hace valer: una finalidad de ámbito estudio sin `ref_estudio` se rechaza; una de ámbito persona con `ref_estudio` también.

**7.d — Sin texto activo no hay otorgamiento.**

`texto_consentimiento` ya existe con `(finalidad, version, cuerpo, activo)`. Se hace valer: otorgar una finalidad `requiere_texto` sin una versión activa cargada se rechaza en la base. Es lo que convierte al consentimiento en demostrable y no en una fila con una cadena escrita a mano.

**Criterios de aceptación**

- Las cuatro finalidades nuevas se pueden otorgar, consultar y retirar, y cada una aparece en `v_persona_convocable` bajo su propio código.
- Una finalidad que no está en el catálogo se rechaza **en la base**, no en Python.
- Una finalidad activa sin texto activo no se puede otorgar; el error dice cuál falta.
- `grabacion_av` otorgada para un `ref_estudio` **no** habilita otro `ref_estudio`.
- `uso_semantico_cuali` no se satisface con `uso_semantico` vigente, ni al revés.
- Retirar `difusion_verbatim` deja la finalidad no vigente de inmediato y genera pendientes de borrado solo para los sistemas cuyo alcance la incluye.
- Las filas de consentimiento existentes quedan válidas sin tocarlas, y el alta actual sigue funcionando con su default.
- Las 409 pruebas existentes pasan. Las que verifican el rechazo de una finalidad desconocida siguen verdes, ahora por FK.

---

#### R0.8 — Cliente de verificación

La fase no termina cuando las migraciones aplican. Termina cuando algo que no es `paneles` demuestra que la bóveda se defiende sola.

Un script de verificación se conecta **con el rol `coloquio_app`** y ejecuta la batería completa: lee convocables, intenta leer `persona` y falla, pide un contacto legítimo y verifica que quedó auditado, pide un contacto de alguien sin consentimiento y falla, simula una baja y verifica que le llegó el pendiente, lo confirma y verifica que se cerró.

Es el sustituto honesto de "lo revisamos": si el script pasa, la bóveda está lista para COLOQUIO; si no pasa, no lo está.

**Criterios de aceptación**

- El script corre contra el cluster de pruebas con `scripts/pg_pruebas.sh`, igual que el resto de la suite.
- Falla si cualquier privilegio de más está otorgado.
- Queda en el repo y corre en CI, de modo que una migración futura que abra un acceso de más rompa la build.

---

### Nice-to-Have (P1)

- **Event trigger de PII** del lado semántico (el nivel 2 de R0.5), sujeto a lo que permita Cloud SQL.
- **Vista de cumplimiento para el DPO**: una superficie única con bajas abiertas, consentimientos por finalidad, textos activos y accesos a contacto del último período. Hoy eso se arma a mano.
- **Notificación de baja por evento** (Pub/Sub) además del *polling* sobre `borrado_pendiente`. El *polling* alcanza para el volumen actual y no tiene modos de falla escondidos; el evento reduce la latencia del borrado. Primero el mecanismo confiable, después el rápido.
- **Métricas de latencia de borrado**: cuánto tarda cada sistema en confirmar, para poder fijar un SLA con dato en vez de con intuición.

### Future Considerations (P2)

- **Retención y purga por inactividad**, que es una pregunta abierta transversal del PRD de `paneles`. El mecanismo de R0.3 es el que la va a ejecutar cuando la política exista: conviene no cerrarle la puerta ahora.
- **Un tercer consumidor.** El registro de R0.4 y los roles están diseñados para que sumar uno sea una fila y un `grant`, no una migración. Si sumar el tercero obliga a rediseñar, esta fase salió mal.
- **Trazabilidad de la entrega**: poder responder "¿a qué cliente le entregamos un clip de esta persona, bajo qué versión de consentimiento?" cuando alguien retira `difusion_verbatim` después de que el clip ya salió. El modelo de 7.c lo hace posible; el registro de entregas es de la Fase 3 de COLOQUIO.
- **Bóveda como repo propio.** Hoy las migraciones viven en `paneles` porque ahí nacieron. Si la bóveda es plataforma, en algún momento sus migraciones dejan de ser de un consumidor. No ahora: mover el repo antes de tener el segundo consumidor andando es reorganizar sin evidencia.

---

## 6. Contratos

Lo que COLOQUIO puede tocar. **Todo lo que no está acá, no existe para COLOQUIO**, y la base lo hace cumplir.

**Lectura**

```
v_persona_convocable   (id_persona, finalidad, sexo, localidad, tramo_etario, edad)
v_fatiga_panelista     (id_persona, panel_id, recientes, totales, ultima_convocatoria, respondidas)
v_finalidad            (codigo, descripcion, requiere_texto, ambito, activa)
v_texto_consentimiento_activo (finalidad, version, cuerpo)
```

**Ejecución**

```
contacto_para_convocatoria(id_persona, canal, motivo, actor) -> text
otorgar_consentimiento(id_persona, finalidad, version_texto, ref_estudio) -> bigint
retirar_consentimiento(id_persona, finalidad, ref_estudio) -> void
mis_borrados_pendientes() -> setof (id_persona, solicitado_en, alcance)
confirmar_borrado(id_persona) -> void
reportar_error_de_borrado(id_persona, error) -> void
```

`sistema` no es parámetro de ninguna función: se deriva del rol conectado (R0.6).

**Prohibido y verificado por prueba:** cualquier acceso a `persona`, `consentimiento`, `participacion`, `membresia`, `encuesta`, `puntos_movimiento`, `canje`, `inscripcion`, `alta_en_revision`.

## 7. Migraciones y orden de despliegue

Cada paso es aditivo y deja el sistema funcionando. En ningún momento hay una ventana en la que `paneles` esté roto.

| # | Migración | Qué trae |
|---|---|---|
| `boveda/0007` | Catálogo de consentimiento | `finalidad_consentimiento` con las dos finalidades actuales sembradas; FK desde `consentimiento` y `texto_consentimiento`; se retiran los dos `check`. **Sin cambios de comportamiento.** |
| `boveda/0008` | Finalidades del cualitativo | Las cuatro filas nuevas; `consentimiento.ref_estudio`; validación de ámbito; exigencia de texto activo; trigger sobre `inscripcion.finalidades` |
| `boveda/0009` | Superficie y control de acceso | `v_persona_convocable`, `v_fatiga_panelista`, `contacto_para_convocatoria`, `sistema_consumidor`, `borrado_pendiente`, `v_borrados_sin_confirmar`, columna `sistema` en auditoría, roles y `grant` |
| `semantica/0004` | Catálogo de PII | Tabla de campos PII del lado semántico y, si la plataforma lo permite, el event trigger de R0.5 |

**Orden.** `0007` puede ir sola y sin riesgo: es puro refactor de dominio. `0008` depende de `0007`. `0009` es la que crea acceso externo y va última, porque hasta que exista no hay nada que proteger. `semantica/0004` es independiente y puede ir en paralelo.

**Después de las migraciones**, un cambio acotado en `panel_api`: que `muestreo` y `consentimiento` se apoyen en las vistas nuevas en vez de reimplementar el gate. Si ese cambio no se hace, quedan dos implementaciones de la misma regla y el problema que esta fase vino a resolver vuelve por la ventana.

**Actualizar** `scripts/verificar_esquema.py` para que conozca las migraciones nuevas, y `CLAUDE.md` para que diga que la bóveda tiene más de un consumidor y que las reglas se hacen valer en la base.

## 8. Dependencias

- **Bloqueante, legal:** los textos de las cuatro finalidades nuevas. Bloquean *otorgar*, no implementar: el trabajo técnico arranca sin ellos.
- **Bloqueante, ingeniería:** confirmar si el rol administrativo de Cloud SQL permite crear event triggers (decide si R0.5 entrega su nivel 2).
- **Bloqueante, producto:** definir el `alcance_finalidades` de COLOQUIO en `sistema_consumidor`, porque de eso depende qué bajas le llegan. Propuesta: las cuatro nuevas más `contacto_participacion`.
- **No bloqueante:** nada de COLOQUIO. Esta fase se hace entera sin que exista una línea del otro sistema.

## 9. Definition of Done

1. Las cuatro migraciones aplican en orden sobre una copia de producción, sin downtime.
2. **Las 409 pruebas existentes de `paneles` pasan sin modificar ninguna** por cambio de comportamiento. Si alguna hay que tocar, el motivo se documenta en `decisiones.md`.
3. `muestreo` apoyado en las vistas nuevas devuelve exactamente el mismo conjunto de elegibles que antes, sobre el mismo set de prueba.
4. El script de verificación de R0.8 pasa entero, conectado como `coloquio_app`.
5. Las cuatro finalidades nuevas se otorgan y retiran; la de ámbito estudio no cruza entre estudios.
6. Una baja de prueba genera pendientes, se confirma y se cierra; una baja con consumidor caído queda abierta, listada y reintentable.
7. El chequeo de PII del lado semántico corre en CI y bloquea el deploy ante una columna prohibida.
8. `decisiones.md` suma las decisiones de esta fase: por qué el gate es vista y la fatiga es hecho, por qué el contacto es función, por qué el catálogo reemplaza al `check`, y por qué las vistas no llevan `security_invoker`.

## 10. Success Metrics

**Leading**

- Privilegios efectivos de `coloquio_app` fuera de la lista blanca: **cero**, verificado por prueba en cada build.
- Caminos de acceso de COLOQUIO a la bóveda que no pasan por la superficie de §6: **cero**.
- Bajas de prueba con cascada completa verificada: **100%**.
- Columnas con nombre de PII del lado semántico: **cero**, verificado antes de cada deploy.

**Lagging**

- Tiempo medio de confirmación de borrado por consumidor, una vez COLOQUIO esté en producción. Es el número que convierte "la cascada anda" en un SLA.
- Bajas abiertas por más de N días: la métrica del DPO, y la única que representa un incumplimiento real si sube.
- Costo de sumar un tercer consumidor, medido en migraciones. El objetivo es cero: una fila y un `grant`.
- Implementaciones del gate de consentimiento en el repo: debe bajar de dos a una.

## 11. Riesgos y preguntas abiertas

- **[ingeniería, bloqueante]** ¿Permite Cloud SQL crear event triggers con el rol administrativo disponible? Decide si R0.5 llega al nivel 2 o se queda en el gate de despliegue. Se responde en una tarde, probando.
- **[ingeniería]** **La fatiga no es expresable como vista sin parámetros**, porque su cálculo actual excluye la encuesta en curso y sus umbrales son por panel. La decisión de esta spec —exponer hechos y dejar el umbral en el consumidor— mantiene la vista simple y es correcta para el gate legal, pero **deja la política de fatiga sin hacerse valer en la base**. Es una diferencia deliberada entre las dos reglas: el consentimiento es legal y no se negocia; la fatiga es negocio y admite criterios distintos por consumidor. Conviene que quede escrita como decisión y no descubrirla después como omisión.
- **[ingeniería]** El trigger de `inscripcion.finalidades` valida un `text[]` contra el catálogo. Es el punto más frágil de 7.a, porque es la única validación que no es una FK. Merece prueba propia.
- **[legal]** ¿`moderacion_automatizada` es una finalidad de tratamiento o un deber de información? Si es lo segundo, el modelo igual sirve, pero el texto y la consecuencia de no aceptarla cambian.
- **[legal]** ¿El consentimiento de grabación se otorga por estudio o por sesión? La spec modela por estudio (`ref_estudio`). Si tiene que ser por sesión, el campo alcanza igual pero el granulado del registro cambia y conviene saberlo antes de `0008`.
- **[producto]** La lectura de contacto queda auditada, lo que va a generar volumen en `reidentificacion` con COLOQUIO convocando a escala. Hay que decidir retención de esa auditoría antes de que crezca, no después.
- **[operaciones]** El registro de consumidores es una tabla, y una tabla se olvida de actualizar. Si alguien despliega un consumidor nuevo sin darlo de alta, sus artefactos no reciben pendientes de borrado y el incumplimiento es invisible. Mitigación propuesta: que el `grant` del rol y el alta en `sistema_consumidor` sean el mismo paso de migración, y que el chequeo de esquema falle si existe un rol de consumidor sin fila en el registro.
