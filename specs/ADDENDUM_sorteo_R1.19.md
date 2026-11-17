# ADDENDUM — COLOQUIO · R1.19: la selección de candidatos es un sorteo con semilla

**Agrega a:** `coloquio/specs/SPEC_fase1.md`, requisito R1.19
**Toca:** `paneles` (`db/boveda/0035`) y `coloquio` (selección y propuesta)
**Antecedente:** `paneles` · decisión **D89 / R-ALE**, ya implementada y en producción
**Última actualización:** 2026-11-17

---

## 1. Problem Statement

La superficie de selección cualitativa termina así:

```sql
return query
  select x, array(...)
    from unnest(ids) x
   order by x          -- x es el id_persona
   limit p_limite;
```

Ordena por `id_persona` —un uuid opaco— y corta. Como el uuid de una persona no cambia nunca, **la misma búsqueda devuelve siempre a la misma gente, en el mismo orden, para siempre**. Si un filtro alcanza a 3.000 personas y el límite es 500, se opera sobre las 500 de uuid más bajo y las otras 2.500 no existen para el sistema.

Eso rompe tres cosas:

- **La propuesta de invitación pierde sentido.** Su desempate final es el orden de la lista de espera, que hereda el orden en que el coordinador incorporó a la gente, que hereda el orden de la búsqueda. Si arriba siempre están los mismos, la propuesta siempre propone a los mismos.
- **El panel efectivo pasa a ser el límite, no su tamaño real.**
- **Interactúa mal con el filtro de fatiga.** A medida que se queman los primeros, la fatiga los excluye y se baja en la lista de uuids — pero determinísticamente, siempre a los mismos siguientes. La fatiga termina administrando una cola fija en vez de repartir.

**Esto ya pasó en `paneles` y ya está resuelto.** La decisión **D89** lo cuenta: una consulta demográfica contaba bien el segmento pero mostraba `order by p.nombre limit 50`, y «Crear encuesta con estos panelistas» tomaba exactamente a esas personas. *«El nombre está asociado al sexo y a la generación: el sesgo pasaba directo a la audiencia de la encuesta.»* La `0034` reintrodujo el mismo problema con otro orden arbitrario.

## 2. Goals

- Que una búsqueda demográfica pura reparta sobre todo el segmento elegible, no sobre un subconjunto fijo.
- Que la selección siga siendo **reproducible y auditable**: volver a ejecutar la misma búsqueda tiene que dar la misma gente.
- Que el coordinador sepa **cuántos cumplen el filtro en total**, y cuántos hay por cada celda de cuota, antes de empezar a convocar.
- Que la factibilidad de una cuota se vea al armar la sesión y no cuando falta gente el día del grupo.
- Que la propuesta de invitación herede un orden justo sin cambiar su lógica.
- Reusar el mecanismo de `paneles`, no inventar uno.

## 3. Non-Goals

- **No se usa `random()`.** Rompe la reproducibilidad y la estabilidad entre cargas de pantalla: el coordinador refresca y la lista se le mueve abajo de los pies. D89 ya lo descartó por lo mismo.
- No se cambia la lógica de `proponer_invitacion()`: su cadena de desempate está bien, el problema es el orden que recibe.
- No se toca el ranking semántico. Cuando hay criterio semántico, el orden por relevancia es un criterio legítimo y es el que el coordinador quiere.
- No se agrega rotación por «hace cuánto que no se lo invita». Es mejor, pero ese dato está en COLOQUIO y no en la bóveda, y obliga a cruzar los dos mundos antes de cortar. Después, si el sorteo no alcanza.

## 4. User Stories

- Como coordinador, quiero que dos estudios distintos del mismo segmento no me propongan a la misma gente, para no quemar siempre a los mismos panelistas.
- Como coordinador, quiero que si refresco la pantalla o vuelvo mañana, la lista de candidatos sea la misma, para no perder el trabajo de haber ido eligiendo.
- Como coordinador, quiero poder **volver a sortear** cuando la lista que salió no me sirve.
- Como investigador, quiero saber que el filtro alcanzó a 3.000 personas aunque vea 500, para entender si lo que estoy mirando es el segmento o una parte.
- Como investigador, quiero poder rehacer la selección de un estudio viejo tal cual fue, para defender cómo se reclutó.

## 5. Requisitos

### R1.19.a — Sorteo con semilla en la bóveda

`f_persona_convocable_filtrada()` suma un parámetro de semilla y, cuando viene, ordena por el sorteo en vez de por el uuid.

```sql
f_persona_convocable_filtrada(
    p_finalidad text,
    p_filtros   jsonb,
    p_limite    int  default 500,
    p_semilla   text default null)
```

- Con `p_semilla`, el orden es **`md5(id_persona::text || p_semilla), id_persona`** — exactamente `demografia.ORDEN_DE_SORTEO` de `paneles`. El desempate por id es solo para que el orden sea total.
- Sin `p_semilla`, se conserva el comportamiento actual (`order by id_persona`). Mantiene la compatibilidad y no obliga a desplegar las dos puntas a la vez.
- **No se usa `random()`.** Misma semilla y mismos datos ⇒ misma selección.
- La semilla se valida con el mismo criterio que `consultas.normalizar_semilla()`: letras, números, `-` o `_`, hasta 64.

### R1.19.b — Cuántos cumplen en total

La función devuelve también el tamaño real del conjunto que pasó el filtro, antes del `limit`.

- Se agrega `total bigint` a la salida (un `count(*) over ()`, que no cuesta una segunda pasada).
- Sin esto, el coordinador no puede distinguir «el segmento tiene 500» de «vi 500 de 3.000», y el sorteo le parecería innecesario.

### R1.19.c — La semilla vive en la sesión

Acá COLOQUIO se aparta de `paneles`, y es la decisión de diseño del requisito.

En `paneles` la semilla vive en la ejecución de la consulta, porque una consulta se corre y se mira. En COLOQUIO la lista de candidatos **se construye a lo largo de días**: el coordinador busca, incorpora algunos, vuelve al otro día, busca de nuevo. Si la semilla fuera por ejecución, cada búsqueda le reordenaría la lista y perdería el hilo.

- La primera vez que se ejecuta una selección en una sesión, se genera una semilla y **se guarda en la sesión**.
- Todas las búsquedas siguientes de esa sesión usan esa semilla.
- La semilla **se muestra en pantalla**, corta y copiable, igual que en `paneles`.
- Hay un **«volver a sortear»** que genera una semilla nueva, la guarda y vuelve a buscar. Avisa que la lista va a cambiar.
- La semilla queda en la sesión para siempre: es lo que permite rehacer la selección de un estudio viejo tal cual fue.

### R1.19.d — Qué pasa con el criterio semántico

- **Con criterio semántico, el orden por defecto sigue siendo el ranking.** Es un criterio legítimo y es lo que el coordinador quiere: los más relevantes primero.
- La semilla igual se guarda y se usa para el desempate entre personas de puntaje idéntico.
- **P1:** ofrecer, como en `R-ALE.2` de `paneles`, la opción de sortear entre los que cumplen en vez de rankear. Tiene sentido para estudios donde la relevancia no es el criterio de recluta. No es P0 porque el problema real es la búsqueda demográfica pura.

### R1.19.e — La propuesta hereda el orden, no lo rehace

- `proponer_invitacion()` **no cambia**. Su desempate final por `ordenListaEspera` pasa a ser justo solo, porque la lista de espera ahora viene del sorteo.
- Lo mismo vale para `reemplazo.py`, que ordena por `(evidencia_floja, ordenListaEspera)`.
- **No se sortea de nuevo en la propuesta.** El sorteo ya ocurrió aguas arriba, y volver a sortear acá rompería la reproducibilidad que R1.19.a vino a dar.

### R1.19.f — El límite deja de ser global

Un tope único de 500 sobre un universo que se va a usar para llenar cuotas es el error de fondo: reparte bien el sesgo, pero no garantiza que cada estrato tenga con qué cerrarse. Se reemplaza por dos cosas.

**Paginación estable sobre el sorteo.** El sorteo con semilla la hace posible —es la misma propiedad que D89 señala: con `random()` cada página saldría de un sorteo distinto—. La función acepta un desplazamiento y la pantalla trae de a tandas; el coordinador puede recorrer el segmento entero si quiere, y el orden no se mueve entre tandas ni entre días.

- `f_persona_convocable_filtrada()` suma `p_desde int default 0`.
- El tope duro de 5.000 por llamada **se conserva**: es la guarda contra usar la superficie para bajarse el padrón, y no es lo mismo que el límite de pantalla.

**Sorteo por estrato cuando la sesión tiene cuotas.** Es lo que vuelve correcta la aritmética de la propuesta.

- Dada una sesión con cuotas, la búsqueda devuelve, por cada celda de cuota, **su total elegible** y una tanda sorteada de esa celda, en vez de una tanda global.
- Con eso la pantalla puede decir, antes de convocar a nadie: «mujeres 55+ Canelones: necesitás 6 invitadas, hay 80 elegibles» o «hay 3». La **factibilidad de la cuota se ve al armar la sesión**, no cuando falta gente a tres horas del grupo.
- Dada una sesión sin cuotas, se sortea global y se pagina, que es el caso simple.

**Criterios de aceptación**

- Dado un segmento de 3.000 con cuotas definidas, entonces cada celda informa su total elegible, y ninguna queda representada solo por los pocos que cayeron en una tanda global.
- Dada una celda cuyo total elegible es menor que su meta de invitación, entonces se avisa **al armar la sesión**, no al proponer.
- Dadas dos tandas consecutivas con la misma semilla, entonces no hay repetidos ni salteados.
- Dada una llamada con más de 5.000, entonces se rechaza.

## 6. Criterios de aceptación

- Dos sesiones distintas con el mismo filtro y semillas distintas devuelven conjuntos distintos, y la diferencia es grande cuando el segmento es mucho mayor que el límite.
- La misma sesión, ejecutada dos veces, devuelve exactamente la misma gente en el mismo orden.
- «Volver a sortear» cambia la semilla, cambia la lista, y la semilla nueva queda guardada.
- Con un filtro que alcanza a más personas que el límite, la respuesta informa el total y la pantalla lo muestra.
- Llamar a la función sin semilla se comporta como antes (compatibilidad).
- Una semilla con caracteres inválidos se rechaza.
- Sobre un segmento grande, la proporción por categoría de los sorteados se parece a la del segmento entero. Es la prueba de que el sesgo se fue.
- La propuesta de invitación sigue pasando todas sus pruebas sin cambios.
- Dado un estudio viejo con su semilla guardada, se puede reproducir su selección.

## 7. Migración de lo que ya existe

Las sesiones creadas antes de este cambio no tienen semilla. Al abrir la selección de una de ellas se le genera una y se guarda, igual que a una nueva. No hace falta script de migración: la lista de esas sesiones va a cambiar la primera vez, y es lo correcto — la que tenían estaba sesgada.

Conviene avisarlo en el documento de despliegue, para que nadie se sorprenda si una sesión en curso muestra candidatos distintos.

## 8. Dependencias

- **Bloqueante:** `db/boveda/0035` en `paneles` con R1.19.a, R1.19.b y R1.19.f, y el `grant` de la firma nueva a `coloquio_app`. Como la firma cambia, hay que otorgar la nueva y revocar la vieja, o dejar las dos por un tiempo.
- `scripts/verificar_coloquio.py` suma la firma nueva a su lista blanca.
- Nada más: el cambio en COLOQUIO es de orden y de estado de sesión, no de modelo de datos.

## 9. Definition of Done

1. La `0035` aplica y es re-ejecutable, en una transacción.
2. Las pruebas de `paneles` siguen pasando sin modificar ninguna.
3. `verificar_coloquio.py` pasa con la firma nueva.
4. Las 118 pruebas de COLOQUIO pasan, más las nuevas de los criterios de §6.
5. La prueba de representatividad del §6 corre sobre un segmento sintético grande y es parte de la suite, no una verificación manual.
6. `decisiones.md` de COLOQUIO suma la decisión, citando D89 de `paneles` como antecedente, y explicando por qué acá la semilla vive en la sesión y no en la ejecución.

## 10. Costo

Nulo. Un `md5` sobre un conjunto que ya se está recorriendo y un `count(*) over ()` en la misma pasada. No agrega consultas, ni recursos, ni llamadas a terceros.

## 11. Preguntas abiertas

- **[producto]** ¿«Volver a sortear» debería dejar rastro? En `paneles` cada ejecución se guarda. Acá, si alguien sortea cinco veces hasta que le gusta la lista, eso es un sesgo de selección que nadie ve. Registrar cuántas veces se sorteó una sesión es barato y hace visible la práctica.
