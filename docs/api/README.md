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

**Ejemplo de respuesta (200)**

La misma entrada, ahora con `status: "REDEEMED"`, `redeemed_at` con la
fecha y hora del canje y `redeemed_by` como `"acceso-1:jperez"`.

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

### `POST /api/v1/woocommerce/webhook`

WooCommerce llama a este endpoint cuando un pedido pasa a estado
"Procesando" o "Completado". No usa `X-Terminal-Key`: usa la firma propia
de WooCommerce, en el encabezado `X-WC-Webhook-Signature`, calculada con
el secreto configurado al crear el webhook en WooCommerce.

Si la firma falta o no coincide, responde `401` y no procesa el pedido.

Si la firma es válida, el backend crea la entrada (si no existe una para
ese `id` de pedido), envía el correo con el QR al comprador y responde:

```json
{ "received": true }
```

Reintentar el webhook para un pedido que ya tiene entrada no crea una
segunda entrada: se reconoce por `woo_order_id`, que es único.

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

## Documentación interactiva

Una vez desplegado el backend, Django Ninja publica la documentación
interactiva (generada desde el mismo contrato OpenAPI) en:

```
https://acceso.vallederomeral.cl/api/docs
```

Ahí se puede ver cada endpoint, probar solicitudes con una clave de
terminal real y revisar los esquemas completos.
