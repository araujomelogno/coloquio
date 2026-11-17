# Desplegar R1.14 a R1.17 — paso a paso

Lo que trae esta versión, en la pantalla de Selección:

- **R1.14:** filtros armados desde el catálogo de atributos de `paneles`, y
  cuotas por cualquier atributo.
- **R1.15:** columnas elegibles en la lista.
- **R1.16:** la ficha del candidato.
- **R1.17:** identificar a los candidatos tildados.

**Tiempo:** unos 30 minutos.
**Proyecto / región:** `gestion-paneles` · `southamerica-east1`.

Hay que hacer dos cosas en orden: **desplegar y, enseguida, migrar** unos datos
de Firestore. Todo lo demás son chequeos.

---

## Antes de empezar, tené a mano

- [ ] Un clon de `araujomelogno/coloquio` en tu máquina.
- [ ] `firebase` (Firebase CLI) con sesión iniciada en una cuenta con permisos de
      deploy en `gestion-paneles`. Se comprueba con `firebase projects:list`.
- [ ] `gcloud` con *application default credentials* de una cuenta que pueda
      escribir en Firestore (`gcloud auth application-default login`).
- [ ] Python 3.11, con ese nombre: `python3.11 --version` tiene que responder.
      El deploy arma el entorno de la función con `python3.11`, así que hace
      falta aunque tengas otro Python. En macOS, si no está:
      `brew install python@3.11`.
- [ ] Acceso a la bóveda con `psql` como dueño (`$DSN_BOVEDA`, el mismo de
      [`DESPLIEGUE_coloquio_fase1.md` §1](DESPLIEGUE_coloquio_fase1.md)).
- [ ] Un usuario de COLOQUIO producción con rol de administrador, para la prueba
      de humo.

---

## Paso 1 · Comprobar que la `0034` está en la bóveda

Las cinco piezas nuevas las agregó `paneles` con la migración
`boveda/0034_superficie_seleccion_cuali.sql`. Esta versión de COLOQUIO no
funciona sin ellas.

```bash
psql "$DSN_BOVEDA" -At -c "select
  has_table_privilege('coloquio_app', 'v_atributo_catalogo', 'select'),
  has_function_privilege('coloquio_app', 'atributos_de_personas(uuid[], timestamptz)', 'execute'),
  has_function_privilege('coloquio_app', 'f_persona_convocable_filtrada(text, jsonb, int)', 'execute'),
  has_function_privilege('coloquio_app', 'ficha_candidato(uuid, timestamptz)', 'execute'),
  has_function_privilege('coloquio_app', 'identificar_candidatos(uuid[], text, text, text)', 'execute');"
```

**Tenés que ver:** `t|t|t|t|t`

**Si ves una `f`, o un error que dice que la función no existe:** pará acá. Hay
que pedirle a `paneles` que aplique la `0034`.

---

## Paso 2 · Traer la versión y correr las pruebas

```bash
cd coloquio
```

```bash
git checkout main && git pull
```

Las dependencias van en un entorno virtual, `functions/.venv`. En macOS no hay
un comando `pip` suelto, y el Python de Homebrew no deja instalar paquetes
fuera de un entorno. La carpeta ya está en `.gitignore`, y el deploy la ignora.

Crear el entorno (una sola vez):

```bash
python3.11 -m venv functions/.venv
```

Activarlo:

```bash
source functions/.venv/bin/activate
```

**Tenés que ver:** el prompt empieza con `(.venv)`.

> **Usá esta misma terminal hasta el final.** El script de migración (pasos 3
> y 5) necesita estas dependencias. Si abrís otra terminal, volvé a correr el
> `source` de arriba.

Instalar:

```bash
python -m pip install -r functions/requirements.txt pytest
```

Correr las pruebas:

```bash
cd functions && python -m pytest -q && cd ..
```

**Tenés que ver:** `118 passed`.

**Si falla alguna:** no despliegues. Mandá la salida.

> Cada bloque es **un** comando. Copialos de a uno: si se pegan dos en la misma
> línea, quedan cosas como `pytestcd functions` y la terminal no los entiende.

---

## Paso 3 · Ver qué va a cambiar la migración (no escribe nada)

Las cuotas y los segmentos que ya están guardados usan la clave vieja
`tramoEtario`. Desde esta versión la dimensión se llama como en el catálogo:
`tramo_etario`. Los valores (`25-34`, `F`, `Montevideo`) no cambian.

Sin `--aplicar`, el script solo lista lo que cambiaría:

```bash
python scripts/migrar_claves_r114.py
```

**Tenés que ver:** una línea por documento a cambiar, y al final
`En seco: N documento(s) cambiarían.` Anotá ese `N`. Si nunca se cargó una
cuota por tramo, `N` puede ser 0, y está bien.

---

## Paso 4 · Desplegar (funciones y front juntos)

```bash
export VPC_CONNECTOR=paneles-conn
```

```bash
firebase deploy --only functions:coloquio,hosting:coloquio
```

**Tenés que ver:** `Deploy complete!`

> **Funciones y front van juntos, en el mismo comando.** El front nuevo manda
> los filtros con la forma nueva y la API vieja no los entiende. Al revés, el
> front viejo manda `tramoEtario` y `edadMin`, y la API nueva los rechaza.

---

## Paso 5 · Migrar, enseguida después del deploy

```bash
python scripts/migrar_claves_r114.py --aplicar
```

**Tenés que ver:** `Listo: N documento(s) actualizados.`, con el mismo `N` del
paso 3 (o uno o dos más, si alguien incorporó gente mientras tanto).

Volvé a correrlo en seco para confirmar que no quedó nada:

```bash
python scripts/migrar_claves_r114.py
```

**Tenés que ver:** `En seco: 0 documento(s) cambiarían.`

> **Por qué después del deploy y no antes.** Si se migra antes, la versión vieja
> sigue corriendo y escribe `tramoEtario` en las convocatorias nuevas. Entre el
> paso 4 y el 5, una sesión con cuota por tramo muestra esa cuota sin contar a
> la gente ya cargada. Se corrige sola al migrar. Por eso conviene no dejar pasar
> tiempo entre los dos pasos.

---

## Paso 6 · Dar el permiso de identificar

Ver el nombre, el celular y el email de un candidato **antes de convocarlo**
exige un rol nuevo: **Identificar candidatos**. Nadie lo tiene por ser
coordinador o investigador. Los administradores ya lo tienen.

1. Entrá a COLOQUIO producción como administrador.
2. Andá a **Configuración → Roles**.
3. Tildá **Identificar candidatos** en las personas que tienen que poder
   hacerlo, y tocá **Guardar** en cada fila.

---

## Paso 7 · Prueba de humo en producción

Usá una sesión de prueba. En la pestaña **Selección**:

- [ ] **Filtros (R1.14).** Hay un control por atributo del catálogo, en el
      mismo orden que en `paneles`. Elegí dos categorías de un mismo atributo y
      buscá: la lista trae gente de cualquiera de las dos.
- [ ] **Columnas (R1.15).** Tocá **Columnas ▾** y tildá un atributo. La columna
      aparece sin que la búsqueda vuelva a correr. Recargá la página: la
      columna sigue elegida.
- [ ] **Ficha (R1.16).** Tocá **Ficha** en cualquier fila. Muestra estado,
      atributos con procedencia, paneles e historial, y **ningún nombre ni
      contacto**.
- [ ] **Identificar (R1.17).** Tildá **una sola** persona y tocá
      **Identificar (1)**. Aparece la columna «Identidad» con su nombre y su
      contacto. Al salir de la pantalla y volver, ya no está.
- [ ] **Cuotas.** En **Armado**, **+ Cuota** ofrece los atributos del catálogo
      que tienen categorías, y las cuotas existentes se ven igual que antes.

Opcional: la auditoría de la identificación del último punto quedó en la bóveda
con tu email y la sesión.

```bash
psql "$DSN_BOVEDA" -c "select actor_uid, motivo, sistema, contexto->>'referencia' as sesion, creado_en
  from reidentificacion where motivo = 'seleccion_cuali' order by creado_en desc limit 1;"
```

**Tenés que ver:** tu email · `seleccion_cuali` · `coloquio` · el id de la sesión.

---

## Si algo sale mal: volver atrás

En este orden:

1. Volver a desplegar la versión anterior (`c276523`, el `main` antes de este
   cambio):

   ```bash
   git checkout c276523
   ```

   ```bash
   export VPC_CONNECTOR=paneles-conn
   ```

   ```bash
   firebase deploy --only functions:coloquio,hosting:coloquio
   ```

2. Devolver las claves viejas, que son las que esa versión entiende:

   ```bash
   python scripts/migrar_claves_r114.py --revertir --aplicar
   ```

3. Volver a `main`:

   ```bash
   git checkout main
   ```

No hay nada que revertir en la bóveda: la `0034` es aditiva y la versión
anterior no la usa.

Hay dos cosas que no se pueden deshacer, y no hace falta. Las cuotas sobre
atributos que la versión vieja no conoce (por ejemplo, nivel educativo) quedan
guardadas, pero esa versión no las puede editar. Y las filas de auditoría de
las identificaciones quedan en la bóveda, que es lo que corresponde.

---

## Qué contarles a los coordinadores

Está en el manual (§1.2, §4 y §5.1–5.2):

- **Los filtros son todos los atributos del panel.** Si en `paneles` se crea un
  atributo nuevo, aparece en COLOQUIO al recargar.
- **Columnas ▾** suma columnas a la lista y la elección se recuerda.
  **∅ no consta** quiere decir que el dato nunca se cargó; no es lo mismo que
  «Sin dato».
- **Ficha** muestra todo lo que se sabe del candidato, sin identificarlo.
- **Identificar**, para quien tiene el rol: muestra nombre y contacto de los
  tildados. La bóveda lo registra y COLOQUIO no lo guarda.
- **Cuotas**: ahora se pueden poner sobre cualquier atributo con categorías.
