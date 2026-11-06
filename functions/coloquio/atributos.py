"""R1.14 · R1.15 — los atributos demográficos, sin un solo nombre escrito acá.

El vocabulario es el catálogo de la bóveda (`v_atributo_catalogo`): un
atributo nuevo en `paneles` aparece en COLOQUIO sin desplegar nada, y uno
dado de baja desaparece. Este módulo no conoce ninguna clave: las recibe.

* **Filtros.** Viajan con la forma de `f_persona_convocable_filtrada()`:
  `{clave: {en: [...]} | {min, max} | {desde, hasta}}`. Categorías del mismo
  atributo se combinan con *o*; atributos distintos, con *y*. Quien valida es
  la bóveda: una clave, un operador o una categoría desconocidos son error.
  Acá solo se limpia lo vacío que manda un formulario.
* **Segmento.** Las cuotas de una sesión son por cualquier atributo del
  catálogo que tenga categorías. El segmento de una persona son sus valores en
  las dimensiones con cuota de la sesión, leídos con `atributos_de_personas()`.
  Se guarda solo eso (minimización): no la demografía entera.
"""

from .errores import DatosInvalidos

OPERADORES = ("en", "min", "max", "desde", "hasta")


def catalogo(ctx):
    """El catálogo vigente. Sin caché: un atributo nuevo o dado de baja en
    `paneles` se ve en el próximo pedido, sin desplegar ni esperar."""
    return ctx.boveda.catalogo()


def por_clave(catalogo_):
    return {a["clave"]: a for a in catalogo_}


def dimensiones_de_cuota(catalogo_):
    """Los atributos sobre los que se puede poner una cuota: los que tienen
    categorías (categóricos, y derivados como un tramo)."""
    return {a["clave"]: a for a in catalogo_ if a.get("categorias")}


def _vacio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip()) or valor == []


def normalizar_filtros(crudo):
    """Lo que manda el formulario → la forma de la bóveda, sin lo vacío.

    Acepta una lista suelta como atajo de `{en: lista}`. No valida claves ni
    tipos: eso lo hace la bóveda, que es la que sabe.
    """
    if crudo is None:
        return {}
    if not isinstance(crudo, dict):
        raise DatosInvalidos("Los filtros van en un objeto {atributo: condición}.")
    salida = {}
    for clave, cond in crudo.items():
        clave = str(clave).strip()
        if isinstance(cond, (list, tuple, str)):
            cond = {"en": cond}
        if not isinstance(cond, dict):
            raise DatosInvalidos(f"La condición de «{clave}» tiene que ser un objeto.")
        limpia = {}
        for op, valor in cond.items():
            if op == "en":
                if isinstance(valor, str):
                    valor = [v.strip() for v in valor.split(",")]
                valor = [str(v).strip() for v in (valor or []) if not _vacio(v)]
            elif isinstance(valor, str):
                valor = valor.strip()
            if not _vacio(valor):
                limpia[op] = valor
        if limpia:
            salida[clave] = limpia
    return salida


def filas_por_persona(filas):
    salida = {}
    for f in filas:
        salida.setdefault(f["idPersona"], {})[f["atributo"]] = f
    return salida


def segmentos(ctx, ids, dimensiones, filas=None):
    """{idPersona: {dimensión: valor}} para las dimensiones pedidas.

    Una dimensión que la persona no tiene cargada no aparece: no se inventa
    un valor, y entonces no cuenta para ninguna categoría de esa cuota.
    """
    if filas is None:
        filas = ctx.boveda.atributos(ids) if ids and dimensiones else []
    por_persona = filas_por_persona(filas)
    return {i: {d: por_persona[i][d]["valor"] for d in dimensiones if d in por_persona.get(i, {})}
            for i in ids}


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        raise DatosInvalidos(f"«{valor}» no es un número.") from None


def cumple(filas_de_persona, filtros, catalogo_):
    """¿Esta persona cumple los filtros? Para la selección **mixta**.

    En mixta el universo son los ids que rankeó el motor de `paneles` (que ya
    aplicó estos mismos filtros); COLOQUIO los vuelve a pasar por la bóveda
    (`atributos_de_personas`) en vez de confiar. Es la misma regla que
    `f_persona_convocable_filtrada()` —`en` sobre el valor, `min`/`max` sobre
    el número, `desde`/`hasta` sobre la fecha—, y una prueba compara las dos
    sobre el panel entero.
    """
    tipos = {a["clave"]: a["tipo"] for a in catalogo_}
    for clave, cond in filtros.items():
        f = filas_de_persona.get(clave)
        if clave not in tipos:
            raise DatosInvalidos(f"El atributo «{clave}» no está en el catálogo.")
        if f is None:
            return False
        if "en" in cond and (tipos[clave] == "numerico" or f["valor"] not in cond["en"]):
            return False
        for op, compara in (("min", lambda v, x: v >= x), ("max", lambda v, x: v <= x)):
            if op in cond and (f["valorNum"] is None or not compara(f["valorNum"], _numero(cond[op]))):
                return False
        for op, compara in (("desde", lambda v, x: v >= x), ("hasta", lambda v, x: v <= x)):
            if op in cond and (f["valorFecha"] is None or not compara(f["valorFecha"], str(cond[op]))):
                return False
    return True


def validar_columnas(claves):
    """Preferencia de columnas: solo claves (nunca valores)."""
    if not isinstance(claves, list) or len(claves) > 60:
        raise DatosInvalidos("Las columnas van en una lista de hasta 60 atributos.")
    salida = []
    for c in claves:
        c = str(c or "").strip()
        if not c or len(c) > 80 or not all(ch.isalnum() or ch in "_-." for ch in c):
            raise DatosInvalidos(f"Clave de atributo inválida: {c!r}.")
        if c not in salida:
            salida.append(c)
    return salida
