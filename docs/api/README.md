# API de romeralQRAccess

Guía para quien integra la aplicación local del acceso (o cualquier otro
cliente) contra el backend de entradas online con QR. El contrato formal,
completo y siempre actualizado está en [`openapi.yaml`](./openapi.yaml).
Este documento es una introducción en español; ante cualquier duda sobre
un campo o un código de respuesta, el YAML manda.

## URL base

```
https://acceso.vallederomeral.cl
```

Todas las rutas empiezan con `/api/v1/`. Por ejemplo, la consulta de una
entrada es:

```
GET https://acceso.vallederomeral.cl/api/v1/tickets/{code}
```

## Autenticación: clave de terminal

Todas las rutas requieren el encabezado `X-Terminal-Key`, salvo el webhook
de WooCommerce (ver más abajo, que usa su propia firma).

Cada terminal del acceso tiene su propia clave, entregada por el
administrador del sistema. El backend solo guarda el hash de la clave, no
la clave misma, igual que con los códigos QR.

```
GET /api/v1/tickets/VR1K7M2Q9XW4TB8N3HD6PA5RC
X-Terminal-Key: <clave-de-la-terminal>
```

Si la clave falta o es inválida, el backend responde `401` con un cuerpo:

```json
{ "detail": "Clave de terminal ausente o inválida." }
```

## Endpoints

### `GET /api/v1/tickets/{code}`

Consulta una entrada por el código leído del QR. No cambia nada. Usarlo
cada vez que la pistola lee un código, para mostrar la ficha de la
entrada antes de canjear.

El backend nunca guarda el código en texto plano: compara el hash
SHA-256 del código recibido contra `code_hash`. Por eso el código se pasa
en la ruta tal como lo entrega la pistola, sin transformarlo.

**Ejemplo de solicitud**

```
GET /api/v1/tickets/VR1K7M2Q9XW4TB8N3HD6PA5RC
X-Terminal-Key: <clave-de-la-terminal>
```

**Ejemplo de respuesta (200)**

```json
{
  "id": "6f1a2e3a-9b9e-4a2a-9b2b-1c2d3e4f5a6b",
  "woo_order_id": 10452,
  "woo_order_number": "10452",
  "buyer_name": "María Pérez",
  "buyer_email": "maria.perez@example.com",
  "people_count": 3,
  "total_paid": 36000,
  "payment_method": "Webpay",
  "purchased_at": "2026-11-20T15:32:00-03:00",
  "season_id": 1,
  "valid_until": "2027-03-31",
  "status": "VALID",
  "redeemed_at": null,
  "redeemed_by": null,
  "invoice_status": "NOT_ISSUED",
  "invoice_folio": null,
  "source": "WEBHOOK",
  "created_at": "2026-11-20T15:32:05-03:00",
  "updated_at": "2026-11-20T15:32:05-03:00",
  "lines": [
    {
      "woo_product_id": 142,
      "product_name": "Entrada General",
      "quantity": 3,
      "unit_price": 12000,
      "line_total": 36000
    }
  ]
}
```

Si ningún código coincide, responde `404`:

```json
{ "detail": "No existe una entrada con ese código." }
```

### `GET /api/v1/tickets?order=...` o `?email=...`

Búsqueda manual para cuando el QR no se puede leer (pantalla rota, luz,
etc.). Se debe indicar al menos uno de los dos parámetros:

- `order`: número de pedido de WooCommerce (`woo_order_number`).
- `email`: correo del comprador (`buyer_email`).

**Ejemplo de solicitud**

```
GET /api/v1/tickets?order=10452
X-Terminal-Key: <clave-de-la-terminal>
```

**Ejemplo de respuesta (200)**

Un arreglo de `OnlineTicket`, con la misma forma que la respuesta de la
consulta por código. Puede venir vacío (`[]`) si no hay coincidencias.

Si no se indica ni `order` ni `email`, responde `400`.

### `POST /api/v1/tickets/{code}/redeem`

Canjea la entrada. El canje es atómico: si dos solicitudes llegan al
mismo tiempo para el mismo código, solo una tiene éxito y la otra recibe
`409`. El canje es total, para todas las personas de la entrada; no hay
canjes parciales ni reingresos.

**Cuerpo de la solicitud**

```json
{
  "terminal": "acceso-1",
  "redeemed_by": "jperez"
}
```

`terminal` y `redeemed_by` son dos campos separados y los dos son
obligatorios. `terminal` identifica el equipo del acceso y queda en el
evento de auditoría de la entrada (`ticket_event.terminal`);
`redeemed_by` identifica a la persona que canjeó y queda en la entrada
misma.

**Ejemplo de respuesta (200)**

La misma entrada, ahora con `status: "REDEEMED"`, `redeemed_at` con la
fecha y hora del canje y `redeemed_by` con el valor enviado tal cual
(`"jperez"`), sin combinarlo con `terminal`.

**Errores**

- `404`: no existe una entrada con ese código.
- `409`: la entrada ya no se puede canjear porque está `REDEEMED`,
  `CANCELLED` o `REFUNDED_AFTER_REDEMPTION`. El cuerpo trae el detalle,
  por ejemplo `{ "detail": "La entrada ya fue canjeada." }`.

### `POST /api/v1/tickets/{code}/invoice`

La aplicación local llama a este endpoint después de emitir (o intentar
emitir) la boleta en Facturacion.cl, para dejar registrado el folio o
marcar la boleta como pendiente de revisión.

**Cuerpo de la solicitud, boleta emitida**

```json
{
  "status": "ISSUED",
  "folio": "26193"
}
```

**Cuerpo de la solicitud, boleta pendiente**

```json
{
  "status": "PENDING_REVIEW",
  "folio": null
}
```

Responde `200` con la entrada actualizada, incluyendo `invoice_status` y
`invoice_folio`.

**Errores**

- `404`: no existe una entrada con ese código.
- `409`: la entrada no está en estado `REDEEMED`, así que todavía no
  corresponde informar su boleta. El cuerpo trae el detalle:
  `{ "detail": "Solo se puede informar la boleta de una entrada ya canjeada." }`.
  La boleta de una entrada online se emite al canjear, nunca antes.

### `POST /api/v1/woocommerce/webhook`

WooCommerce llama a este endpoint en cada creación o actualización de
pedido. No usa `X-Terminal-Key`: usa la firma propia de WooCommerce, en el
encabezado `X-WC-Webhook-Signature`, calculada con el secreto configurado
al crear el webhook en WooCommerce.

Si la firma falta o no coincide, responde `401` y no procesa el pedido.

No hay un evento distinto para la anulación: el backend decide qué hacer
según el campo `status` del pedido.

| `status` del pedido | Qué hace el backend |
|---|---|
| `processing`, `completed` | Crea la entrada (si no existe una para ese `id`), con una línea por producto, y envía el correo con el QR al comprador. |
| `cancelled`, `refunded` | Si la entrada estaba `VALID`, la pasa a `CANCELLED` y ya no se puede canjear. Si ya estaba `REDEEMED`, la pasa a `REFUNDED_AFTER_REDEMPTION`: hay una boleta DTE 39 real ya emitida, así que queda visible y distinguible para conciliación, sin resolverse automáticamente (Fase 3). Si ya estaba en uno de esos dos estados, no hace nada. |
| Cualquier otro (`pending`, `on-hold`, `failed`, `draft`, ...) | No es un pedido pagado ni una anulación: no hace nada. |

Con la firma válida responde siempre `200`, sea cual sea la rama:

```json
{ "received": true }
```

Reintentar el webhook para un pedido que ya tiene entrada no crea una
segunda entrada: se reconoce por `woo_order_id`, que es único. Un segundo
aviso de anulación tampoco cambia nada.

## Valores de `status`

| Valor | Significado |
|---|---|
| `VALID` | La entrada existe, está dentro de temporada y no se ha canjeado. |
| `REDEEMED` | Ya se usó en el acceso. No se puede volver a canjear. |
| `CANCELLED` | El pedido se anuló o reembolsó en WooCommerce antes del canje. |
| `REFUNDED_AFTER_REDEMPTION` | El pedido se reembolsó en WooCommerce después de que la entrada ya había sido canjeada. Queda registrada para conciliación; la persona ya ingresó. |

## Valores de `invoice_status`

| Valor | Significado |
|---|---|
| `NOT_ISSUED` | Todavía no se ha canjeado la entrada, o el canje no ha intentado emitir boleta. |
| `ISSUED` | La boleta se emitió en Facturacion.cl. `invoice_folio` trae el folio. |
| `PENDING_REVIEW` | El canje ocurrió pero la emisión de la boleta falló o quedó incierta. El supervisor debe resolverlo manualmente; la persona ya ingresó porque ya pagó. |

## Configuración en el PC del acceso

La aplicación del acceso (`desktop/`) no tiene un archivo de configuración
aparte: lee todo de la tabla `config` de su propia base SQLite
(`~/Documents/ROMERAL_Datos/romeral.sqlite3`), con la función
`romeral.config(key)`. La comparación de la clave es sensible a mayúsculas
y minúsculas, así que estas cuatro claves van siempre en minúsculas, igual
que las que ya existían (`precio`, `rut_empresa`, `impresora_80mm`).

| Clave | Para qué sirve | Si falta |
|---|---|---|
| `acceso_api_url` | URL base del backend, sin barra final. Por ejemplo `https://acceso.vallederomeral.cl`. | Toda llamada al backend falla con "Falta configurar acceso_api_url." |
| `acceso_terminal_key` | Clave de esta terminal, enviada en el encabezado `X-Terminal-Key`. La entrega el comando `create_terminal` del backend (se muestra una sola vez). | Toda llamada al backend falla con "Falta configurar acceso_terminal_key." |
| `acceso_terminal_nombre` | Nombre de la terminal que se envía como `terminal` al canjear y queda en la auditoría de la entrada. | Se usa `acceso-1`. |
| `acceso_terminal_operador` | Nombre del operador que se envía como `redeemed_by` al canjear. | Se usa el usuario del sistema operativo (`USERNAME`/`USER`), o `operador`. |

Para obtener la clave de la terminal, en el servidor:

```
python manage.py create_terminal "acceso-1"
```

Ese comando genera una clave al azar, guarda solo su hash y la imprime una
única vez. Si se pierde, se reemplaza con `--rotate` (la anterior deja de
funcionar de inmediato).

Para dejar las cuatro claves en el PC del acceso, con la aplicación
cerrada:

```
sqlite3 "%USERPROFILE%\Documents\ROMERAL_Datos\romeral.sqlite3"
```

```sql
INSERT OR REPLACE INTO config VALUES ('acceso_api_url', 'https://acceso.vallederomeral.cl');
INSERT OR REPLACE INTO config VALUES ('acceso_terminal_key', '<clave-impresa-por-create_terminal>');
INSERT OR REPLACE INTO config VALUES ('acceso_terminal_nombre', 'acceso-1');
INSERT OR REPLACE INTO config VALUES ('acceso_terminal_operador', 'jperez');
```

La clave de la terminal no se escribe en ningún registro ni se muestra en
la interfaz; vive solo en esa fila de `config`.

## Documentación interactiva

Una vez desplegado el backend, Django Ninja publica la documentación
interactiva (generada desde el mismo contrato OpenAPI) en:

```
https://acceso.vallederomeral.cl/api/docs
```

Ahí se puede ver cada endpoint, probar solicitudes con una clave de
terminal real y revisar los esquemas completos.
