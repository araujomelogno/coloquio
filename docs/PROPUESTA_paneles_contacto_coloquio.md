# Propuesta para `paneles` — `contacto_para_convocatoria()` y la convocatoria activa de COLOQUIO

**Para:** equipo de `paneles` (repo `araujomelogno/paneles`)
**Origen:** desarrollo de COLOQUIO Fase 1
**Estado:** **bloqueante para convocar en producción** · propuesta, no aplicada
**Fecha:** 2026-09-26

---

## El problema

`contacto_para_convocatoria()` (migración `boveda/0014`) exige, además del
consentimiento, que la persona tenga una **convocatoria activa**. Pero lo
verifica mirando **solo las tablas de `paneles`**:

```sql
select exists (
  select 1 from participacion pa
    join encuesta e on e.id = pa.encuesta_id
   where pa.id_persona = p_id_persona
     and e.estado <> 'cerrada')
  into tiene_convocatoria;
```

La SPEC de la Fase 5 dice otra cosa (R5.2): *«Exige que la persona tenga una
convocatoria activa **en el sistema que llama** (ver R5.4: el registro de
consumidores declara cómo se verifica eso para cada uno)»*. La migración
implementó el caso de `paneles` y no el de un segundo consumidor.

Consecuencia: **cuando COLOQUIO pide el contacto de alguien que convocó a un
grupo, la bóveda lo rechaza** con «no tiene una convocatoria activa», salvo
que por casualidad esa persona esté en una encuesta abierta de `paneles`. Y
COLOQUIO no puede arreglarlo de su lado sin romper otras reglas:

- no puede escribir en `participacion` (DoD 11, y no tiene privilegio);
- sus convocatorias viven en su propio store (Firestore), que la bóveda no ve.

COLOQUIO ya maneja el rechazo: el embudo muestra el mensaje de la bóveda, el
canal WhatsApp degrada a manual y nada se rompe. Pero sin el dato de contacto
no hay convocatoria, así que **la fase no puede salir a producción** hasta
resolver esto. El caso está cubierto por la prueba
`test_rechazo_por_convocatoria_activa_se_informa`.

## Propuesta: `boveda/0016` — convocatoria externa declarada

Que el consumidor **declare** la convocatoria en la bóveda por una función de
la superficie (no por una tabla), y que `contacto_para_convocatoria()` la
acepte como motivo. Sigue siendo un gate: sin declaración vigente, no hay
contacto; y la declaración queda auditada con sistema y vencimiento.

```sql
-- boveda/0016_convocatoria_externa.sql
create table convocatoria_externa (
  id_persona   uuid not null,
  sistema      text not null references sistema_consumidor(codigo),
  referencia   text not null,              -- id de sesión del consumidor (opaco)
  vence_en     timestamptz not null,
  declarada_en timestamptz not null default now(),
  primary key (id_persona, sistema, referencia)
);
alter table convocatoria_externa enable row level security;

-- La única escritura que COLOQUIO haría sobre la bóveda, y por función.
create function declarar_convocatoria(p_id_persona uuid, p_referencia text,
                                      p_vence_en timestamptz)
returns void language plpgsql security definer set search_path = public as $$
begin
  if p_vence_en > now() + interval '60 days' then
    raise exception 'Una convocatoria no puede declararse por más de 60 días.';
  end if;
  -- El gate de consentimiento, también acá: no se declara a quien no consintió.
  if not exists (select 1 from v_persona_convocable
                  where id_persona = p_id_persona
                    and finalidad = 'contacto_participacion') then
    raise exception 'Sin consentimiento vigente de contacto_participacion.'
      using errcode = 'insufficient_privilege';
  end if;
  insert into convocatoria_externa (id_persona, sistema, referencia, vence_en)
  values (p_id_persona, sistema_de_la_conexion(), p_referencia, p_vence_en)
  on conflict (id_persona, sistema, referencia) do update set vence_en = excluded.vence_en;
end; $$;

revoke execute on function declarar_convocatoria(uuid, text, timestamptz) from public;
grant  execute on function declarar_convocatoria(uuid, text, timestamptz) to coloquio_app;
```

Y en `contacto_para_convocatoria()`, el chequeo pasa a ser por sistema:

```sql
select exists (
  select 1 from participacion pa join encuesta e on e.id = pa.encuesta_id
   where el_sistema = 'paneles' and pa.id_persona = p_id_persona and e.estado <> 'cerrada'
  union all
  select 1 from convocatoria_externa c
   where c.sistema = el_sistema and c.id_persona = p_id_persona and c.vence_en > now()
) into tiene_convocatoria;
```

Más: la cascada de baja borra `convocatoria_externa` de la persona, la lista
blanca de `scripts/verificar_coloquio.py` suma la función, y hay que decidir
si la bóveda purga las declaraciones vencidas (sugerido: sí, a los 30 días).

## Lo que cambia en COLOQUIO si se aprueba

Una llamada a `declarar_convocatoria(id_persona, sesion_id, fecha_sesion + 2 días)`
al invitar (paso `candidato → invitado`), fuera de la transacción de Firestore.
Es un cambio chico en `coloquio/boveda.py` y `coloquio/embudo.py`; se hace
cuando la migración esté aplicada.

## Alternativa descartada

Relajar el chequeo para `sistema = 'coloquio'` (confiar en el consumidor). Es
más simple, pero deja a COLOQUIO poder barrer la agenda de a una persona por
vez, que es exactamente lo que el chequeo existe para impedir.
