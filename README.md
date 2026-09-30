# COLOQUIO

Sistema de investigación cualitativa de Equipos Consultores, sobre el panel y las
bóvedas de `paneles`. **Fase 1:** estudio y pauta, selección de candidatos
(demográfica, semántica o mixta), filtro anti-panelista-profesional, embudo de
convocatoria por canal manual y WhatsApp, sobre-reclutamiento y reemplazo con
revalidación de cuota, recepción desde el teléfono, cierre con registro de
participación propio, incentivos y cascada de baja.

- Producto: [`docs/PRD_coloquio_detallado.md`](docs/PRD_coloquio_detallado.md)
- Especificación de la fase: [`specs/SPEC_coloquio_fase1.md`](specs/SPEC_coloquio_fase1.md)
- Relación con `paneles`: [`docs/HANDOFF_coloquio_fase1.md`](docs/HANDOFF_coloquio_fase1.md)
- **Manual de usuario:** [`docs/manual/Manual_de_usuario.pdf`](docs/manual/Manual_de_usuario.pdf)
- Decisiones de diseño: [`docs/decisiones.md`](docs/decisiones.md)
- **Despliegue:** [`docs/DESPLIEGUE_coloquio_fase1.md`](docs/DESPLIEGUE_coloquio_fase1.md); si la Fase 1 ya está desplegada, la actualización R5.2.a en [`docs/DESPLIEGUE_R5.2.a.md`](docs/DESPLIEGUE_R5.2.a.md)
- Convocatoria declarada en la bóveda (R5.2.a, resuelto): [`docs/PROPUESTA_paneles_contacto_coloquio.md`](docs/PROPUESTA_paneles_contacto_coloquio.md)

## Probarlo en local

```bash
python3 scripts/servidor_local.py     # http://localhost:8765 — datos ficticios, sin Firebase
```

## Pruebas

```bash
cd functions
python3 -m venv venv && venv/bin/pip install -r requirements.txt pytest
venv/bin/python -m pytest -q
```
