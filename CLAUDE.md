# COLOQUIO — investigación cualitativa sobre el panel

Referencias: `docs/PRD_coloquio_detallado.md` (producto), `specs/SPEC_coloquio_fase1.md`
(la fase en curso), `docs/HANDOFF_coloquio_fase1.md` (cómo se relaciona con `paneles`),
`docs/DESPLIEGUE_coloquio_fase1.md` (cómo se despliega), `docs/decisiones.md` (por qué está
hecho así: leerlo antes de revertir algo) y `docs/manual/` (manual de usuario en PDF).

## Invariantes que no se negocian

- **Cero PII en el store de COLOQUIO (R1.12).** La base Firestore `coloquio` guarda
  `id_persona`, estados, timestamps, segmentos y referencias. Nunca nombre, documento,
  email, celular, dirección ni fecha de nacimiento. Lo hace valer `coloquio/store.py`:
  **toda** escritura pasa por `pii.validar_sin_pii()`. No agregar caminos de escritura
  que no pasen por `Store`. No hay notas libres sobre personas.
- **La bóveda solo por la superficie de la Fase 5.** `v_persona_convocable` (el gate de
  consentimiento es la vista, no un `if`), `declarar_convocatoria()`,
  `contacto_para_convocatoria()` y las tres funciones de la cascada. Nada de `persona`,
  `consentimiento`, `participacion`. La única escritura es `declarar_convocatoria()`.
  `test_boveda_solo_superficie_fase5` lo controla.
- **Invitar es declarar (R5.2.a).** Todo paso que deja a alguien invitado (lista de
  invitación, fila, reemplazo, WhatsApp, reingreso) y toda reprogramación pasa por
  `coloquio/declaracion.py`, **fuera de la transacción de Firestore y antes**. Sin
  declaración la bóveda no entrega el contacto.
- **`p_actor` es siempre el email del usuario humano** que pidió el contacto.
- **El dato de contacto se usa y se descarta**: no se guarda, no se loguea, no va al evento.
- **Nunca se confirma un borrado que no ocurrió** (`cascada.py` verifica antes de confirmar).
- **Los agregados se mantienen en la misma transacción** que cambia el estado
  (`conteo`, `cuotas[].cubierto`, `valorComprometido`, `participacionCuali`).
  `consistencia.py` los recalcula y repara.
- **En una transacción, todas las lecturas antes que las escrituras** (regla de
  Firestore; `StoreMemoria` la hace cumplir en las pruebas). Nada de efectos externos
  (WhatsApp, bóveda) adentro de una transacción: se puede reintentar.

## Estructura

- `functions/main.py` — `coloquio_api` (HTTP) y `coloquio_cascada` (programada).
  Codebase `coloquio`, mismo proyecto que `paneles`: los nombres llevan prefijo.
- `functions/coloquio/` — dominio. `ruteo.py` declara las rutas `/api/cuali/**` y su permiso.
- `functions/tests/` — `test_dod.py` recorre el DoD de la SPEC; `fabrica.py` arma un panel
  ficticio en memoria.
- `web/public/` — HTML + módulos ES, sin build. Estética de Equipos (Montserrat, naranja
  `#E96436`, sidebar oscuro), la misma de Reloj y `paneles`.
- `scripts/servidor_local.py` — la app y la API reales con stores en memoria.

## Trabajo

```bash
cd functions && python3 -m pytest -q                     # en memoria
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 python3 -m pytest -q   # contra el emulador
python3 scripts/servidor_local.py                        # http://localhost:8765
```

- Identificadores y dominio en **español**.
- Secretos a Secret Manager y **declarados** en `SECRETOS` de `main.py` (una prueba lo verifica).
- Región `southamerica-east1` en todo; `scripts/verificar_region.py` corre en el predeploy.
- Si cambia una pantalla, rehacer las capturas y el PDF del manual (`docs/manual/README.md`).
- Una decisión de diseño nueva y no obvia va a `docs/decisiones.md`, con su prueba si la tiene.
- Trabajar por fases: no implementar la Fase 2 (sala virtual, grabación) hasta cerrar el DoD de la 1.
