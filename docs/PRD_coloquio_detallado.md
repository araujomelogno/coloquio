# PRD detallado — COLOQUIO · Sistema de investigación cualitativa sobre el panel

**Contexto:** Equipos Consultores · investigación de mercado
**Estado:** Borrador para revisión · versión detallada
**Última actualización:** 2026-09-16

**Sobre el nombre.** *Coloquio*: conversación formal entre dos o más personas sobre un tema. Cubre las dos modalidades del sistema —entrevista en profundidad y focus group— sin privilegiar ninguna.

**Relación con el sistema de paneles.** Las bóvedas —la de identidad y la semántica— **no son de `paneles`: son infraestructura compartida**. `paneles` es un sistema construido sobre ellas; COLOQUIO es otro. Los dos las consultan directo, ninguno depende de que el otro esté corriendo, y ninguno de los dos es dueño del dato.

Ese encuadre resuelve las dos alternativas que se descartaron. **Meter el cualitativo adentro de `paneles`** convertiría a `paneles` en otra cosa: un sistema que hace todo deja de tener invariantes que valga la pena defender. **Consultar por API** acoplaría la disponibilidad de COLOQUIO a la de `paneles`, que es peor que acoplar el esquema —el esquema se versiona, la caída se sufre—.

Lo que sí hereda esa decisión es un trabajo que hasta ahora no se notaba porque había un solo consumidor: las invariantes de la bóveda (gate de consentimiento, cascada de baja, prohibición de PII del lado semántico) viven hoy en el código de `panel_api`, y un `if` en Python no es un contrato cuando hay dos sistemas que lo tienen que cumplir. Eso, más la reformulación del modelo de consentimiento para cubrir lo que el cualitativo exige bajo URCDP, es la **Fase 5 de `paneles`**: el incumbente externaliza sus bóvedas antes de entregarlas. No es un prólogo de COLOQUIO, es una fase del otro sistema, con su propia spec y su propio criterio de salida.

**Dos principios de diseño que gobiernan todo el documento.**

1. **Hay dos inteligencias artificiales en COLOQUIO y son independientes.** La de **recuperación** —bóveda semántica, selección de a quién convocar— es núcleo del producto y va en la Fase 1. La de **conducción** —moderación automatizada sobre la capa de voz— es una apuesta separada, en fases posteriores. No se confunden ni se condicionan.
2. **COLOQUIO es un producto completo sin moderación automatizada.** Las Fases 1 a 3 entregan un sistema vendible y operativo con moderador humano en todas las sesiones. Las Fases 4 y 5 agregan escala; si no se construyeran nunca, el proceso de COLOQUIO sigue siendo válido de punta a punta.

**Qué es de COLOQUIO y qué no.** COLOQUIO **lee** de las bóvedas: quiénes son las personas, por criterio demográfico y semántico, y si se las puede contactar. Todo lo demás —pauta, sesiones, convocatoria, **su propio registro de participaciones**, incentivos, grabaciones, transcripciones y segmentos— vive en las bases de COLOQUIO. El registro de participación cualitativa no se escribe en la bóveda: es del cualitativo, y COLOQUIO lo administra.

**Documentos de referencia.** `paneles/CLAUDE.md` (invariantes y stack), `paneles/docs/PRD_gestion_de_paneles_detallado.md` (el sistema del que COLOQUIO consume), `paneles/docs/PRD_consulta_semantica_cuestionarios.md` (mecánica del motor semántico, que COLOQUIO reusa y no reimplementa).

---

## 1. Marco

### Problem Statement

Equipos produce investigación cualitativa —entrevistas en profundidad y focus groups— con un proceso enteramente artesanal: el reclutamiento se hace por agenda y WhatsApp, la selección de participantes no aprovecha el panel ni lo que esas personas ya contestaron, y el resultado de cada estudio muere en un informe. Eso impone tres costos. **Operativo:** la convocatoria es el cuello de botella y el no-show se gestiona a mano, con sobre-reclutamiento improvisado. **De calidad:** sin registro central no hay forma de garantizar que no se esté sentando en el grupo a un panelista profesional, que es el vicio clásico del cuali de campo. **Estratégico:** cada estudio cualitativo es un activo que se tira, porque los verbatims no quedan consultables junto a las respuestas cuantitativas de las mismas personas.

El costo de no resolverlo no es solo margen: es que el volumen de cualitativo que Equipos puede vender queda topeado por las horas de moderador disponibles, y que el panel —el activo diferencial— no se capitaliza del lado cuali.

### Goals

- **Convertir la convocatoria en un proceso con estados, no en una agenda.** Que el embudo de reclutamiento sea medible y que el no-show se gestione con sobre-reclutamiento y reemplazo automático, no con suerte.
- **Usar el panel como filtro de selección**: seleccionar participantes por criterio demográfico, semántico o mixto contra las bóvedas existentes, con el gate de consentimiento y el umbral de fatiga aplicados por construcción.
- **Producir registro atribuido por hablante como subproducto de la sesión**, no como una tarea posterior de desgrabación.
- **Incorporar el verbatim al corpus consultable**, de modo que un estudio cualitativo nuevo pueda preguntarle a todos los estudios cualitativos y cuantitativos anteriores.
- **Romper el techo de horas-moderador**: habilitar moderación asistida y moderación automatizada para que el n de un estudio cualitativo deje de estar determinado por la agenda del moderador.

### Non-Goals

- **No administra el panel.** Enrolamiento, dedup, membresías, puntos y bajas siguen siendo de `paneles`. COLOQUIO consume; no duplica el módulo de personas.
- **No reimplementa el motor semántico.** Embeddings, ranking y verificación viven en el módulo de consulta semántica de `paneles`. COLOQUIO aporta un tipo de contenido nuevo al mismo motor.
- **No reemplaza al investigador en el análisis.** El sistema segmenta, transcribe, indexa y propone; la interpretación y la codificación final son humanas. Un análisis automático presentado como conclusión sería un producto distinto y peor.
- **No es una plataforma de videoconferencia general.** La sala virtual existe para sesiones de investigación con participantes identificados; no compite con Zoom ni sirve para reuniones internas.
- **No automatiza el pago del incentivo ni su tratamiento fiscal.** Registra el compromiso y su estado; la liquidación y su tratamiento impositivo quedan fuera, con la misma pregunta abierta que ya arrastra `paneles` para el canje de premios.
- **No hace multi-idioma en v1.** Español rioplatense. La moderación automatizada en otro idioma o dialecto es una extensión posterior, no un requisito.
- **No hace moderación automatizada en estudios sensibles.** Temas de salud, duelo, violencia o vulnerabilidad quedan explícitamente reservados a moderador humano, con o sin copiloto.

### Arquitectura

Un sistema, **tres stores**, y una sola regla que los ordena.

- **Bóveda** (`paneles`, Cloud SQL — existente). Identidad, consentimiento, membresías, participación, fatiga. COLOQUIO la lee a través de **vistas**, nunca de tablas, y escribe únicamente en lo suyo. Es el origen autoritativo de `id_persona` y del derecho a convocar.
- **Store cuali** (nuevo, Cloud SQL, **régimen de bóveda**). Estudio, pauta, sesión, convocatoria, asistencia, incentivo, grabación, turnos de transcripción y segmentos. **Contiene PII por definición**: una transcripción cruda tiene a la gente diciendo su nombre y su barrio en voz alta, y una grabación tiene su cara y su voz. Por eso vive del lado bóveda, en instancia dedicada, con las mismas restricciones de acceso y región.
- **Semántico** (`paneles`, Cloud SQL + pgvector — existente). Recibe del cuali **solo el segmento despersonalizado**: `id_persona`, `ref_estudio`, tópico, texto pasado por redacción de PII, y su embedding. Nada más.
- **Objetos de medios** (Cloud Storage, región de la bóveda, CMEK). Las grabaciones no van a la base; va la referencia. El ciclo de vida del objeto sigue al de la persona.

**Regla dura #1, heredada y extendida.** La PII nunca se escribe en el store semántico. Para el cuantitativo eso se resolvía no copiando columnas. Para el cualitativo no alcanza: el texto mismo es el riesgo. Por eso entre el store cuali y el semántico hay un **paso de despersonalización obligatorio**, y ningún segmento cruza sin haberlo pasado.

**Cruce entre stores.** Por conjuntos de `id_persona`, como ya hace `paneles`. COLOQUIO comparte el `ref_estudio` (uuid) con la bóveda y con el semántico, de modo que un estudio mixto cuali-cuanti es un solo `ref_estudio` con dos tipos de contenido.

**Stack: dos planos, no uno.**

- **Plano de control** (todo lo que no es sesión en vivo): Firebase con proyecto propio —Auth, Hosting, Cloud Functions en Python—, en continuidad con `paneles`. Acá viven el estudio, la pauta, la convocatoria, el registro de participación, los incentivos y la administración.
- **Plano de medios** (la sesión en vivo): un servicio de larga duración en **Cloud Run o GKE**, no en Cloud Functions. Una sesión de noventa minutos mantiene abiertos un WebSocket hacia la capa de voz y el consumo de las pistas del SFU; eso excede el modelo de ejecución de una función y no se resuelve con configuración. El orquestador de sesión, el director y el grabador viven acá.
- **SFU WebRTC de terceros** para la sala multiparte, con estado caliente de sesión en Redis (Memorystore) y persistencia en Postgres.
- **Capa de voz** sobre GPT-Live-1.
- **Embeddings** con el mismo proveedor que `paneles` (Voyage `voyage-3.5`), detrás de la misma interfaz.

La separación importa porque el plano de control puede caerse sin cortar una sesión en curso, y porque los dos tienen perfiles de escalado opuestos: el de control es ráfagas cortas, el de medios son procesos largos y pocos.

### Personas

- **Coordinador de campo cuali** — arma las sesiones, convoca, confirma, reemplaza, recibe, liquida incentivos. Es quien más usa el sistema.
- **Moderador / investigador** — define la pauta, conduce (o supervisa la conducción), analiza, arma la entrega.
- **Participante** — es la `persona` de la bóveda. Recibe la invitación, consiente, entra a la sala, participa, cobra el incentivo.
- **Analista** — consulta el corpus cuali, solo o cruzado con el cuantitativo.
- **DPO / cumplimiento** — consentimiento de grabación y de difusión, retención de medios, bajas en cascada.

---

## 2. Fases

Cada fase se especifica con: objetivo, alcance, historias, requisitos con criterios de aceptación, dependencias, criterios de salida (DoD), métricas y riesgos.

**Sobre el orden.** Esta numeración empieza en 1: lo que en borradores anteriores era la «Fase 0» pasó a ser la **Fase 5 de `paneles` — Externalización de las bóvedas**, porque el trabajo es sobre el esquema de ese sistema, toca su código y su criterio de salida son sus pruebas. Está especificada en `paneles/specs/SPEC_fase5.md` y es precondición de despliegue de la Fase 1 de acá. El embudo de convocatoria va primero porque es la condición de posibilidad de todo lo demás: no se pueden hacer doscientas entrevistas si la convocatoria es una persona mandando mensajes. El corpus semántico (Fase 3) va **antes** que la moderación automatizada porque entrega valor con el volumen actual y no depende de que la IA sepa moderar. Las Fases 4 y 5 son las que rompen el techo de escala, y son las que cargan el supuesto más riesgoso del proyecto.

---

### Fase 1 — Estudio cualitativo y embudo de convocatoria

**Objetivo.** Tener operativo el campo cualitativo sin nada de inteligencia artificial y sin sala virtual: definir un estudio con su pauta, seleccionar candidatos contra las bóvedas, convocarlos con un embudo de estados, confirmar, recibir y liquidar el incentivo. Al cierre, Equipos puede correr un focus group presencial entero desde el sistema.

**Alcance — dentro**
- Entidad `estudio_cuali` con `ref_estudio` compartido con la bóveda y el semántico.
- **Pauta** como objeto de primera clase: tópicos ordenados, con objetivo, tiempo estimado y repreguntas previstas. Es el instrumento del cualitativo, el equivalente al cuestionario.
- Entidad `sesion`: modalidad (presencial / virtual), tipo (IDI / grupo), fecha, lugar o sala, moderador, cupo objetivo y cuotas de composición de esa sesión.
- **Selección de candidatos**: consulta demográfica, semántica o mixta contra las vistas de bóveda y el store semántico, con el gate de consentimiento y fatiga ya aplicados por R0.1.
- **Filtro anti-panelista profesional**: exclusión por participación cualitativa reciente, configurable por ventana temporal y por categoría de estudio.
- **Embudo de convocatoria** con estados explícitos: `candidato → invitado → contactado → aceptó → confirmado → asistió` y sus ramas `rechazó`, `no contactable`, `no-show`, `reemplazado`.
- **Sobre-reclutamiento y lista de espera**: convocar más de lo necesario contra un ratio configurable, y reemplazo que revalida la cuota de composición al momento de reemplazar.
- **Recepción / check-in**: registro de asistencia con hora, y verificación de identidad contra la bóveda.
- **Módulo de incentivos propio**: catálogo de regalos, compromiso por participación, entrega y estado. No son puntos ni canje: el incentivo cualitativo es un regalo por sesión, con un valor sustancialmente mayor al de una encuesta. Es un módulo distinto del de gamificación de `paneles`, no una extensión.
- **Registro de participación cualitativa propio**, en las bases de COLOQUIO. No se escribe en la bóveda.
- **Historial de participación por persona** para el analista: cuántas veces participó, en qué estudios, en qué rol y cuándo.

**Alcance — fuera:** sala virtual, grabación, transcripción, IA, análisis, entrega al cliente.

**Historias de usuario**
- Como moderador, quiero cargar la pauta del estudio con sus tópicos y tiempos, para que después el sistema sepa contra qué medir la cobertura.
- Como coordinador de campo, quiero seleccionar candidatos combinando criterio demográfico y lo que dijeron en estudios anteriores, para armar un grupo con la gente correcta y no con la que tengo a mano.
- Como coordinador de campo, quiero que el sistema excluya automáticamente a quien participó de un grupo de la misma categoría en los últimos meses, para no sentar panelistas profesionales.
- Como coordinador de campo, quiero convocar doce para sentar ocho y que el sistema me diga a quién reemplazar cuando alguien cae, sin romper la cuota del grupo.
- Como coordinador de campo, quiero registrar la llegada de cada participante, para saber en el momento con cuántos cuento.
- Como analista, quiero ver cuántas veces participó una persona y en qué estudios, en el momento de armar el grupo, para decidir si la llamo o no.
- Como coordinador de campo, quiero asignar y registrar el regalo de cada participante, porque el incentivo del cuali no son puntos.

**Requisitos y criterios de aceptación**

R1.1 — Estudio y pauta.
- Dada la creación de un estudio cualitativo, cuando se confirma, entonces se emite un `ref_estudio` y queda vinculable a encuestas del mismo estudio en la bóveda.
- Dada una pauta, cuando se guarda, entonces sus tópicos quedan ordenados, con objetivo y tiempo estimado, y son referenciables desde cualquier sesión del estudio.
- Una sesión no se puede abrir sin pauta asociada.

R1.2 — Selección de candidatos contra las bóvedas.
- Dada una consulta demográfica pura, cuando se ejecuta, entonces se resuelve contra la vista de bóveda y no accede al store semántico.
- Dada una consulta que incluye criterio semántico, cuando se ejecuta, entonces usa el motor de consulta de `paneles` y devuelve `id_persona` rankeados.
- Dada cualquier selección, entonces ninguna persona sin consentimiento vigente para contacto/participación aparece en el resultado, y esto se garantiza por la vista, no por el filtro de la aplicación.

R1.3 — Filtro de fatiga cualitativa.
- Dada una ventana configurable y una categoría de estudio, cuando se selecciona, entonces se excluye a quien participó de una sesión cualitativa de esa categoría dentro de la ventana.
- Dado un intento de convocar manualmente a alguien excluido, entonces el sistema lo bloquea y exige una anulación explícita, registrada con motivo y usuario.

R1.4 — Embudo de convocatoria.
- Dada una convocatoria, cuando cambia de estado, entonces queda registrado el estado anterior, el nuevo, el canal, el timestamp y el usuario o proceso que lo produjo.
- Dado un estado terminal (`rechazó`, `no contactable`, `no-show`), entonces la persona no puede volver al embudo de esa sesión sin una acción explícita.
- El dato de contacto usado para convocar se obtiene por R0.2 y queda auditado.

R1.5 — Sobre-reclutamiento y reemplazo con revalidación de cuota.
- Dado un cupo objetivo y un ratio de sobre-reclutamiento, cuando se lanza la convocatoria, entonces el sistema propone una lista de invitación que cumple la cuota de composición **asumiendo** la tasa de caída configurada.
- Dado un `no-show` o una baja de último momento, cuando se pide un reemplazo, entonces el sistema propone candidatos que restituyen el segmento perdido, no cualquiera de la lista de espera.
- Dado que ningún candidato disponible restituye el segmento, entonces el sistema lo informa explícitamente en vez de proponer un reemplazo que rompe la cuota en silencio.

R1.6 — Recepción y verificación de identidad.
- Dada una sesión en curso de check-in, cuando llega un participante, entonces se registra su asistencia con hora y queda vinculada a su `id_persona`.
- Dado alguien que se presenta y no está confirmado para esa sesión, entonces el sistema lo señala antes de dejarlo entrar.

R1.7 — Incentivos como módulo propio.
- Existe un catálogo de regalos con su valor, distinto del catálogo de premios de `paneles`. El incentivo cualitativo no se expresa en puntos ni pasa por el ledger de gamificación.
- Dada una asistencia registrada, cuando se cierra la sesión, entonces queda un compromiso de incentivo por participante, con el regalo asignado y su estado (`comprometido → entregado`).
- El sistema registra el compromiso y la entrega; no ejecuta el pago ni resuelve su tratamiento fiscal.

R1.8 — Registro de participación propio.
- Dada una asistencia registrada, cuando se cierra la sesión, entonces la participación queda escrita en el store de COLOQUIO, con estudio, sesión, rol y fecha.
- COLOQUIO **no escribe** participación en la bóveda. El registro cualitativo es suyo y él lo administra.
- El filtro de fatiga cualitativa (R1.3) se resuelve contra este registro, no contra `umbral_fatiga` de `paneles`.

R1.9 — Historial de participación por persona.
- Dado un `id_persona`, cuando el analista abre su historial cualitativo, entonces ve cuántas veces participó, en qué estudios, en qué modalidad y cuándo fue la última vez.
- El historial es visible en el momento de armar la sesión, no solo como reporte posterior: es lo que permite decidir a quién no volver a llamar.

**Dependencias:** **Fase 5 de `paneles` desplegada** (externalización de las bóvedas: consentimiento reformulado, superficie de lectura, cascada extensible y rol propio). Consulta semántica de `paneles` operativa (ya lo está, Fase 2 de ese sistema).

**Criterios de salida (DoD).** Se puede crear un estudio con pauta, seleccionar candidatos por criterio mixto, convocar con sobre-reclutamiento, reemplazar a un caído restituyendo su segmento, registrar la recepción de ocho personas, y cerrar la sesión con participación registrada e incentivos asignados. El analista ve el historial cualitativo de una persona antes de convocarla. Un focus group presencial se corre entero desde el sistema. Cero acceso a tablas de bóveda fuera de las vistas; cero escrituras de COLOQUIO en la bóveda.

**Métricas de la fase**
- Tasa de show (asistieron / confirmados) medida por primera vez.
- Tiempo de convocatoria: de lanzamiento a cupo confirmado.
- Ratio de sobre-reclutamiento efectivamente necesario, contra el configurado.
- Incidencia de re-convocatoria bloqueada por el historial cualitativo.

**Riesgos y preguntas de la fase**
- **[producto]** La ventana y la categorización del filtro anti-panelista-profesional son una definición metodológica, no técnica. Hay que fijarla con los investigadores antes de implementar.
- **[ingeniería]** `umbral_fatiga` de `paneles` es **por panel** y cuenta convocatorias a encuestas. No sirve para el filtro cualitativo, que es por categoría de estudio y por participación efectiva en sesión. Son dos mecanismos separados por diseño: el de la bóveda (R0.1) evita sobre-convocar a encuestas; el de COLOQUIO (R1.3, contra su propio registro) evita al panelista profesional.
- **[producto]** **Consecuencia asumida de que el registro sea propio:** `paneles` no se entera de que una persona estuvo en tres focus groups, así que para su muestreo esa persona sigue pareciendo descansada. Es una decisión, no un olvido, y hay que tomarla a ojos abiertos (ver Preguntas abiertas transversales). La vuelta atrás es barata: una vista de solo lectura desde el store de COLOQUIO, que `paneles` consulte si algún día quiere una fatiga unificada. No requiere que COLOQUIO escriba nada.
- **[datos]** La selección semántica de candidatos depende de que las personas del panel tengan contenido embebido. Para segmentos poco encuestados, la selección se degrada a demográfica pura.
- **[operaciones]** El reemplazo con revalidación de cuota es el requisito más difícil de la fase y el que más valor operativo tiene. No cortarlo.

---

### Fase 2 — Sala virtual, registro atribuido y copiloto

**Objetivo.** Montar la espina dorsal técnica de todo lo que viene: audio por participante, transcripción atribuida en vivo, y un agente que lee esa transcripción contra la pauta. En esta fase el agente **no habla**: asiste al moderador humano. Al cierre, una sesión virtual produce su transcripción con hablante identificado como subproducto, sin desgrabación posterior.

**Sobre la atribución de hablante.** La identidad del que habla **no se resuelve por diarización**. Cada participante entra por el portal web autenticado con su `id_persona`, y cada uno aporta su propia pista de audio. Quién habla se sabe por construcción, no por algoritmo. Ésa es la razón de que el portal sea un requisito y no una comodidad.

**Alcance — dentro**
- Portal de participante: acceso autenticado a la sala, consentimiento de grabación en el momento de entrar, prueba de audio y video.
- Sala virtual sobre SFU de terceros, con pistas separadas por participante.
- Grabación: mezcla para revisión humana, más pistas individuales para el procesamiento.
- **Transcripción por pista**, en vivo, produciendo turnos con `id_persona`, timestamp de inicio y fin, texto y confianza.
- **Agente director** (modelo de razonamiento en backend, no la capa de voz): lee la transcripción atribuida contra la pauta y mantiene estado de cobertura de tópicos y de balance de participación.
- **Copiloto del moderador**: panel en vivo con tópicos cubiertos y pendientes, tiempo por tópico, quién no habló y hace cuánto, y repreguntas sugeridas.
- Ingesta de grabaciones de sesiones **presenciales** por archivo, para que el resto del pipeline sirva igual a lo presencial (con atribución manual o asistida, que es el caso degradado aceptado).
- Consentimiento de grabación audiovisual como finalidad propia.

**Alcance — fuera:** que el sistema hable; análisis semántico del corpus; entrega al cliente.

**Historias de usuario**
- Como participante, quiero entrar a la sala con un link y saber claramente que me están grabando y para qué, antes de que empiece.
- Como moderador, quiero ver en vivo qué tópicos de la pauta ya cubrí y cuáles me faltan, para no llegar al final con un tema sin tocar.
- Como moderador, quiero que me avise quién lleva mucho rato sin hablar, para poder darle lugar.
- Como moderador, quiero que al terminar la sesión la transcripción ya esté hecha y con cada frase atribuida a quien la dijo, para no pagar desgrabación.
- Como investigador, quiero subir la grabación de un grupo presencial y que entre al mismo pipeline, para no tener dos flujos.

**Requisitos y criterios de aceptación**

R2.1 — Portal de participante y consentimiento en sala.
- Dado un participante confirmado, cuando abre su link, entonces se autentica y el sistema lo asocia a su `id_persona` y a esa sesión.
- Dado que el participante no otorga el consentimiento de grabación, entonces no ingresa a la sala y su convocatoria pasa a un estado terminal registrado.
- El consentimiento de grabación se registra en la bóveda como finalidad separada, con versión del texto y timestamp, igual que los demás.

R2.2 — Pistas separadas.
- Dada una sesión virtual con N participantes, cuando se graba, entonces quedan N pistas de audio individuales más la mezcla, todas con la misma base de tiempo.
- Cada pista queda vinculada al `id_persona` de su participante.

R2.3 — Transcripción atribuida.
- Dada una sesión en curso, cuando alguien habla, entonces se produce un turno con `id_persona`, inicio, fin, texto y confianza, disponible en vivo.
- Dado un solapamiento de habla entre dos participantes, entonces se producen dos turnos con sus tiempos reales, no uno.
- Dada una sesión terminada, entonces la transcripción completa queda disponible sin intervención manual.

R2.4 — Agente director: cobertura de pauta.
- Dada una pauta y una transcripción en curso, cuando el agente evalúa, entonces mantiene por cada tópico su estado (no tocado / en curso / cubierto) y el tiempo transcurrido en él.
- Dado un tópico marcado como cubierto, entonces el sistema puede mostrar los turnos que sustentan esa marca.

R2.5 — Agente director: balance de participación.
- Dada una sesión grupal en curso, cuando el agente evalúa, entonces mantiene por participante su tiempo de habla acumulado y el tiempo desde su última intervención.
- Dado un participante por debajo de un umbral configurable de participación, entonces el copiloto lo señala.

R2.6 — Copiloto del moderador.
- Dado el panel del copiloto, cuando el moderador lo mira durante la sesión, entonces ve cobertura de pauta, reloj por tópico, balance de participación y repreguntas sugeridas.
- El copiloto no emite audio ni interviene en la sala bajo ninguna circunstancia en esta fase.

R2.7 — Ingesta de grabación presencial.
- Dado un archivo de audio o video de una sesión presencial y su lista de asistentes, cuando se ingesta, entonces entra al mismo pipeline de turnos y segmentos.
- Dado que no hay pistas separadas, entonces el sistema produce turnos con hablante propuesto y los marca como **no verificados** hasta confirmación humana.

R2.8 — Medios y retención.
- Las grabaciones se guardan en Cloud Storage en la región de la bóveda, cifradas, y la base guarda la referencia, nunca el objeto.
- Dada la baja de una persona, cuando corre la cascada, entonces sus pistas individuales se borran y la mezcla queda marcada para tratamiento según la política de retención definida.

**Dependencias:** Fase 1. Elección de proveedor de SFU. Definición legal de la retención de medios.

**Criterios de salida (DoD).** Ocho personas entran a una sala virtual desde el portal, consienten la grabación, la sesión se graba con pistas separadas, y al terminar existe una transcripción completa con cada turno atribuido a su `id_persona`, más un registro de cobertura de pauta que el moderador vio en vivo. Una grabación presencial subida produce el mismo artefacto en su versión no verificada.

**Métricas de la fase**
- % de sesiones virtuales cuya transcripción no requiere corrección manual de atribución (objetivo: prácticamente todas, dado que la atribución es por construcción).
- Costo de desgrabación eliminado por sesión.
- Latencia del copiloto: tiempo entre que algo se dice y aparece en el panel.
- Cobertura de pauta declarada por el agente contra la evaluación del moderador (validación manual).

**Riesgos y preguntas de la fase**
- **[ingeniería]** La elección del SFU condiciona todo lo que viene. Ver Preguntas abiertas transversales.
- **[legal]** Grabación de voz e imagen de personas identificadas: definir si califica como categoría especial bajo la interpretación de URCDP y cuál es el plazo de retención. *Bloqueante para grabar en producción.*
- **[producto]** El copiloto puede distraer más de lo que ayuda. El diseño del panel es un problema de atención, no de información: menos es más.
- **[costos]** Transcripción por pista multiplica el costo por número de participantes. Medir en la primera sesión real.

---

### Fase 3 — Corpus cualitativo: ingesta semántica, consulta cruzada y entrega

**Objetivo.** Convertir cada sesión en activo reutilizable. El verbatim entra al corpus consultable junto con las respuestas cuantitativas de las mismas personas, y el cliente recibe **las dos cosas que pide: el informe y el clip**. Esta fase entrega valor con el volumen de cualitativo que Equipos hace **hoy**, sin depender de que la moderación automatizada funcione.

**Alcance — dentro**
- **Segmentación**: agrupación de turnos en segmentos temáticamente coherentes, atados a tópicos de la pauta.
- **Despersonalización obligatoria**: pasada de redacción de PII hablada (nombres, direcciones, lugares de trabajo, teléfonos) sobre el texto del segmento, antes de cualquier escritura del lado semántico.
- Ingesta al store semántico: embedding del segmento despersonalizado, con `id_persona`, `ref_estudio` y tópico. Nada más.
- Consentimiento de **uso semántico cualitativo** como finalidad separada.
- **Consulta cruzada**: el analista pregunta y recibe resultados que mezclan verbatims de sesiones cualitativas y respuestas abiertas de encuestas, de las mismas personas.
- **Entrega, en sus dos formas.** El cliente quiere el informe **y** el clip, no uno u otro. (a) **Material de informe**: evidencia organizada por tópico de la pauta, con los verbatims que la sustentan y su procedencia, de modo que el investigador escriba el informe apoyado en el sistema en vez de releer transcripciones. (b) **Clip**: el fragmento de audio o video de la cita, con timecode, sujeto al consentimiento de difusión.
- Consentimiento de **difusión de verbatim** como finalidad separada: el clip sale de Equipos hacia el cliente, y eso no está cubierto por el consentimiento de grabación.

**Alcance — fuera:** codificación automática presentada como análisis final; generación del informe.

**Historias de usuario**
- Como analista, quiero preguntarle al corpus qué dijo la gente sobre un tema y que me traiga tanto verbatims de grupos como respuestas abiertas de encuestas, para no tener dos búsquedas.
- Como analista, quiero ver si la misma persona dijo una cosa en el grupo y contestó otra en la encuesta, porque ahí está el hallazgo.
- Como investigador, quiero exportar una cita con su clip de cuarenta segundos, porque es lo que el cliente va a poner en la presentación.
- Como investigador, quiero que el sistema me junte la evidencia por tópico de la pauta, para escribir el informe apoyado en el material y no releyendo transcripciones.
- Como DPO, quiero que ningún nombre propio dicho en voz alta termine en el store semántico.
- Como investigador, quiero que un estudio nuevo pueda apoyarse en los verbatims de estudios anteriores, para no volver a preguntar lo mismo.

**Requisitos y criterios de aceptación**

R3.1 — Segmentación por tópico.
- Dada una transcripción y la pauta de su sesión, cuando se segmenta, entonces cada segmento queda atado a un tópico y conserva los `id_persona` de los turnos que lo componen.
- Un segmento puede contener turnos de varios participantes: la interacción es el dato, no el ruido.

R3.2 — Despersonalización obligatoria.
- Dado un segmento, cuando se prepara para el store semántico, entonces su texto pasa por redacción de PII y el resultado queda marcado como despersonalizado.
- Dado un segmento no marcado como despersonalizado, entonces la escritura del lado semántico se rechaza. Este rechazo ocurre en la base (R0.5), no solo en la aplicación.
- El texto original, sin redactar, permanece únicamente en el store cuali.

R3.3 — Gate de consentimiento semántico cualitativo.
- Dado un participante sin consentimiento vigente para uso semántico cualitativo, entonces sus segmentos no se ingestan al store semántico, aunque la sesión sí se haya grabado.
- La finalidad es distinta de `uso_semantico` del cuantitativo y de `grabacion_av`.

R3.4 — Consulta cruzada cuali-cuanti.
- Dada una consulta semántica, cuando se ejecuta sobre el corpus completo, entonces devuelve resultados de ambos tipos de contenido, cada uno identificado por su procedencia.
- Dado un `id_persona`, cuando se pide su vista integrada, entonces se muestran sus verbatims y sus respuestas de encuesta en una sola línea de tiempo.

R3.5 — Material de informe por tópico.
- Dado un estudio con varias sesiones, cuando se pide el material de informe, entonces se entrega la evidencia agrupada por tópico de la pauta, con los verbatims que la sustentan y la sesión de la que salen.
- El sistema organiza y evidencia; no redacta el informe ni presenta conclusiones como propias.

R3.6 — Exportación de verbatim con clip.
- Dado un segmento, cuando se exporta, entonces se entrega el texto con su timecode y el fragmento de medio correspondiente.
- Dado un participante sin consentimiento de difusión vigente, entonces el clip no se exporta y el verbatim se entrega anonimizado o no se entrega, según la política del estudio.

R3.7 — Consentimiento de difusión.
- La difusión de un clip identificable fuera de Equipos requiere una finalidad de consentimiento propia, registrada con versión de texto y timestamp.

**Dependencias:** Fase 2. Definición legal de las dos finalidades nuevas. Motor semántico de `paneles`.

**Criterios de salida (DoD).** Una sesión transcrita produce segmentos despersonalizados e indexados; una consulta semántica devuelve verbatims y respuestas de encuesta juntos, con procedencia; el material de informe de un estudio sale agrupado por tópico con su evidencia; un verbatim se exporta con su clip solo si hay consentimiento de difusión; una auditoría del store semántico no encuentra un solo nombre propio.

**Métricas de la fase**
- Precisión de la despersonalización: nombres propios detectados / nombres propios presentes, sobre un set de prueba anotado a mano. Objetivo explícito y alto: es el requisito de cumplimiento de la fase.
- % de estudios cualitativos nuevos que consultan el corpus de estudios anteriores.
- Tiempo entre fin de sesión y corpus consultable.
- Uso de la exportación de clips por estudio.

**Riesgos y preguntas de la fase**
- **[legal/datos]** La despersonalización no es anonimización. Un verbatim puede reidentificar por contenido aunque no tenga nombres ("el dueño de la panadería de la esquina de mi barrio"). Hay que decidir si eso se acepta, igual que `paneles` ya aceptó que los datos siguen siendo personales.
- **[producto]** La granularidad del segmento es la decisión de diseño de la fase: turno, intervención temática o intercambio completo. Un segmento chico pierde el contexto de la interacción; uno grande diluye el embedding. Requiere calibración con datos reales, como la que ya se hizo para la Fase 2 de `paneles`.
- **[producto]** Mezclar verbatims conversacionales con respuestas de encuesta en el mismo espacio vectorial puede degradar el ranking de ambos. Medirlo antes de asumirlo.

---

### Fase 4 — Moderación automatizada: entrevista en profundidad 1:1

**Objetivo.** Que el sistema conduzca la entrevista. Es el caso donde la tecnología está madura —GPT-Live-1 es full duplex y está diseñado para conversación uno a uno con delegación de razonamiento al backend— y es el que carga el supuesto crítico del proyecto: si la IA no entrevista bien en rioplatense, la apuesta de escala no existe.

**La arquitectura, en tres partes.** Los oídos son la transcripción por pista de la Fase 2. El cerebro es el agente director de la Fase 2, ahora con capacidad de decidir la próxima intervención. La boca es una sesión de GPT-Live-1 que recibe instrucciones por el canal de datos y habla. El modelo de voz no razona sobre la pauta: ejecuta. Es literalmente el patrón de delegación al backend que la documentación de la API recomienda.

**Alcance — dentro**
- Sesión de voz conversacional integrada a la sala, con persona, tono y ritmo configurables por estudio.
- Agente director con capacidad de **decidir intervención**: avanzar de tópico, repreguntar, pedir un ejemplo, cerrar.
- Política de repregunta derivada de la pauta: cada tópico lleva sus repreguntas previstas, y el director elige.
- Transparencia obligatoria: el participante sabe, antes de empezar, que lo entrevista un sistema automatizado.
- **Escalamiento a humano**: condiciones bajo las cuales la sesión se deriva a un moderador o se termina.
- Panel de supervisión: un investigador puede observar N entrevistas en curso e intervenir en cualquiera.

**Alcance — fuera:** grupos; temas sensibles; idiomas distintos del español rioplatense.

**Historias de usuario**
- Como investigador, quiero lanzar cincuenta entrevistas en profundidad en una semana sin cincuenta horas de moderador, para poder vender un cualitativo con n que hoy no puedo.
- Como investigador, quiero que la entrevista siga mi pauta y repregunte donde yo repreguntaría, para que el material sirva.
- Como participante, quiero saber desde el principio que estoy hablando con un sistema, para decidir si sigo.
- Como participante, quiero poder pedir hablar con una persona si la cosa se pone incómoda.
- Como investigador, quiero mirar las entrevistas en curso y meterme en una si veo que se está yendo de tema.

**Requisitos y criterios de aceptación**

R4.1 — Conducción según pauta.
- Dada una pauta con tópicos, cuando la sesión transcurre, entonces el sistema cubre los tópicos en orden, con el tiempo asignado, y no cierra dejando tópicos sin tocar salvo que se agote el tiempo máximo.
- Dada una respuesta que ya cubre un tópico posterior, entonces el sistema lo registra como cubierto y no lo vuelve a preguntar mecánicamente.

R4.2 — Repregunta.
- Dada una respuesta vaga, corta o evasiva, cuando el director evalúa, entonces genera una repregunta antes de avanzar.
- Dada una repregunta ya intentada sin resultado, entonces el sistema avanza en vez de insistir. No hay bucles.

R4.3 — Transparencia.
- Dado el ingreso a la sala, cuando empieza la sesión, entonces el participante recibe y acepta una declaración explícita de que la conducción es automatizada.
- Esa aceptación se registra como consentimiento con finalidad propia.

R4.4 — Manejo de interrupción.
- Dado que el participante empieza a hablar mientras el sistema habla, entonces el sistema se detiene y escucha.
- El trabajo pendiente del backend no se cancela automáticamente por una interrupción; el sistema no afirma haber hecho algo hasta que el backend lo confirma.

R4.5 — Escalamiento y corte.
- Dado que el participante pide hablar con una persona, entonces la sesión se marca para escalamiento y se le ofrece reprogramar con moderador humano.
- Dado que el participante manifiesta malestar, o el tema deriva a una categoría sensible definida por el estudio, entonces el sistema cierra la entrevista con cortesía y la marca para revisión humana.
- Dada una falla de la capa de voz, entonces la sesión degrada a un estado recuperable: la transcripción parcial se conserva y se puede reprogramar.

R4.6 — Supervisión en vivo.
- Dado un investigador supervisando, cuando abre el panel, entonces ve las sesiones en curso con su cobertura de pauta y puede entrar a cualquiera.
- Dado que el supervisor entra, entonces la conducción automatizada cede el control y el participante es informado.

R4.7 — Control de costo por sesión.
- Dado un estudio, cuando se configura, entonces tiene un tope de duración por entrevista, y el sistema cierra al alcanzarlo.
- El costo de capa de voz por sesión queda registrado y es reportable por estudio. La capa de voz se factura **por duración de sesión abierta**, incluidos los silencios y el tiempo en que el backend está trabajando: cerrar la sesión a tiempo es parte del control de costo, no una prolijidad.

R4.8 — Neutralidad de la conducción.
- El sistema no formula preguntas inductivas: pregunta qué impresión genera algo, no si no parece más moderno.
- El sistema no evalúa ni premia las respuestas: no dice "muy bien", "exactamente" ni "es lo que queríamos saber". Agradece y abre.
- El sistema nunca menciona métricas internas de participación al participante. Que el director sepa que alguien habló poco no habilita a decírselo.
- La neutralidad se verifica sobre transcripciones reales con un chequeo explícito, no se asume del prompt.

R4.9 — La voz del participante es contenido, no instrucción.
- Dado un participante que dice algo con forma de instrucción, entonces el sistema lo trata como material de investigación y no lo obedece. La jerarquía de control es: reglas del sistema, reglas del estudio, instrucción del investigador, guía del director, contenido del participante.

R4.10 — Recuperación de la sesión de voz.
- El estado metodológico se persiste como snapshot y no reside únicamente en el contexto del modelo; ante una caída, el sistema abre una sesión nueva, le restituye el snapshot y retoma.

**Dependencias:** Fases 2 y 3. **Y el resultado de la prueba de concepto descrita en Preguntas abiertas transversales**, que debe correrse antes de construir esta fase.

**Criterios de salida (DoD).** Veinte entrevistas en profundidad reales conducidas por el sistema, con cobertura completa de pauta, sin bucles de repregunta, con escalamiento funcionando, y con material que un investigador de Equipos califica como utilizable para análisis. El costo por entrevista es conocido.

**Métricas de la fase**
- Cobertura de pauta por entrevista automatizada, contra la de un moderador humano sobre la misma pauta.
- Tasa de abandono del participante durante la entrevista.
- Tasa de escalamiento a humano.
- Riqueza del material: longitud media de respuesta y densidad de elaboración espontánea, contra el benchmark humano.
- Costo por entrevista completada, comparado con el costo del moderador.

**Riesgos y preguntas de la fase**
- **[producto]** *Éste es el riesgo principal del proyecto entero.* Que la entrevista automatizada produzca material más pobre que la humana. No se mitiga con ingeniería: se mide.
- **[producto]** La transparencia obligatoria puede sesgar la respuesta —la gente le habla distinto a una máquina—. Es un problema metodológico real y hay que caracterizarlo, no esconderlo.
- **[producto]** El escalamiento por tema sensible es un clasificador con falsos negativos. Definir la política conservadora: ante la duda, cerrar y derivar.
- **[costos]** A cincuenta entrevistas por estudio, el costo de la capa de voz deja de ser despreciable. Modelarlo antes de cotizar.

---

### Fase 5 — Moderación automatizada: focus group virtual N:N

**Objetivo.** Que el sistema modere un grupo. Es la fase más ambiciosa y la menos probada: la documentación de la API de voz no contempla múltiples hablantes, y la conducción de un grupo no es entrevistar a varios en serie, sino administrar una dinámica.

**Qué es capacidad documentada y qué es arquitectura nuestra.** GPT-Live es una capa de voz **uno a uno**: OpenAI no documenta sala multiparte, múltiples hablantes ni diarización. La sala de N personas, el SFU, la atribución por pista, el algoritmo de hablante activo y el director son **piezas que construimos nosotros**, no funcionalidades del modelo. Que la arquitectura sirva para N:N es una inferencia razonable, no una capacidad garantizada por el proveedor, y el riesgo se asume en consecuencia.

**Por qué la falta de diarización no bloquea.** La identidad del hablante no sale del audio: sale del login y de la pista. La transcripción atribuida (Fase 2) la produce el orquestador, y al modelo de voz se le inyecta quién está hablando por los canales de contexto documentados —`session.thinking.append` para contexto que no debe pronunciar, `session.instructions.append` para cambiar su comportamiento, `session.commentary.append` para lo que sí debe decir—. La atribución nunca dependió del modelo.

**El problema real es otro, y es el que gobierna esta fase: el modelo decide solo cuándo habla.** La documentación de migración de GPT-Live es explícita: el audio se transmite de forma continua, el modelo decide cuándo hablar, y los disparadores manuales de turno desaparecen; no hay evento de cliente que cree, cancele o trunque una respuesta. **No existe un parámetro de VAD que se pueda ajustar** —`server_vad`, `semantic_vad`, `eagerness` son de la API Realtime anterior y no aplican acá—. Esto importa porque el turno es el oficio del moderador de grupo: en una conversación uno a uno, "el otro dejó de hablar" es una señal confiable de fin de turno; en un grupo de ocho, dos segundos de silencio son casi siempre una persona cediéndole el lugar a otra, y meterse ahí es exactamente lo que hace un mal moderador.

**La palanca que queda es el audio que le damos de escuchar.** Ésa es la consecuencia de diseño central de la fase: como no se puede pedirle al modelo que espere más, el silencio del moderador se administra **controlando qué oye**. El orquestador mantiene siempre las pistas individuales y genera dinámicamente lo que entra a la sesión de voz; mientras el director evalúa que la conversación grupal es productiva, atenúa o retiene ese ingreso, y lo abre —o inyecta `commentary`— cuando decide que corresponde intervenir. **La compuerta de audio del orquestador reemplaza a la perilla de VAD que no existe.** Si esto no funciona, no hay configuración que lo arregle: es rediseño.

**Alcance — dentro**
- Una sesión de voz conversacional por sala, no por participante.
- Director con **política de turnos**: a quién darle la palabra, cuándo cortar al dominante, cuándo abrir al grupo.
- Balanceo de participación activo: el director interpela por nombre a quien no habló.
- Manejo de solapamiento: qué hace el sistema cuando hablan tres a la vez.
- Técnicas de grupo: contraste ("¿alguien piensa distinto?"), profundización sobre lo que otro dijo, cierre de ronda.
- Modo **moderación mixta**: humano conduce, el sistema interviene solo para tareas acotadas y delegadas.
- **Estímulos**: mostrar a la sala un concepto, un packaging, una pieza de comunicación o un video, con el moderador enterado de qué está visible y desde cuándo, y con el protocolo de exposición que evita sesgo (mostrar, esperar, pedir reacción espontánea, recién después profundizar por atributos). Sin esto el sistema no sirve para evaluación de concepto ni de packaging, que son buena parte de lo que se vende.
- **Rol observador**: el cliente mira la sesión sin estar en ella.

**Alcance — fuera:** grupos de más de un tamaño máximo a definir; temas sensibles; ejercicios proyectivos y dinámicas con producción (collages, dramatizaciones), que quedan para una extensión posterior.

**Historias de usuario**
- Como investigador, quiero correr grupos sin depender de la agenda de un moderador, para multiplicar el volumen de cualitativo grupal.
- Como investigador, quiero que el sistema le dé lugar a los callados y contenga al que acapara, porque es la mitad del oficio de moderar.
- Como participante de un grupo, quiero que no me interrumpan cada vez que hablo al mismo tiempo que otro, porque así no se conversa.
- Como investigador, quiero poder usar el sistema solo para partes del grupo y moderar yo el resto.

**Requisitos y criterios de aceptación**

R5.1 — Sesión única por sala.
- Dada una sala con N participantes, cuando se habilita la moderación automatizada, entonces existe **una sola** sesión de voz para la sala, y el costo escala con la duración, no con N.
- El director recibe la transcripción atribuida de todas las pistas.
- **Orden de magnitud, para dimensionar:** la capa de voz se factura por duración (US$0,05 por minuto a la fecha de este documento), así que un grupo de ocho personas por noventa minutos cuesta **unos US$4,50 de capa de voz, no ocho veces eso**. Lo que sí escala con N es la transcripción por pista, que es barata y además ya es necesaria para el registro atribuido de la Fase 2, con moderación automatizada o sin ella. El director escala con el volumen de conversación, no con la cantidad de participantes. Una arquitectura de una sesión de voz **por participante** multiplicaría el costo por N y perdería el contexto compartido: queda explícitamente descartada.

R5.2 — Política de turnos.
- Dado un participante que no intervino por encima de un umbral, cuando el director evalúa, entonces genera una interpelación nominal.
- Dado un participante cuyo tiempo de habla supera un umbral relativo, entonces el director genera una intervención que redirige sin descalificar.
- Toda decisión de turno queda registrada con su motivo, para poder auditar la conducción después.

R5.3 — Solapamiento y conversación cruzada.
- Dado que dos o más participantes hablan simultáneamente, entonces el sistema no interviene inmediatamente: espera a que la superposición se resuelva, dentro de un límite configurable.
- Dado que la superposición persiste más allá del límite, entonces el sistema interviene para ordenar el turno.
- El detector distingue **asentimiento breve** ("sí", "claro", "exacto", "mmm") de **solapamiento significativo**, combinando duración, transcripción e identidad. Un asentimiento nunca dispara intervención: es parte de cómo la gente escucha.

R5.4 — Recuperación del turno interrumpido.
- Dado un participante que empezó a hablar y quedó tapado, cuando se resuelve la superposición, entonces el sistema lo registra en una cola de turnos pendientes y vuelve a él nominalmente.
- La cola se vacía antes de cerrar el tópico: nadie queda con la idea a medias porque lo pisaron.

R5.5 — Técnicas de grupo.
- Dado un tópico con posiciones homogéneas, cuando el director evalúa, entonces puede generar una intervención de contraste.
- Dada una afirmación de un participante, entonces el director puede pedirle a otro que reaccione a ella, nominalmente.
- Toda intervención del director cabe en el presupuesto de contexto de la capa de voz (**500 tokens por inyección**). La guía metodológica larga vive en el backend; lo que baja a la boca es una instrucción corta.

R5.6 — Compuerta de audio del orquestador.
- El orquestador mantiene **siempre** las pistas individuales y genera dinámicamente lo que ingresa a la sesión de voz. No se envía la mezcla cruda sin control.
- Dado que el director evalúa que el intercambio grupal es productivo, entonces el orquestador retiene o atenúa el ingreso de audio a la capa de voz, de modo que el moderador no se meta en una cesión de turno entre dos participantes.
- Dado que el director decide intervenir, entonces se abre el ingreso y/o se inyecta la instrucción correspondiente.
- El sistema registra cada decisión de compuerta, para poder auditar después por qué el moderador habló o se quedó callado.

R5.7 — Modos de moderación y corte de emergencia.
- La sesión tiene cuatro modos explícitos: **autónomo** (el sistema conduce), **asistido** (el humano conduce y delega tareas acotadas), **controlado por humano** (el sistema está mudo) y **pausado**.
- En modo asistido el sistema nunca interviene sin delegación explícita.
- Existe un control que, en un paso, silencia el audio del sistema, pausa la sesión o la termina, disponible para el supervisor durante toda la sesión. No requiere entrar a una configuración.

R5.8 — Transparencia grupal y escalamiento.
- Todos los participantes reciben y aceptan la declaración de conducción automatizada antes de entrar.
- Dado que cualquier participante manifiesta malestar o pide un moderador humano, entonces el sistema escala para toda la sesión, no solo para esa persona.

R5.9 — Supervisión, observación y toma de control.
- Dado un investigador supervisando un grupo, cuando toma el control, entonces la conducción automatizada se silencia y los participantes son informados.
- Existe un rol **observador**: investigador o cliente que escucha y ve la sesión y sus métricas, sin aparecer como participante y sin emitir audio a la sala. Es el equivalente de la sala de observación del cualitativo presencial, y el cliente lo va a pedir.

R5.10 — Recuperación de sesión, en grupo.
- Aplica R4.10, con un snapshot que además incluye el estado por participante (tiempo de habla, última intervención, turnos pendientes) y la cola de R5.4.
- Dada una caída con ocho personas en la sala, entonces el sistema silencia al moderador, avisa a la sala, restituye y retoma. Una caída silenciosa con ocho personas esperando es la peor falla posible de esta fase.

R5.11 — Estímulos.
- Dado un estímulo mostrado a la sala, entonces el moderador sabe cuál está visible y desde cuándo, y el evento queda en la línea de tiempo.
- Dado el protocolo de exposición, entonces el sistema pide reacción espontánea **antes** de preguntar por atributos específicos, y no nombra atributos que nadie mencionó.

R5.12 — Jerarquía de control.
- Aplica R4.9 sin cambios: la voz de cualquier participante es contenido, nunca instrucción privilegiada, y un intento de manipulación se registra como evento —además de ser, en sí mismo, un dato de campo—.

**Dependencias:** Fase 4 cerrada, con sus métricas de calidad alcanzadas. Si la Fase 4 falla en calidad de material, esta fase no se construye: se retiene el copiloto de la Fase 2 como producto.

**Criterios de salida (DoD).** Cinco grupos reales moderados por el sistema, con balance de participación medible mejor que el de un grupo humano comparable (el sistema no se olvida de nadie), cobertura completa de pauta, y material que un investigador de Equipos califica como utilizable. La codificación a ciegas de grupos automatizados contra grupos humanos no muestra una pérdida de calidad que invalide el método.

**Métricas de la fase**
- **Tasa de intervención falsa: cuántas veces el moderador habla en un silencio que no era fin de turno.** Es la métrica que manda en esta fase, porque mide directamente lo que el modelo decide solo y nosotros solo podemos administrar con la compuerta de audio.
- Índice de balance de participación: desvío del tiempo de habla entre participantes, contra el de grupos humanos.
- Tasa de intervenciones evaluadas como inoportunas por el investigador que revisa.
- Turnos interrumpidos recuperados sobre turnos interrumpidos totales.
- Cobertura de pauta.
- Tasa de abandono durante el grupo.
- Concordancia de codificación a ciegas entre grupos automatizados y humanos.

**Riesgos y preguntas de la fase**
- **[ingeniería/producto]** **El control de turnos no es configurable.** GPT-Live decide solo cuándo habla y no expone un VAD ajustable; los parámetros de la API Realtime anterior (`server_vad`, `semantic_vad`, `eagerness`) no aplican. En un grupo, un silencio de dos segundos casi siempre es una cesión de turno entre dos personas, no un fin de turno. Toda la mitigación pasa por la compuerta de audio del orquestador (R5.6). *Es el riesgo técnico principal de la fase y hay que medirlo en el primer prototipo, antes que cualquier otra cosa.*
- **[producto]** Que un grupo de ocho personas no le tome el peso a un moderador automatizado, y que la dinámica —que es todo el valor del focus group— no se produzca. Riesgo social, no técnico, y es el más alto del proyecto.
- **[ingeniería]** La latencia entre que alguien termina de hablar y el sistema interviene define si la conducción se siente natural o robótica. Medir `fin de habla → primer audio del moderador` por percentiles, no por promedio.
- **[producto]** La interpelación nominal al callado puede leerse como incómoda o invasiva. Es una decisión de diseño conversacional, no de prompt.
- **[metodológico]** Un grupo moderado por IA puede no ser comparable con la serie histórica de grupos de Equipos. Si el cliente compara contra estudios anteriores, hay que decirlo.

---

## 3. Métricas globales de éxito

**Leading**
- Tasa de show por sesión y su tendencia.
- Tiempo de campo: de pauta aprobada a corpus consultable.
- Costo por entrevista o grupo completado, por modalidad (humano / copiloto / automatizado).
- Cobertura de pauta por sesión.
- Incidencia de panelista profesional detectada y bloqueada.

**Lagging**
- **n cualitativo por estudio**: la métrica de la apuesta. Si no sube, el proyecto no cumplió su objetivo estratégico aunque funcione todo.
- % de estudios cualitativos que se apoyan en el corpus de estudios anteriores.
- Fatiga del panel atribuible al cualitativo: personas convocadas a cuali sobre panel activo, y su efecto en la tasa de respuesta cuantitativa.
- Ingresos de cualitativo y su participación en la facturación.
- Cumplimiento operativo: SLA de bajas con cascada completa sobre artefactos cualitativos.

## 4. Preguntas abiertas transversales

- **[producto]** **¿La moderación automatizada produce material de la calidad necesaria, en rioplatense?** Es el supuesto que sostiene las Fases 4 y 5 y no se resuelve razonando. Se prueba en tres pasos, y antes de escribir código de esas fases:

  **(1) Prueba de conducción 1:1.** Cinco entrevistas en profundidad con una pauta real de un estudio ya hecho, contra la API directamente, sin sistema. Costo: unos pocos dólares y tiempo de investigador. Mide si repregunta bien en voseo, si tolera el silencio y si no suena a call center. *Bloqueante — Fase 4.*

  **(2) Spike técnico de sala.** Una sala mínima con dos humanos y el moderador —sin pauta, sin panel, sin nada más— para medir lo único que no se puede razonar de antemano: cuántas veces el moderador habla en un silencio que era una cesión de turno, y cuánto la compuerta de audio del orquestador mueve ese número. También valida que identifique al hablante por pista, que lo llame por su nombre y que el investigador pueda inyectarle una instrucción invisible. *Bloqueante — Fase 5, y es el que más temprano hay que correr porque si falla, el rediseño es grande.*

  **(3) Comparación a ciegas.** Un grupo automatizado y uno humano sobre la misma pauta, codificados a ciegas por un investigador de Equipos. *Bloqueante — Fase 5.*
- **[legal]** Grabación de voz e imagen de personas identificadas bajo URCDP: calificación del dato, plazo de retención de medios, y si la mezcla se conserva tras una baja. *Bloqueante — Fase 2.*
- **[legal]** Las tres finalidades de consentimiento nuevas —grabación audiovisual, uso semántico cualitativo, difusión de verbatim— y sus textos. La de difusión es la más delicada: el clip sale de Equipos. *Bloqueante — Fases 2 y 3.*
- **[legal]** ¿Hay que declarar la conducción automatizada al participante? El PRD asume que sí, por honestidad metodológica antes que por obligación. Confirmar si además hay obligación.
- **[ingeniería]** **Elección del SFU.** Condiciona las Fases 2 a 5. Criterios: pistas separadas por participante, grabación individual, capacidad de insertar un participante-bot, eventos del lado servidor, latencia regional aceptable desde Uruguay y Argentina, y costo por minuto-participante. **LiveKit es el candidato a vencer**: cumple los criterios y además publica un plugin de GPT-Live, lo que quita trabajo de integración del camino crítico; mediasoup y Janus dan más control a cambio de más implementación. *Bloqueante — Fase 2.*
- **[ingeniería]** **Presupuesto de contexto del moderador.** Cada inyección a la capa de voz admite unos 500 tokens. Eso obliga a que la guía del director sea corta y a que la pauta larga viva en el backend. Define cuánto estado puede sostener el moderador y hay que calibrarlo con datos reales. *No bloqueante — Fase 4.*
- **[producto/datos]** **Fatiga entre sistemas.** El registro de participación cualitativa es de COLOQUIO y no se escribe en la bóveda (R1.8), de modo que el muestreo de `paneles` no ve las participaciones en cuali: para él, alguien que estuvo en tres grupos sigue estando descansado. La pregunta es si eso es aceptable —cuali y cuanti como fatigas independientes— o si a cierto volumen empieza a quemar el panel sin que nadie lo vea. No bloquea la Fase 1; se responde con datos de uso real. La solución, si hace falta, es una vista de solo lectura desde el store de COLOQUIO que `paneles` consulte, sin que COLOQUIO escriba nada.
- **[producto/datos]** Granularidad del segmento cualitativo para el embedding, y si conviene el mismo espacio vectorial que el cuantitativo o uno separado. Requiere calibración con datos reales, con el mismo protocolo que se usó para la Fase 2 de `paneles`.
- **[producto]** Definición metodológica del filtro anti-panelista-profesional: ventana temporal y categorización de estudios.
- **[finanzas/legal]** Tratamiento fiscal del incentivo cualitativo en Uruguay. Es el mismo problema que `paneles` tiene abierto para el canje de premios, con montos bastante mayores. *Bloqueante — liquidación en Fase 1.*
- **[ingeniería]** La cascada de baja entre bases separadas no es transaccional. Definir el mecanismo y su verificación. *Se resuelve en la Fase 5 de `paneles`.*
- **[producto]** ¿Cuál es el tamaño máximo de grupo que la moderación automatizada admite? Se responde con la evidencia de la Fase 5, no antes.

## 5. Dependencia entre sistemas

COLOQUIO **no puede tocar las bóvedas hasta que la Fase 5 de `paneles` esté cerrada**: es ahí donde el consentimiento se reformula, donde las invariantes bajan a la base y donde nace el rol con el que COLOQUIO se conecta. Es una dependencia dura y va primero en el cronograma, no en paralelo. Su spec vive en `paneles/specs/SPEC_fase5.md`.

El **motor de consulta semántica** debe estar operativo para las Fases 1 (selección de candidatos) y 3 (corpus cualitativo). COLOQUIO no lo reimplementa: aporta un tipo de contenido nuevo al mismo motor y hereda su calibración.

**La bóveda de identidad es el único origen de `id_persona` y del consentimiento.** COLOQUIO no enrola, no deduplica y no da de baja: lee. Todo lo demás —pauta, sesiones, convocatoria, participación, incentivos, medios y transcripciones— es suyo y vive en sus bases.

**Ninguno de los dos sistemas necesita que el otro esté corriendo.** Si `paneles` está caído, COLOQUIO sigue convocando y sesionando mientras la bóveda responda; si COLOQUIO está caído, `paneles` no se entera. Ése era el punto de separarlos.

La relación en una línea: **la bóveda dice quién es la gente y si se la puede contactar; `paneles` responde qué contestó cuando se le preguntó; COLOQUIO responde qué dijo cuando se la escuchó.**
