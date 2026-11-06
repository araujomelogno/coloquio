"""R1.2 · R1.3 — Selección de candidatos contra las bóvedas, con fatiga.

El cruce entre los dos mundos (SPEC §7.3):

```
1. Bóveda   → v_persona_convocable + criterio demográfico  → id_persona
2. Motor    → ranking semántico de `paneles`               → id_persona ordenados
3. Firestore→ participacionCuali/{id} de los candidatos    → descarta por fatiga
4. Acá      → combina y devuelve la lista con evidencia e historial
```

* **Demográfica pura**: se resuelve entera contra la vista y **no llama al
  motor semántico** (`abrioSemantica: false` en la respuesta, como en
  `paneles`).
* **Semántica o mixta**: el motor de `paneles` ordena; después los ids se
  cruzan contra `v_persona_convocable` con `contacto_participacion`. Así
  «nadie sin consentimiento vigente aparece» lo garantiza la vista, no un
  filtro de esta aplicación: si la vista no devuelve a alguien, no está.
* El historial cualitativo de cada candidato viaja en la misma respuesta
  (R1.9): decidir a quién llamar sin ver cuántas veces vino es el error que
  la fase viene a eliminar.
* La fatiga **excluye** (R1.3). Los excluidos se devuelven aparte, con el
  motivo, y solo entran al embudo con una anulación registrada.
* **Filtros del catálogo (R1.14).** El formulario se arma con
  `v_atributo_catalogo` y la búsqueda demográfica es
  `f_persona_convocable_filtrada()`: ningún atributo tiene nombre en COLOQUIO.
  Cada candidato vuelve con su **segmento**: sus valores en las dimensiones
  con cuota de la sesión, leídos con `atributos_de_personas()`.
* **Modo laxo o estricto, por consulta (R1.18).** Por defecto, laxo: quien
  tiene evidencia dudosa o ausente entra **marcado** (`penalizado`,
  `confianzaBaja`), en vez de desaparecer. Cada criterio puede ser `duro`
  (filtra en los dos modos). La respuesta dice qué modo se usó y, siempre,
  cuántos dejó afuera el motor y por qué (`excluidosSemanticos`).
"""

from . import (
    atributos, configuracion, embudo, historial, sesiones, util,
)
from .errores import DatosInvalidos, NoEncontrado, RequiereAnulacion
from .motor import MODO_POR_DEFECTO, MODOS as MODOS_SEMANTICOS, ErrorMotor, normalizar_criterios

MODOS = ("demografica", "semantica", "mixta")

# R1.18 — las marcas de calidad de evidencia que viajan con un candidato hasta
# el embudo, para que la propuesta de invitación no complete cuota con ellos.
MARCAS_EVIDENCIA = ("penalizado", "verificacionIncompleta", "confianzaBaja")
LIMITE_MAXIMO = 500


def seleccionar(ctx, actor, sesion_id, cuerpo):
    sesion = sesiones.exigir(ctx.store, sesion_id)
    modo = cuerpo.get("modo") or "demografica"
    if modo not in MODOS:
        raise DatosInvalidos(f"Modo desconocido: {modo!r}.", {"modos": list(MODOS)})
    filtros = atributos.normalizar_filtros(cuerpo.get("filtros"))
    criterios = normalizar_criterios(cuerpo.get("criterios"))
    modo_semantico = str(cuerpo.get("modoSemantico") or MODO_POR_DEFECTO).strip().lower()
    if modo_semantico not in MODOS_SEMANTICOS:
        raise DatosInvalidos(f"Modo semántico desconocido: {modo_semantico!r}.",
                             {"modosSemanticos": list(MODOS_SEMANTICOS)})
    limite = util.entero(cuerpo.get("limite"), "limite", 1, LIMITE_MAXIMO, por_defecto=200)
    if modo in ("semantica", "mixta") and not criterios:
        raise DatosInvalidos("Una selección semántica o mixta necesita al menos un criterio en texto.")
    if modo == "mixta" and not filtros:
        raise DatosInvalidos("Una selección mixta necesita algún criterio demográfico.")

    degradaciones = []
    abrio_semantica = False
    ranking = None
    excluidos_semanticos = None
    modo_usado = None
    vaciado_por_el_modo = False

    if modo != "demografica":
        abrio_semantica = True
        try:
            resultado = ctx.motor.consultar(
                filtros if modo == "mixta" else {}, criterios, actor.token, limite=limite,
                modo=modo_semantico)
            ranking = resultado["items"]
            modo_usado = resultado.get("modo") or modo_semantico
            excluidos_semanticos = resultado.get("excluidos")
            degradaciones.extend(resultado.get("degradaciones") or [])
            if not ranking and (excluidos_semanticos or {}).get("total"):
                # El motor encontró gente y la dejó afuera (modo estricto o un
                # criterio duro). Caer a demográfica pura metería por la
                # ventana a quienes el modo acaba de excluir: la lista queda
                # vacía y se dice por qué.
                vaciado_por_el_modo = True
                degradaciones.append({
                    "etapa": "semantica",
                    "motivo": (f"El motor dejó afuera a los {excluidos_semanticos['total']} "
                               f"candidatos que encontró (modo {modo_usado})."),
                    "consecuencia": ("No hay candidatos. Probá en modo laxo o sin marcar "
                                     "criterios como duros."),
                })
            elif not ranking:
                degradaciones.append({
                    "etapa": "semantica",
                    "motivo": ("El motor no encontró contenido embebido que se acerque "
                               "al criterio para este segmento."),
                    "consecuencia": "Se muestra la selección demográfica pura, sin ranking.",
                })
        except ErrorMotor as error:
            degradaciones.append({
                "etapa": "semantica",
                "motivo": str(error),
                "consecuencia": ("Se resolvió demográfica pura. El ranking semántico no "
                                 "está disponible en este momento."),
            })
            ranking = None

    # 1 · La vista. Con ranking, restringida a sus ids: el gate lo pone la bóveda.
    if vaciado_por_el_modo:
        base, descartados_gate = [], 0
    elif ranking:
        por_id = {r["idPersona"]: r for r in ranking}
        # El gate lo pone la bóveda: quien no tiene contacto_participacion
        # vigente no está, aunque el motor lo haya rankeado.
        vigentes = ctx.boveda.vigentes(list(por_id))
        ids_rank = [i for i in por_id if i in vigentes]
        filas = ctx.boveda.atributos(ids_rank) if ids_rank else []
        if filtros:
            # Mixta: los ids del ranking pasan otra vez por los filtros, con
            # los valores de la bóveda. Antes, la bóveda valida los filtros
            # (una clave o una categoría desconocida es error, no un filtro
            # que no se aplicó).
            ctx.boveda.convocables(filtros, limite=1)
            por_persona = atributos.filas_por_persona(filas)
            cat = atributos.catalogo(ctx)
            ids_rank = [i for i in ids_rank if atributos.cumple(por_persona.get(i, {}), filtros, cat)]
        segs = atributos.segmentos(ctx, ids_rank, sesiones.dimensiones_con_cuota(sesion), filas)
        base = [{"idPersona": i, "segmento": segs[i]} for i in ids_rank]
        for b in base:
            r = por_id[b["idPersona"]]
            b.update({"puntaje": r.get("puntaje"), "confianza": r.get("confianza"),
                      "estado": r.get("estado"),
                      "rango": r.get("rango"), "evidencia": r.get("evidencia") or [],
                      **{m: bool(r.get(m)) for m in MARCAS_EVIDENCIA}})
        base.sort(key=lambda b: b.get("rango") or 10 ** 9)
        descartados_gate = len(por_id) - len(base)
    else:
        ids_demo = ctx.boveda.convocables(filtros, limite=limite)
        segs = atributos.segmentos(ctx, ids_demo, sesiones.dimensiones_con_cuota(sesion))
        base = [{"idPersona": i, "segmento": segs[i]} for i in ids_demo]
        descartados_gate = 0

    # 2 · Historial y fatiga, por lectura puntual (la cláusula `in` está topeada).
    ids = [b["idPersona"] for b in base]
    docs = ctx.store.get_many([historial.ruta(i) for i in ids])
    cfg_fatiga = configuracion.fatiga(ctx.store)
    ahora = ctx.ahora()
    candidatos, excluidos = [], []
    for b in base:
        doc = docs.get(historial.ruta(b["idPersona"]))
        fatiga = historial.evaluar_fatiga(doc, sesion["categoria"], cfg_fatiga, ahora)
        en_sesion = any(c.get("sesionId") == sesion_id for c in (doc or {}).get("convocadoEn") or [])
        otra = historial.sesion_del_mismo_estudio(doc, sesion["estudioId"], excepto_sesion=sesion_id)
        item = {
            **b,
            "codigo": util.codigo_de(b["idPersona"]),
            "historial": historial.resumen(doc),
            "fatiga": fatiga,
            "enEstaSesion": en_sesion,
            "enOtraSesionDelEstudio": otra,
        }
        (excluidos if fatiga["excluido"] else candidatos).append(item)

    ya_en_sesion = embudo.convocatorias(ctx.store, sesion_id)
    seleccionables = [c for c in candidatos if not c["enEstaSesion"] and not c["enOtraSesionDelEstudio"]]
    return {
        "modo": modo,
        "abrioSemantica": abrio_semantica,
        # R1.18 — el modo con que el motor combinó los criterios. `None` si
        # no hubo ranking semántico (demográfica pura o motor caído): no se
        # puede decir «laxo» de una lista que el motor no tocó.
        "modoSemantico": modo_usado,
        "excluidosSemanticos": excluidos_semanticos,
        "calidad": _calidad(candidatos) if modo_usado else None,
        "filtros": filtros,
        "criterios": criterios,
        "total": len(candidatos),
        "candidatos": candidatos,
        "excluidosPorFatiga": excluidos,
        "descartadosPorGate": descartados_gate,
        "degradaciones": degradaciones,
        "configFatiga": cfg_fatiga,
        "avisosCuota": sesiones.avisos_de_disponibilidad(sesion, seleccionables, ya_en_sesion),
        "cuota": sesiones.estado_de_cuota(sesion, ya_en_sesion),
    }


def _calidad(candidatos):
    """El pie de la lista: «187 candidatos · 23 penalizados · 4 sin verificar»."""
    return {
        "penalizados": sum(1 for c in candidatos if c.get("penalizado")),
        "sinVerificar": sum(1 for c in candidatos if c.get("verificacionIncompleta")),
        "confianzaBaja": sum(1 for c in candidatos if c.get("confianzaBaja")),
    }


def marcas_evidencia(pedido):
    """Las marcas R1.18 que manda la lista, reducidas a la lista blanca.

    Solo nombres de marca, nunca texto: la evidencia (la respuesta textual)
    no se guarda en el embudo. Viajan desde el cliente igual que `puntaje`:
    son lo que el coordinador vio al elegir.
    """
    return [m for m in MARCAS_EVIDENCIA if (pedido or {}).get(m) is True]


def incorporar(ctx, actor, sesion_id, cuerpo):
    """Suma candidatos a la lista de espera de la sesión (estado `candidato`).

    El segmento **no** lo manda el cliente: se relee de la bóveda, que además
    vuelve a aplicar el gate. La fatiga se reevalúa acá; quien está excluido
    solo entra con `anulacion: {motivo}` y el permiso `anular_fatiga`.
    """
    pedidos = cuerpo.get("candidatos") or []
    if not pedidos:
        raise DatosInvalidos("No hay candidatos para incorporar.")
    por_id = {}
    for p in pedidos:
        pid = util.validar_id_persona(p.get("idPersona") if isinstance(p, dict) else p)
        por_id[pid] = p if isinstance(p, dict) else {}
    motivo_general = str((cuerpo.get("anulacion") or {}).get("motivo") or "").strip()
    sesion = sesiones.exigir(ctx.store, sesion_id)
    sesiones.exigir_abierta(sesion)

    vigentes = vigentes_con_segmento(ctx, sesion, list(por_id))
    sin_gate = [i for i in por_id if i not in vigentes]
    cfg_fatiga = configuracion.fatiga(ctx.store)
    ahora = ctx.ahora()
    return _incorporar_tx(ctx, actor, sesion_id, por_id, vigentes, sin_gate,
                          motivo_general, cfg_fatiga, ahora,
                          es_reemplazo_de=cuerpo.get("esReemplazoDe"))


def vigentes_con_segmento(ctx, sesion, ids):
    """{id: {segmento}} de los que siguen convocables. El segmento **no** lo
    manda el cliente: se relee de la bóveda, que además reaplica el gate."""
    gate = ctx.boveda.vigentes(ids)
    vigentes = [i for i in ids if i in gate]
    segs = atributos.segmentos(ctx, vigentes, sesiones.dimensiones_con_cuota(sesion))
    return {i: {"segmento": segs[i]} for i in vigentes}


def _incorporar_tx(ctx, actor, sesion_id, por_id, vigentes, sin_gate, motivo_general,
                   cfg_fatiga, ahora, es_reemplazo_de=None, estado_final=None):
    ids = [i for i in por_id if i in vigentes]

    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        if not sesion:
            raise NoEncontrado("No existe esa sesión.")
        sesiones.exigir_abierta(sesion)
        convs = tx.get_many([embudo.ruta(sesion_id, i) for i in ids])
        hists = tx.get_many([historial.ruta(i) for i in ids])
        existentes = tx.listar(f"sesion/{sesion_id}/convocatoria")
        orden = max([int(d.get("ordenListaEspera") or 0) for _, d in existentes] or [0])

        requieren, repetidos, en_otra = [], [], []
        altas = []
        for i in ids:
            if convs[embudo.ruta(sesion_id, i)]:
                repetidos.append(i)
                continue
            hist = hists[historial.ruta(i)]
            otra = historial.sesion_del_mismo_estudio(hist, sesion["estudioId"], excepto_sesion=sesion_id)
            if otra:
                en_otra.append({"idPersona": i, "sesionId": otra})
                continue
            fatiga = historial.evaluar_fatiga(hist, sesion["categoria"], cfg_fatiga, ahora)
            anulacion = None
            if fatiga["excluido"]:
                motivo = str((por_id[i].get("anulacion") or {}).get("motivo") or motivo_general).strip()
                if not motivo or not actor.puede("anular_fatiga"):
                    requieren.append({"idPersona": i, "codigo": util.codigo_de(i),
                                      "motivos": fatiga["motivos"]})
                    continue
                anulacion = {"regla": "fatiga_cualitativa", "motivo": motivo,
                             "actorUid": actor.uid, "ts": ahora,
                             "motivosFatiga": [m["mensaje"] for m in fatiga["motivos"]]}
            altas.append((i, hist, anulacion))

        if requieren:
            # El bloqueo se cuenta aunque la operación no siga: es la métrica
            # de «re-convocatorias bloqueadas por el filtro» (SPEC §12). Como
            # esta transacción aborta, se registra afuera (`_contar_bloqueo`).
            raise RequiereAnulacion(
                "Hay candidatos excluidos por el filtro de fatiga cualitativa. Se "
                "puede saltar la regla, pero no en silencio: indicá el motivo.",
                {"excluidos": requieren})

        for i, hist, anulacion in altas:
            orden += 1
            conv = embudo.nueva(i, vigentes[i]["segmento"], orden, actor.uid, ahora,
                                anulacion=anulacion, es_reemplazo_de=es_reemplazo_de,
                                puntaje=por_id[i].get("puntaje"),
                                marcas_evidencia=marcas_evidencia(por_id[i]))
            embudo.contar_alta(sesion, conv)
            if anulacion:
                embudo._sumar(sesion, "anulacionesFatiga")
            if estado_final:
                embudo.aplicar(sesion, conv, estado_final, conv["canal"], actor.uid, ahora,
                               resultado="reemplazo")
            tx.set(embudo.ruta(sesion_id, i), conv)
            tx.set(historial.ruta(i), historial.registrar_convocatoria(hist, sesion_id, sesion))
        tx.update(f"sesion/{sesion_id}", embudo._campos_sesion(sesion))
        return {
            "incorporados": [a[0] for a in altas],
            "conAnulacion": [a[0] for a in altas if a[2]],
            "yaEstaban": repetidos,
            "enOtraSesionDelEstudio": en_otra,
            "sinConsentimientoVigente": sin_gate,
        }

    try:
        return ctx.store.transaccion(tx_fn)
    except RequiereAnulacion:
        _contar_bloqueo(ctx, sesion_id)
        raise


def _contar_bloqueo(ctx, sesion_id):
    def tx_fn(tx):
        sesion = tx.get(f"sesion/{sesion_id}")
        if sesion:
            m = sesion.setdefault("metricas", {})
            m["reconvocatoriasBloqueadas"] = int(m.get("reconvocatoriasBloqueadas") or 0) + 1
            tx.update(f"sesion/{sesion_id}", {"metricas": m})
    ctx.store.transaccion(tx_fn)


def proponer_invitacion(ctx, sesion_id):
    sesion = sesiones.exigir(ctx.store, sesion_id)
    return sesiones.proponer_invitacion(sesion, embudo.convocatorias(ctx.store, sesion_id))

