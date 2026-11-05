# Despliegue — R1.18 en COLOQUIO (modo laxo y detalle de cumplimiento)

**Qué es:** la actualización de la selección de candidatos para R1.18
(`specs/ADDENDUM_seleccion_R1.14-R1.18.md`). Trae cuatro cosas:
- cada criterio semántico puede ser **duro**;
- la búsqueda corre en modo **laxo** (por defecto) o **estricto**, a elección;
- si el motor deja afuera a alguien, se informa cuántos y por qué;
- la lista marca al candidato **penalizado**, de **confianza baja** o con
  **verificación incompleta**, y la propuesta de invitación no completa cuota
  con ellos mientras haya verificados.

Viene en el mismo cambio la limpieza de `boveda.py` posterior a la `0021`. No
modifica ninguna consulta SQL.
**Para quién:** quien ya tiene desplegada la Fase 1 y R5.2.a
([`DESPLIEGUE_coloquio_fase1.md`](DESPLIEGUE_coloquio_fase1.md),
[`DESPLIEGUE_R5.2.a.md`](DESPLIEGUE_R5.2.a.md)). Si todavía no se desplegó
nada, se sigue el de la Fase 1 y se agrega el paso 1 de este documento.
**Proyecto / región:** `gestion-paneles` · `southamerica-east1`
**Fecha:** 2026-11-05

---

## En corto: qué hay que cambiar

| | ¿Cambia? |
|---|---|
| Bóveda (Cloud SQL) | **No.** Ninguna migración nueva. La consulta a `v_persona_convocable` ya usaba `finalidades` (`boveda/0021`), y sigue igual. |
| API de `paneles` (`POST /api/consultas`) | **No se toca, pero se depende de ella.** Tiene que ser una versión que acepte `duro` y `modo` y devuelva las marcas por candidato y `excluidos` (paso 1). |
| Secretos, variables de entorno, `functions/.env` | No |
| `requirements.txt`, conector VPC, cuenta de servicio, IAM | No |
| Reglas e índices de Firestore | No. La convocatoria gana un campo, `marcasEvidencia`, que no se consulta por índice. |
| `firebase.json`, `.firebaserc` | No |
| Código de funciones (`coloquio_api`) | **Sí:** hay que volver a desplegar |
| Front (`web/public`) | **Sí:** cambia la pantalla de Selección y el diálogo de la lista de invitación |

Resumen: **se verifica qué versión de `paneles` está corriendo y se
redespliega.** No hay configuración nueva.

---

## 1 · Antes: que `paneles` entienda lo que COLOQUIO le va a mandar

COLOQUIO manda ahora, en cada consulta semántica, `modo` explícito y `duro` en
cada criterio. Lee de la respuesta `penalizado`, `verificacion_incompleta`,
`confianza`, `estado`, los veredictos por criterio y `excluidos`. Todo eso está
en el `main` de `paneles` (`panel_api/consultas.py`, contrato v2). Lo que hay
que confirmar es que **lo desplegado** sea esa versión.

**Chequeo sin costo.** `solo_estimar` normaliza la consulta y no corre nada: no
llama al verificador ni gasta. Con un `modo` inválido, una versión que entiende
`modo` lo rechaza y dice cuáles acepta.

El ID token se saca de una sesión abierta en COLOQUIO producción, desde la
consola del navegador:

```js
await (await import('/js/api.js')).estado.obtenerToken()
```

```bash
PANELES_API_URL=https://gestion-paneles.web.app/api      # el de functions/.env
TOKEN='<el ID token>'
curl -s -X POST "$PANELES_API_URL/consultas" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"criterios":[{"tipo":"semantico","texto":"prueba","duro":true}],"modo":"x","solo_estimar":true}'
#   {"error": "datos_invalidos", "mensaje": "Modo desconocido: 'x'.",
#    "detalle": {"modos_validos": ["estricto", "laxo"]}}
```

- **Si responde así:** `paneles` entiende `modo`. Se puede seguir.
- **Si responde 401 o 403:** el usuario no tiene `consultar` en `paneles`.
  Repetir con uno que lo tenga.
- **Si devuelve una estimación en vez del error:** esa versión de `paneles`
  ignora `modo`. **Conviene no desplegar** hasta actualizar `paneles`. COLOQUIO
  no se rompería, pero el modo estricto no tendría efecto y la pantalla diría
  «estricto» igual.

`duro` y las marcas de la respuesta no se pueden ver sin correr una consulta.
Se comprueban en la prueba de humo (paso 4).

> **Si `paneles` no manda alguna marca**, COLOQUIO no se cae ni la da por
> buena. La deduce de los veredictos, y ante la duda marca al candidato como de
> confianza baja (D49 en `docs/decisiones.md`). Es un respaldo, no un modo de
> operar: con un `paneles` viejo, la lista sale llena de marcas que no
> significan nada.

## 2 · Pruebas locales

```bash
cd functions && python3 -m pytest -q      # 96 pruebas
```

Las de R1.18 son las `test_r118_*` de `tests/test_dod.py`.
`test_r118_normalizar_no_descarta_lo_que_manda_paneles` ejercita el cliente
HTTP real contra una respuesta con la forma de `consultas._combinar()`.

## 3 · Deploy

El mismo comando de siempre:

```bash
export VPC_CONNECTOR=paneles-conn
firebase deploy --only functions:coloquio,hosting:coloquio
```

**Orden: primero funciones, después hosting**, o los dos juntos como arriba.
Si se despliegan por separado, nunca el hosting primero:
- **API nueva con front viejo:** funciona como antes, en laxo. La API sigue
  aceptando los criterios como texto suelto.
- **Front nuevo con API vieja:** **la búsqueda semántica falla con error 500.**
  El front manda cada criterio como `{texto, duro}` y la API anterior espera
  texto. La demográfica sigue andando.

## 4 · Después: prueba de humo

En una sesión de prueba, pestaña **Selección**:

1. **Laxo.** Modo *Semántica*, un criterio que se sepa que tiene evidencia en el
   panel, sin tocar el modo. Buscar.
   - El título de la lista empieza con **«modo laxo · N candidatos»**.
   - Si hay penalizados, el título lo dice y esas filas tienen borde ámbar y la
     marca **⚠ penalizado**.
   - Cada candidato muestra, por criterio, el veredicto, la razón y la
     respuesta.
2. **Estricto.** Misma búsqueda, modo *Estricto*.
   - El título dice **«modo estricto»**.
   - Si quedó gente afuera, un cartel dice cuántas personas y por qué motivo.
   - No hay ningún ⚠ penalizado en la lista.
3. **Duro.** Dos criterios, el segundo marcado **duro**, en laxo. Todos los de
   la lista tienen evidencia del criterio duro.
4. **Propuesta.** Agregar a la lista de espera candidatos con y sin marca, y
   tocar **Proponer lista de invitación**.
   - Si había verificados suficientes, ninguna fila dice ⚠ evidencia floja.
   - Si no los había, un cartel lo avisa.
   - **No invitar desde la sesión de prueba con personas reales del panel.**
     Invitar declara la convocatoria en la bóveda.

Para ver que las marcas quedaron guardadas sin texto, en la consola de
Firestore, base `coloquio`, en
`sesion/<id>/convocatoria/<id_persona>`: `marcasEvidencia` tiene que ser una
lista de nombres (`penalizado`, `confianzaBaja`, `verificacionIncompleta`) o
estar vacía. Nunca una frase.

## 5 · Lo que pasa con lo que ya estaba en curso

- **Las listas de espera armadas antes de este deploy** no tienen
  `marcasEvidencia`. La propuesta de invitación trata a esas personas como
  verificadas, porque no tiene cómo saber con qué evidencia entraron. Si una
  sesión abierta se armó con una búsqueda semántica y todavía no se invitó,
  conviene repetir la búsqueda y agregar de nuevo: quien ya estaba en la lista
  no se duplica, y solo los nuevos entran con su marca. No hay migración: es un
  dato que solo existe en el momento de elegir.
- **No cambia la cantidad de candidatos.** COLOQUIO ya mandaba `modo: "laxo"`
  desde la Fase 1, así que los dudosos ya entraban a la lista. El addendum dice
  que COLOQUIO corría en estricto sin saberlo; eso no aplica a lo desplegado. Lo
  nuevo es que ahora se ven marcados, y que se puede elegir estricto.

## 6 · Volver atrás

Se puede volver a la versión anterior sin tocar nada fuera de COLOQUIO:
- La versión anterior ignora `marcasEvidencia` en las convocatorias que ya lo
  tienen.
- Vuelve a mandar `laxo` fijo, sin `duro`.
- Vuelve a descartar las marcas al leer la respuesta.

No hay nada en la bóveda ni en `paneles` que revertir.

**Hay que revertir funciones y hosting juntos, o el hosting primero.** Por la
misma razón que en el paso 3: el front de esta versión con la API anterior
rompe la búsqueda semántica.

## Qué cambia en la pantalla

Conviene contárselo a los coordinadores (está en el manual, §5.1, §5.2 y §6.2):

- **Laxo es el modo de siempre.** Quien tiene evidencia dudosa o ninguna entra
  a la lista, ahora **marcado ⚠**. El filtro fino lo hacen ellos al llamar.
- **Estricto** deja afuera a esas personas y dice cuántas y por qué. Si deja la
  lista vacía, no se rellena con una búsqueda demográfica: hay que probar en
  laxo o sacar la marca de duro.
- **Duro** en un criterio: quien no lo cumple queda afuera, en cualquier modo.
- **Celeste no es dudoso.** «Verificación incompleta» quiere decir que nadie
  llegó a juzgar la evidencia, no que se la juzgó y se dudó.
- **La lista de invitación propuesta** prefiere a los verificados. Si tuvo que
  usar a alguien con evidencia floja, lo dice arriba y marca la fila.
