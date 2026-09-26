# Handoff — COLOQUIO Fase 1

**Para:** Claude Code, al desarrollar la Fase 1 de COLOQUIO
**Precondición:** Fase 0 desplegada (la bóveda ya expone su superficie de acceso)
**Última actualización:** 2026-09-26

---

## 1. Dónde vive COLOQUIO

**En el mismo proyecto que `paneles`: `gestion-paneles`.** Se evaluó ponerlo en
un proyecto propio con Shared VPC y se descartó (cuota de facturación y
complejidad); la separación que importa —la de **privilegios**— ya está hecha
en la base y no depende de separar proyectos.

Consecuencias concretas para el desarrollo:

- **Hosting propio, mismo proyecto.** COLOQUIO va en un sitio de Firebase
  Hosting aparte (`firebase hosting:sites:create`), con su propio *target*, para
  poder desplegar sin tocar `paneles`.
- **Firebase Auth es compartido.** Los usuarios son los mismos que los de
  `paneles`. El control de qué ve cada uno va en los **roles**, no en la
  separación de proyectos. COLOQUIO define los suyos y los hace valer.
- **Firestore es compartido.** Separar las colecciones de COLOQUIO por prefijo
  o usar una base con nombre propio; no mezclarlas con `usuarios`.
- **Las funciones van al mismo proyecto**, así que los nombres tienen que ser
  únicos. Declarar COLOQUIO como un **codebase separado** en `firebase.json`.
- **Reutiliza el conector VPC existente** (`paneles-conn`). No crear uno nuevo:
  serían ~US$ 10–15/mes al pedo.

> **Direct VPC egress no es opción.** Se verificó: el SDK de Python de
> `firebase-functions` (hasta 0.6.0) no lo expone. Usar `vpc_connector`, como
> hace `paneles`.

---

## 2. Cómo COLOQUIO accede a la bóveda

**Nunca directo a las tablas.** La bóveda expone una superficie acotada y la
base lo hace cumplir: si el código intenta leer `persona`, `consentimiento` o
`participacion`, recibe `permission denied`. Eso es por diseño, no un permiso
que falte.

**Identidad de conexión:**

| | |
|---|---|
| Cuenta de servicio | `coloquio-app@gestion-paneles.iam.gserviceaccount.com` |
| Usuario de base | `coloquio-app@gestion-paneles.iam` |
| Rol de grupo | `coloquio_app` |
| Autenticación | IAM de Cloud SQL (la instancia tiene `cloudsql.iam_authentication=on`) |
| Instancia | `gestion-paneles:southamerica-east1:paneles-boveda` |

**Lo que COLOQUIO puede leer y ejecutar** (verificado: 4 relaciones y 6
funciones, nada más):

- `v_persona_convocable` — la única superficie desde la que ve personas. Ya
  aplica el gate de consentimiento: quien no consintió, no aparece.
- `v_fatiga_panelista` — los hechos de fatiga (cuántas convocatorias, cuándo la
  última). **El umbral lo pone COLOQUIO**, la bóveda solo da los hechos.
- `v_finalidad` y `v_texto_consentimiento_activo` — el catálogo.
- `contacto_para_convocatoria()` — el **único** camino a un dato de contacto.
- Las funciones de la cascada de baja (ver §4).

---

## 3. `contacto_para_convocatoria()`: la regla que no se puede omitir

Es la única forma de obtener un email o un celular. Devuelve **un canal por
vez** y audita la entrega en la misma transacción.

> ### `p_actor` es obligatorio en la práctica
>
> **`p_actor` debe ser el email del usuario humano de COLOQUIO** que pidió el
> contacto — **no** la cuenta de servicio, no un valor fijo, no nulo.
>
> La función hace `coalesce(p_actor, session_user)`: si COLOQUIO no lo pasa, la
> auditoría registra «coloquio» y **se pierde quién fue la persona**, que es
> justamente el dato que una reidentificación necesita tener.
>
> **Regla para el código:** toda llamada lleva el email del usuario autenticado
> de la sesión. No hay caso en que corresponda omitirlo. Si una operación no
> tiene un usuario humano detrás, probablemente no debería estar pidiendo un
> dato de contacto.

Otras dos cosas que la función ya hace y COLOQUIO no debe reimplementar:

- **Rechaza si falta el consentimiento.** No hace falta chequearlo antes: el
  gate está en la base. Si devuelve rechazo, es que esa persona no se puede
  contactar, y no hay forma de saltearlo.
- **Un canal por llamada.** Pedir `email` o `celular`, no los dos.

---

## 4. La cascada de baja: COLOQUIO tiene que cerrarla

Cuando alguien ejerce su derecho de baja en `paneles`, la bóveda genera un
**pendiente** para cada sistema consumidor. COLOQUIO está obligado a:

1. Leer sus pendientes (`mis_borrados_pendientes()`).
2. **Borrar efectivamente** los datos de esa persona en COLOQUIO.
3. Confirmar (`confirmar_borrado()`), o reportar el fallo
   (`reportar_error_de_borrado()`).

Un pendiente sin confirmar aparece en `v_borrados_sin_confirmar` y es un
incumplimiento visible. **No confirmar sin haber borrado**: la confirmación es
una declaración, y la bóveda confía en ella.

Un consumidor no puede cerrar el pendiente de otro — está verificado.

---

## 5. COLOQUIO entra inactivo

`sistema_consumidor.coloquio` está en `activo = false`. Se activa cuando el
sistema esté listo, no antes. Que el desarrollo funcione contra la bóveda no
implica activarlo.

---

## 6. Cambios de comportamiento ya vigentes en `paneles`

Tres cosas que la Fase 0 activó y que afectan a cualquier código que toque
consentimientos:

- **El alta exige una versión de texto publicada.** Otorgar un consentimiento
  con una versión que no esté activa en `texto_consentimiento` falla.
- **El gate es algo más estricto que antes.**
- **La auditoría registra de qué sistema vino cada acción**, derivado de la
  conexión (`sistema_de_la_conexion()`), no de lo que declare el llamador.

---

## 7. Pendientes conocidos, para no re-descubrirlos

- **Corregir el test de la batería** (`scripts/verificar_coloquio.py`), chequeo
  «el contacto legítimo queda auditado»: hoy pasa la cuenta de servicio como
  `p_actor` y espera otra cosa. Debe pasar un email de usuario y verificar que
  ese email quede registrado. **La migración `0014` no se toca.**
- **Chequeo «un rol sin registrar no consigue nada»:** no es verificable contra
  Cloud SQL (toda conexión exige credenciales). Solo corre en cluster local.
- **`scripts/pg_pruebas.sh` es solo Linux** (`/usr/lib/postgresql/*/bin`); en
  macOS no corre.
- **P2 a decidir:** si `contacto_para_convocatoria()` debería **rechazar** la
  llamada cuando `p_actor` viene nulo, en vez de caer a `session_user`.
- **Textos de consentimiento con cuerpo `PENDIENTE`:** las versiones
  `consentimiento-2026-01` de `contacto_participacion` y `uso_semantico` se
  insertaron con un placeholder para destrabar la migración. **Hay que
  reemplazarlas por el texto real**; no borrarlas (el trigger las exige).

---

## 8. Costos: qué sumar y qué no

Regla del proyecto: **toda decisión técnica con costo recurrente se cuantifica
al proponerla.**

| Decisión | Costo |
|---|---|
| COLOQUIO en `gestion-paneles`, reutilizando el conector | **US$ 0** adicionales |
| Sitio de Hosting propio | US$ 0 |
| Un conector VPC propio | ~US$ 10–15/mes — **no hacerlo** |
| Proyecto separado + Shared VPC | US$ 0 de infraestructura, pero obliga a conector propio |
| Instancia de Cloud SQL propia para COLOQUIO | ~US$ 10/mes (`db-f1-micro`) — evaluar si de verdad hace falta |

Contexto: las dos instancias están en `db-f1-micro` (~US$ 28/mes las dos) y el
conector suma ~US$ 10–15. Ver `COSTOS.md`.

> **Si COLOQUIO necesita su propia base** (para sus datos cualitativos, que no
> van en la bóveda ni en el store semántico), cuantificarlo **antes** de
> crearla, y evaluar si alcanza con un esquema separado en una instancia
> existente.

---

## 9. Reglas de trabajo

- **Migraciones versionadas**, nunca cambios a mano en la base. Aplicarlas
  siempre con `--single-transaction`: sin eso, una migración que falla a mitad
  deja confirmado lo ya ejecutado.
- **Nada de PII al store semántico.** El guardrail está activo y aborta la
  escritura.
- **Secretos a Secret Manager**, nunca al repositorio.
- **Región `southamerica-east1`** en todo: funciones, conector e instancias.
  Una función en otra región no llega a las bases.
