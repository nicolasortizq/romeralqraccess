# Diseño: Fase 1 — Entradas online con QR

Fecha: 23-11-2026
Base: `docs/PROYECTO.md` secciones 3, 4, 5, 11 y 12 (diseño aprobado).
Este documento no redefine nada marcado DECIDIDO en `docs/PROYECTO.md`; lo
completa con las respuestas de la sesión de brainstorming y queda listo
para pasar a `writing-plans`.

## Intención y por qué

El parque abrió la temporada (20-11-2026) con una aplicación de venta
presencial que emite boletas reales, pero el módulo de ventas online
(`ventas_online.py`) solo guarda el hash del QR sin validar nada y tiene
el botón de emisión bloqueado. Cada compra online hoy no tiene forma de
canjearse ni facturarse en el acceso. La Fase 1 cierra ese hueco: un
backend Django que recibe pedidos pagados de WooCommerce, emite un QR por
correo, y una pantalla de canje en la aplicación local que consulta ese
backend, marca el canje de forma atómica y dispara la emisión de boleta
ya existente en `romeral.py`.

Es urgente porque el parque ya está vendiendo entradas online sin que
nadie pueda canjearlas correctamente en el acceso.

## Alcance de este diseño

Dentro: webhook de WooCommerce, modelo de datos de la entrada online,
generación y envío del QR, API de consulta/búsqueda/canje/boleta,
importación de pedidos anteriores, despliegue en el VPS, y la pantalla de
canje + línea "Online" en el cierre de caja dentro de `desktop/`.

Fuera (otras fases, no se diseña aquí): profesionalización completa de la
app local (Fase 2), plataforma de caja/admin en la nube (Fase 3), venta
online de entradas gratuitas, y cambios al módulo DTE existente en
`romeral.py` más allá de invocarlo.

## Metas

- Toda compra online pagada en WooCommerce termina en una entrada
  canjeable una sola vez en el acceso, con su boleta DTE 39.
- Ningún canje duplicado, aunque lleguen dos solicitudes a la vez.
- El cajero nunca necesita mirar WooCommerce ni Facturacion.cl
  directamente: todo pasa por la pantalla de canje.
- La base de datos no permite reconstruir un QR válido a partir de una
  fuga (solo se guarda el hash).

## No-metas

- No se vende ni se gestiona online Cabañas, Camping, Piscina Temperada
  ni entradas gratuitas.
- No hay modo sin conexión; una caída de internet se resuelve con el
  procedimiento manual ya acordado (sección 10 de PROYECTO.md).
- No se reestructura `romeral.py` ni `ventas_online.py` más allá de
  completar el panel y reutilizar `emitir_automaticamente`.
- No se emite ninguna boleta real desde pruebas o scripts sin
  autorización explícita de Nico.

## Anti-metas

- Que el cajero pueda canjear dos veces la misma entrada por una
  condición de carrera.
- Que un correo con QR caiga en spam por falta de SPF/DKIM.
- Que una entrada quede canjeada sin boleta y sin que nadie se entere
  (debe quedar visible en una lista de pendientes para el supervisor).
- Que el módulo nuevo rompa el flujo de venta presencial existente.

## Restricciones

- Una semana de plazo para la Fase 1 completa (ver sección 12 de
  PROYECTO.md).
- Stack ya decidido: Django 6.1, Django Ninja, PostgreSQL, VPS Hostgator
  Snappy 2000 sin cPanel, Nginx, Gunicorn, Let's Encrypt.
- El VPS **todavía no está contratado** (en trámite por Nico). El plan de
  despliegue debe poder ejecutarse en cuanto esté disponible, sin
  bloquear el resto de las tareas (contrato, mocks, backend local,
  pruebas) que no dependen de él.
- El plan **no incluirá respaldos del proveedor**: Hostgator no los
  ofrece para este plan a un costo razonable. Se necesita un respaldo
  diario externo.
- La pistola lectora 2D **todavía no está comprada**. El desarrollo y las
  pruebas de la pantalla de canje deben funcionar con ingreso manual del
  código (el mismo campo de texto sirve para ambos casos, igual que hoy
  en `ventas_online.py`).
- Las claves de la API REST de WooCommerce y el ID del producto "Entrada
  General" **no están disponibles todavía**. Bloquean solo la prueba con
  pedidos reales y la importación real de pedidos anteriores, no el
  desarrollo del webhook ni del modelo de datos.
- Se asume que Facturacion.cl tiene ambiente de pruebas (sandbox) para
  DTE de prueba. Pendiente de confirmar con Rodrigo; si no existiera, las
  pruebas de emisión se simulan (mock) y la emisión real queda solo para
  el primer pedido real, con autorización explícita.
- La pantalla de canje se usa táctil, igual que el resto de la app
  (pantalla 1024x768). Mantiene botones grandes y el mismo lenguaje
  visual.

## Enfoque

Hay una sola forma razonable de construir esto: seguir exactamente el
stack y el flujo ya aprobados en `docs/PROYECTO.md` secciones 3 y 5. No
se evaluaron alternativas de lenguaje, framework o arquitectura porque ya
están decididas; la única decisión de diseño abierta era de datos y
contrato de API, resuelta abajo.

## Decisiones tomadas en esta sesión

- **Temporada:** `season.starts_on = 2026-11-20`, `season.ends_on
  = 2027-02-28` (la temporada cruza de año).
- **Respaldo externo:** volcado diario de PostgreSQL subido con `rclone`
  a una carpeta de Google Drive (cuenta de servicio dedicada). Propuesta
  de Nico durante el brainstorming; puede cambiar de destino sin tocar
  el resto del diseño.
- **Correo remitente:** `entradas@vallederomeral.cl`. Nico tiene acceso
  completo al hosting y al DNS de Hostgator para configurar SPF y DKIM.
- **Subdominio:** `acceso.vallederomeral.cl`, confirmado.
- **Separación de precio:** el precio de venta presencial vivirá como
  parámetro de configuración en el backend (para control futuro desde
  administración); las entradas online siempre usan el monto
  efectivamente pagado en WooCommerce (`total_paid`), nunca ese
  parámetro. Esto no cambia el modelo de `online_ticket`.
- **Momento de emisión de boleta:** decisión de negocio, no técnica. La
  boleta de una entrada online se emite exclusivamente al canjear, nunca
  al pagar. No queda detrás de un parámetro configurable. Ver riesgo
  abajo.
- **Entradas gratuitas:** fuera de alcance de la Fase 1 (no se venden
  online por ahora).

## Riesgo abierto a documentar (no bloqueante)

**Emisión de boleta al canjear, no al pagar.** Es una decisión de
negocio ya tomada y no configurable. El riesgo es que una entrada online
pagada y nunca canjeada quede sin boleta. Falta validar con el contador
de Rodrigo si eso es aceptable tributariamente. Esta validación corre en
paralelo y no bloquea la programación; si el contador la objeta más
adelante, el cambio de este comportamiento es un problema a resolver en
ese momento, no ahora.

## Modelo de datos, contenido del QR y rutas de API

Se adopta tal como está propuesto en `docs/PROYECTO.md` 5.3, 5.4 y 5.5,
sin cambios: entidades `season`, `online_ticket`, `online_ticket_line`,
`ticket_event`, `terminal`; QR con prefijo `VR1`, solo mayúsculas y
dígitos, se guarda solo el hash SHA-256; rutas
`GET /api/v1/tickets/{code}`, `GET /api/v1/tickets?order=...|email=...`,
`POST /api/v1/tickets/{code}/redeem`, `POST /api/v1/tickets/{code}/invoice`,
`POST /api/v1/woocommerce/webhook`. El contrato formal, con tipos y
respuestas exactas, se escribe en `docs/api/openapi.yaml` como primera
tarea del plan de ejecución.

## Integración con la aplicación local (hallazgo de la revisión de código)

`mock/ROMERAL_v2_10_19/romeral.py` ya tiene el flujo de boleta que debe
reutilizarse, sin modificarlo:

- `registrar()` (línea ~664) inserta una fila en `ventas` y llama a
  `self.emitir_automaticamente(venta_id, total)`.
- `emitir_automaticamente()` (línea ~725) hace el único envío SOAP,
  reintenta la consulta del PDF oficial, copia el timbre e imprime, y dejó
  `folio_dte`/`estado_boleta` en `ventas` y eventos en `eventos_dte`.

La nueva pantalla de canje (reemplazo de `panel_qr_online`, hoy en
`romeral.py` línea ~986, apoyada en un `ventas_online.py` completado)
debe, tras un canje exitoso confirmado por el backend:

1. Insertar una fila en `ventas` con medio `Webpay` y una marca de origen
   online (campo nuevo o reutilización de `tipo`/`referencia_venta`, a
   definir en el plan).
2. Llamar a `self.emitir_automaticamente(venta_id, total)` igual que una
   venta presencial, sin duplicar lógica de boleta.
3. Cuando la emisión informe folio (o falle), notificar al backend vía
   `POST /api/v1/tickets/{code}/invoice`.

Esto evita tocar el módulo DTE y limita el trabajo nuevo en `desktop/` a:
completar `ventas_online.py` (cliente HTTP al backend, validación de
estado), reemplazar `panel_qr_online` por la pantalla de canje real, y
agregar la línea "Online" al cierre de caja.

## Revisión de constructor (resuelta)

Un subagente revisó este documento como si fuera a planificarlo sin poder
preguntar. Verificó las líneas citadas arriba (coinciden) y encontró tres
huecos, resueltos así:

- **Validaciones previas de `registrar()` (producción habilitada, sin
  envío SOAP pendiente de conciliar, jornada no cerrada, `emision_en_curso`):**
  el canje online las replica todas antes de llamar a
  `emitir_automaticamente()`. Existen para evitar justo los problemas de
  confiabilidad de boleta que este proyecto quiere prevenir; saltárselas
  reabriría ese hueco. (Decisión del constructor.)
- **Lock `emision_en_curso` compartido entre venta presencial y canje
  online:** se comparte. Hay un solo carril y la misma persona cobra y
  deja entrar (regla de negocio ya decidida en PROYECTO.md 4.8), así que
  de todas formas no podría hacer ambas cosas a la vez. (Decisión del
  constructor.)
- **Reembolso en WooCommerce de una entrada ya canjeada y con boleta DTE 39
  ya emitida:** no pasa a `CANCELLED`. Queda en un estado aparte,
  `REFUNDED_AFTER_REDEMPTION` ("reembolsada tras canje"), distinto de una
  anulación antes del canje. Es un caso con una boleta tributaria real ya
  emitida y asociada; cómo resolverlo (nota de crédito, reversa contable,
  etc.) se deja para la Fase 3. Por ahora el sistema solo necesita dejarlo
  visible y distinguible, no resolverlo automáticamente. (Decisión de
  Nico.)

Esto agrega `REFUNDED_AFTER_REDEMPTION` al conjunto de valores de
`online_ticket.status` definido en PROYECTO.md 5.4 (`VALID`, `REDEEMED`,
`CANCELLED`, y ahora también `REFUNDED_AFTER_REDEMPTION`).

## Qué queda a cargo de quien construya (el plan de `writing-plans`)

- Diseño exacto de columnas/tipos en el OpenAPI y en los modelos Django
  (los campos ya están listados arriba a nivel conceptual).
- Mecanismo exacto de atomicidad del canje (`select_for_update` vs.
  constraint de base de datos vs. transacción con estado).
- Formato exacto del correo (HTML, construido primero como maqueta en
  `mock/frames/`).
- Cómo exactamente se marca el origen "online" en la tabla `ventas` sin
  romper el cierre de caja existente.
- Estructura de pruebas (pytest) para webhook, canje atómico y
  vigencia de temporada.
- Detalle de scripts de despliegue en `deploy/` (Nginx, Gunicorn,
  systemd, cron de conciliación, cron de respaldo con rclone).
