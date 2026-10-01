"""El store de COLOQUIO: Firestore, **base con nombre propio** (SPEC §6, §7.2).

El código de dominio no habla con Firestore directamente: habla con `Store`.
Hay dos motivos, y ninguno es estético.

1. **R1.12 se hace valer acá.** Toda escritura —`set`, `update`, en
   transacción o fuera de ella— pasa por `pii.validar_sin_pii()` antes de
   salir. No hay otro camino para escribir, así que no hay forma de olvidarse
   la validación.
2. **La misma lógica corre en memoria.** Las pruebas y el servidor local usan
   `StoreMemoria`, que imita las dos reglas de Firestore que más muerden:
   en una transacción todas las lecturas van antes que las escrituras, y las
   escrituras se aplican juntas al final. Si el dominio viola la primera, la
   prueba falla acá en vez de en producción.

Las rutas son las de Firestore: `sesion/abc/convocatoria/<id_persona>`.
"""

import copy
import threading

from . import pii

OPERADORES = {"==", "!=", "<", "<=", ">", ">=", "in", "array_contains"}


def coleccion_raiz(ruta):
    return ruta.strip("/").split("/")[0]


def _validar(ruta, datos):
    pii.validar_sin_pii(datos, coleccion_raiz(ruta))


class Store:
    """Interfaz. Ver `StoreFirestore` y `StoreMemoria`."""

    def get(self, ruta):
        raise NotImplementedError

    def get_many(self, rutas):
        raise NotImplementedError

    def set(self, ruta, datos, merge=False):
        raise NotImplementedError

    def update(self, ruta, datos):
        raise NotImplementedError

    def delete(self, ruta):
        raise NotImplementedError

    def listar(self, coleccion, filtros=(), orden=None, desc=False, limite=None):
        """[(id, datos)] de una colección, con filtros `(campo, op, valor)`."""
        raise NotImplementedError

    def grupo(self, nombre, filtros=()):
        """[(ruta, datos)] de todas las subcolecciones con ese nombre."""
        raise NotImplementedError

    def todos(self):
        """{ruta: datos} de toda la base. Para auditorías (DoD 10) y pruebas."""
        raise NotImplementedError

    def transaccion(self, funcion):
        """Corre `funcion(tx)` en una transacción y devuelve su resultado.

        OJO: Firestore puede reintentar `funcion` si hay contención. No poner
        adentro efectos externos (mandar un WhatsApp, llamar a la bóveda).
        """
        raise NotImplementedError


# ════════════════════════════════════════════════════════════════════
#  Firestore
# ════════════════════════════════════════════════════════════════════

class StoreFirestore(Store):
    def __init__(self, cliente):
        self.c = cliente

    @classmethod
    def conectar(cls, proyecto=None, base="coloquio"):
        from google.cloud import firestore

        return cls(firestore.Client(project=proyecto, database=base))

    def _ref(self, ruta):
        return self.c.document(ruta)

    def get(self, ruta):
        snap = self._ref(ruta).get()
        return snap.to_dict() if snap.exists else None

    def get_many(self, rutas):
        rutas = list(dict.fromkeys(rutas))
        salida = {r: None for r in rutas}
        # `get_all` acepta muchas referencias, pero se trocea para no armar
        # pedidos gigantes con selecciones de cientos de candidatos.
        for i in range(0, len(rutas), 300):
            refs = [self._ref(r) for r in rutas[i:i + 300]]
            for snap in self.c.get_all(refs):
                if snap.exists:
                    salida[snap.reference.path] = snap.to_dict()
        return salida

    def set(self, ruta, datos, merge=False):
        _validar(ruta, datos)
        self._ref(ruta).set(datos, merge=merge)

    def update(self, ruta, datos):
        _validar(ruta, datos)
        self._ref(ruta).update(datos)

    def delete(self, ruta):
        self._ref(ruta).delete()

    def _consulta(self, base, filtros, orden=None, desc=False, limite=None):
        from google.cloud.firestore_v1.base_query import FieldFilter
        from google.cloud import firestore

        q = base
        for campo, op, valor in filtros:
            q = q.where(filter=FieldFilter(campo, op, valor))
        if orden:
            q = q.order_by(orden, direction=(
                firestore.Query.DESCENDING if desc else firestore.Query.ASCENDING))
        if limite:
            q = q.limit(limite)
        return q

    def listar(self, coleccion, filtros=(), orden=None, desc=False, limite=None):
        q = self._consulta(self.c.collection(coleccion), filtros, orden, desc, limite)
        return [(d.id, d.to_dict()) for d in q.stream()]

    def grupo(self, nombre, filtros=()):
        q = self._consulta(self.c.collection_group(nombre), filtros)
        return [(d.reference.path, d.to_dict()) for d in q.stream()]

    def todos(self):
        salida = {}

        def recorrer(colecciones):
            for col in colecciones:
                for doc in col.stream():
                    salida[doc.reference.path] = doc.to_dict()
                for ref in col.list_documents():
                    recorrer(ref.collections())

        recorrer(self.c.collections())
        return salida

    def transaccion(self, funcion):
        from google.cloud import firestore

        store = self

        @firestore.transactional
        def correr(transaction):
            return funcion(_TxFirestore(store, transaction))

        return correr(self.c.transaction())


class _TxFirestore:
    def __init__(self, store, transaction):
        self.s = store
        self.t = transaction

    def get(self, ruta):
        snap = self.s._ref(ruta).get(transaction=self.t)
        return snap.to_dict() if snap.exists else None

    def get_many(self, rutas):
        rutas = list(dict.fromkeys(rutas))
        salida = {r: None for r in rutas}
        if rutas:
            for snap in self.s.c.get_all([self.s._ref(r) for r in rutas],
                                         transaction=self.t):
                if snap.exists:
                    salida[snap.reference.path] = snap.to_dict()
        return salida

    def listar(self, coleccion, filtros=(), orden=None, desc=False, limite=None):
        from google.cloud.firestore_v1.collection import CollectionReference
        from google.cloud.firestore_v1.query import Query

        q = self.s._consulta(self.s.c.collection(coleccion), filtros, orden, desc, limite)
        # `transaction.get` acepta un Query o un documento, no una colección.
        if isinstance(q, CollectionReference):
            q = Query(q)
        return [(d.id, d.to_dict()) for d in self.t.get(q)]

    def set(self, ruta, datos, merge=False):
        _validar(ruta, datos)
        self.t.set(self.s._ref(ruta), datos, merge=merge)

    def update(self, ruta, datos):
        _validar(ruta, datos)
        self.t.update(self.s._ref(ruta), datos)

    def delete(self, ruta):
        self.t.delete(self.s._ref(ruta))


# ════════════════════════════════════════════════════════════════════
#  Memoria (pruebas y servidor local)
# ════════════════════════════════════════════════════════════════════

class LecturaDespuesDeEscritura(RuntimeError):
    """Firestore exige leer todo antes de escribir en una transacción."""


def _cumple(datos, campo, op, valor):
    actual = datos
    for parte in campo.split("."):
        if not isinstance(actual, dict) or parte not in actual:
            return False
        actual = actual[parte]
    try:
        if op == "==":
            return actual == valor
        if op == "!=":
            return actual != valor
        if op == "<":
            return actual < valor
        if op == "<=":
            return actual <= valor
        if op == ">":
            return actual > valor
        if op == ">=":
            return actual >= valor
        if op == "in":
            return actual in valor
        if op == "array_contains":
            return isinstance(actual, list) and valor in actual
    except TypeError:
        return False
    raise ValueError(f"Operador no soportado: {op}")


class StoreMemoria(Store):
    def __init__(self):
        self.docs = {}
        self._candado = threading.RLock()

    def get(self, ruta):
        with self._candado:
            d = self.docs.get(ruta.strip("/"))
            return copy.deepcopy(d) if d is not None else None

    def get_many(self, rutas):
        return {r: self.get(r) for r in dict.fromkeys(rutas)}

    def set(self, ruta, datos, merge=False):
        _validar(ruta, datos)
        with self._candado:
            ruta = ruta.strip("/")
            if merge and ruta in self.docs:
                nuevo = copy.deepcopy(self.docs[ruta])
                nuevo.update(copy.deepcopy(datos))
                self.docs[ruta] = nuevo
            else:
                self.docs[ruta] = copy.deepcopy(datos)

    def update(self, ruta, datos):
        _validar(ruta, datos)
        with self._candado:
            ruta = ruta.strip("/")
            if ruta not in self.docs:
                raise KeyError(f"No existe el documento {ruta}")
            self.docs[ruta].update(copy.deepcopy(datos))

    def delete(self, ruta):
        with self._candado:
            self.docs.pop(ruta.strip("/"), None)

    def _filtrar(self, items, filtros, orden, desc, limite):
        for campo, op, valor in filtros:
            if op not in OPERADORES:
                raise ValueError(op)
            items = [(k, d) for k, d in items if _cumple(d, campo, op, valor)]
        if orden:
            items = [(k, d) for k, d in items if orden in d]
            items.sort(key=lambda kd: kd[1][orden], reverse=desc)
        if limite:
            items = items[:limite]
        return [(k, copy.deepcopy(d)) for k, d in items]

    def listar(self, coleccion, filtros=(), orden=None, desc=False, limite=None):
        coleccion = coleccion.strip("/")
        profundidad = coleccion.count("/") + 1
        with self._candado:
            items = [
                (ruta.split("/")[-1], d) for ruta, d in self.docs.items()
                if ruta.startswith(coleccion + "/") and ruta.count("/") == profundidad
            ]
        return self._filtrar(items, filtros, orden, desc, limite)

    def grupo(self, nombre, filtros=()):
        with self._candado:
            items = [
                (ruta, d) for ruta, d in self.docs.items()
                if len(ruta.split("/")) >= 2 and ruta.split("/")[-2] == nombre
            ]
        return self._filtrar(items, filtros, None, False, None)

    def todos(self):
        with self._candado:
            return copy.deepcopy(self.docs)

    def transaccion(self, funcion):
        with self._candado:
            tx = _TxMemoria(self)
            resultado = funcion(tx)
            tx._aplicar()
            return resultado


class _TxMemoria:
    def __init__(self, store):
        self.s = store
        self.escrituras = []

    def _leer(self):
        if self.escrituras:
            raise LecturaDespuesDeEscritura(
                "En una transacción de Firestore todas las lecturas van antes "
                "que las escrituras.")

    def get(self, ruta):
        self._leer()
        return self.s.get(ruta)

    def get_many(self, rutas):
        self._leer()
        return self.s.get_many(rutas)

    def listar(self, coleccion, filtros=(), orden=None, desc=False, limite=None):
        self._leer()
        return self.s.listar(coleccion, filtros, orden, desc, limite)

    def set(self, ruta, datos, merge=False):
        _validar(ruta, datos)
        self.escrituras.append(("set", ruta, copy.deepcopy(datos), merge))

    def update(self, ruta, datos):
        _validar(ruta, datos)
        if self.s.get(ruta) is None and not any(
                e[1] == ruta and e[0] == "set" for e in self.escrituras):
            raise KeyError(f"No existe el documento {ruta}")
        self.escrituras.append(("update", ruta, copy.deepcopy(datos), False))

    def delete(self, ruta):
        self.escrituras.append(("delete", ruta, None, False))

    def _aplicar(self):
        for tipo, ruta, datos, merge in self.escrituras:
            if tipo == "set":
                self.s.set(ruta, datos, merge=merge)
            elif tipo == "update":
                self.s.update(ruta, datos)
            else:
                self.s.delete(ruta)
