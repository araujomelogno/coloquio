# ADDENDUM — COLOQUIO · Fase 1: la pantalla de selección

**Agrega a:** `coloquio/specs/SPEC_fase1.md`, requisitos R1.14 a R1.18
**Afecta a:** la pantalla 3 (Selección de candidatos) y R1.2
**Dependencia:** una migración nueva en `paneles` (§5). Sin ella, tres de los cuatro requisitos no se pueden implementar.
**Última actualización:** 2026-10-06

---

## 1. El modelo que ya existe, y que hay que copiar en vez de inventar

`paneles` se encontró con este mismo problema en su Fase 7 y lo resolvió con **tres niveles**, no con una regla binaria. Están en el código y conviene nombrarlos antes de especificar nada, porque los cuatro requerimientos caen limpiamente en ellos:

| Nivel | En `paneles` | Qué muestra | Registro |
|---|---|---|---|
| **Atributos** | `GET /panelistas/{id}/ficha` · «los atributos de la persona, **sin un solo dato identificatorio**» | demografía, paneles, estado | ninguno — es la misma información que ya devuelve una consulta con filtros |
| **Reidentificación** | `POST /reidentificacion`, permiso propio `reidentificar` | nombre y contacto de una **lista** de `id_persona` | una fila en `reidentificacion` por persona, **antes** de devolver, con autor y motivo |
| **Ficha identificada** | `GET /panelistas/{id}` · «abrir una ficha es ver la PII de una persona identificada: es una reidentificación deliberada y queda registrada» | la persona completa | ídem, con motivo `ficha` |

La respuesta de la bóveda a «¿quién puede ver PII?» nunca fue *nadie*. Fue **quien tenga un motivo, y queda registrado**. La tabla `reidentificacion` existe para eso desde la Fase 2 de `paneles`, y su columna `motivo` ya contempla `convocatoria`.

Entonces tus requerimientos 3 y 4 no contradicen el diseño: piden que COLOQUIO use el mismo mecanismo que `paneles` usa. Lo que sí hay que decidir con cuidado es **cuándo** se dispara cada nivel, porque ahí está la diferencia entre una auditoría útil y una auditoría que registra todo y por lo tanto no señala nada.

---

## 2. Requisitos

### R1.14 — Atributos demográficos dinámicos en el formulario

El formulario de búsqueda deja de tener campos fijos y se arma desde el catálogo de la bóveda (`atributo_demografico` + `atributo_categoria`, migración `boveda/0008`).

- Dado el catálogo, cuando se abre la pantalla de selección, entonces se ofrece un control por cada atributo **activo**, en su `orden`, con su `etiqueta`.
- El control depende del `tipo`:
  - `categorico` y `derivado` → **combo de selección múltiple**, con las categorías activas del atributo. Varias categorías del mismo atributo se combinan con *o*; atributos distintos, con *y*.
  - `numerico` → rango (mínimo / máximo).
  - `fecha` → rango de fechas.
- Un atributo dado de baja (`activo = false`) deja de ofrecerse, pero un filtro guardado que lo use sigue siendo legible y se muestra marcado como inactivo. No se borra silenciosamente lo que alguien configuró.
- La clave del atributo —no su etiqueta— es lo que viaja en el filtro y lo que se guarda. Es lo mismo que hace `objetivo_composicion.dimension` en `paneles`, y es lo que permite renombrar una etiqueta sin romper nada.

**Atributos marcados `es_especial`.** El catálogo de `paneles` marca como especiales las categorías del artículo 18 de la Ley 18.331: salud, origen étnico o racial, convicciones religiosas, afiliación sindical, ideología política y vida sexual. **No se ofrecen como filtro por defecto en COLOQUIO.** Si un estudio los necesita —y en investigación de mercado a veces se necesitan—, se habilitan por estudio, el control queda visiblemente marcado, y el uso se registra. La marca existe justamente para que su uso sea visible en una revisión de cumplimiento en vez de pasar inadvertido; perderla en la pantalla de COLOQUIO sería desperdiciarla.

**Criterios de aceptación**

- Dado un atributo nuevo creado en `paneles`, cuando se recarga la selección de COLOQUIO, entonces aparece sin desplegar nada.
- Dado un atributo categórico con ocho categorías, entonces el control permite elegir varias y la búsqueda las combina con *o*.
- Dado un filtro sobre un atributo especial no habilitado para el estudio, entonces la búsqueda lo rechaza.
- Ningún atributo se nombra en el código de COLOQUIO. Si aparece `sexo` escrito a mano en el front, el requisito está incumplido.

---

### R1.15 — Columnas elegibles en la lista de candidatos

Espeja `R7.4` de `paneles`, incluida la parte que importa y es fácil de perder.

- Dado el catálogo, cuando el usuario abre **Columnas**, entonces puede elegir qué atributos demográficos ve como columna de la lista.
- La elección **se recuerda por usuario**, no por sesión de trabajo ni por estudio.
- **Agregar una columna no vuelve a ejecutar la búsqueda.** Los atributos se resuelven en una sola llamada en lote sobre los `id_persona` que la lista ya tiene. Es la diferencia entre un clic instantáneo y esperar de nuevo a la consulta semántica.
- Un atributo **ausente** se distingue de un atributo **vacío**: que no sepamos el nivel educativo de alguien es información, y mostrarlo como celda en blanco igual que un «sin dato» declarado los confunde. `paneles` ya resolvió esto devolviendo el atributo ausente del objeto en vez de con valor nulo; COLOQUIO lo pinta distinto.
- Columnas fijas que no se pueden sacar: el identificador corto y el **historial cualitativo** (R1.9). Ver cuántas veces vino alguien es la razón de ser de esta pantalla.

**Criterios de aceptación**

- Dada una lista de 200 candidatos, cuando se agrega una columna, entonces la lista se completa sin re-ejecutar la búsqueda y sin recargar la página.
- Dado un usuario que vuelve al día siguiente, entonces sus columnas son las que había elegido.
- Dado un atributo que se dio de baja entre dos sesiones, entonces desaparece de las columnas elegidas sin error.

---

### R1.16 — Ficha del candidato

Dos niveles, igual que `paneles`, y el que se abre desde un resultado es el seudónimo.

**Ficha seudónima (la que abre el botón «Ver ficha»).** Muestra lo mismo que `GET /panelistas/{id}/ficha`: estado, fecha de enrolamiento, todos los atributos demográficos con su procedencia, y los paneles a los que pertenece. **Más lo que COLOQUIO sabe y `paneles` no**: su historial cualitativo completo —estudios, categorías, fechas, modalidad—, que es exactamente el dato que el investigador necesita para decidir.

Sin nombre, sin contacto, sin registro de reidentificación: es la misma información demográfica que la búsqueda ya devolvió, vista de a una persona.

**Ficha identificada.** Es otra acción, deliberada, y cae bajo R1.17.

**Criterios de aceptación**

- Dada la ficha seudónima, entonces no aparece ningún campo de `pii.CAMPOS_PII`.
- Dada una persona que participó en tres sesiones cualitativas, entonces las tres aparecen con estudio, categoría y fecha.
- Abrir una ficha seudónima **no** escribe en `reidentificacion`.

---

### R1.17 — Identidad y contacto en la lista

Es el requisito que necesita una decisión explícita, y propongo partirlo en dos porque las dos mitades tienen costos muy distintos.

**Nombre: sí, con registro, a pedido.**

Elegir doce personas entre doscientas mirando UUIDs no es un trabajo que se pueda hacer. El nombre es lo que vuelve usable la pantalla, y es el dato identificatorio de menor sensibilidad.

- Dado un conjunto de candidatos, cuando el usuario pide verlos identificados, entonces se devuelven los nombres y queda **una fila en `reidentificacion` por persona**, con actor, motivo (`seleccion_cuali`) y sistema (`coloquio`), escrita **antes** de devolver la respuesta.
- Requiere un permiso propio en COLOQUIO, espejo de `reidentificar` en `paneles`. No todo usuario de COLOQUIO lo tiene.
- **Es una acción explícita, no la carga de la página.** Acá está la recomendación que más me importa de todo el addendum: si cada búsqueda reidentifica automáticamente a los doscientos resultados, la tabla `reidentificacion` pasa a tener todo y por lo tanto a no señalar nada. El precedente de `paneles` para el lote es `POST /reidentificacion` con una lista de ids y un motivo —una acción— y la exportación identificada, que además exige un permiso aparte. Lo mismo acá: el coordinador filtra, achica, y recién entonces pide ver quiénes son.

**Celular y email: no hace falta surface nueva, y conviene que no la haya.**

- `contacto_para_convocatoria()` exige **convocatoria activa declarada**, y se niega con «no hay motivo para leer su contacto» si no la hay. Eso no es un obstáculo accidental: es la regla.
- Y el flujo ya la respeta sin esfuerzo. El coordinador arma la lista corta, los incorpora al embudo (`candidato → invitado`), COLOQUIO llama a `declarar_convocatoria()`, y **a partir de ahí el contacto está disponible** — que es exactamente cuando se necesita, porque es cuando va a escribir o llamar (R1.5).
- Dicho de otro modo: el contacto no es para *mirar la lista*, es para *convocar*. Pedirlo antes de decidir significa leer el teléfono de ciento ochenta y ocho personas a las que nunca se va a llamar.

Si aun así querés el contacto en la lista antes de convocar, se puede —requiere una función nueva en la bóveda que no exija convocatoria declarada—, pero es una decisión que afloja una regla deliberada y debería tomarse por escrito, no por conveniencia de pantalla.

**Y en los dos casos, la regla que no se mueve:** la PII viaja al navegador y muere ahí. **No se escribe en Firestore**, ni en la lista guardada, ni en el evento del embudo, ni en un log (R1.12).

**Criterios de aceptación**

- Dada una búsqueda, cuando se cargan los resultados, entonces **no** se escribe ninguna fila en `reidentificacion`.
- Dada la acción de identificar sobre veinte candidatos, entonces se escriben veinte filas con motivo `seleccion_cuali` y sistema `coloquio`, y recién después se devuelven los nombres.
- Dado un usuario sin el permiso, entonces la acción se rechaza y la lista sigue funcionando seudónima.
- Dada una auditoría del store de COLOQUIO después de identificar, entonces no hay un solo nombre guardado.
- Dado un candidato todavía no incorporado al embudo, entonces su contacto no está disponible y el mensaje lo explica.

---

### R1.18 — Modo laxo y detalle de cumplimiento del criterio semántico

**Antes del requisito, un hallazgo: hoy COLOQUIO corre en modo estricto sin saberlo.**

`paneles` expone dos perillas independientes, y COLOQUIO no manda ninguna:

| Perilla | Alcance | Qué hace |
|---|---|---|
| `modo` | de la consulta | `estricto` (**el default de `paneles`**) o `laxo` |
| `duro` | de cada criterio | un criterio duro **filtra** como si fuera demográfico; uno no duro **ordena** |

`motor.criterios_para_paneles()` arma los criterios como `{"tipo": "semantico", "texto": …}` y no envía `modo`, así que `paneles` aplica su default: **estricto**. Las reglas de combinación, tal como están escritas en `consultas._combinar()`:

```
no_cumple en cualquier criterio   → afuera, en los dos modos
criterio duro sin cumplir         → afuera, en los dos modos
dudoso o sin_evidencia + estricto → afuera
dudoso o sin_evidencia + laxo     → adentro, marcada como penalizada
sin_verificar                     → adentro en los dos modos, marcada «verificación incompleta»
```

O sea: **en cada selección que hiciste hasta hoy, los candidatos con veredicto `dudoso` o sin evidencia se descartaron en silencio.** En `paneles` eso es razonable: una consulta estricta devuelve un ranking más limpio y nadie se entera de lo que no apareció. En COLOQUIO el costo es distinto, porque el universo útil ya es chico: si necesitás doce mujeres de 35 a 44 de Montevideo que tomen determinada bebida, descartar a las dudosas sin avisar puede dejarte sin grupo, y el coordinador no tiene forma de saber que pasó.

**Recomendación, y es un cambio de default:** en COLOQUIO el modo por defecto es **laxo**, al revés que en `paneles`. El razonamiento es que acá hay un humano que va a llamar por teléfono y hacer un filtro de admisión antes de sentar a nadie — un dudoso que entra a la lista cuesta una llamada; un dudoso que no entra puede costar el grupo. El filtro fino lo hace el moderador, no el ranking.

**El requisito**

- Al definir un criterio semántico, el usuario puede marcarlo **duro** (filtra) o dejarlo laxo (ordena). Es por criterio, igual que en `paneles`.
- La búsqueda tiene un **modo** —estricto o laxo— que se elige por consulta. Por defecto, **laxo**.
- La interfaz dice **qué modo se usó** junto con el total de resultados. Un número de candidatos sin el modo al lado no es interpretable.
- Cuando el modo es estricto, la respuesta informa **cuántas personas quedaron excluidas y por qué motivo** (`no_cumple`, `dudoso`, `sin_evidencia`). Que el estricto descarte está bien; que descarte sin decirlo, no.
- `peso` y `umbral_distancia` quedan con sus valores por defecto y **no se exponen** en la interfaz de COLOQUIO. Son perillas de calibración del motor y tocarlas sin el protocolo de calibración de `paneles` es empeorar el resultado con confianza.

**El detalle de cumplimiento, por candidato**

Hoy `motor._evidencias()` se queda con `criterio`, `veredicto`, `razon`, `respuesta`, `pregunta` y `estudio`, y descarta el resto. Falta lo que distingue a un buen candidato de uno que entró de rebote:

- Por cada criterio: **veredicto** (`cumple` · `no_cumple` · `dudoso` · `sin_verificar` · `sin_evidencia`), la **razón** del verificador, y la **evidencia** —la respuesta textual, la pregunta y de qué estudio salió—.
- Por candidato: las marcas **`penalizado`**, **`verificacion_incompleta`** y **`confianza_baja`**, que `paneles` ya devuelve y COLOQUIO está tirando.
- En la lista, el candidato penalizado o de confianza baja se distingue a simple vista. No se esconde: entró a propósito, y quien decide tiene que ver con qué calidad de evidencia entró.

**La consecuencia que no es cosmética**

El modo laxo mete gente con evidencia floja en la lista. Eso está bien mientras un humano decida; deja de estar bien si el sistema la elige solo. Entonces:

- **La propuesta automática de invitación (R1.6) no completa cuota con candidatos penalizados o de confianza baja mientras haya candidatos verificados disponibles**, y si tiene que recurrir a ellos, lo dice.
- Lo mismo vale para el reemplazo: restituir un segmento con alguien de evidencia dudosa es una decisión del coordinador, no un relleno silencioso.

**Criterios de aceptación**

- Dada una búsqueda semántica sin indicar modo, entonces se ejecuta en **laxo** y la interfaz lo muestra.
- Dado un criterio marcado como duro en modo laxo, entonces quien no lo cumple queda afuera igual.
- Dada una búsqueda en estricto, entonces se informa cuántos quedaron excluidos y por qué motivo.
- Dado un candidato con veredicto `dudoso`, entonces aparece en la lista marcado, con su razón y su evidencia a la vista.
- Dada una verificación caída (`sin_verificar`), entonces los candidatos aparecen marcados «verificación incompleta» y **no** se los confunde con dudosos: nadie juzgó la evidencia, que no es lo mismo que haberla juzgado y dudado.
- Dada la propuesta de invitación con candidatos verificados suficientes, entonces no incluye penalizados.
- Dado que `paneles` no responde, entonces la selección degrada a demográfica pura y lo dice (sin cambios respecto de `motor.py`).

**Qué hay que tocar**

Nada en la bóveda: todo esto ya lo devuelve `POST /api/consultas` de `paneles`. Los cambios son dos, los dos en COLOQUIO:

1. `motor.criterios_para_paneles()` pasa `duro` por criterio y `modo` en la consulta.
2. `motor._evidencias()` deja de descartar `penalizado`, `verificacion_incompleta`, `confianza_baja` y los excluidos con su motivo, y `seleccion.py` los propaga a la respuesta.

**Costo:** cero. Es el mismo motor, la misma llamada y la misma calibración; cambia qué se le pide y qué se conserva de lo que contesta.

---

## 3. Qué cambia en la pantalla

```
┌─ Filtros ──────────────────────────────────────────────────┐
│ [armados desde el catálogo de atributos — R1.14]           │
│ Criterio semántico: [__________________] ☐ duro            │
│                     [+ agregar criterio]                   │
│ Modo: (•) laxo  ( ) estricto                     — R1.18   │
└────────────────────────────────────────────────────────────┘

┌─ Candidatos (187) ──────────── [Columnas ▾] [Identificar (12)] ┐
│ ☐  id      │ hist.cuali │ <columnas elegidas — R1.15>  │       │
│ ☑  a3f2…   │ 2 · 2025   │ F │ 35-44 │ Montevideo │ ✓   │ Ficha │
│ ☐  7b91…   │ —          │ M │ 25-34 │ Canelones  │ ⚠   │ Ficha │
└────────────────────────────────────────────────────────────────┘
  modo laxo · 187 candidatos · 23 penalizados · 4 sin verificar
  ⚠ = veredicto dudoso o confianza baja (R1.18)
```

`Identificar` actúa sobre lo seleccionado, no sobre todo. `Ficha` abre la seudónima (R1.16).

---

## 4. Dónde choca con lo ya escrito

- **R1.2** gana el formulario dinámico y las columnas; su criterio de aceptación sobre el historial visible en la misma pantalla sigue valiendo y ahora es columna fija.
- **R1.12** (cero PII en el store) **no se toca**: mostrar no es guardar, y el criterio de aceptación nuevo lo verifica explícitamente.
- **§7.3 de la spec**, el cruce entre los dos mundos, gana dos pasos: el catálogo de atributos al abrir la pantalla, y la resolución de atributos en lote al elegir columnas.
- **El riesgo de notas libres** (§13) se agrava: con nombres en pantalla, la tentación de escribir «la señora que atendió bien» en un campo de observaciones sube. Vale reforzar la advertencia en la interfaz.

---

## 5. Lo que hay que agregar en `paneles` (migración nueva)

Tres de los cuatro requisitos **no se pueden implementar con la superficie actual**. Hoy `coloquio_app` tiene `select` sobre `v_persona_convocable`, `v_fatiga_panelista`, `v_finalidad`, `v_texto_consentimiento_activo` y `v_persona_finalidad_vigente`, y nada más. No ve el catálogo de atributos, no ve los valores por persona, y no tiene forma de obtener un nombre.

| # | Qué | Para | Nota |
|---|---|---|---|
| 1 | `v_atributo_catalogo` — atributos y categorías activas, con tipo, orden, etiqueta y `es_especial` | R1.14 | Es vocabulario, no PII. El grant es barato. |
| 2 | `atributos_de_personas(ids uuid[])` → `(id_persona, clave, valor, etiqueta, procedencia)` | R1.15, R1.16 | Espejo de `POST /resultados/atributos`. `security definer`, porque `f_atributo_persona` no se le presta al consumidor. |
| 3 | Filtro por atributo dinámico en la superficie de convocables | R1.14 | **Es la pieza más grande.** Hoy `f_persona_convocable()` devuelve cuatro columnas fijas (`sexo`, `localidad`, `tramo_etario`, `edad`) y no sabe filtrar por un atributo arbitrario. Hace falta una variante que acepte los filtros —`f_persona_convocable_filtrada(filtros jsonb)`— porque resolverlo en memoria sobre un panel de decenas de miles no es viable. |
| 4 | `ficha_candidato(id_persona)` → estado, enrolamiento, atributos, paneles | R1.16 | Equivalente de `ficha.seudonima()`. Sin PII, sin registro. |
| 5 | `identificar_candidatos(ids uuid[], motivo, actor)` → `(id_persona, nombre)` | R1.17 | Escribe `reidentificacion` antes de devolver, con `sistema_de_la_conexion()`. **No exige convocatoria declarada** — ésa es la decisión que esta función materializa, y por eso devuelve solo el nombre y no el contacto. |

Los puntos 1, 2 y 4 son mecánicos. El 3 es trabajo real. El 5 es el que necesita tu visto bueno explícito, porque es el único que amplía lo que COLOQUIO puede ver.

**Costo:** nulo. Son vistas, funciones y `grant` sobre instancias que ya existen; el único consumo adicional son unas pocas lecturas más por búsqueda y filas en `reidentificacion`, que son texto corto. Nada de esto agrega un recurso facturable.

---

## 6. Preguntas abiertas

- **[producto, bloqueante del 5]** ¿Se aprueba que COLOQUIO pueda ver el **nombre** de un candidato antes de convocarlo, con registro? Sin ese sí, la lista queda seudónima y la selección se hace sobre atributos nada más.
- **[producto]** ¿Y el **contacto** antes de convocar? Mi recomendación es que no: se obtiene al incorporar al embudo, que es cuando se usa. Si la respuesta es sí, hay que escribir por qué, porque afloja una regla deliberada de la bóveda.
- **[cumplimiento]** ¿Los atributos `es_especial` se ofrecen como filtro en COLOQUIO? Propuesta: habilitados por estudio, marcados en pantalla, y su uso registrado.
- **[producto]** ¿Se confirma el cambio de default a **laxo** (R1.18)? Es lo contrario de lo que hace `paneles`, y la justificación —que acá hay un humano filtrando después— es de método, no de ingeniería.
- **[producto]** ¿El permiso de identificar es un rol nuevo en COLOQUIO o alcanza con el de coordinador de campo? En `paneles` es un permiso aparte (`reidentificar`), y copiar esa separación cuesta poco.
