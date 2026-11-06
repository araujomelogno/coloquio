#!/usr/bin/env python3
"""R1.14 — renombra en Firestore las dimensiones de cuota a las claves del catálogo.

Hasta R1.14 las cuotas y los segmentos usaban tres dimensiones fijas, con un
nombre propio de COLOQUIO para una de ellas: `tramoEtario`. Desde R1.14 la
dimensión de una cuota es la **clave del atributo** en `v_atributo_catalogo`,
que para el tramo es `tramo_etario`. `sexo` y `localidad` ya coincidían, y los
valores (`F`, `25-34`, `Montevideo`) son las claves de las categorías: no
cambian.

Qué toca, en la base `coloquio`:

    sesion/{id}.cuotas[].dimension
    sesion/{id}.alertasBaja[].segmento
    sesion/{id}.decisionesCuota[].perdido.segmento
    sesion/{id}/convocatoria/{id}.segmento

Es idempotente (correrlo dos veces deja todo igual) y escribe por `Store`, así
que cada escritura pasa por el validador de PII (R1.12). Por defecto **no
escribe**: muestra qué cambiaría. Con `--aplicar`, escribe.

    python3 scripts/migrar_claves_r114.py                      # en seco
    python3 scripts/migrar_claves_r114.py --aplicar            # escribe
    python3 scripts/migrar_claves_r114.py --revertir --aplicar # vuelta atrás

Es el único lugar del repo que nombra la clave vieja, y por eso vive acá y no
en `functions/coloquio/`.
"""

import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "functions"))

RENOMBRES = {"tramoEtario": "tramo_etario"}


def _segmento(seg, renombres=RENOMBRES):
    if not isinstance(seg, dict):
        return seg, False
    nuevo = {renombres.get(k, k): v for k, v in seg.items()}
    return nuevo, nuevo != seg


def migrar_sesion(sesion, renombres=RENOMBRES):
    """(cambios, hubo_cambio) para el documento de una sesión."""
    cambios = {}
    cuotas = [dict(c, dimension=renombres.get(c.get("dimension"), c.get("dimension")))
              for c in sesion.get("cuotas") or []]
    if cuotas != (sesion.get("cuotas") or []):
        cambios["cuotas"] = cuotas
    alertas, cambio = [], False
    for a in sesion.get("alertasBaja") or []:
        seg, c = _segmento(a.get("segmento"), renombres)
        alertas.append(dict(a, segmento=seg) if c else a)
        cambio = cambio or c
    if cambio:
        cambios["alertasBaja"] = alertas
    decisiones, cambio = [], False
    for d in sesion.get("decisionesCuota") or []:
        perdido = d.get("perdido") or {}
        seg, c = _segmento(perdido.get("segmento"), renombres)
        decisiones.append(dict(d, perdido=dict(perdido, segmento=seg)) if c else d)
        cambio = cambio or c
    if cambio:
        cambios["decisionesCuota"] = decisiones
    return cambios


def migrar(store, aplicar=False, salida=print, revertir=False):
    """Recorre las sesiones y sus convocatorias. Devuelve cuántos documentos
    cambian (o cambiarían, en seco). `revertir` vuelve a las claves viejas,
    para volver a desplegar la versión anterior de COLOQUIO."""
    renombres = {v: k for k, v in RENOMBRES.items()} if revertir else RENOMBRES
    total = 0
    for sesion_id, sesion in store.listar("sesion"):
        cambios = migrar_sesion(sesion, renombres)
        if cambios:
            total += 1
            salida(f"sesion/{sesion_id}: {', '.join(sorted(cambios))}")
            if aplicar:
                store.update(f"sesion/{sesion_id}", cambios)
        for pid, conv in store.listar(f"sesion/{sesion_id}/convocatoria"):
            seg, cambio = _segmento(conv.get("segmento"), renombres)
            if cambio:
                total += 1
                salida(f"sesion/{sesion_id}/convocatoria/{pid}: segmento")
                if aplicar:
                    store.update(f"sesion/{sesion_id}/convocatoria/{pid}", {"segmento": seg})
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--aplicar", action="store_true", help="escribir (sin esto, en seco)")
    parser.add_argument("--revertir", action="store_true", help="volver a las claves viejas")
    parser.add_argument("--proyecto", default=os.environ.get("GOOGLE_CLOUD_PROJECT", "gestion-paneles"))
    parser.add_argument("--base", default="coloquio")
    args = parser.parse_args()

    from coloquio import store

    st = store.StoreFirestore.conectar(args.proyecto, args.base)
    n = migrar(st, aplicar=args.aplicar, revertir=args.revertir)
    if args.aplicar:
        print(f"Listo: {n} documento(s) actualizados.")
    else:
        print(f"En seco: {n} documento(s) cambiarían. Para escribir: --aplicar")


if __name__ == "__main__":
    main()
