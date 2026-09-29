#!/usr/bin/env python3
"""DoD 10 — auditoría de PII del store de COLOQUIO (base Firestore `coloquio`).

Recorre **todos** los documentos de la base con nombre propio y aplica la
misma validación que el store aplica al escribir (`coloquio/pii.py`): claves
con nombre de PII y patrones de email, teléfono o cédula en los campos de
texto libre. Sale con código 1 si encuentra algo.

    gcloud auth application-default login
    python3 scripts/auditar_store.py --proyecto gestion-paneles --base coloquio

Con el emulador: `FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 python3 ... --proyecto demo-coloquio`.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "functions"))

from coloquio import pii, store  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--proyecto", default="gestion-paneles")
    p.add_argument("--base", default="coloquio")
    args = p.parse_args()
    docs = store.StoreFirestore.conectar(args.proyecto, args.base).todos()
    problemas = 0
    for ruta, datos in sorted(docs.items()):
        for h in pii.hallazgos(datos, store.coleccion_raiz(ruta)):
            problemas += 1
            print(f"✗ {ruta}: {h['campo']} ({h['motivo']})")
    print(f"\n{len(docs)} documentos revisados · {problemas} hallazgos de PII")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
