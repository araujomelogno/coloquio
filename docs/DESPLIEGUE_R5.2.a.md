# Despliegue — R5.2.a en COLOQUIO (convocatoria declarada)

**Qué es:** la actualización de COLOQUIO para el cambio de contrato de la bóveda
R5.2.a. Desde ahora COLOQUIO llama a `declarar_convocatoria()` al invitar y al
reprogramar.
**Para quién:** quien ya tiene la Fase 1 desplegada según
[`DESPLIEGUE_coloquio_fase1.md`](DESPLIEGUE_coloquio_fase1.md). Si todavía no se
desplegó nada, alcanza con seguir ese documento, que ya incluye esto.
**Proyecto / región:** `gestion-paneles` · `southamerica-east1`
**Fecha:** 2026-09-30

---

## En corto: qué hay que cambiar

| | ¿Cambia? |
|---|---|
| Bóveda (Cloud SQL) | **Sí, pero lo hace `paneles`.** La migración `boveda/0016` tiene que estar aplicada **antes**. Del lado de COLOQUIO no hay SQL que correr. |
| Secretos, variables de entorno, `functions/.env` | No |
| `requirements.txt`, conector VPC, cuenta de servicio, IAM | No |
| Reglas e índices de Firestore | No |
| `firebase.json`, `.firebaserc` | No |
| Código de funciones (`coloquio_api`) | **Sí:** hay que volver a desplegar |
| Front (`web/public`) | **Sí:** cambian dos pantallas (avisos nuevos). Hay que volver a desplegar el hosting |

Resumen: **se verifica que la 0016 esté aplicada y se redespliega.** No hay
configuración nueva.

---

## 1 · Antes: la 0016 aplicada y con permiso para `coloquio_app`

```bash
gcloud config set project gestion-paneles

# La función existe y coloquio_app la puede ejecutar
psql "$DSN_BOVEDA" -c "select has_function_privilege('coloquio_app',
  'declarar_convocatoria(uuid, text, timestamptz)', 'execute');"
#   t

# COLOQUIO sigue activo como consumidor
psql "$DSN_BOVEDA" -c "select codigo, activo from sistema_consumidor where codigo = 'coloquio';"
#   coloquio | t
```

**Si la primera consulta falla o da `f`, no desplegar.** Esta versión de
COLOQUIO no puede invitar a nadie sin la función: la invitación da error, se
corta antes de la transacción y no se invita a nadie a medias. Hay que pedirle a
`paneles` que aplique la 0016 (ver `paneles/docs/DESPLIEGUE - R5.2.a
convocatoria externa.md`).

Opcional: la batería de `paneles`, conectada como coloquio, tiene que dar en
verde sus dos chequeos de R5.2.a:

```bash
python3 scripts/verificar_coloquio.py     # en el repo paneles
```

## 2 · Pruebas locales

```bash
cd functions && python3 -m pytest -q      # 84 pruebas
```

Si está el cluster de pruebas de `paneles` a mano, conviene correr también la
integración contra la bóveda real:

```bash
source ../paneles/scripts/pg_pruebas.sh
python3 scripts/integracion_boveda.py     # 11 chequeos
```

> ⚠️ `integracion_boveda.py` **escribe filas de prueba**. Solo se corre contra
> el cluster local de pruebas, **nunca contra producción**.

## 3 · Deploy

Es el mismo comando de siempre. `firestore` puede quedar afuera porque no
cambió, pero dejarlo no hace daño:

```bash
export VPC_CONNECTOR=paneles-conn
firebase deploy --only functions:coloquio,hosting:coloquio
```

No hace falta un orden entre funciones y hosting: el front nuevo solo muestra
campos opcionales que manda la API (`noDeclarados`, `redeclaracion`).

## 4 · Después: prueba de humo

Con una sesión de prueba y una persona de prueba que tenga consentimiento de
`contacto_participacion`:

1. En el embudo, **invitarla** (o usar «Invitar a los propuestos» en Selección).
2. Abrir **«📞»**: tiene que mostrar el celular.
3. En la bóveda, comprobar que quedaron la declaración y la lectura hecha con el
   email humano:

```sql
select sistema, referencia, vence_en from convocatoria_externa where id_persona = '<id>';
--   coloquio | <id de la sesión> | <fecha de la sesión + 2 días>
select actor_uid, sistema from reidentificacion where id_persona = '<id>' order by creado_en desc limit 1;
--   <email de quien abrió «📞»> | coloquio      ← nunca la cuenta de servicio ni vacío
```

4. **Reprogramar** la sesión (cambiar la fecha) y repetir la primera consulta.
   Tiene que seguir habiendo **una sola** fila, con el `vence_en` nuevo.

## 5 · Lo que pasa con lo que ya estaba en curso

Las personas que quedaron invitadas **antes** de este deploy no tienen
declaración. No hay que hacer nada con ellas. La primera vez que alguien abre
«📞» o manda el WhatsApp, la bóveda rechaza, COLOQUIO las declara y reintenta
una sola vez (D47 en `docs/decisiones.md`). Si la persona retiró el
consentimiento, el reintento también falla y el embudo muestra el motivo.

Si se prefiere dejarlas declaradas desde el principio, alcanza con abrir cada
sesión abierta y guardarla con otra fecha. Pero no es necesario.

## 6 · Volver atrás

Si hubiera que volver a la versión anterior de COLOQUIO, hay que tener en cuenta
que **esa versión no declara**. Con la 0016 aplicada, la bóveda le negaría el
contacto a toda invitación nueva. Por eso volver atrás solo tiene sentido si
`paneles` también revierte la 0016. Las declaraciones que ya existen no molestan:
vencen solas y la bóveda las purga a los 30 días.

## Qué avisa la pantalla ahora

Conviene contárselo a los coordinadores:

- **Selección → Invitar:** si la bóveda no acepta a alguien (en general porque
  no tiene consentimiento vigente), esa persona **queda como candidata**, en la
  lista de espera, y un aviso dice cuántas no se pudieron invitar.
- **Sesiones → Guardar con otra fecha:** se vuelve a declarar a los que están
  en curso. Si la bóveda no responde, la fecha se guarda igual y aparece un
  aviso. La declaración se repone sola al leer cada contacto.
- **Embudo, «📞» sobre un candidato:** pide invitarlo primero.

Está también en el manual, §6.4.
