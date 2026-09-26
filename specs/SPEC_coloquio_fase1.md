# SPEC — COLOQUIO · Fase 1: Estudio cualitativo y embudo de convocatoria

**Sistema:** COLOQUIO · investigación cualitativa · Equipos Consultores
**PRD de referencia:** `PRD_coloquio_detallado.md` (Fase 1)
**Dónde se implementa:** repo `coloquio` — aplicación propia sobre el proyecto GCP `gestion-paneles`
**Precondición de despliegue:** **Fase 5 de `paneles` desplegada** (`paneles/specs/SPEC_fase5.md`): consentimiento reformulado, superficie de lectura de la bóveda, cascada de baja extensible y el rol `coloquio_app` creado
**Estado:** Borrador para desarrollo · primer sprint de COLOQUIO
**Última actualización:** 2026-09-24

---

## 1. Problem Statement

El campo cualitativo de Equipos se opera con una agenda y WhatsApp. El coordinador arma una lista mirando estudios anteriores, escribe uno por uno, anota en una planilla quién dijo que sí, y el día de la sesión se entera de cuántos vinieron cuando los ve entrar. Cuando alguien no aparece —que es la regla, no la excepción— el reemplazo se elige por quién atiende el teléfono, no por qué segmento se perdió.

Eso tiene tres costos. **No se puede medir**: no hay tasa de show, ni tiempo de convocatoria, ni idea de cuánto sobre-reclutamiento hace falta, porque nunca se registró. **No se puede garantizar calidad de muestra**: sin registro central, nada impide sentar por tercera vez en el año a la misma señora que va a todos los grupos, que es el vicio clásico del cualitativo de campo y el que un cliente serio pregunta. Y **no escala**: el volumen de cualitativo que Equipos puede vender está topeado por las horas de una persona coordinando a mano.

Esta fase convierte ese proceso en un sistema, **sin nada de inteligencia artificial en la sala**. Al cerrarla, un focus group presencial se corre entero desde COLOQUIO: se define el estudio y su pauta, se seleccionan candidatos contra el panel por criterio demográfico o semántico, se convoca con sobre-reclutamiento, se reemplaza a los caídos restituyendo el segmento perdido, se recibe a la gente y se liquida el incentivo. Y por primera vez queda el dato para saber si todo eso funcionó.

## 2. Goals

- **Que la convocatoria sea un embudo con estados, no una planilla.** Que cada contacto quede registrado y que al final de la sesión exista tasa de show, tiempo de convocatoria y sobre-reclutamiento real.
- **Que el panel decida a quién llamar.** Selección por criterio demográfico, semántico o mixto contra las bóvedas, con el gate de consentimiento aplicado por construcción y no por memoria del coordinador.
- **Que no se repita gente.** Historial cualitativo por persona visible en el momento de armar el grupo, y exclusión automática por ventana y categoría de estudio.
- **Que el reemplazo no rompa la cuota.** Que caerse un participante a tres horas de la sesión no degrade la composición del grupo en silencio.
- **Que el cualitativo empiece a ser un activo.** Que la pauta, las sesiones y las participaciones queden modeladas, de modo que las fases siguientes tengan de dónde colgarse.

## 3. Non-Goals

- **Nada de IA de conducción.** Ni sala virtual, ni transcripción, ni moderador automatizado, ni copiloto. La IA que sí está es la de **recuperación** —la consulta semántica para elegir a quién convocar—, que es núcleo y está en R1.2.
- **No hay sala virtual ni grabación.** Las sesiones de esta fase son presenciales. El portal de participante, el SFU y los medios son Fase 2. Por lo tanto **esta fase no necesita el consentimiento de grabación**, y no lo usa.
- **No se administra el panel.** Enrolamiento, dedup, altas, bajas y consentimiento son de `paneles`. COLOQUIO lee y, cuando corresponde, otorga consentimiento por la función que la bóveda expone; no escribe personas.
- **No se analizan resultados.** Ni transcripciones, ni verbatims, ni corpus. Fase 3.
- **No se paga el incentivo ni se resuelve su tratamiento fiscal.** Se registra el compromiso y la entrega.
- **No hay app de participante.** El convocado no entra a ningún sistema en esta fase: recibe un mensaje o una llamada y va a una dirección.

## 4. User Stories

**Moderador / investigador**

- Como moderador, quiero cargar la pauta del estudio con sus tópicos, objetivos y tiempos, para que el sistema sepa después contra qué medir la cobertura.
- Como moderador, quiero ver el historial cualitativo de una persona antes de aprobarla para un grupo, para no sentar a alguien que ya vino dos veces este año.
- Como moderador, quiero definir la composición que quiero en la sala —cuántos de cada segmento— y que el sistema la sostenga durante toda la convocatoria.

**Coordinador de campo**

- Como coordinador, quiero seleccionar candidatos combinando criterio demográfico con lo que la gente dijo en estudios anteriores, para armar el grupo con quien corresponde y no con quien tengo a mano.
- Como coordinador, quiero elegir cómo convoco a cada persona —a mano o por WhatsApp—, porque a algunos los llamo y a otros les escribo.
- Como coordinador, quiero convocar doce para sentar ocho y que el sistema me avise cuándo llegué al cupo.
- Como coordinador, quiero que cuando alguien se cae, el sistema me proponga un reemplazo **del mismo segmento**, y que me avise si no hay ninguno en vez de darme cualquiera.
- Como coordinador, quiero registrar la llegada de cada participante el día de la sesión, para saber en el momento con cuántos cuento y no contar cabezas.
- Como coordinador, quiero asignar y marcar entregado el regalo de cada participante.

**Responsable de operaciones**

- Como responsable, quiero ver la tasa de show por sesión y su tendencia, para saber con qué ratio de sobre-reclutamiento tengo que trabajar en vez de adivinarlo.

**DPO / cumplimiento**

- Como DPO, quiero que cuando una persona se da de baja del panel, COLOQUIO borre lo suyo y lo confirme, para que la cascada no se corte en el sistema nuevo.
- Como DPO, quiero que el dato de contacto se lea en el momento de convocar y no quede guardado en COLOQUIO.

**Casos borde**

- Segmento sin candidatos suficientes en el panel → se informa al armar la sesión, antes de empezar a convocar, no cuando falta gente.
- Persona que acepta y después se da de baja del panel → sale del embudo automáticamente y dispara el flujo de reemplazo.
- Persona convocada a dos sesiones del mismo estudio por error → el sistema lo impide.
- Todos los de la lista de espera de un segmento agotados → el sistema lo dice explícitamente y ofrece: bajar el cupo, correr la fecha, o aceptar la sesión con la cuota incompleta, dejando registro de cuál se eligió.
- Sesión cancelada con gente ya confirmada → estado propio, con los incentivos comprometidos resueltos a mano y registrados.
- Alguien se presenta el día de la sesión sin estar confirmado → se señala antes de dejarlo entrar; se puede aceptar con anulación registrada.
- Plantilla de WhatsApp rechazada por Meta o número bloqueado → el canal degrada a manual sin perder el embudo.

---

## 5. Requirements

### Must-Have (P0)

---

#### R1.1 — Estudio y pauta

- Dada la creación de un estudio cualitativo, cuando se confirma, entonces se emite un `ref_estudio` (uuid) que es el mismo identificador que `paneles` usa para cruzar encuesta ↔ cuestionario. Un estudio mixto cuanti-cuali comparte `ref_estudio`.
- El estudio declara una **categoría** (bebidas, banca, política, …), que es lo que después usa el filtro anti-panelista-profesional de R1.3.
- Dada una pauta, cuando se guarda, entonces sus tópicos quedan ordenados, cada uno con objetivo, minutos estimados y repreguntas previstas, y queda versionada.
- **Una sesión no se puede abrir sin pauta activa asociada.** La pauta es el instrumento; una sesión sin instrumento es una charla.

#### R1.2 — Selección de candidatos contra las bóvedas

Es la IA de recuperación, y es el diferencial del producto: nadie que no tenga el panel puede hacer esto.

- Dada una consulta demográfica pura, cuando se ejecuta, entonces se resuelve contra `v_persona_convocable` (bóveda) y **no accede al store semántico**.
- Dada una consulta con criterio semántico, entonces usa el motor de consulta de `paneles` y devuelve `id_persona` rankeados, con la evidencia de por qué entró cada uno —la respuesta y de qué estudio salió—, igual que la consulta de `paneles`. El coordinador tiene que poder defender la selección.
- Dada cualquier selección, entonces ninguna persona sin consentimiento vigente de `contacto_participacion` aparece, y eso lo garantiza la vista, no el filtro de la aplicación.
- El resultado muestra, por candidato: segmento (sexo, tramo etario, localidad) y **su historial cualitativo** (R1.9), en la misma pantalla. Decidir a quién llamar sin ver cuántas veces ya vino es el error que esta fase viene a eliminar.

#### R1.3 — Filtro de fatiga cualitativa

- Dada una ventana configurable y la categoría del estudio, cuando se selecciona, entonces se excluye automáticamente a quien participó de una sesión cualitativa de esa categoría dentro de la ventana.
- Existe además un tope global por persona, independiente de la categoría.
- Los umbrales son configurables desde la aplicación, no constantes en el código.
- Dado un intento de convocar a alguien excluido, entonces el sistema lo bloquea y exige una **anulación explícita**, que queda registrada con motivo y usuario. Se puede saltar la regla; no se puede saltarla en silencio.
- Este filtro corre contra el registro propio de COLOQUIO (R1.8), **no** contra `umbral_fatiga` de `paneles`, que mide otra cosa: convocatorias a encuestas.

#### R1.4 — Embudo de convocatoria

Estados y transiciones, explícitos:

```
candidato → invitado → contactado → aceptó → confirmado → asistió
                ↓           ↓          ↓          ↓
            no contactable  rechazó   se cayó   no-show
                                          ↓
                                     reemplazado
```

- Dada una transición, entonces queda registrado estado anterior, estado nuevo, canal, timestamp y quién o qué la produjo.
- Los estados terminales (`rechazó`, `no contactable`, `no-show`) sacan a la persona del embudo de esa sesión; volver a entrar requiere acción explícita.
- Una persona no puede estar en dos sesiones del mismo estudio.
- El dato de contacto se obtiene llamando a `contacto_para_convocatoria()` de la bóveda **en el momento de convocar**, queda auditado del lado de la bóveda, y **no se persiste en COLOQUIO** (R1.12).

#### R1.5 — Canal de convocatoria: manual y WhatsApp, elegido por el usuario

El canal es una propiedad de cada convocatoria y lo elige el coordinador, persona por persona. Detrás hay una interfaz de canal con dos implementaciones.

**Canal manual (P0, se construye primero)**

- El sistema muestra el contacto obtenido de la bóveda y el guion sugerido; el coordinador llama o escribe por fuera y vuelve a registrar el resultado.
- Registrar el resultado es un clic por estado, no un formulario. Si registrar cuesta más que la llamada, no se registra y el embudo miente.

**Canal WhatsApp (P0, se construye último)**

- Plantillas de invitación, recordatorio y confirmación, aprobadas por Meta, con las variables del caso.
- La respuesta del convocado actualiza el estado del embudo automáticamente.
- **Diseño obligatorio por costo:** la plantilla de invitación tiene que provocar respuesta, porque cuando la persona contesta se abre una ventana de servicio de 24 horas en la que todo el intercambio posterior es gratis. Mandar tres plantillas separadas en vez de una conversación es multiplicar la factura por tres (§9).
- Dado un fallo del canal —plantilla rechazada, número bloqueado, entrega fallida—, entonces la convocatoria degrada a manual conservando su estado. El embudo nunca se pierde por un problema de mensajería.

#### R1.6 — Sobre-reclutamiento y reemplazo con revalidación de cuota

Es el requisito con más valor operativo de la fase y el más difícil. No cortarlo.

- La sesión declara cupo objetivo, cuotas de composición y ratio de sobre-reclutamiento.
- Dada la lista de invitación propuesta, entonces cumple la cuota **asumiendo** la tasa de caída configurada, y se muestra el supuesto.
- Dado un `no-show` o una baja de último momento, cuando se pide reemplazo, entonces el sistema propone candidatos que **restituyen el segmento perdido**, no cualquiera de la lista de espera.
- Dado que ningún candidato disponible restituye el segmento, entonces el sistema **lo informa explícitamente** y ofrece las tres salidas (bajar cupo, correr fecha, aceptar cuota incompleta), registrando cuál se eligió. Nunca propone un reemplazo que rompe la cuota sin decirlo.
- El estado de cuota de la sesión —cuántos faltan de cada segmento— es visible en todo momento, no solo al armar.

#### R1.7 — Recepción y verificación de identidad

- Dada una sesión en curso de check-in, cuando llega un participante, entonces se registra su asistencia con hora, vinculada a su `id_persona`.
- La pantalla de recepción funciona en un teléfono: el coordinador recibe gente parado en una puerta, no sentado.
- Dado alguien que se presenta y no está confirmado, entonces el sistema lo señala antes de dejarlo entrar, y aceptarlo requiere anulación registrada.

#### R1.8 — Registro de participación propio

- Dada una asistencia registrada, cuando se cierra la sesión, entonces la participación queda escrita **en el store de COLOQUIO**, con estudio, categoría, sesión, rol y fecha.
- **COLOQUIO no escribe participación en la bóveda.** El registro cualitativo es suyo.
- Consecuencia asumida y documentada: el muestreo de `paneles` no ve estas participaciones. Ver el riesgo en §13.

#### R1.9 — Historial de participación por persona

- Dado un `id_persona`, cuando se consulta su historial cualitativo, entonces se ve cuántas veces participó, en qué estudios y categorías, en qué modalidad y cuándo fue la última.
- **Visible en la pantalla de selección** (R1.2), no solo como reporte posterior. Es en el momento de elegir cuando sirve.

#### R1.10 — Incentivos como módulo propio

- Catálogo de regalos con su valor, administrable desde la aplicación. **No son puntos ni pasan por el ledger de gamificación de `paneles`**: el incentivo cualitativo es un regalo por sesión y su valor es de otro orden.
- Dada una asistencia registrada, entonces queda un compromiso de incentivo por participante, con el regalo asignado y su estado (`comprometido → entregado`).
- El sistema registra compromiso y entrega; no ejecuta el pago ni resuelve el tratamiento fiscal.
- El valor total comprometido por sesión y por estudio es consultable: es lo que el investigador necesita para cotizar.

#### R1.11 — Atender la cascada de baja

Sin esto, la promesa de cumplimiento de la Fase 5 de `paneles` es hueca. Es el requisito que no se negocia.

- Un proceso programado consulta `mis_borrados_pendientes()` en la bóveda, borra todo lo de esa persona en el store de COLOQUIO, y llama a `confirmar_borrado()`.
- Dado un fallo del borrado, entonces se llama a `reportar_error_de_borrado()` y el pendiente queda abierto para reintento. Nunca se confirma un borrado que no ocurrió.
- El borrado alcanza convocatorias, asistencias, participaciones, incentivos y el documento de historial. El documento de historial por persona (§6) es lo que hace que encontrar todo sea una lectura y no un barrido.
- Dada una persona dada de baja mientras está en un embudo activo, entonces sale del embudo y dispara el flujo de reemplazo de R1.6.

#### R1.12 — Cero PII en el store de COLOQUIO

Es la condición que hace admisible la decisión de usar Firestore (§7.2), y es un invariante, no una recomendación.

- El store de COLOQUIO guarda `id_persona`, estados, timestamps, segmentos y referencias. **Nunca** nombre, documento, email, celular, dirección ni fecha de nacimiento.
- El dato de contacto se lee de la bóveda en el momento de usarlo y se descarta. No se cachea, no se guarda en el evento del embudo, no se escribe en un log.
- Toda escritura al store pasa por una validación de PII análoga a `pii.validar_sin_pii()` de `panel_api`, contra la misma lista de campos.
- **Las notas libres sobre una persona no existen.** Las observaciones son de la sesión, no del participante. Es la vía de fuga más probable y por eso se cierra por diseño y no por advertencia.

#### R1.13 — Autenticación y roles

- Firebase Auth, con el mismo padrón de usuarios de Equipos que ya usa `paneles`. No se crea un segundo directorio de personal.
- Roles: **coordinador de campo** (convoca, recibe, liquida), **investigador** (estudios, pautas, selección, historial), **administrador** (catálogos y umbrales). Un usuario puede tener más de uno.
- Toda escritura pasa por la API; el cliente no escribe en la base directamente.

---

### Nice-to-Have (P1)

- **Recordatorio automático programado** el día previo, respetando la ventana de servicio para no pagar plantilla de más.
- **Importar una sesión histórica**: cargar a mano grupos ya realizados para que el filtro anti-panelista-profesional arranque con memoria en vez de con la hoja en blanco. Sin esto, R1.3 no sirve durante los primeros meses — vale la pena evaluarlo temprano.
- **Guion de convocatoria por estudio**, editable, que el canal manual muestra y el de WhatsApp usa como base de plantilla.
- **Tablero de sesiones de la semana**, para ver todo lo que está en convocatoria de un vistazo.
- **Exportar el embudo** a planilla, porque alguien siempre lo va a pedir.

### Future Considerations (P2)

- **Portal de participante**, que llega en Fase 2 y cambia la recepción: el check-in pasa a ser el ingreso a la sala. Conviene que la entidad `asistencia` ya contemple modalidad virtual.
- **Agenda y disponibilidad**: proponer fecha de sesión según la disponibilidad declarada de los candidatos.
- **Fatiga unificada cuali-cuanti** (§13).
- **Incentivo con liquidación**, cuando la definición fiscal exista.

---

## 6. Modelo de datos (Firestore)

Base Firestore **con nombre propio**, separada de la base por defecto del proyecto (§7.2). Todo documento respeta R1.12.

```
estudio/{estudioId}
  refEstudio, nombre, cliente, categoria, estado, creadoPor, creadoEn

estudio/{estudioId}/pauta/{pautaId}
  version, activa, topicos[] { orden, titulo, objetivo, minutos, repreguntas[] }

sesion/{sesionId}
  estudioId, refEstudio, categoria
  tipo: idi | grupo
  modalidad: presencial            (virtual llega en Fase 2)
  fecha, lugar, moderadorUid
  cupoObjetivo, ratioSobrerreclutamiento
  cuotas[] { dimension, categoria, objetivo, cubierto }
  estado: planificada | convocando | confirmada | realizada | cancelada

sesion/{sesionId}/convocatoria/{idPersona}        ← el id del documento ES el id_persona
  estado, canal, segmento { sexo, tramoEtario, localidad }
  esReemplazoDe, ordenListaEspera
  anulacion { motivo, actorUid, ts }              (si se saltó R1.3)
  eventos[] { de, a, canal, resultado, ts, actor }

sesion/{sesionId}/asistencia/{idPersona}
  llegoEn, verificadaPor, modalidad

sesion/{sesionId}/incentivo/{idPersona}
  regaloId, valor, estado, entregadoEn, entregadoPor

participacionCuali/{idPersona}                    ← el documento clave del diseño
  total, ultimaEn
  porCategoria { <categoria>: { total, ultimaEn } }
  sesiones[] { sesionId, refEstudio, categoria, fecha }

catalogoRegalo/{regaloId}       nombre, valor, activo
config/fatigaCuali              ventanaDias, maxPorCategoria, maxGlobal
contador/{...}                  agregados mantenidos en escritura
```

**Tres decisiones que conviene entender antes de tocar esto.**

**El id del documento de convocatoria es el `id_persona`.** Eso hace que "una persona no puede estar dos veces en la misma sesión" sea una propiedad del store y no una validación que alguien puede olvidar. Firestore no tiene índices únicos; ésta es la forma de conseguir uno.

**`participacionCuali/{idPersona}` es el documento que sostiene tres requisitos distintos.** Es el filtro de fatiga (R1.3), el historial (R1.9) y —lo más importante— **el índice de borrado** (R1.11): cuando llega una baja, ese documento dice exactamente qué sesiones tocar, así que la cascada es una lectura y unos borrados dirigidos, no un barrido de toda la base. Se mantiene en la misma transacción en que se cierra una sesión. Si se desincroniza, se rompen los tres a la vez, así que tiene una verificación de consistencia propia.

**Los agregados se mantienen al escribir.** Firestore no hace `group by`. Tasa de show, convocados por estado y valor comprometido se actualizan con contadores en la transacción que cambia el estado. Es el precio de la decisión de store y hay que pagarlo con disciplina, no descubrirlo cuando alguien pida el primer reporte.

**Reglas de seguridad:** todo denegado desde el cliente, igual que en `paneles`. Las escrituras entran por Cloud Functions con el Admin SDK, que no pasa por las reglas. No se replica el modelo de lectura directa desde el navegador.

## 7. Stack y entorno

### 7.1 Composición

| Pieza | Decisión |
|---|---|
| Proyecto GCP | `gestion-paneles`, el mismo que `paneles`. Sin proyecto nuevo, sin Shared VPC, sin conectividad cruzada. |
| Región | `southamerica-east1` para todo, incluida la base Firestore. **Inmutable en Firestore: hay que elegirla bien la primera vez.** |
| Hosting | Firebase Hosting, sitio propio, con reescritura de `/api/**` a la función de COLOQUIO |
| Backend | Cloud Functions for Firebase, runtime `python311`, igual que `paneles` |
| Frontend | HTML + módulos ES, **sin paso de build**, con la identidad visual de `paneles` (`css/estilo.css`) |
| Auth | Firebase Auth del mismo proyecto — mismo padrón de personal |
| Store propio | Firestore, **base con nombre propio** (no la base por defecto) |
| Bóveda | Cloud SQL `paneles-boveda`, **solo lectura y solo por la superficie de la Fase 5**, con el rol IAM `coloquio_app` |
| Semántico | Cloud SQL `paneles-semantica`, a través del motor de consulta de `paneles` |
| Mensajería | WhatsApp Cloud API de Meta, directo, sin intermediario |
| Repo | `coloquio`, separado de `paneles` |

Compartir proyecto de GCP no compromete nada de lo que veníamos sosteniendo: la separación que importa es la de **repos** y la de **privilegios de base**, y las dos se mantienen. Lo que se evita es trabajo de red que no aporta a esta fase.

### 7.2 Firestore: la condición que lo hace admisible

Elegir Firestore para el store cualitativo choca de frente con una regla escrita del proyecto. `firestore.rules` de `paneles` dice, textualmente, que Firestore en este proyecto guarda **una sola cosa** —el padrón de usuarios de la app de administración— y que **nada de PII de panelistas puede escribirse ahí**. Esa regla existe porque toda la arquitectura de privacidad del sistema se apoya en que la PII vive en Cloud SQL, controlada.

La decisión se sostiene con dos condiciones, y sin las dos no se sostiene:

**1. Base con nombre propio.** COLOQUIO no escribe en la base Firestore por defecto. Usa una base separada dentro del mismo proyecto, con sus propias reglas, sus propios índices y su propia política de respaldo. La invariante de `paneles` sobre su base queda intacta, y el comentario de `firestore.rules` se actualiza para decir que existe una segunda base con otro régimen documentado.

**2. La base de COLOQUIO es PII-free por diseño (R1.12).** Y esto es posible precisamente por la Fase 5: el dato de contacto se pide a la bóveda en el momento de convocar, se usa y se descarta. Lo que queda en Firestore es `id_persona`, estados y timestamps — tokens opacos y máquina de estados. Bajo esa condición, Firestore no guarda PII y la regla del proyecto se respeta en su sustancia, no solo en su letra.

**Lo que se gana** con esta elección, y que no es poco: cero costo incremental de base (§9), sin problema de pool de conexiones desde Cloud Functions —que con Cloud SQL es un dolor real cuando la función escala—, y **listeners en tiempo real**, que es exactamente lo que va a necesitar el tablero de la sala en la Fase 2 y que con Postgres obligaría a sumar Redis y WebSockets.

**Lo que se pierde, y hay que asumirlo:** no hay agregados (se pagan con contadores mantenidos, §6), no hay índices únicos (se paga con el id de documento, §6), no hay `join` con la bóveda (el cruce se hace en memoria de la aplicación sobre conjuntos chicos de `id_persona`), y la cláusula `in` de Firestore está topeada, así que el filtro de fatiga sobre 200 candidatos se resuelve con lecturas puntuales del documento de historial, no con una consulta.

### 7.3 El cruce entre los dos mundos

Es el patrón central de la fase y conviene que esté escrito una vez:

```
1. Bóveda (Postgres)   → v_persona_convocable + criterio demográfico   → conjunto de id_persona
2. Semántico (Postgres)→ ranking por criterio                          → id_persona ordenados
3. Firestore           → participacionCuali/{id} de los candidatos     → descarta por fatiga
4. Aplicación          → combina y devuelve la lista con evidencia
5. Al convocar         → contacto_para_convocatoria() puntual          → se usa y se descarta
```

Los conjuntos son chicos —un panel de decenas de miles, una selección de cientos, una sesión de doce—, así que el cruce en memoria es adecuado. Si alguna vez deja de serlo, el síntoma va a ser el paso 3 y la salida es una consulta por rango sobre `ultimaEn`, no cambiar de base.

### 7.4 Pantallas

Siete, y ninguna necesita un framework:

1. **Estudios** — lista y ficha, con la pauta y sus tópicos.
2. **Sesión** — armado: fecha, lugar, cupo, cuotas, ratio de sobre-reclutamiento.
3. **Selección de candidatos** — la consulta (demográfica / semántica / mixta), resultados con segmento, evidencia semántica e historial cualitativo, y selección a la sesión.
4. **Embudo** — el tablero de la sesión: estados, cuota cubierta contra objetivo, quién falta, acción de reemplazo.
5. **Recepción** — check-in del día, **pensada para teléfono**: lista, búsqueda, marcar llegada.
6. **Incentivos** — asignación y entrega, con el total comprometido.
7. **Configuración** — catálogo de regalos, umbrales de fatiga cualitativa, guiones.

## 8. Contratos de API

Bajo `/api/cuali/**`, con la misma convención de `paneles`.

```
POST   /api/cuali/estudios                          crear estudio (emite refEstudio)
POST   /api/cuali/estudios/{id}/pauta               crear/versionar pauta
POST   /api/cuali/sesiones                          crear sesión con cuotas y cupo
POST   /api/cuali/sesiones/{id}/candidatos          ejecutar selección (demográfica|semántica|mixta)
POST   /api/cuali/sesiones/{id}/convocatorias       incorporar candidatos al embudo
PATCH  /api/cuali/convocatorias/{sesionId}/{idPersona}   transición de estado
GET    /api/cuali/convocatorias/{sesionId}/{idPersona}/contacto   contacto puntual (auditado en bóveda)
POST   /api/cuali/sesiones/{id}/reemplazo           proponer reemplazo que restituye segmento
POST   /api/cuali/sesiones/{id}/asistencias         check-in
POST   /api/cuali/sesiones/{id}/cerrar              cierra, escribe participación, compromete incentivos
GET    /api/cuali/personas/{idPersona}/historial    historial cualitativo
GET    /api/cuali/sesiones/{id}/embudo              estado del embudo y de la cuota
POST   /api/cuali/webhooks/whatsapp                 entrada del canal (respuestas y estados de entrega)
```

## 9. Costos

**Costo incremental de infraestructura: prácticamente nulo.** Lo único que se paga de verdad es la mensajería, y solo si se usa.

| Concepto | Estimación |
|---|---|
| **Firestore** | A 100 sesiones/mes × ~12 convocatorias × ~10 escrituras = ~12.000 escrituras/mes, más lecturas del mismo orden. La cuota gratuita de Firestore es de decenas de miles de operaciones **por día**. En la práctica, **US$0**. |
| **Cloud Functions** | Volumen despreciable sobre la capa gratuita y sobre lo que ya se paga. **~US$0**. |
| **Firebase Hosting / Auth** | Sitio estático y usuarios internos. **~US$0**. |
| **Cloud SQL** | Sin cambios: las instancias ya existen y esta fase no las agranda. **US$0 incremental**. |
| **WhatsApp Cloud API** | Ver abajo. Es el único costo real. |

**WhatsApp, con el modelo vigente.** Desde julio de 2025 Meta factura **por mensaje de plantilla entregado**, no por conversación. Y —esto es lo que gobierna el diseño de R1.5— **cuando la persona responde se abre una ventana de servicio de 24 horas donde el intercambio posterior no se cobra**.

Con una plantilla de invitación por convocado y, si hace falta, una de recordatorio fuera de ventana:

```
12 convocados × 2 plantillas         =  24 mensajes pagos por sesión
100 sesiones/mes                     = 2.400 mensajes pagos/mes
```

A una tarifa de utilidad del orden de **US$0,01–0,05 por mensaje** para Uruguay y Argentina, eso da **entre US$25 y US$120 por mes**, o **entre US$0,25 y US$1,20 por sesión**. Es ruido frente al valor de un focus group. La tarifa exacta hay que leerla del rate card de Meta por país y categoría antes de cotizar, porque varía y cambia.

Dos decisiones que mueven ese número:

- **Usar Cloud API de Meta directo**, sin proveedor intermediario. Twilio, 360dialog y similares agregan un recargo por mensaje sobre la tarifa de Meta. Con un solo número y un solo caso de uso, el intermediario no aporta.
- **Conversar en vez de notificar.** Si la invitación provoca respuesta, el recordatorio y la confirmación caen dentro de la ventana gratuita y el costo se reduce a la mitad o menos. Si se mandan tres plantillas sueltas, se paga tres veces. Está en R1.5 como requisito, no como consejo.

**Costo que no es de infraestructura:** el número de WhatsApp Business verificado y la aprobación de plantillas por parte de Meta tienen plazos que no controlás. Es la dependencia externa de la fase.

## 10. Dependencias

- **Bloqueante:** Fase 5 de `paneles` desplegada. Sin la superficie de lectura, el rol `coloquio_app`, `contacto_para_convocatoria()` y la cascada extensible, esta fase no tiene de dónde leer ni a qué responder.
- **Bloqueante:** motor de consulta semántica de `paneles` operativo — ya lo está.
- **Bloqueante, externo:** número de WhatsApp Business verificado y plantillas aprobadas, **solo para el canal WhatsApp**. El canal manual no depende de nada y es el que se construye primero, justamente por esto.
- **Bloqueante, producto:** la definición metodológica del filtro anti-panelista-profesional — qué ventana, cómo se categorizan los estudios. Es una definición de los investigadores, no de ingeniería, y sin ella R1.3 no se puede implementar.
- **Bloqueante, infraestructura:** la ubicación de la base Firestore. Es inmutable; hay que confirmar que la base por defecto del proyecto está en `southamerica-east1` y crear la de COLOQUIO ahí.
- **No bloqueante:** la definición fiscal del incentivo. Se registra el compromiso sin liquidarlo.

## 11. Definition of Done

Un focus group presencial real, de punta a punta, en el sistema:

1. Se crea un estudio con su pauta y una sesión con cupo y cuotas.
2. Se seleccionan candidatos por criterio **mixto** (demográfico + semántico), con evidencia y con el historial cualitativo visible en la misma pantalla.
3. Ninguna persona sin consentimiento vigente aparece en la selección, y eso se verifica intentando forzarlo.
4. El filtro anti-panelista-profesional excluye a quien corresponde, y la anulación queda registrada con motivo y usuario.
5. Se convoca a doce por los **dos canales** —algunos a mano, otros por WhatsApp— y el embudo refleja ambos.
6. Se cae un participante y el sistema propone un reemplazo **del mismo segmento**; se fuerza el caso sin candidatos y el sistema lo informa en vez de romper la cuota.
7. Se registra la recepción de ocho personas desde un teléfono.
8. Se cierra la sesión: participación escrita, incentivos comprometidos, historial por persona actualizado.
9. **Una baja de prueba en `paneles` llega como pendiente, COLOQUIO borra todo lo de esa persona y confirma**; se verifica que no quedó rastro.
10. Una auditoría del store de COLOQUIO no encuentra un solo campo de PII.
11. Cero escrituras de COLOQUIO sobre la bóveda fuera de las funciones que la Fase 5 expone.

## 12. Success Metrics

**Leading** (se pueden medir apenas corra la primera sesión, y por primera vez)

- **Tasa de show**: asistieron / confirmados. Hoy no existe el número.
- **Ratio de sobre-reclutamiento realmente necesario**, contra el configurado. A los tres meses esto deja de ser una intuición.
- **Tiempo de convocatoria**: de lanzamiento a cupo confirmado.
- **Intentos de contacto por confirmación lograda**, por canal. Es lo que decide si WhatsApp vale la pena frente a la llamada.
- **Re-convocatorias bloqueadas** por el filtro de fatiga, y cuántas se anularon a mano. Si todas se anulan, el umbral está mal puesto.
- **Sesiones cerradas con la cuota completa**, sobre el total.

**Lagging**

- Sesiones cualitativas por mes: si el sistema no sube este número, la fase no cumplió su objetivo aunque funcione todo.
- Horas de coordinación por sesión.
- Costo por participante sentado, incluyendo incentivo y mensajería.
- Incidencia de panelista repetido detectada por un cliente: objetivo, cero.

## 13. Riesgos y preguntas abiertas

- **[producto, bloqueante]** La ventana y la categorización del filtro anti-panelista-profesional. Sin esa definición, R1.3 no se implementa.
- **[producto]** **R1.3 arranca sin memoria.** El filtro no sabe nada de los grupos que Equipos ya hizo, así que durante los primeros meses no excluye a nadie — justo cuando el panelista profesional ya está en el panel. La carga de sesiones históricas está en P1; conviene evaluar subirla a P0, porque es lo que hace que el diferencial exista desde el día uno y no dentro de un año.
- **[ingeniería]** **Los contadores de Firestore se pueden desincronizar.** Los agregados mantenidos al escribir son la contrapartida de no tener `group by`, y una transacción fallida a mitad de camino deja un número mal. Necesita una verificación de consistencia que se pueda correr y que repare, no solo que avise.
- **[ingeniería]** El documento `participacionCuali/{idPersona}` sostiene fatiga, historial y borrado. Es una dependencia concentrada: si se desincroniza, se rompen los tres. Merece pruebas propias y una reconstrucción posible desde las sesiones.
- **[cumplimiento]** **Las notas libres son la vía de fuga de PII.** R1.12 las prohíbe sobre personas, pero un campo de observaciones de sesión puede recibir "la señora de Pocitos que trabaja en el banco". La validación automática detecta campos con nombre de PII, no contenido. Es un riesgo residual que se mitiga con diseño de formulario y con advertencia en la interfaz, y conviene decirlo en vez de suponerlo resuelto.
- **[producto/datos]** **Fatiga ciega en una dirección.** El registro de participación cualitativa es de COLOQUIO (R1.8), así que el muestreo de `paneles` no ve que alguien estuvo en tres grupos: para él sigue descansado. Es una decisión, no un olvido. La salida, si a volumen empieza a doler, es que `paneles` lea un resumen desde COLOQUIO — sin que COLOQUIO escriba nada en la bóveda.
- **[operaciones]** La aprobación de plantillas de WhatsApp por Meta tiene plazos ajenos. Por eso el canal manual es P0 y se construye primero: si la aprobación demora, la fase se entrega igual.
- **[datos]** La selección semántica de candidatos depende de que la gente del panel tenga contenido embebido. Para segmentos poco encuestados se degrada a demográfica pura, y la interfaz tiene que decirlo en vez de devolver un ranking de ruido.
- **[infraestructura]** La ubicación de Firestore es inmutable. Confirmar antes de crear, no después.
