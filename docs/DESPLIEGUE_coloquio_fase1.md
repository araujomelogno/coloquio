# Despliegue — COLOQUIO · Fase 1

**Sistema:** COLOQUIO · investigación cualitativa · Equipos Consultores
**Cubre:** SPEC `specs/SPEC_coloquio_fase1.md` (R1.1 a R1.13, más dos P1: importación histórica y tablero)
**Proyecto GCP:** `gestion-paneles` (el mismo que `paneles`, HANDOFF §1)
**Región:** `southamerica-east1` en todo
**Fecha:** 2026-09-26 · **Revisión 2026-09-30:** R5.2.a (convocatoria declarada)

---

## 0 · Qué se despliega

| Pieza | Nombre | Dónde |
|---|---|---|
| Sitio de Hosting | `coloquio-equipos` (target `coloquio`) | Firebase Hosting, sitio propio |
| Función HTTP | `coloquio_api` | Cloud Functions, codebase `coloquio`, python311 |
| Función programada | `coloquio_cascada` (cada 30 min) | ídem + Cloud Scheduler |
| Base Firestore | `coloquio` (con nombre propio) | Firestore nativo, `southamerica-east1` |
| Identidad de ejecución | `coloquio-app@gestion-paneles.iam.gserviceaccount.com` | la creada en la Fase 0 |
| Salida a la VPC | conector existente `paneles-conn` | **no se crea otro** |

Lo que **no** cambia: la bóveda, el store semántico, las funciones y el sitio de
`paneles`. El codebase separado hace que `firebase deploy` de COLOQUIO no toque
las funciones de `paneles`, y el target de Hosting propio, que no toque su sitio.

### La precondición: R5.2.a aplicada en la bóveda

COLOQUIO **declara** cada convocatoria en la bóveda al invitar
(`declarar_convocatoria()`, migración `boveda/0016` de `paneles`), y sin esa
declaración `contacto_para_convocatoria()` no entrega el contacto. Por eso la
`0016` tiene que estar aplicada **antes** de desplegar esta versión (1.2). La
historia del cambio está en
[`PROPUESTA_paneles_contacto_coloquio.md`](PROPUESTA_paneles_contacto_coloquio.md),
y cómo lo hace COLOQUIO, en `docs/decisiones.md` (D44, D46 y D47).

---

## 1 · Chequeos previos

```bash
gcloud config set project gestion-paneles

# 1.1 La Fase 5 de paneles está desplegada y COLOQUIO registrado (inactivo)
psql "$DSN_BOVEDA" -c "select codigo, activo, rol_bd from sistema_consumidor;"
#   coloquio | f | coloquio-app@gestion-paneles.iam

# 1.2 R5.2.a aplicada: existe declarar_convocatoria() y coloquio_app la puede ejecutar
psql "$DSN_BOVEDA" -c "select has_function_privilege('coloquio_app',
  'declarar_convocatoria(uuid, text, timestamptz)', 'execute');"
#   t

# 1.3 La batería, conectada como coloquio (paneles/docs/DESPLIEGUE - R5.2.a convocatoria externa.md)
python3 scripts/verificar_coloquio.py          # en el repo paneles
#   16 chequeos; los dos de R5.2.a en verde. Contra Cloud SQL, los dos rojos
#   conocidos de la Fase 0 (p_actor en el test y rol sin credenciales) siguen igual.

# 1.4 Ubicación de la base Firestore por defecto (es INMUTABLE: confirmar antes de crear nada)
gcloud firestore databases describe --database='(default)' --format='value(locationId)'
#   southamerica-east1
```

Si 1.4 no da `southamerica-east1`, **parar** y decidir con el equipo: la base
de COLOQUIO va igual en `southamerica-east1` (es la región de la bóveda y de las
funciones), pero conviene saberlo.

---

## 2 · La base Firestore con nombre propio

```bash
gcloud firestore databases create \
  --database=coloquio \
  --location=southamerica-east1 \
  --type=firestore-native \
  --delete-protection
```

> **Inmutable.** La ubicación no se puede cambiar después. Por eso el comando
> la dice explícita.

Opcional pero recomendado — respaldo diario con retención de 14 días:

```bash
gcloud firestore backups schedules create --database=coloquio \
  --recurrence=daily --retention=14d
```

Costo del respaldo: centavos por mes al volumen de la SPEC (§9).

### 2.1 El comentario de `paneles/firestore.rules`

La SPEC §7.2 pide actualizar el comentario de las reglas de `paneles` para que
diga que existe una segunda base, `coloquio`, con otro régimen documentado. Es
un cambio de texto en el **repo `paneles`**, no en este. Sugerido:

```
// Esta base (default) guarda una sola cosa: el padrón de usuarios. Nada de PII
// de panelistas. Existe además la base `coloquio`, de COLOQUIO, con reglas
// propias (deny-all) y régimen PII-free validado en cada escritura: ver
// coloquio/firestore.rules.
```

---

## 3 · Permisos de la cuenta de servicio

La función corre como `coloquio-app@…`, que ya tiene `cloudsql.client` y
`cloudsql.instanceUser` (Fase 0). Le faltan Firestore y, para el deploy, que
quien despliega pueda actuar como ella.

```bash
SA=coloquio-app@gestion-paneles.iam.gserviceaccount.com

# Lectura y escritura en Firestore. Con condición, para que solo pueda
# escribir en la base `coloquio`:
gcloud projects add-iam-policy-binding gestion-paneles \
  --member="serviceAccount:$SA" --role=roles/datastore.user \
  --condition='expression=resource.name.startsWith("projects/gestion-paneles/databases/coloquio"),title=solo-base-coloquio'

# Lectura del padrón de `paneles` (base por defecto, colección `usuarios`):
gcloud projects add-iam-policy-binding gestion-paneles \
  --member="serviceAccount:$SA" --role=roles/datastore.viewer \
  --condition='expression=resource.name.startsWith("projects/gestion-paneles/databases/(default)"),title=padron-solo-lectura'

# Quien despliega tiene que poder «actuar como» la cuenta:
gcloud iam service-accounts add-iam-policy-binding $SA \
  --member="user:garaujo@equipos.com.uy" --role=roles/iam.serviceAccountUser
```

`firebase deploy` le otorga sola `secretmanager.secretAccessor` sobre los
secretos declarados.

---

## 4 · Secretos

Cuatro, todos en Secret Manager. Tienen que **existir** aunque WhatsApp todavía
no esté listo (el deploy falla si falta uno declarado). Secret Manager no admite
un valor vacío: se carga `-`, y COLOQUIO lo trata como «no configurado».

```bash
for s in WHATSAPP_TOKEN WHATSAPP_PHONE_NUMBER_ID WHATSAPP_APP_SECRET WHATSAPP_VERIFY_TOKEN; do
  printf -- '-' | gcloud secrets create $s --replication-policy=user-managed \
    --locations=southamerica-east1 --data-file=- 2>/dev/null \
  || echo "$s ya existe (si es de paneles, se comparte: ver nota)"
done
```

> **Nota:** `paneles` ya tiene `WHATSAPP_TOKEN` y `WHATSAPP_PHONE_NUMBER_ID`. Si
> COLOQUIO usa **el mismo número** emisor, se comparten tal cual; si usa otro,
> hay que crearlos con otro nombre y cambiarlos en `SECRETOS` de
> `functions/main.py` y en `coloquio/config.py`. La recomendación es un número
> propio para COLOQUIO: los convocados a un grupo no deberían recibir el
> mensaje desde el mismo número que les manda encuestas.

La configuración no secreta está en `functions/.env` (instancia, base,
`PANELES_API_URL`). Revisarla antes del deploy.

---

## 5 · Hosting y Auth

```bash
firebase hosting:sites:create coloquio-equipos
firebase target:apply hosting coloquio coloquio-equipos   # ya está en .firebaserc
```

En la consola: **Authentication → Settings → Authorized domains → Add domain**
→ `coloquio-equipos.web.app` (y el dominio propio si se usa). Sin esto el login
falla con `auth/unauthorized-domain`.

---

## 6 · Deploy

```bash
export VPC_CONNECTOR=paneles-conn
firebase deploy --only functions:coloquio,hosting:coloquio,firestore
```

- `functions:coloquio` despliega **solo** el codebase de COLOQUIO.
- `firestore` despliega reglas e índices de las bases listadas en
  `firebase.json`, que es **solo** `coloquio`. La base por defecto de `paneles`
  no se toca.
- El `predeploy` corre `scripts/verificar_region.py`: frena el deploy si la
  región de la función, la del rewrite y la del conector no coinciden.

Los índices de grupo de colección (para la cascada) tardan unos minutos en
construirse; hasta que estén, la cascada falla y reporta el error a la bóveda,
que deja el pendiente abierto. Es el comportamiento correcto.

---

## 7 · Primer ingreso y roles

1. Un usuario con rol `admin` en el padrón de `paneles` es **administrador de
   COLOQUIO por construcción**. Entra a `https://coloquio-equipos.web.app`.
2. Configuración → **Roles en COLOQUIO**: asigna coordinador / investigador /
   administrador al resto. Quien no tiene rol ve «sin roles en COLOQUIO».
3. Configuración → **Catálogo de regalos**, **categorías** y **umbrales de
   fatiga**. Los umbrales por defecto (180 días por categoría, tope de 3 en 365
   días) son un punto de partida: la definición es de los investigadores
   (SPEC §10, bloqueante de producto).
4. Recomendado (SPEC §13): **importar sesiones históricas** para que el filtro
   de fatiga arranque con memoria.

Para que la selección **semántica** funcione, el usuario tiene que tener además
un rol en `paneles` con permiso `consultar` (admin, operaciones o analista):
COLOQUIO reenvía su token al motor de `paneles`, y es `paneles` quien decide. Si
no lo tiene, la selección degrada a demográfica y lo dice.

---

## 8 · WhatsApp (se construye último, no bloquea)

El canal manual funciona sin esto. Para el de WhatsApp:

1. **Número verificado** en WhatsApp Business (Meta) y los valores del paso 4
   cargados como nueva versión de cada secreto.
2. **Tres plantillas de utilidad**, en español, con 5 variables y **dos botones
   de respuesta rápida** (el orden importa: el primero es «sí»):

   | Plantilla | Cuerpo sugerido |
   |---|---|
   | `coloquio_invitacion` | Hola, te escribimos de Equipos Consultores. Estamos organizando un encuentro de conversación sobre {{1}} el {{2}} en {{3}}. Por participar te llevás {{4}}. ¿Te interesa? Tu código es {{5}}. — Botones: «Sí, me interesa» / «No puedo» |
   | `coloquio_confirmacion` | ¡Gracias! ¿Nos confirmás tu lugar para el encuentro sobre {{1}} el {{2}} en {{3}}? Te llevás {{4}}. Tu código: {{5}}. — «Sí, confirmo» / «No puedo» |
   | `coloquio_recordatorio` | Te recordamos el encuentro sobre {{1}}, {{2}} en {{3}}. Tu código es {{5}} ({{4}}). ¿Seguís pudiendo venir? — «Sí, voy» / «No puedo» |

   La confirmación y el recordatorio **solo se mandan como plantilla** si la
   ventana de servicio de 24 h está cerrada; si la persona respondió, salen
   como mensaje libre, que no se cobra (SPEC §9).
3. **Webhook** en la app de Meta:
   - URL: `https://coloquio-equipos.web.app/api/cuali/webhooks/whatsapp`
   - Token de verificación: el valor de `WHATSAPP_VERIFY_TOKEN`
   - Suscribir el campo `messages`.
   - Cada POST se valida con `X-Hub-Signature-256` y `WHATSAPP_APP_SECRET`.
4. Si Meta rechaza una plantilla o falla una entrega, la convocatoria **pasa a
   canal manual conservando su estado** y el embudo lo marca.

---

## 9 · Verificación (el DoD de la SPEC §11)

**Automática, antes de desplegar:**

```bash
cd functions && python3 -m pytest -q                       # 84 pruebas, en memoria
# y contra la implementación real de Firestore, con el emulador:
firebase emulators:start --only firestore --project demo-coloquio &
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 python3 -m pytest -q
```

`tests/test_dod.py` recorre los once puntos del DoD en ese orden, y
`tests/test_declaracion.py` el contrato de R5.2.a.

**Contra la bóveda de verdad** (las migraciones de `paneles` en el cluster de
pruebas, conectado como `coloquio_app`):

```bash
source ../paneles/scripts/pg_pruebas.sh
python3 scripts/integracion_boveda.py      # 11 chequeos; escribe filas de prueba: nunca contra producción
```

**Una prueba de R5.2.a contra la bóveda real**, con una persona de prueba:
invitarla desde el embudo, abrir «📞» (tiene que mostrar el celular) y verificar
del lado de la bóveda que quedó la declaración y la lectura con el email humano:

```sql
select sistema, referencia, vence_en from convocatoria_externa where id_persona = '<id>';
--   coloquio | <id de la sesión> | <fecha de la sesión + 2 días>
select actor_uid, sistema from reidentificacion where id_persona = '<id>' order by creado_en desc limit 1;
--   <email del coordinador> | coloquio      ← nunca «coloquio» en actor_uid
```

**Manual, en producción** (una sesión real o de prueba):

| # | Qué | Cómo se ve |
|---|---|---|
| 1 | Estudio con pauta y sesión con cupo y cuotas | Estudios → ficha; sin pauta, «Nueva sesión» está deshabilitado |
| 2 | Selección **mixta** con evidencia e historial | Selección → Mixta: cada fila con la respuesta, el estudio y el chip 🗂 |
| 3 | Nadie sin consentimiento aparece | Forzar: `POST /api/cuali/sesiones/{id}/convocatorias` con un id sin consentimiento → `sinConsentimientoVigente` |
| 4 | Fatiga y anulación registrada | Un excluido pide motivo; en Eventos queda motivo y usuario |
| 5 | Doce convocados por los dos canales | Embudo: columna Canal mezclada; métricas por canal |
| 6 | Caída → reemplazo del mismo segmento; caso sin candidatos | «Se cayó» → «Reemplazar»; sin candidatos, las tres salidas |
| 7 | Recepción de ocho desde un teléfono | Recepción en el celular, por código |
| 8 | Cierre: participación, incentivos, historial | Recepción → Cerrar sesión; Incentivos; historial de un presente |
| 9 | Baja de prueba en `paneles` → borrado y confirmación | Ver §10 |
| 10 | Auditoría de PII del store | `python3 scripts/auditar_store.py` → 0 hallazgos |
| 11 | Cero escrituras en la bóveda fuera de la superficie | `verificar_coloquio.py` (lista blanca) + `test_boveda_solo_superficie_fase5` |

---

## 10 · Activar la cascada (el día de salida a producción)

COLOQUIO entra **inactivo** en `sistema_consumidor` (HANDOFF §5). El día que
sale a producción, y no antes:

```sql
update sistema_consumidor set activo = true, alta_en = now() where codigo = 'coloquio';
```

Desde ahí, cada baja en `paneles` le genera un pendiente. Probarlo (DoD 9):

1. Dar de baja una persona de prueba que haya pasado por una sesión.
2. Esperar la pasada de `coloquio_cascada` (30 min) o forzarla desde
   Configuración → Cumplimiento → «Correr cascada de baja».
3. En la bóveda: `select * from v_borrados_sin_confirmar where sistema = 'coloquio';` → vacío.
4. En COLOQUIO: el historial de esa persona da 404 y `auditar_store.py` no la
   encuentra. Si estaba en un embudo activo, la sesión muestra la alerta de baja
   con el segmento perdido.

---

## 11 · Costos

| Concepto | Costo mensual |
|---|---|
| Firestore `coloquio` (≈12 000 escrituras/mes) | US$ 0 (capa gratuita diaria) |
| Respaldo diario de Firestore (opcional) | < US$ 0,10 |
| Cloud Functions (`coloquio_api` + `coloquio_cascada`) | ~US$ 0 |
| Cloud Scheduler (1 job) | US$ 0 si quedan jobs gratis en la cuenta; si no, US$ 0,10 |
| Hosting / Auth | US$ 0 |
| Conector VPC | US$ 0 adicional (se reutiliza `paneles-conn`) |
| Cloud SQL | US$ 0 adicional |
| WhatsApp Cloud API | US$ 25–120 a 100 sesiones/mes, **solo si se usa** (SPEC §9) |

---

## 12 · Vuelta atrás

- **Funciones:** `firebase functions:delete coloquio_api coloquio_cascada --region southamerica-east1`.
- **Hosting:** `firebase hosting:disable --site coloquio-equipos`.
- **Cascada:** si COLOQUIO se da de baja, **primero** `activo = false` en
  `sistema_consumidor`, y confirmar a mano los pendientes abiertos solo después
  de haber borrado la base `coloquio`. Nunca confirmar un borrado que no ocurrió.
- **Base:** tiene protección contra borrado; se quita con
  `gcloud firestore databases update --database=coloquio --no-delete-protection`.
