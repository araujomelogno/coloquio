# Desplegar R1.19 — paso a paso

Lo que trae esta versión: la selección de candidatos pasa a ser un **sorteo
con la semilla de la sesión**.

- La misma búsqueda da la misma gente.
- La lista reparte sobre todo el segmento, no sobre los primeros por uuid.
- La pantalla dice cuántos cumplen en total y cuántos hay por cuota.
- La factibilidad de cada cuota se ve en Armado.
- «Volver a sortear» queda registrado.

**Tiempo:** unos 20 minutos.
**Proyecto / región:** `gestion-paneles` · `southamerica-east1`.

**Bloqueante: `paneles` tiene que desplegar primero** la versión nueva de
`f_persona_convocable_filtrada()`, la que tiene semilla, desplazamiento y
total (el paso 1 lo comprueba). COLOQUIO no tiene SQL que correr, ni datos que
migrar.

---

## Antes de empezar, tené a mano

- [ ] Un clon de `araujomelogno/coloquio` en tu máquina.
- [ ] `firebase` (Firebase CLI) con sesión iniciada en una cuenta con permisos de
      deploy en `gestion-paneles`. Se comprueba con `firebase projects:list`.
- [ ] Python 3.11, con ese nombre: `python3.11 --version` tiene que responder.
      En macOS, si no está: `brew install python@3.11`.
- [ ] Acceso a la bóveda con `psql` como dueño (`$DSN_BOVEDA`).

---

## Paso 1 · Comprobar que `paneles` ya tiene el sorteo

```bash
psql "$DSN_BOVEDA" -At -c "select has_function_privilege('coloquio_app',
  'f_persona_convocable_filtrada(text, jsonb, int, text, int)', 'execute');"
```

**Tenés que ver:** `t`

```bash
psql "$DSN_BOVEDA" -At -c "select pg_get_function_result(
  'f_persona_convocable_filtrada(text, jsonb, int, text, int)'::regprocedure);"
```

**Tenés que ver** una tabla que termina en `total bigint`, por ejemplo
`TABLE(id_persona uuid, finalidades text[], total bigint)`.

**Si alguno falla** («function … does not exist», o una `f`): pará acá. Esta
versión de COLOQUIO llama a la función con `p_semilla` y `p_desde`, y contra la
versión vieja la búsqueda de candidatos da error. Primero tiene que desplegar
`paneles`.

---

## Paso 2 · Traer la versión y correr las pruebas

```bash
cd coloquio
```

```bash
git checkout main && git pull
```

Si ya armaste el entorno para un despliegue anterior, saltá directo a
«Activarlo». Si no, crealo (una sola vez):

```bash
python3.11 -m venv functions/.venv
```

Activarlo:

```bash
source functions/.venv/bin/activate
```

**Tenés que ver:** el prompt empieza con `(.venv)`.

Instalar:

```bash
python -m pip install -r functions/requirements.txt pytest
```

Correr las pruebas:

```bash
cd functions && python -m pytest -q && cd ..
```

**Tenés que ver:** `131 passed`.

**Si falla alguna:** no despliegues. Mandá la salida.

> Cada bloque es **un** comando. Copialos de a uno.

---

## Paso 3 · Desplegar (funciones y front juntos)

```bash
export VPC_CONNECTOR=paneles-conn
```

```bash
firebase deploy --only functions:coloquio,hosting:coloquio
```

**Tenés que ver:** `Deploy complete!`

---

## Paso 4 · Prueba de humo en producción

En una sesión de prueba, pestaña **Selección**, búsqueda demográfica:

- [ ] Arriba de la lista aparece la barra **🎲 Sorteo · semilla …** y
      «Mostrando N de M elegibles».
- [ ] Refrescá la página y buscá de nuevo con el mismo filtro: **la misma
      gente, en el mismo orden**.
- [ ] Si la sesión tiene cuotas, la barra muestra cada una con sus elegibles.
- [ ] Si hay más de una tanda, **Traer más del sorteo** suma gente nueva, sin
      repetir.
- [ ] **Volver a sortear** pide confirmación, cambia la semilla y cambia la
      lista.
- [ ] En **Armado**, **Factibilidad de las cuotas** muestra los elegibles de
      cada cuota contra su meta, y debajo los sorteos de la selección (el
      primero y el que hiciste recién).

---

## Paso 5 · Avisar a los coordinadores

> Las sesiones que ya estaban en curso no tenían semilla. La primera vez que se
> abra su selección se les asigna una, y **los candidatos que aparecen van a
> ser otros**. Es lo esperado: la lista de antes salía siempre de los mismos.
> Lo que ya está en la lista de espera o en el embudo no cambia.

Lo demás está en el manual (§4 y §5.2, «El sorteo»).

---

## Si algo sale mal: volver atrás

Volver a desplegar la versión anterior (`c0e80b8`, el `main` antes de este
cambio):

```bash
git checkout c0e80b8
```

```bash
export VPC_CONNECTOR=paneles-conn
```

```bash
firebase deploy --only functions:coloquio,hosting:coloquio
```

```bash
git checkout main
```

No hay datos que revertir. La semilla y los sorteos guardados en las sesiones
la versión anterior los ignora, y la función vieja de `paneles` sigue andando
igual sin semilla.
