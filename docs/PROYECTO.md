# romeralQRAccess

Documento maestro del proyecto. Reúne el contexto, las decisiones tomadas, el alcance por fases, el diseño propuesto y las preguntas abiertas. Es la referencia para trabajar desde este chat, desde un servidor o desde Claude Code en una terminal.

Versión: 0.2 (23-11-2026)
Responsable: Nico (agencia)
Cliente: Rodrigo, Valle del Romeral SpA (RUT 78.180.502-5)

Convenciones de este documento:

- **[DECIDIDO]**: acordado con Nico. No se cambia sin volver a conversarlo.
- **[PROPUESTA]**: recomendación técnica pendiente de aprobación.
- **[PENDIENTE]**: falta información para decidir.

---

## 1. Contexto

### 1.1 Quiénes somos

Agencia de marketing chilena dirigida por Nico. Nico tiene formación en finanzas y datos, y programa en SQL, Python, C, R, HTML, CSS y algo de JavaScript. Usa GitHub.

### 1.2 Cliente

Rodrigo es dueño de Framondi, cliente de la agencia en campañas de Google Ads y Meta Ads. Su empresa familiar, Valle del Romeral (https://vallederomeral.cl), es un parque acuático que además ofrece cabañas, camping y piscina temperada. El sitio web está en WordPress y la venta online se hace con WooCommerce, con Webpay Plus como medio de pago. Todo está alojado en un hosting compartido de Hostgator.

### 1.3 Problema

El computador que corría el software de venta de entradas se quemó. Rodrigo armó con ChatGPT una aplicación local en Python que registra las ventas en el acceso y emite boletas electrónicas a través de Facturacion.cl. La versión en uso es la v2.10.19 (copia en `mock/ROMERAL_v2_10_19/`). La v2.9.0 se conserva en `mock/ROMERAL_v2_9_0/` solo como referencia histórica.

En días de alta demanda entran más de 2.000 personas. El parque abrió la temporada el 21-11-2026 y está operando con esa aplicación.

### 1.4 Qué hace hoy la aplicación de Rodrigo (v2.10.19)

- Interfaz de escritorio en Tkinter, adaptada a la pantalla táctil Windows de 1024x768, y base SQLite local en `Documentos\ROMERAL_Datos`.
- Dependencias: requests, zeep, keyring, PyMuPDF, Pillow, numpy y reportlab. La impresión en Windows usa SumatraPDF.
- Modalidades: Entrada General y Piscina Temperada a precio fijo, y Cabañas y Camping con valor por persona ingresado a mano.
- Medios de pago: Efectivo, Webpay y Tarjeta.
- Cierre de caja diario con clave de supervisor. Hay un solo cierre por fecha y se guarda una copia inmutable de las operaciones. No permite vender si quedan jornadas anteriores sin cerrar.
- Auditoría de cambios de precio.
- Emisión real y automática de boleta electrónica (DTE 39), activa desde la v2.10.14. La primera boleta real fue el folio 26193, el 21-11-2026. En cada venta:
  1. Guarda la venta.
  2. Hace un único envío SOAP (`Procesar`, archivo TXT) a Facturacion.cl.
  3. Consulta el PDF oficial hasta 10 veces, con esperas crecientes.
  4. Copia el timbre PDF417 del PDF oficial a un ticket de 80 mm propio.
  5. Lo imprime con SumatraPDF.
- Protección contra duplicados: si un envío queda incierto, bloquea las ventas nuevas hasta conciliarlo en el portal.
- Optimizaciones ya hechas por Rodrigo: caché del WSDL, caché de la lista de impresoras, esperas más cortas y reutilización de la sesión HTTPS.
- Medición de tiempos por etapa. Los registros quedan en el PC del acceso, en `romeral_diagnostico_etapas.jsonl` y `romeral_tiempos_impresion.jsonl`.
- Un módulo QR preliminar (`ventas_online.py`, sin cambios desde la v2.9.0) que solo guarda la huella SHA-256 del código escaneado. No valida pago, fecha ni cantidad, y deja el botón de emitir boleta deshabilitado. Ese es justamente el vacío que cubre la Fase 1.

La carpeta del paquete incluye además más de 40 archivos LEER y scripts de prueba de una sola vez, acumulados versión tras versión.

### 1.5 Infraestructura actual

- Sitio WordPress + WooCommerce en hosting compartido de Hostgator.
- **No existía un VPS.** Rodrigo contrata el plan Hostgator Snappy 2000 - NVMe 4 para este proyecto (ver sección 3).
- El computador del acceso usa Windows. Rodrigo también ha probado la aplicación en Mac.
- La conexión a internet en el acceso es Starlink, y se considera suficientemente estable.

---

## 2. Objetivo y fases

Rodrigo no puede rehacer todo ahora: la temporada está en curso. Por eso el proyecto se divide en tres partes, cada una funcional por sí misma. **[DECIDIDO]**

| Fase | Nombre | Cuándo | Resultado |
|---|---|---|---|
| 1 | Entradas online con QR | Ahora, urgente | Cada compra online genera una entrada con QR guardada en una base de datos en la nube. La aplicación local la escanea, muestra quién compró, para cuántas personas, el detalle de precios y el total pagado, y la marca como canjeada. |
| 2 | Profesionalizar la aplicación local | Durante la temporada, en paralelo y por entregas pequeñas | La aplicación de Rodrigo con estructura de producción: carpetas ordenadas, pruebas, registros de errores, documentación, instalador `.exe` para Windows (también ejecutable en Mac) y menos tiempo entre presionar el botón y tener la boleta. |
| 3 | Plataforma en la nube | Después de la temporada | Reemplazo de la aplicación local por una aplicación web de producción, rápida, que soporte el flujo de un día peak y que incluya estadísticas. |

Todo lo conversado sobre la arquitectura en la nube sigue vigente. Se aplica en la Fase 3, y la Fase 1 sienta sus bases.

---

## 3. Decisiones tomadas

| Tema | Decisión | Estado |
|---|---|---|
| Fuente de verdad de las entradas | Nuestro backend, no WooCommerce. WooCommerce solo vende y cobra. | DECIDIDO |
| Lenguaje y framework del backend | Python + Django (empezar en 6.1 y pasar a 6.2 LTS cuando salga, abril 2027) | DECIDIDO |
| Base de datos en la nube | PostgreSQL | DECIDIDO |
| Interfaz de caja (Fase 3) | Plantillas Django + Bootstrap 5 (+ HTMX para actualizaciones parciales) | DECIDIDO |
| Interfaz de administración y estadísticas (Fase 3) | React | DECIDIDO |
| Consistencia visual | Un solo tema Bootstrap 5 compartido. En React se usa React-Bootstrap. | PROPUESTA |
| API para React | Django Ninja | PROPUESTA |
| React en TypeScript o JavaScript | TypeScript recomendado | PENDIENTE |
| Hosting | VPS Hostgator Snappy 2000 - NVMe 4 (2 vCPU, 4 GB RAM, 100 GB NVMe), sin cPanel, AlmaLinux 9, pagado por Rodrigo. Se parte por el plan menor porque Hostgator permite subir de plan pero no bajar. | DECIDIDO |
| Software del servidor | Nginx, Gunicorn, PostgreSQL y certificado Let's Encrypt | PROPUESTA |
| Mover el WordPress al VPS | No por ahora. Se mantiene separado para que una falla en un sistema no tumbe al otro. | PROPUESTA |
| Respaldos | La documentación de Hostgator no menciona respaldos para los planes NVMe: confirmar al contratar si vienen incluidos o son un adicional. En cualquier caso, un volcado diario de la base de datos copiado fuera del servidor. | PROPUESTA |
| Subdominio | Por ejemplo `acceso.vallederomeral.cl` | PROPUESTA |
| Facturación | Facturacion.cl es la única fuente de verdad tributaria. Toda boleta (efectivo, tarjeta, online) la emite Facturacion.cl. Se delega en ellos todo lo posible: folios, CAF, PDF e impresión. | DECIDIDO |
| Tipo de documento | Solo boletas (DTE 39) | DECIDIDO |
| Boleta de una entrada online | Se emite al canjear la entrada en el acceso, no al comprar | DECIDIDO (validar con el contador de Rodrigo; ver riesgos) |
| Terminales de pago (Transbank/Getnet) | Sin integración. El cajero solo registra el medio de pago. | DECIDIDO |
| Lector | Pistola lectora USB **2D** que lea pantallas de celular, en modo teclado | DECIDIDO |
| Modo sin conexión | No en la primera versión. Se reemplaza por un procedimiento manual escrito para cortes de internet. | DECIDIDO |
| Envío del QR | Por correo desde nuestro sistema | DECIDIDO |
| QR en la página de "gracias" de WooCommerce | Solo si resulta simple. Si no, queda para más adelante. | DECIDIDO |
| Datos históricos de la aplicación de Rodrigo | La Fase 2 conserva y migra la base SQLite del PC del acceso, que tiene ventas y cierres reales. La plataforma de la Fase 3 parte de cero. | DECIDIDO |
| Aplicación local | Nico toma el control del código. La v2.10.19 queda congelada como versión base y Rodrigo no instala versiones propias desde ahora. | DECIDIDO |
| Fase 1 | Aprobada según el diseño de la sección 5 | DECIDIDO |
| Documentación de la API | Contrato OpenAPI en `docs/api/openapi.yaml`, escrito antes que el código, y una guía en español en `docs/api/README.md`. Django Ninja publica además la documentación interactiva en `/api/docs`. | DECIDIDO |
| Herramientas de desarrollo | Claude Code con el conjunto de skills superpowers: diseño, plan detallado, ejecución por tareas, pruebas primero y revisión de código | DECIDIDO |
| Plazo | Una semana para la Fase 1 completa y la base de la Fase 2 (ver sección 12) | DECIDIDO |
| Idioma de la interfaz | Solo español | DECIDIDO |
| Idioma del código | Inglés | DECIDIDO |
| Idioma de la documentación | Español | DECIDIDO |
| Estilo de código y documentación | Escrito como lo haría una persona: claro, sin muletillas, sin emojis ni adornos | DECIDIDO |
| Roles | Cajero, supervisor y administrador | DECIDIDO |
| Inicio de sesión | Usuario y contraseña | DECIDIDO |
| Propiedad del código | De Rodrigo. Repositorio en el GitHub de Nico. | DECIDIDO |
| Metodología | Ágil por sprints. Maqueta HTML antes de construir cada pantalla. | DECIDIDO |

---

## 4. Reglas de negocio

1. **Entrada general.** Es el único producto que entra al sistema por ahora y da acceso al parque acuático. Cabañas, camping y piscina temperada se gestionan con formularios y agenda, y quedan para el futuro.
2. **Precio.** $12.000 CLP la entrada general. Puede cambiar, así que es un parámetro.
   - **[PROPUESTA]** El precio del acceso vive como configuración en nuestro sistema. Las ventas online usan lo que el cliente pagó en WooCommerce. Así, un descuento en la web no cambia el precio en el acceso.
3. **Vigencia.** Una entrada online deja de ser para una fecha específica y sirve para cualquier día de la temporada en que se compró. La fecha de término de la temporada es un parámetro configurable, no una fecha fija en el código.
4. **Canje.** Una entrada se canjea una sola vez, completa, para todas las personas que incluye. No hay canjes parciales ni reingresos; el control dentro del parque se hace con pulseras.
5. **Entradas gratuitas y con descuento.** Existen, y por ahora solo en el acceso.
   - Los niños con entrada gratuita se cuentan como ingresos y no se cobran. **[PENDIENTE]** Confirmar que no llevan boleta y si se imprime algo.
   - Venderlas online es una mejora futura.
6. **Boleta de una entrada online.** Se emite al momento del canje, por el total pagado, con medio de pago Webpay.
7. **Cierre de caja.** Los canjes online aparecen en una línea propia del cierre: suman personas y boletas, pero no suman al efectivo esperado.
8. **Un solo carril de acceso.** La misma persona cobra y deja entrar.

---

## 5. Fase 1: entradas online con QR

### 5.1 Flujo

1. El cliente compra en WooCommerce y paga con Webpay Plus.
2. Cuando el pedido queda pagado (estado "Procesando" o "Completado"), WooCommerce avisa a nuestro backend con un webhook firmado.
3. El backend verifica la firma, lee el pedido y crea la entrada, con un código único.
4. El backend envía un correo al comprador con el QR, el número de pedido, la cantidad de personas y la vigencia.
5. Cada 10 minutos, una tarea programada consulta a WooCommerce por pedidos pagados sin entrada, por si algún webhook se perdió.
6. En el acceso, el cajero escanea el QR con la pistola. La aplicación local consulta al backend y muestra:
   - nombre del comprador
   - número de pedido
   - cantidad de personas
   - detalle de productos con precio unitario
   - total pagado
   - estado: válida, ya canjeada (con fecha y hora), anulada o fuera de temporada
7. El cajero presiona "Canjear". El backend marca la entrada como canjeada de forma atómica: si dos solicitudes llegan a la vez, solo una gana.
8. La aplicación local emite la boleta con Facturacion.cl e imprime, igual que una venta presencial.
9. La aplicación local informa el folio al backend.
10. Si la boleta falla, la entrada queda "canjeada con boleta pendiente" y aparece en una lista para que el supervisor la resuelva. La persona igual entra, porque ya pagó.

Si no se puede leer el QR, el cajero puede buscar la entrada por número de pedido o por correo.

Si un pedido se anula o se reembolsa en WooCommerce, la entrada pasa a "anulada".

### 5.2 Dónde vive **[DECIDIDO]**

Un servicio Django pequeño en el VPS nuevo, con PostgreSQL. Es la semilla de la plataforma de la Fase 3: el mismo proyecto, la misma base de datos y el mismo servidor. En la Fase 3 se le agregan la caja, las estadísticas y el resto.

Alternativa descartada: un plugin de WordPress en PHP sobre el hosting compartido. Es más rápido de instalar, pero contradice la decisión de que la fuente de verdad sea nuestro backend, obliga a escribir PHP y no se reutiliza en la Fase 3.

### 5.3 Contenido del QR **[PROPUESTA]**

- El QR contiene solo un código aleatorio, sin datos personales ni montos. Por ejemplo: `VR1K7M2Q9XW4TB8N3HD6PA5RC`.
- El prefijo `VR1` permite que la aplicación local reconozca una entrada online y la distinga de cualquier otra cosa que se escanee.
- Solo usa mayúsculas y números. Las pistolas en modo teclado pueden cambiar símbolos como `-` o `:` según la distribución del teclado de Windows. Con letras y números se evita ese problema.
- La base de datos guarda la huella SHA-256 del código, no el código, como ya hacía Rodrigo. Si alguien obtuviera una copia de la base, no podría fabricar QR válidos.
- Si hay que reenviar una entrada, se genera un código nuevo y el anterior queda invalidado.

### 5.4 Modelo de datos **[PROPUESTA]**

`season` (temporada)
- `id`, `name`, `starts_on`, `ends_on`, `is_active`

`online_ticket` (entrada online)
- `id` (UUID)
- `code_hash` (único)
- `woo_order_id` (único), `woo_order_number`
- `buyer_name`, `buyer_email`
- `people_count`
- `total_paid` (CLP, entero), `payment_method`
- `purchased_at`
- `season_id`, `valid_until`
- `status`: `VALID`, `REDEEMED`, `CANCELLED`
- `redeemed_at`, `redeemed_by` (terminal y usuario)
- `invoice_status`: `NOT_ISSUED`, `ISSUED`, `PENDING_REVIEW`
- `invoice_folio`
- `source`: `WEBHOOK`, `RECONCILIATION`, `IMPORT`
- `created_at`, `updated_at`

`online_ticket_line` (detalle de precios)
- `ticket_id`, `woo_product_id`, `product_name`, `quantity`, `unit_price`, `line_total`

`ticket_event` (bitácora inmutable, base de las estadísticas)
- `ticket_id`, `event_type`, `occurred_at`, `terminal`, `detail` (JSON)
- Tipos de evento: creada, correo enviado, consultada, canjeada, canje rechazado, boleta emitida, boleta pendiente, anulada, reenviada.

`terminal`
- `name`, `api_key_hash`, `is_active`

Datos personales: se guarda solo nombre y correo del comprador, lo mínimo para identificar la entrada. Esto deja el sistema preparado para la Ley 21.719, cuya entrada en vigencia estaba fijada para el 01-12-2026 y está en discusión una postergación.

### 5.5 API para la aplicación local **[PROPUESTA]**

Todo va por HTTPS, con una clave por terminal en un encabezado. El contrato formal se escribe primero en `docs/api/openapi.yaml`, para que el backend y la integración de la aplicación local se construyan en paralelo sobre la misma definición.

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/v1/tickets/{code}` | Consulta. No cambia nada. |
| GET | `/api/v1/tickets?order=...` o `?email=...` | Búsqueda manual cuando el QR no se puede leer |
| POST | `/api/v1/tickets/{code}/redeem` | Canje atómico. Responde 409 si ya estaba canjeada. |
| POST | `/api/v1/tickets/{code}/invoice` | Informa folio o falla de boleta |
| POST | `/api/v1/woocommerce/webhook` | Recibe pedidos. Valida la firma `X-WC-Webhook-Signature`. |

### 5.6 Correo

- Se envía desde una casilla del dominio del parque. **[PENDIENTE]** Definir cuál.
- Hay que configurar los registros SPF y DKIM en el DNS para que el correo no caiga en spam.
- Contenido: QR, número de pedido, personas, vigencia y una instrucción simple ("muestra este código en el acceso").

### 5.7 Importación de pedidos anteriores

Es un comando que lee de WooCommerce los pedidos pagados y no usados de la temporada actual y les crea su entrada. Así se pueden validar por número de pedido, y opcionalmente se les envía el QR por correo.

### 5.8 Cambios en la aplicación local

- Se completa el módulo "Ventas Online QR" que Rodrigo ya dejó preparado.
- Pantalla de canje: el campo de escaneo queda siempre activo, aparece una ficha con los datos de la entrada y hay un botón "Canjear y emitir boleta".
- Mensajes de error claros: entrada ya canjeada, anulada, fuera de temporada o sin conexión.
- Nueva línea "Online" en el cierre de caja.

---

## 6. Fase 2: profesionalizar la aplicación local

Objetivo: que la aplicación de Rodrigo sea mantenible, se instale con un `.exe` en Windows (y siga corriendo en Mac) y emita más rápido. Siempre se mantiene la versión anterior como respaldo, y cada cambio se entrega por separado y probado, porque la aplicación está en uso.

### 6.1 Estándares

No existe una norma ISO que se aplique directamente a una aplicación de este tamaño. ISO 27001, por ejemplo, certifica la gestión de seguridad de una organización completa, no un programa. **[PROPUESTA]** En su lugar se aplican prácticas concretas y verificables:

- **Estructura de paquete Python:** `pyproject.toml` y carpeta `src/`, con módulos separados para interfaz, base de datos, boletas (DTE), impresión, entradas online y configuración.
- **Estilo:** PEP 8 revisado automáticamente con `ruff`.
- **Pruebas:** con `pytest`, partiendo por lo crítico: cálculo de totales, cierre de caja, armado del TXT de la boleta y lectura de respuestas de Facturacion.cl.
- **Configuración y secretos:** la configuración sale del código, y las credenciales se guardan en el llavero del sistema (ya lo hace con `keyring`).
- **Registro de errores:** archivos de log rotativos.
- **Versionamiento:** numeración semántica, un `CHANGELOG.md` y un solo `README` en español, que reemplaza los más de 30 archivos LEER_PRIMERO.
- **Base de datos:** migraciones de SQLite numeradas y respaldo automático diario.
- **Instalador:** el `.exe` se genera con PyInstaller en GitHub Actions sobre Windows, así no hace falta un PC Windows para compilarlo.
  - Windows mostrará una advertencia al abrir un `.exe` sin firma digital. Firmarlo tiene costo y queda como opción.

### 6.2 Velocidad

Meta: menos que los ~10 segundos actuales entre presionar y tener la boleta impresa. **[PENDIENTE]** Fijar una meta concreta, por ejemplo 5 segundos.

Método:
1. Medir cada paso con la herramienta de tiempos que ya existe: armado del TXT, llamada a Facturacion.cl, su respuesta, descarga del PDF e impresión.
2. Optimizar solo lo que se midió.

Rodrigo ya aplicó las optimizaciones simples: caché del WSDL, caché de impresoras, esperas más cortas y reutilización de la sesión HTTPS. El primer paso es analizar los registros de tiempos del PC del acceso (`romeral_diagnostico_etapas.jsonl` y `romeral_tiempos_impresion.jsonl`).

Hipótesis principal: la mayor parte del tiempo se va en esperar a que Facturacion.cl genere el PDF oficial, ya que la aplicación lo consulta hasta 10 veces para copiar el timbre.

- Si la respuesta de `Procesar` (u otra consulta del proveedor) entrega los datos del timbre (TED), el PDF417 se podría dibujar localmente e imprimir sin esperar el PDF. Así imprime la mayoría de los sistemas de punto de venta.
- Hay que comprobarlo con las respuestas SOAP guardadas y confirmarlo con Facturacion.cl antes de cambiar nada.
- Otra alternativa es el módulo de ticket de 80 mm de Facturacion.cl (BETICKET).

---

## 7. Fase 3: plataforma en la nube (después de la temporada)

Todo lo acordado en las secciones 3 y 4 aplica aquí:

- Django + PostgreSQL en el mismo VPS y el mismo proyecto de la Fase 1.
- Pantalla de caja en Bootstrap 5 + HTMX: liviana, rápida y pensada para pantalla táctil.
- Impresión silenciosa con Chrome en modo `--kiosk-printing` hacia la impresora de 80 mm predeterminada.
- Administración y estadísticas en React (React-Bootstrap), conectadas al backend por una API.
- Estadísticas construidas sobre la bitácora de eventos: ingresos por día y hora, mezcla online y presencial, medios de pago, entradas vendidas y no canjeadas.
- Usuarios con roles de cajero, supervisor y administrador.
- Cierre de caja con las mismas reglas que la aplicación de Rodrigo.
- Respaldos diarios y un manual para reconstruir el servidor desde cero.

---

## 8. Forma de trabajo

- **Sprints cortos**, de una semana durante la temporada.
- **Flujo con superpowers en Claude Code:**
  1. Brainstorming sobre este documento, que actúa como diseño aprobado.
  2. Plan detallado con `writing-plans`, guardado en `docs/plans/`.
  3. Ejecución tarea por tarea en un worktree de Git, con pruebas primero.
  4. Revisión de código entre tareas.
  5. Cierre de rama.
- **El contexto permanente para Claude Code** está en `CLAUDE.md`, en la raíz del repositorio.
- **Maqueta primero:** cada pantalla o correo nuevo se dibuja como HTML estático en `mock/frames/`, se revisa con Nico (y con Rodrigo si corresponde) y solo después se programa.
- **Desarrollo:** cada cambio va en una rama de Git, y Nico revisa antes de unir a `main`.
- **Entornos:** se prueba primero en un entorno de pruebas (base de datos y correo de prueba, sin boletas reales) y después en producción.
- **Boletas reales:** nunca se emiten boletas reales para probar sin una autorización explícita.
- **Documentación** en `docs/`, en español.

---

## 9. Estructura del repositorio

```
romeralQRAccess/
  CLAUDE.md             contexto permanente para Claude Code
  docs/                 documentación del proyecto (este archivo y decisiones)
    api/                contrato OpenAPI y guía de la API
    plans/              planes detallados generados con superpowers
  mock/
    ROMERAL_v2_10_19/   versión de Rodrigo en uso, base de la Fase 2 (no se modifica)
    ROMERAL_v2_9_0/     versión anterior, solo referencia histórica
    frames/             maquetas HTML para iterar antes de programar
  backend/              proyecto Django (Fase 1 y Fase 3)
  admin/                React de administración y estadísticas (Fase 3)
  desktop/              aplicación local profesionalizada (Fase 2)
  deploy/               scripts de instalación del VPS y respaldos
```

La carpeta `desktop/` parte como copia de `mock/ROMERAL_v2_10_19/`. La copia en `mock/` no se toca, para tener siempre la versión original como respaldo.

---

## 10. Riesgos

| Riesgo | Mitigación |
|---|---|
| Modificar una aplicación que está en uso en plena temporada | Entregas pequeñas, versión anterior siempre disponible, pruebas antes de instalar y cambios fuera del horario de atención |
| Dos versiones del programa de Rodrigo (la suya y la nuestra) | Nico toma el control del código. Una sola copia oficial en Git, y Rodrigo no instala versiones propias. |
| Emitir la boleta al canjear en vez de al pagar, y entradas que nunca se canjean y quedan sin boleta | Validarlo con el contador de Rodrigo. El momento de emisión queda configurable. |
| El VPS es un único punto de falla | Respaldos de Hostgator, volcado diario externo de la base y manual de reconstrucción |
| Caída de internet en el acceso | Procedimiento manual escrito, más la búsqueda por número de pedido cuando vuelve la conexión |
| Correos con QR que caen en spam | SPF y DKIM configurados, remitente del dominio del parque |
| Pistola 1D que no lee QR en pantallas | Comprar un lector 2D |
| Ley 21.719 de datos personales | Datos mínimos, plazo de conservación definido y acceso restringido |

---

## 11. Preguntas abiertas y pendientes

**Bloquean la Fase 1 (esta semana)**
1. Contratar el VPS (Snappy 2000 - NVMe 4, sin cPanel) y confirmar si incluye respaldos.
2. Comprar la pistola lectora 2D, USB y capaz de leer pantallas de celular.
3. Casilla de correo del dominio que enviará los QR, y acceso al DNS en Hostgator para configurar SPF y DKIM.
4. ID del producto "Entrada General" en WooCommerce y claves de la API REST de WooCommerce (solo lectura sobre pedidos).
5. Subdominio definitivo para el backend (propuesta: `acceso.vallederomeral.cl`).
6. Fecha de término de la temporada actual, para cargarla como parámetro.

**Necesarias para la base de la Fase 2**

7. Copia de los registros de tiempos del PC del acceso: `romeral_diagnostico_etapas.jsonl` y `romeral_tiempos_impresion.jsonl`, en `Documentos\ROMERAL_Datos`.
8. Consultar a Facturacion.cl:
    - ¿Tienen ambiente de pruebas?
    - ¿La respuesta de `Procesar` puede incluir el timbre (TED)?
    - ¿Tienen formato de ticket de 80 mm (módulo BETICKET)?
9. Meta de velocidad concreta para la emisión (por ejemplo, menos de 5 segundos).

**Para más adelante**

10. ¿El computador del acceso tiene pantalla táctil? (la v2.10.19 está ajustada a una pantalla táctil de 1024x768)
11. ¿React en TypeScript? (recomendado)
12. ¿Las entradas gratuitas imprimen algo (comprobante interno) o solo se cuentan?
13. ¿Se aprueba que el precio del acceso viva en nuestro sistema y no en WooCommerce?
14. Validar con el contador de Rodrigo que la boleta de una entrada online se emita al canjearla.

---

## 12. Plan de la semana 1 **[DECIDIDO en alcance; el detalle lo genera superpowers en `docs/plans/`]**

**Fase 1, completa:**
1. Contrato OpenAPI y guía de la API.
2. Maquetas en `mock/frames/`: correo con QR y pantalla de canje en la aplicación local.
3. Proyecto Django base con PostgreSQL, modelo de datos y pruebas.
4. Webhook de WooCommerce con validación de firma, y conciliación cada 10 minutos.
5. Generación del código y del QR, y envío del correo.
6. API de consulta, búsqueda, canje atómico y registro de boleta.
7. Importación de pedidos anteriores de la temporada.
8. Instalación en el VPS: Nginx, Gunicorn, PostgreSQL, HTTPS y respaldo diario.
9. Pantalla de canje en la aplicación local, sobre la copia en `desktop/`.
10. Prueba con pedidos ficticios en el ambiente de pruebas y después con un pedido real.

**Fase 2, solo la base:**
1. Copiar la v2.10.19 a `desktop/` y dejar una sola versión oficial en Git.
2. Ordenar: mover los archivos LEER y los scripts de una sola vez a un archivo histórico, y escribir un README único y un CHANGELOG.
3. Generar el `.exe` de Windows automáticamente con PyInstaller en GitHub Actions.
4. Analizar los registros de tiempos y definir las optimizaciones.

**Semanas siguientes:** reestructuración profunda de la aplicación local y optimización de la emisión, en entregas pequeñas.

**Después de la temporada (Fase 3):** se planifica en detalle al cerrar la temporada.

---

## 13. Historial de este documento

| Fecha | Versión | Cambio |
|---|---|---|
| 23-11-2026 | 0.1 | Primera versión con contexto, decisiones y las tres fases |
| 23-11-2026 | 0.2 | Versión base v2.10.19, VPS elegido, Fase 1 aprobada, OpenAPI, superpowers, plan de la semana 1 |
