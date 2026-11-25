# Fase 1: Entradas Online con QR — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Django backend, email flow, WooCommerce webhook/reconciliation, and desktop redeem screen that let a paid WooCommerce order become a once-redeemable QR ticket, checked and invoiced from the existing gate application.

**Architecture:** A small Django project (`backend/`) with Django Ninja exposes the API defined in `docs/api/openapi.yaml`. WooCommerce pushes paid orders via a signed webhook; a 10-minute cron reconciles any webhook that was lost. Each ticket gets a random `VR1…` code (only its SHA-256 hash is stored) and is emailed to the buyer from a template built in `mock/frames/`. The gate application (`desktop/`, a copy of `mock/ROMERAL_v2_10_19/`) gets a real redeem screen that calls the API, and on a successful atomic redeem reuses the existing `registrar()`/`emitir_automaticamente()` invoice flow unchanged, then reports the folio back to the API.

**Tech Stack:** Python, Django 6.1, Django Ninja, PostgreSQL, Nginx, Gunicorn, Let's Encrypt, AlmaLinux 9 (VPS), rclone (backup), Tkinter/SQLite (existing desktop app), pytest.

**Spec:** `docs/plans/2026-11-23-fase1-entradas-online-qr-design.md` (design), `docs/PROYECTO.md` sections 3-5, 11-12 (approved master design). Executors read both before starting.

## Global Constraints

- Backend: Python, Django 6.1 (move to 6.2 LTS later), Django Ninja, PostgreSQL. API docs auto-published at `/api/docs`.
- API contract lives in `docs/api/openapi.yaml`, written before any backend code; Spanish guide in `docs/api/README.md`.
- Server target: AlmaLinux 9 VPS, no cPanel, Nginx + Gunicorn + Let's Encrypt. Subdomain: `acceso.vallederomeral.cl`.
- QR code: opaque random string, prefix `VR1`, uppercase letters and digits only. Store only its SHA-256 hash (`code_hash`), never the code itself.
- Store only buyer name and email as personal data on `online_ticket`.
- A ticket redeems once, atomically, in full. No partial redemption, no re-entry. Concurrent redeem requests: exactly one succeeds.
- The boleta for an online ticket is issued only at redemption, for the total paid, payment method `Webpay`. Not configurable.
- `online_ticket.status` ∈ `VALID`, `REDEEMED`, `CANCELLED`, `REFUNDED_AFTER_REDEMPTION` (the last one added during brainstorming: a WooCommerce refund/cancellation arriving after redemption with an already-issued boleta does not become `CANCELLED`; it is distinguishable and left for Fase 3 to resolve).
- Season is data, not a constant: `season.starts_on`, `season.ends_on`. This run: `2026-11-20` to `2027-02-28`.
- Sender mailbox: `entradas@vallederomeral.cl`. SPF/DKIM must be configured on Hostgator's DNS before relying on deliverability.
- Daily backup: `pg_dump` uploaded via `rclone` to a Google Drive folder (dedicated service account) — the VPS plan has no provider-side backups.
- Mock first: the email and the redeem screen are approved as static HTML in `mock/frames/` before any backend or desktop code is written (Task 3 is a hard gate on this).
- Test first for business logic: redemption, ticket states, webhook signature, season validity, totals.
- Never call Facturacion.cl's real `Procesar` from tests or scripts. Real issuance needs Nico's explicit approval each time; the end-to-end test (Task 21) uses fake orders in a test environment, assumed to have a Facturacion.cl sandbox (to confirm with Rodrigo — not a blocker for this plan).
- Never commit credentials, `.env` files, SQLite databases, CAF files, or anything from `ROMERAL_Datos`.
- `mock/ROMERAL_v2_10_19/` is read-only forever. All desktop changes happen in `desktop/`, which starts as its copy (Task 4).
- The redeem screen replicates `registrar()`'s pre-checks (production enabled, no SOAP send pending reconciliation, jornada not closed) before calling `emitir_automaticamente()`, and shares its `emision_en_curso` lock with in-person sales — both decided in the design doc.
- Code, identifiers, commit messages, comments: English. UI and docs: Spanish.
- External blockers that do not block *writing* this plan, flagged per task below: VPS not yet contracted (Task 16-17 need it to execute, not to write), 2D scanner not yet bought (desktop tests use manual code entry throughout), WooCommerce REST API keys and the "Entrada General" product ID not yet available (blocks only Task 15's real-import run and Task 21's real-order step, not development), Facturacion.cl sandbox existence to confirm with Rodrigo (affects how literally Task 21 can be run, not how it's written).

## Review Focus

- Two redeem requests for the same code arriving at once: exactly one must succeed (200), the other must get 409, never both succeeding or both failing. (Task 10)
- A WooCommerce webhook call with a missing or invalid `X-WC-Webhook-Signature`: must be rejected outright, never processed as if it were genuine. (Task 12)
- A ticket looked up or redeemed after `season.ends_on`: must report "fuera de temporada," not `VALID`. (Task 9)
- A redeem request against a ticket that is already `CANCELLED` or `REFUNDED_AFTER_REDEMPTION`: must return a clear, specific rejection, not a generic error or a silent no-op. (Task 10)
- An invoice callback reporting failure (not success): the ticket must move to `invoice_status = PENDING_REVIEW` ("canjeada con boleta pendiente") and be visible to a supervisor, never silently dropped. (Task 11)

---

## Summary

1. OpenAPI contract (`docs/api/openapi.yaml`) and Spanish API guide (`docs/api/README.md`).
2. HTML mocks for the QR email and the desktop redeem screen (`mock/frames/`).
3. **Gate** — stop and get Nico's approval on Tasks 1-2 before anything else.
4. Copy `mock/ROMERAL_v2_10_19/` into `desktop/` as the single editable copy.
5. Django project scaffold (PostgreSQL, Django Ninja).
6. Models: `Season`, `Terminal`, `OnlineTicket`, `OnlineTicketLine`, `TicketEvent`.
7. QR code generation and SHA-256 hashing.
8. Per-terminal API key authentication.
9. Ticket lookup and search endpoints.
10. Atomic redeem endpoint (concurrency-safe).
11. Invoice status callback endpoint.
12. WooCommerce webhook with signature validation.
13. QR email sending from the approved mock template.
14. 10-minute reconciliation command.
15. Import command for the current season's prior paid orders.
16. VPS deployment scripts (Nginx, Gunicorn, PostgreSQL, Let's Encrypt).
17. Daily off-server backup (rclone to Google Drive) and cron schedule.
18. `desktop/ventas_online.py` as an HTTP client to the backend.
19. `desktop/romeral.py`'s real redeem screen, wired into the existing invoice flow.
20. "Online" line in the daily cash close.
21. End-to-end test with fake orders, then one real order under explicit authorization.

---

## File Structure

```
backend/
  manage.py
  core/
    settings.py          # Django project settings (DB, installed apps, email)
    urls.py
  tickets/
    models.py             # Season, Terminal, OnlineTicket, OnlineTicketLine, TicketEvent
    qr.py                  # code generation + hashing
    auth.py                # per-terminal API key auth for Django Ninja
    api.py                 # Django Ninja router: lookup, search, redeem, invoice
    webhooks.py            # WooCommerce webhook view + signature validation
    woocommerce_client.py  # thin REST client (orders, read-only)
    emails.py              # renders mock/frames email into a Django template and sends it
    management/commands/
      reconcile_orders.py      # 10-minute reconciliation job
      import_prior_orders.py   # one-off import of prior paid orders
    tests/
      test_models.py
      test_qr.py
      test_auth.py
      test_api_lookup.py
      test_api_redeem.py
      test_api_invoice.py
      test_webhooks.py
      test_reconcile_orders.py
      test_import_prior_orders.py
      test_emails.py
  templates/
    emails/
      qr_ticket.html    # built from the approved mock/frames email mock

docs/
  api/
    openapi.yaml
    README.md
  plans/
    2026-11-23-fase1-entradas-online-qr-design.md   # already exists
    2026-11-23-fase1-entradas-online-qr-plan.md      # this file

mock/
  frames/
    correo_qr.html
    canje_online.html

desktop/                 # created in Task 4 as a copy of mock/ROMERAL_v2_10_19/
  ventas_online.py        # completed: HTTP client to the backend API
  romeral.py               # panel_qr_online() replaced by the real redeem screen

deploy/
  nginx.conf
  gunicorn.service
  setup_vps.sh
  backup_db.sh            # pg_dump + rclone upload
  crontab.txt              # reconciliation + backup schedule
```

---

### Task 1: OpenAPI contract and Spanish API guide

**Files:**
- Create: `docs/api/openapi.yaml`
- Create: `docs/api/README.md`

**Interfaces:**
- Produces: the formal contract every later backend task implements against — routes, request/response schemas, and status codes for `GET /api/v1/tickets/{code}`, `GET /api/v1/tickets?order=|email=`, `POST /api/v1/tickets/{code}/redeem`, `POST /api/v1/tickets/{code}/invoice`, `POST /api/v1/woocommerce/webhook`.

- [ ] **Step 1: Write `docs/api/openapi.yaml`**

OpenAPI 3.1 document, Spanish `description`/`summary` fields (docs are Spanish; schema names are English per code conventions). Include:
  - `info`: title "romeralQRAccess API", version `0.1.0`.
  - `servers`: `https://acceso.vallederomeral.cl`.
  - `security`: an `apiKeyAuth` scheme, header `X-Terminal-Key`, applied to every route except the webhook (which uses `X-WC-Webhook-Signature` instead).
  - Schema `OnlineTicket`: fields exactly as in the design doc's `online_ticket` entity, `status` enum `VALID`/`REDEEMED`/`CANCELLED`/`REFUNDED_AFTER_REDEMPTION`, `invoice_status` enum `NOT_ISSUED`/`ISSUED`/`PENDING_REVIEW`, `total_paid` as integer CLP, nested `lines: OnlineTicketLine[]`.
  - Schema `OnlineTicketLine`: `woo_product_id`, `product_name`, `quantity`, `unit_price`, `line_total`.
  - `GET /api/v1/tickets/{code}`: 200 `OnlineTicket`, 404 if no ticket matches the code's hash.
  - `GET /api/v1/tickets` with optional query params `order` and `email` (at least one required): 200 array of `OnlineTicket`.
  - `POST /api/v1/tickets/{code}/redeem`: request body `{terminal: string, redeemed_by: string}`, 200 `OnlineTicket` (now `REDEEMED`), 409 if already redeemed/cancelled/refunded-after-redemption, 404 if unknown code.
  - `POST /api/v1/tickets/{code}/invoice`: request body `{status: "ISSUED"|"PENDING_REVIEW", folio: string|null}`, 200 `OnlineTicket`.
  - `POST /api/v1/woocommerce/webhook`: request body matching WooCommerce's order-paid payload (order id, number, status, billing name/email, line items, total, date_paid), 200 on acceptance, 401 on bad/missing signature.

- [ ] **Step 2: Write `docs/api/README.md`** (Spanish)

Explain, for a developer integrating the gate app: base URL, how the terminal API key header works, each endpoint with a short description and an example request/response, the meaning of each `status`/`invoice_status` value, and how to run the interactive docs at `/api/docs` once the backend is deployed.

- [ ] **Step 3: Validate the OpenAPI document**

Run: `npx --yes @redocly/cli lint docs/api/openapi.yaml`
Expected: no errors (warnings acceptable).

- [ ] **Step 4: Commit**

```bash
git add docs/api/openapi.yaml docs/api/README.md
git commit -m "docs: add Phase 1 OpenAPI contract and API guide"
```

---

### Task 2: HTML mocks — QR email and redeem screen

**Files:**
- Create: `mock/frames/correo_qr.html`
- Create: `mock/frames/canje_online.html`

**Interfaces:**
- Consumes: `docs/api/openapi.yaml` (`OnlineTicket` schema) for what data the redeem screen mock must display.
- Produces: the approved visual reference Task 13 (email template) and Task 19 (desktop redeem screen) build from.

- [ ] **Step 1: Write `mock/frames/correo_qr.html`**

Static HTML email, Spanish copy. Must show: the QR image (placeholder `<img>`), order number, number of people, validity ("válida toda la temporada, hasta el 28 de febrero de 2027"), and one plain instruction ("muestra este código en el acceso"). Table-based layout for email client compatibility, inline styles only.

- [ ] **Step 2: Write `mock/frames/canje_online.html`**

Static HTML mockup of the Tkinter redeem screen, sized to read clearly at 1024x768 touch, matching `mock/ROMERAL_v2_10_19/romeral.py`'s existing color/button conventions (large touch targets, same palette as `panel_qr_online`). Shows: scan/manual-entry field, a result card with buyer name, order number, people count, line-item detail with unit prices, total paid, a status banner (valid / already redeemed with timestamp / cancelled / out of season), and a large "Canjear y emitir boleta" button, disabled unless status is valid.

- [ ] **Step 3: Get Nico's approval on both mocks**

Share both files; do not proceed to Task 3 until he confirms them (or asks for changes, in which case repeat Steps 1-2).

- [ ] **Step 4: Commit**

```bash
git add mock/frames/correo_qr.html mock/frames/canje_online.html
git commit -m "docs: add approved HTML mocks for QR email and redeem screen"
```

---

### Task 3: GATE — stop before any backend or desktop code

**No files.**

- [ ] **Step 1: Confirm Tasks 1 and 2 are both approved by Nico**

Do not start Task 4 or any later task until the OpenAPI contract, the API guide, and both HTML mocks have his explicit sign-off. This is the checkpoint CLAUDE.md's "mock first" and the user's original instruction both require.

---

### Task 4: Copy the gate application into `desktop/`

**Files:**
- Create: `desktop/` (copy of `mock/ROMERAL_v2_10_19/`)

**Interfaces:**
- Produces: the single official, editable copy of the gate application that Tasks 18-20 modify. `mock/ROMERAL_v2_10_19/` stays untouched, forever read-only.

- [ ] **Step 1: Copy the tree**

Run: `cp -R mock/ROMERAL_v2_10_19/ desktop/`
Then remove the one-off scripts and `LEER_*`/`Abrir_*` files that aren't part of the running application (`romeral.py`, `ventas_online.py`, and the other importable modules referenced from `romeral.py` stay; the rest is Fase 2 cleanup and out of scope here — if unsure whether a file is imported, grep for its module name in `romeral.py` before removing it).

- [ ] **Step 2: Verify the app still runs unmodified**

Run: `cd desktop && python3 romeral.py` (or the project's existing smoke-test entry point)
Expected: launches exactly as `mock/ROMERAL_v2_10_19/romeral.py` does — no behavior change yet.

- [ ] **Step 3: Commit**

```bash
git add desktop/
git commit -m "chore: seed desktop/ as the editable copy of ROMERAL v2.10.19"
```

---

### Task 5: Django project scaffold

**Files:**
- Create: `backend/manage.py`
- Create: `backend/core/settings.py`
- Create: `backend/core/urls.py`
- Create: `backend/tickets/__init__.py`, `backend/tickets/apps.py`
- Create: `backend/requirements.txt` (or `pyproject.toml`, following whichever the repo already favors for Python — check `desktop/` and the root for an existing convention before choosing)

**Interfaces:**
- Produces: `backend/core/settings.py` reads `DATABASE_URL`, `DJANGO_SECRET_KEY`, `EMAIL_*`, and `WOOCOMMERCE_*` from environment variables only (never hardcoded), via a `.env` file excluded by `.gitignore`.

- [ ] **Step 1: Scaffold the Django project and the `tickets` app**

`django-admin startproject core backend` then `python manage.py startapp tickets`, with `django_ninja` and `tickets` added to `INSTALLED_APPS`, `DATABASES` pointed at PostgreSQL via `DATABASE_URL`.

- [ ] **Step 2: Add `.env.example` (not `.env`) and confirm `.gitignore` excludes `.env`**

List the required variables with placeholder values: `DJANGO_SECRET_KEY`, `DATABASE_URL`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `WOOCOMMERCE_WEBHOOK_SECRET`, `WOOCOMMERCE_API_URL`, `WOOCOMMERCE_API_KEY`, `WOOCOMMERCE_API_SECRET`.

- [ ] **Step 3: Verify the project boots**

Run: `cd backend && python manage.py check`
Expected: "System check identified no issues."

- [ ] **Step 4: Commit**

```bash
git add backend/ .gitignore
git commit -m "chore: scaffold Django project with PostgreSQL and Django Ninja"
```

---

### Task 6: Models — Season, Terminal, OnlineTicket, OnlineTicketLine, TicketEvent

**Files:**
- Create: `backend/tickets/models.py`
- Test: `backend/tickets/tests/test_models.py`
- Create: `backend/tickets/migrations/0001_initial.py` (generated)

**Interfaces:**
- Consumes: Task 5's `tickets` app.
- Produces: `Season`, `Terminal`, `OnlineTicket`, `OnlineTicketLine`, `TicketEvent` models that every later backend task imports from `tickets.models`.
  - `Season(name: str, starts_on: date, ends_on: date, is_active: bool)`
  - `OnlineTicket(id: UUIDField primary_key, code_hash: str unique, woo_order_id: int unique, woo_order_number: str, buyer_name: str, buyer_email: str, people_count: int, total_paid: int, payment_method: str, purchased_at: datetime, season: FK(Season), valid_until: date, status: str, redeemed_at: datetime|None, redeemed_by: str|None, invoice_status: str, invoice_folio: str|None, source: str, created_at: datetime, updated_at: datetime)`
  - `OnlineTicketLine(ticket: FK(OnlineTicket), woo_product_id: int, product_name: str, quantity: int, unit_price: int, line_total: int)`
  - `TicketEvent(ticket: FK(OnlineTicket), event_type: str, occurred_at: datetime, terminal: str, detail: JSONField)`
  - `Terminal(name: str, api_key_hash: str, is_active: bool)`

- [ ] **Step 1: Write failing model tests**

```python
def test_online_ticket_status_choices_include_refunded_after_redemption():
    assert "REFUNDED_AFTER_REDEMPTION" in dict(OnlineTicket.STATUS_CHOICES)

def test_online_ticket_requires_unique_code_hash():
    season = Season.objects.create(name="2026-2027", starts_on="2026-11-20", ends_on="2027-02-28")
    OnlineTicket.objects.create(code_hash="a"*64, woo_order_id=1, woo_order_number="W-1",
        buyer_name="Ana", buyer_email="ana@example.com", people_count=2, total_paid=24000,
        payment_method="Webpay", purchased_at=timezone.now(), season=season,
        valid_until=season.ends_on, status="VALID", invoice_status="NOT_ISSUED", source="WEBHOOK")
    with pytest.raises(IntegrityError):
        OnlineTicket.objects.create(code_hash="a"*64, woo_order_id=2, ...)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tickets/tests/test_models.py -v`
Expected: FAIL (`ModuleNotFoundError` or `ImportError`).

- [ ] **Step 3: Implement the five models in `backend/tickets/models.py`**

`STATUS_CHOICES`, `INVOICE_STATUS_CHOICES`, `SOURCE_CHOICES` as class-level tuples on `OnlineTicket`, matching the Global Constraints enum exactly.

- [ ] **Step 4: Generate and apply migrations**

Run: `python manage.py makemigrations tickets && python manage.py migrate`
Expected: `0001_initial` created, applies cleanly.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tickets/tests/test_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tickets/models.py backend/tickets/migrations/ backend/tickets/tests/test_models.py
git commit -m "feat: add Season, Terminal, OnlineTicket, OnlineTicketLine, TicketEvent models"
```

---

### Task 7: QR code generation and hashing

**Files:**
- Create: `backend/tickets/qr.py`
- Test: `backend/tickets/tests/test_qr.py`

**Interfaces:**
- Produces: `generate_code() -> str` (returns `"VR1" + 22 random uppercase-letter-or-digit characters`), `hash_code(code: str) -> str` (SHA-256 hex digest), used by Task 12 (webhook ticket creation) and Task 15 (import command).

- [ ] **Step 1: Write failing tests**

```python
def test_generate_code_has_vr1_prefix_and_is_uppercase_alnum():
    code = generate_code()
    assert code.startswith("VR1")
    assert re.fullmatch(r"VR1[A-Z0-9]+", code)

def test_generate_code_is_not_predictable():
    assert generate_code() != generate_code()

def test_hash_code_is_sha256_hex():
    assert hash_code("VR1ABC") == hashlib.sha256(b"VR1ABC").hexdigest()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tickets/tests/test_qr.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `generate_code()` and `hash_code()` in `backend/tickets/qr.py`**

Use `secrets.choice` over `string.ascii_uppercase + string.digits` for the random part — never `random`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tickets/tests/test_qr.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tickets/qr.py backend/tickets/tests/test_qr.py
git commit -m "feat: add QR code generation and SHA-256 hashing"
```

---

### Task 8: Terminal API key authentication

**Files:**
- Create: `backend/tickets/auth.py`
- Test: `backend/tickets/tests/test_auth.py`

**Interfaces:**
- Consumes: `Terminal` model from Task 6.
- Produces: `TerminalKeyAuth` (a Django Ninja `HttpBearer`/`APIKeyHeader`-style auth class, header `X-Terminal-Key`), used by every route in Task 9-11's `api.py`. Its `authenticate(request, key) -> Terminal | None` hashes the presented key and matches it against `Terminal.api_key_hash` for an `is_active=True` terminal.

- [ ] **Step 1: Write failing tests**

```python
def test_valid_active_terminal_key_authenticates():
    terminal = Terminal.objects.create(name="Acceso 1", api_key_hash=hash_key("secret123"), is_active=True)
    assert TerminalKeyAuth().authenticate(request, "secret123") == terminal

def test_inactive_terminal_key_is_rejected():
    Terminal.objects.create(name="Acceso 1", api_key_hash=hash_key("secret123"), is_active=False)
    assert TerminalKeyAuth().authenticate(request, "secret123") is None

def test_unknown_key_is_rejected():
    assert TerminalKeyAuth().authenticate(request, "nope") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tickets/tests/test_auth.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `hash_key(key: str) -> str` and `TerminalKeyAuth` in `backend/tickets/auth.py`**

Same SHA-256 approach as `qr.hash_code`; reuse `qr.hash_code` rather than duplicating it if the implementer judges the hashing identical (same algorithm, different semantic purpose — document which import it uses).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tickets/tests/test_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tickets/auth.py backend/tickets/tests/test_auth.py
git commit -m "feat: add per-terminal API key authentication"
```

---

### Task 9: Lookup and search endpoints

**Files:**
- Create: `backend/tickets/api.py`
- Test: `backend/tickets/tests/test_api_lookup.py`

**Interfaces:**
- Consumes: `OnlineTicket`/`Season` (Task 6), `qr.hash_code` (Task 7), `TerminalKeyAuth` (Task 8).
- Produces: a Django Ninja `Router` mounted at `/api/v1/tickets` with `GET /{code}` and `GET /` (query params `order`, `email`), registered in `backend/core/urls.py`. Both serialize `OnlineTicket` per the `openapi.yaml` schema and compute a derived `display_status` of `"fuera de temporada"` when `today > valid_until` even if stored `status` is still `VALID`.

- [ ] **Step 1: Write failing tests**

```python
def test_lookup_by_code_returns_ticket(client, active_terminal_key):
    ticket = make_online_ticket(code_hash=hash_code("VR1ABC"))
    resp = client.get("/api/v1/tickets/VR1ABC", headers={"X-Terminal-Key": active_terminal_key})
    assert resp.status_code == 200
    assert resp.json()["woo_order_number"] == ticket.woo_order_number

def test_lookup_unknown_code_returns_404(client, active_terminal_key):
    resp = client.get("/api/v1/tickets/VR1DOESNOTEXIST", headers={"X-Terminal-Key": active_terminal_key})
    assert resp.status_code == 404

def test_lookup_past_valid_until_reports_fuera_de_temporada(client, active_terminal_key):
    ticket = make_online_ticket(code_hash=hash_code("VR1OLD"), valid_until=date(2025, 1, 1), status="VALID")
    resp = client.get("/api/v1/tickets/VR1OLD", headers={"X-Terminal-Key": active_terminal_key})
    assert resp.json()["display_status"] == "fuera de temporada"

def test_search_by_order_number(client, active_terminal_key):
    make_online_ticket(woo_order_number="W-42")
    resp = client.get("/api/v1/tickets?order=W-42", headers={"X-Terminal-Key": active_terminal_key})
    assert len(resp.json()) == 1

def test_search_without_order_or_email_is_rejected(client, active_terminal_key):
    resp = client.get("/api/v1/tickets", headers={"X-Terminal-Key": active_terminal_key})
    assert resp.status_code == 400

def test_missing_terminal_key_is_rejected(client):
    resp = client.get("/api/v1/tickets/VR1ABC")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tickets/tests/test_api_lookup.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the router in `backend/tickets/api.py` and mount it in `backend/core/urls.py`**

- [ ] **Step 4: Add `display_status` to the `OnlineTicket` schema in `docs/api/openapi.yaml`**

Task 1 did not anticipate this derived, read-only field (string, e.g. `"fuera de temporada"`, or null/absent when the stored `status` already reflects reality). Add it now so the contract matches the implementation.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tickets/tests/test_api_lookup.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tickets/api.py backend/core/urls.py backend/tickets/tests/test_api_lookup.py docs/api/openapi.yaml
git commit -m "feat: add ticket lookup and search API endpoints"
```

---

### Task 10: Atomic redeem endpoint

**Files:**
- Modify: `backend/tickets/api.py` (add `POST /{code}/redeem`)
- Test: `backend/tickets/tests/test_api_redeem.py`

**Interfaces:**
- Consumes: `Task 9`'s router, `TicketEvent` model (Task 6).
- Produces: `POST /api/v1/tickets/{code}/redeem` — on success, sets `status="REDEEMED"`, `redeemed_at=now()`, `redeemed_by=<request body's redeemed_by>`, writes a `TicketEvent(event_type="canjeada")`, returns 200. Any later task that needs "was this ticket just redeemed" reads `OnlineTicket.status == "REDEEMED"`.

- [ ] **Step 1: Write failing tests, including the concurrency case**

```python
def test_redeem_valid_ticket_succeeds(client, active_terminal_key):
    ticket = make_online_ticket(code_hash=hash_code("VR1ABC"), status="VALID")
    resp = client.post("/api/v1/tickets/VR1ABC/redeem", json={"terminal": "Acceso 1", "redeemed_by": "cajero1"},
                        headers={"X-Terminal-Key": active_terminal_key})
    assert resp.status_code == 200
    assert resp.json()["status"] == "REDEEMED"

def test_redeem_already_redeemed_ticket_returns_409(client, active_terminal_key):
    make_online_ticket(code_hash=hash_code("VR1ABC"), status="REDEEMED")
    resp = client.post("/api/v1/tickets/VR1ABC/redeem", json={"terminal": "Acceso 1", "redeemed_by": "cajero1"},
                        headers={"X-Terminal-Key": active_terminal_key})
    assert resp.status_code == 409

def test_redeem_cancelled_ticket_returns_409_with_reason(client, active_terminal_key):
    make_online_ticket(code_hash=hash_code("VR1ABC"), status="CANCELLED")
    resp = client.post("/api/v1/tickets/VR1ABC/redeem", json={"terminal": "Acceso 1", "redeemed_by": "cajero1"},
                        headers={"X-Terminal-Key": active_terminal_key})
    assert resp.status_code == 409
    assert "anulada" in resp.json()["detail"].lower()

def test_concurrent_redeem_requests_only_one_succeeds(client, active_terminal_key, django_db_serialized_rollback):
    make_online_ticket(code_hash=hash_code("VR1ABC"), status="VALID")
    def call():
        return client.post("/api/v1/tickets/VR1ABC/redeem", json={"terminal": "Acceso 1", "redeemed_by": "cajero1"},
                            headers={"X-Terminal-Key": active_terminal_key})
    results = [r.status_code for r in run_concurrently(call, times=10)]
    assert results.count(200) == 1
    assert results.count(409) == 9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tickets/tests/test_api_redeem.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the redeem endpoint using `select_for_update()` inside an atomic transaction**

Wrap the read-check-write in `with transaction.atomic(): ticket = OnlineTicket.objects.select_for_update().get(...)`, so a second concurrent request blocks until the first commits and then sees the updated `status`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tickets/tests/test_api_redeem.py -v`
Expected: PASS, including the concurrency test with exactly one 200.

- [ ] **Step 5: Commit**

```bash
git add backend/tickets/api.py backend/tickets/tests/test_api_redeem.py
git commit -m "feat: add atomic ticket redeem endpoint"
```

---

### Task 11: Invoice callback endpoint

**Files:**
- Modify: `backend/tickets/api.py` (add `POST /{code}/invoice`)
- Test: `backend/tickets/tests/test_api_invoice.py`

**Interfaces:**
- Consumes: Task 10's redeemed ticket.
- Produces: `POST /api/v1/tickets/{code}/invoice` — sets `invoice_status` to `ISSUED` (with `invoice_folio`) or `PENDING_REVIEW` (folio `None`), writes a `TicketEvent(event_type="boleta emitida"|"boleta pendiente")`.

- [ ] **Step 1: Write failing tests**

```python
def test_invoice_issued_sets_folio(client, active_terminal_key):
    make_online_ticket(code_hash=hash_code("VR1ABC"), status="REDEEMED")
    resp = client.post("/api/v1/tickets/VR1ABC/invoice", json={"status": "ISSUED", "folio": "26200"},
                        headers={"X-Terminal-Key": active_terminal_key})
    assert resp.status_code == 200
    assert resp.json()["invoice_status"] == "ISSUED"
    assert resp.json()["invoice_folio"] == "26200"

def test_invoice_pending_review_has_no_folio_and_is_visible(client, active_terminal_key):
    make_online_ticket(code_hash=hash_code("VR1ABC"), status="REDEEMED")
    resp = client.post("/api/v1/tickets/VR1ABC/invoice", json={"status": "PENDING_REVIEW", "folio": None},
                        headers={"X-Terminal-Key": active_terminal_key})
    assert resp.json()["invoice_status"] == "PENDING_REVIEW"

def test_invoice_on_unredeemed_ticket_is_rejected(client, active_terminal_key):
    make_online_ticket(code_hash=hash_code("VR1ABC"), status="VALID")
    resp = client.post("/api/v1/tickets/VR1ABC/invoice", json={"status": "ISSUED", "folio": "1"},
                        headers={"X-Terminal-Key": active_terminal_key})
    assert resp.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tickets/tests/test_api_invoice.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the invoice endpoint**

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tickets/tests/test_api_invoice.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tickets/api.py backend/tickets/tests/test_api_invoice.py
git commit -m "feat: add invoice status callback endpoint"
```

---

### Task 12: WooCommerce webhook with signature validation

**Files:**
- Create: `backend/tickets/webhooks.py`
- Test: `backend/tickets/tests/test_webhooks.py`

**Interfaces:**
- Consumes: `qr.generate_code`/`hash_code` (Task 7), `OnlineTicket`/`OnlineTicketLine`/`Season` (Task 6).
- Produces: `POST /api/v1/woocommerce/webhook`, registered in `backend/core/urls.py`, handling every order-webhook WooCommerce sends to this one URL (order created/updated carries the order's current `status` field — there is no separate "cancelled" event type to special-case). Branches on the payload's `status`:
  - `processing`/`completed` and no existing ticket for that `woo_order_id`: creates one `OnlineTicket` with `source="WEBHOOK"` and one `OnlineTicketLine` per order line item, and calls `emails.send_ticket_email` (Task 13's interface, imported but not yet implemented — stub it to a no-op if Task 13 hasn't landed yet, matching whichever task actually runs first in execution order).
  - `processing`/`completed` and a ticket already exists: no-op (idempotent — the order was already seen).
  - `cancelled`/`refunded` and an existing ticket is `VALID`: sets it to `CANCELLED` and writes a `TicketEvent(event_type="anulada")`. Per `docs/PROYECTO.md` 5.1 ("si un pedido se anula o reembolsa, la entrada pasa a anulada").
  - `cancelled`/`refunded` and an existing ticket is `REDEEMED` (boleta already issued): sets it to `REFUNDED_AFTER_REDEMPTION` instead of `CANCELLED` and writes a `TicketEvent(event_type="reembolsada tras canje")` — the design doc's resolution; this case is left for Fase 3 to settle on the accounting side, Fase 1 only needs it visible and distinct.
  - `cancelled`/`refunded` and no ticket exists for that order: no-op.
- Produces a shared `create_ticket_from_order(order: dict, send_email: bool = True) -> OnlineTicket` function in this file; Tasks 14 and 15 import it rather than re-implementing order-to-ticket creation.

- [ ] **Step 1: Write failing tests**

```python
def test_webhook_with_valid_signature_creates_ticket(client, settings):
    settings.WOOCOMMERCE_WEBHOOK_SECRET = "shhh"
    payload = sample_order_payload(order_id=501, status="processing", total="12000")
    signature = compute_wc_signature(payload, "shhh")
    resp = client.post("/api/v1/woocommerce/webhook", data=payload,
                        headers={"X-WC-Webhook-Signature": signature})
    assert resp.status_code == 200
    assert OnlineTicket.objects.filter(woo_order_id=501).exists()

def test_webhook_with_missing_signature_is_rejected(client):
    resp = client.post("/api/v1/woocommerce/webhook", data=sample_order_payload(order_id=502, status="processing"))
    assert resp.status_code == 401
    assert not OnlineTicket.objects.filter(woo_order_id=502).exists()

def test_webhook_with_wrong_signature_is_rejected(client, settings):
    settings.WOOCOMMERCE_WEBHOOK_SECRET = "shhh"
    payload = sample_order_payload(order_id=503, status="processing")
    resp = client.post("/api/v1/woocommerce/webhook", data=payload,
                        headers={"X-WC-Webhook-Signature": "wrong"})
    assert resp.status_code == 401

def test_webhook_is_idempotent_on_duplicate_order_id(client, settings):
    settings.WOOCOMMERCE_WEBHOOK_SECRET = "shhh"
    payload = sample_order_payload(order_id=504, status="processing")
    signature = compute_wc_signature(payload, "shhh")
    client.post("/api/v1/woocommerce/webhook", data=payload, headers={"X-WC-Webhook-Signature": signature})
    resp = client.post("/api/v1/woocommerce/webhook", data=payload, headers={"X-WC-Webhook-Signature": signature})
    assert resp.status_code == 200
    assert OnlineTicket.objects.filter(woo_order_id=504).count() == 1

def test_webhook_cancels_an_unredeemed_ticket(client, settings):
    settings.WOOCOMMERCE_WEBHOOK_SECRET = "shhh"
    make_online_ticket(woo_order_id=505, status="VALID")
    payload = sample_order_payload(order_id=505, status="cancelled")
    signature = compute_wc_signature(payload, "shhh")
    client.post("/api/v1/woocommerce/webhook", data=payload, headers={"X-WC-Webhook-Signature": signature})
    assert OnlineTicket.objects.get(woo_order_id=505).status == "CANCELLED"

def test_webhook_refund_after_redemption_does_not_cancel(client, settings):
    settings.WOOCOMMERCE_WEBHOOK_SECRET = "shhh"
    make_online_ticket(woo_order_id=506, status="REDEEMED")
    payload = sample_order_payload(order_id=506, status="refunded")
    signature = compute_wc_signature(payload, "shhh")
    client.post("/api/v1/woocommerce/webhook", data=payload, headers={"X-WC-Webhook-Signature": signature})
    assert OnlineTicket.objects.get(woo_order_id=506).status == "REFUNDED_AFTER_REDEMPTION"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tickets/tests/test_webhooks.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `verify_wc_signature(raw_body: bytes, header_value: str) -> bool`, `create_ticket_from_order(order: dict) -> OnlineTicket`, and the webhook view in `backend/tickets/webhooks.py`**

HMAC-SHA256 of the raw request body against `WOOCOMMERCE_WEBHOOK_SECRET`, base64-compared to the header (constant-time compare via `hmac.compare_digest`). Idempotency via `get_or_create(woo_order_id=...)` on creation; the cancel/refund branch uses `select_for_update()` the same way Task 10's redeem endpoint does, since a cancellation and a redeem could race.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tickets/tests/test_webhooks.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tickets/webhooks.py backend/core/urls.py backend/tickets/tests/test_webhooks.py
git commit -m "feat: add WooCommerce webhook with signature validation and status transitions"
```

---

### Task 13: QR email sending

**Files:**
- Create: `backend/tickets/emails.py`
- Create: `backend/templates/emails/qr_ticket.html` (built from the approved `mock/frames/correo_qr.html`)
- Test: `backend/tickets/tests/test_emails.py`

**Interfaces:**
- Consumes: the approved mock from Task 2, `OnlineTicket` (Task 6).
- Produces: `send_ticket_email(ticket: OnlineTicket, code: str) -> None`, called from Task 12's webhook handler and Task 15's import command (the only two places that ever have the plaintext `code`, since the database stores only its hash).

- [ ] **Step 1: Write failing tests**

```python
def test_send_ticket_email_delivers_one_message(mailoutbox):
    ticket = make_online_ticket(buyer_email="ana@example.com", people_count=2)
    send_ticket_email(ticket, "VR1ABC")
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["ana@example.com"]

def test_send_ticket_email_includes_order_number_and_validity(mailoutbox):
    ticket = make_online_ticket(woo_order_number="W-77", valid_until=date(2027, 2, 28))
    send_ticket_email(ticket, "VR1ABC")
    assert "W-77" in mailoutbox[0].alternatives[0][0]
    assert "28 de febrero" in mailoutbox[0].alternatives[0][0] or "2027-02-28" in mailoutbox[0].alternatives[0][0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tickets/tests/test_emails.py -v`
Expected: FAIL

- [ ] **Step 3: Port `mock/frames/correo_qr.html` into a Django template with placeholders, and implement `send_ticket_email`**

Render the QR as a PNG attachment or embedded data URI (implementer's call — document which); send via Django's `EmailMultiAlternatives` using `EMAIL_HOST*` settings.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tickets/tests/test_emails.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tickets/emails.py backend/templates/emails/qr_ticket.html backend/tickets/tests/test_emails.py
git commit -m "feat: send QR ticket email from the approved mock template"
```

---

### Task 14: Reconciliation management command

**Files:**
- Create: `backend/tickets/woocommerce_client.py`
- Create: `backend/tickets/management/commands/reconcile_orders.py`
- Test: `backend/tickets/tests/test_reconcile_orders.py`

**Interfaces:**
- Consumes: `create_ticket_from_order(order: dict) -> OnlineTicket` from `backend/tickets/webhooks.py` (Task 12) — call it directly rather than re-implementing order-to-ticket creation; do not modify `webhooks.py`.
- Produces: `WooCommerceClient.list_paid_orders(since: datetime) -> list[dict]` (read-only REST call), run every 10 minutes by `deploy/crontab.txt` (Task 17) as `python manage.py reconcile_orders`.

- [ ] **Step 1: Write failing tests**

```python
def test_reconcile_creates_tickets_for_paid_orders_without_one(mock_woocommerce_client):
    mock_woocommerce_client.list_paid_orders.return_value = [sample_order_dict(order_id=601)]
    call_command("reconcile_orders")
    ticket = OnlineTicket.objects.get(woo_order_id=601)
    assert ticket.source == "RECONCILIATION"

def test_reconcile_skips_orders_that_already_have_a_ticket(mock_woocommerce_client):
    make_online_ticket(woo_order_id=602)
    mock_woocommerce_client.list_paid_orders.return_value = [sample_order_dict(order_id=602)]
    call_command("reconcile_orders")
    assert OnlineTicket.objects.filter(woo_order_id=602).count() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tickets/tests/test_reconcile_orders.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `WooCommerceClient` (read-only, `requests` + basic auth with `WOOCOMMERCE_API_KEY`/`SECRET`) and the management command**

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tickets/tests/test_reconcile_orders.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tickets/woocommerce_client.py backend/tickets/management/ backend/tickets/tests/test_reconcile_orders.py
git commit -m "feat: add WooCommerce reconciliation command"
```

---

### Task 15: Import command for prior season orders

**Files:**
- Create: `backend/tickets/management/commands/import_prior_orders.py`
- Test: `backend/tickets/tests/test_import_prior_orders.py`

**Interfaces:**
- Consumes: `WooCommerceClient` (Task 14), `create_ticket_from_order` (Task 12, via `backend/tickets/webhooks.py`).
- Produces: `python manage.py import_prior_orders --season-id=<id> [--send-email]`, run once by hand against the real store once WooCommerce keys exist (external blocker, flagged in Global Constraints — this task's tests don't need the real keys, only a mocked client). When `--send-email` is absent, `create_ticket_from_order` must still run but its email step must not fire — pass it a `send_email: bool = True` parameter (add this parameter to Task 12's `create_ticket_from_order` signature).

- [ ] **Step 1: Write failing tests**

```python
def test_import_creates_tickets_for_unused_paid_orders(mock_woocommerce_client, season):
    mock_woocommerce_client.list_paid_orders.return_value = [sample_order_dict(order_id=701)]
    call_command("import_prior_orders", season_id=season.id)
    ticket = OnlineTicket.objects.get(woo_order_id=701)
    assert ticket.source == "IMPORT"

def test_import_does_not_email_by_default(mock_woocommerce_client, season, mailoutbox):
    mock_woocommerce_client.list_paid_orders.return_value = [sample_order_dict(order_id=702)]
    call_command("import_prior_orders", season_id=season.id)
    assert len(mailoutbox) == 0

def test_import_emails_when_flag_passed(mock_woocommerce_client, season, mailoutbox):
    mock_woocommerce_client.list_paid_orders.return_value = [sample_order_dict(order_id=703)]
    call_command("import_prior_orders", season_id=season.id, send_email=True)
    assert len(mailoutbox) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tickets/tests/test_import_prior_orders.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the command**

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tickets/tests/test_import_prior_orders.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tickets/management/commands/import_prior_orders.py backend/tickets/tests/test_import_prior_orders.py
git commit -m "feat: add command to import prior season's paid orders"
```

---

### Task 16: VPS deployment scripts

**Files:**
- Create: `deploy/nginx.conf`
- Create: `deploy/gunicorn.service`
- Create: `deploy/setup_vps.sh`

**Interfaces:**
- Consumes: `backend/` from Tasks 5-15.
- Produces: a repeatable, documented setup an operator runs once the VPS (external blocker — not yet contracted) exists.

- [ ] **Step 1: Write `deploy/nginx.conf`**

Reverse proxy `acceso.vallederomeral.cl` (443, Let's Encrypt via certbot, redirect 80→443) to Gunicorn on a unix socket.

- [ ] **Step 2: Write `deploy/gunicorn.service`**

A systemd unit running Gunicorn against `core.wsgi:application` as a non-root service user, reading environment from `backend/.env` via `EnvironmentFile`.

- [ ] **Step 3: Write `deploy/setup_vps.sh`**

Idempotent shell script (safe to re-run): installs system packages (Python, PostgreSQL, Nginx, certbot) on AlmaLinux 9 via `dnf`, creates the database and user, copies the two files above into place, enables and starts services, runs `certbot --nginx`.

- [ ] **Step 4: Verify with shellcheck**

Run: `shellcheck deploy/setup_vps.sh`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add deploy/nginx.conf deploy/gunicorn.service deploy/setup_vps.sh
git commit -m "chore: add VPS deployment scripts for Nginx, Gunicorn, and PostgreSQL"
```

---

### Task 17: Daily backup to Google Drive and cron schedule

**Files:**
- Create: `deploy/backup_db.sh`
- Create: `deploy/crontab.txt`

**Interfaces:**
- Consumes: the PostgreSQL database set up in Task 16.
- Produces: a daily off-server copy of the database, since the VPS plan carries no provider backups (Global Constraints).

- [ ] **Step 1: Write `deploy/backup_db.sh`**

`pg_dump` to a timestamped file in a temp directory, then `rclone copy` it to a configured Google Drive remote/folder, then delete the local temp file. Reads the rclone remote name from an environment variable, not hardcoded. Logs success/failure to a file the operator can check.

- [ ] **Step 2: Write `deploy/crontab.txt`**

Two lines: `*/10 * * * *` → `manage.py reconcile_orders`, and one daily off-peak time → `backup_db.sh`.

- [ ] **Step 3: Verify with shellcheck**

Run: `shellcheck deploy/backup_db.sh`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add deploy/backup_db.sh deploy/crontab.txt
git commit -m "chore: add daily off-server backup via rclone and reconciliation cron"
```

---

### Task 18: `desktop/ventas_online.py` — HTTP client to the backend

**Files:**
- Modify: `desktop/ventas_online.py` (replace its SQLite-only logic with an HTTP client; keep the module's public function names where the UI already imports them, per Task 19's needs)
- Test: `desktop/tests/test_ventas_online.py`

**Interfaces:**
- Consumes: `docs/api/openapi.yaml` (Task 1) as the contract to implement against; no backend import (the desktop app and backend are separate processes/languages-of-deployment, talking only over HTTPS).
- Produces: `lookup_ticket(code: str) -> dict | None`, `search_tickets(order: str|None, email: str|None) -> list[dict]`, `redeem_ticket(code: str, terminal: str, redeemed_by: str) -> dict` (raises `TicketAlreadyRedeemedError` on 409), `report_invoice(code: str, status: str, folio: str|None) -> dict`. All read `ACCESO_API_URL` and `ACCESO_TERMINAL_KEY` from the same config mechanism `romeral.py` already uses (`config()`, per the existing codebase — reuse it, don't invent a second one).

- [ ] **Step 1: Write failing tests against a mocked HTTP layer**

```python
def test_lookup_ticket_returns_parsed_json(requests_mock):
    requests_mock.get("https://acceso.vallederomeral.cl/api/v1/tickets/VR1ABC", json=sample_ticket_response())
    result = lookup_ticket("VR1ABC")
    assert result["woo_order_number"] == sample_ticket_response()["woo_order_number"]

def test_lookup_ticket_returns_none_on_404(requests_mock):
    requests_mock.get("https://acceso.vallederomeral.cl/api/v1/tickets/VR1ZZZ", status_code=404)
    assert lookup_ticket("VR1ZZZ") is None

def test_redeem_ticket_raises_on_409(requests_mock):
    requests_mock.post("https://acceso.vallederomeral.cl/api/v1/tickets/VR1ABC/redeem", status_code=409,
                        json={"detail": "Entrada ya canjeada"})
    with pytest.raises(TicketAlreadyRedeemedError):
        redeem_ticket("VR1ABC", terminal="Acceso 1", redeemed_by="cajero1")

def test_report_invoice_sends_folio(requests_mock):
    m = requests_mock.post("https://acceso.vallederomeral.cl/api/v1/tickets/VR1ABC/invoice", json={"invoice_status": "ISSUED"})
    report_invoice("VR1ABC", status="ISSUED", folio="26200")
    assert m.last_request.json() == {"status": "ISSUED", "folio": "26200"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest desktop/tests/test_ventas_online.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the four functions and `TicketAlreadyRedeemedError` in `desktop/ventas_online.py`**

Use the `requests` library already a dependency of the app (per `docs/PROYECTO.md` 1.4's dependency list).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest desktop/tests/test_ventas_online.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add desktop/ventas_online.py desktop/tests/test_ventas_online.py
git commit -m "feat: replace local-only QR registry with backend API client"
```

---

### Task 19: `desktop/romeral.py` — real redeem screen

**Files:**
- Modify: `desktop/romeral.py:986` (`panel_qr_online`, replaced) and the pre-check logic currently inside `registrar()` (`desktop/romeral.py:664-723`)
- Test: `desktop/tests/test_panel_qr_online.py`

**Interfaces:**
- Consumes: Task 18's `ventas_online.lookup_ticket`/`redeem_ticket`/`report_invoice`, and the existing `registrar()`/`emitir_automaticamente()` flow (unchanged signatures) from `desktop/romeral.py`.
- Produces: a redeem screen matching the approved `mock/frames/canje_online.html` (Task 2), wired so later Fase 2 work can keep extending `desktop/` without touching this screen's contract.

- [ ] **Step 1: Extract `registrar()`'s pre-checks into a reusable method**

Pull the production-enabled check, the pending-SOAP-reconciliation check, and the jornada-not-closed check (lines ~668-691) into `self.verificar_condiciones_emision() -> bool` (shows the same `messagebox` errors it does today, returns `False` on any failure), called from both `registrar()` and the new redeem screen. This is a refactor of existing behavior, not a behavior change — `registrar()`'s own tests (if any exist) must keep passing.

- [ ] **Step 2: Write failing tests for the redeem screen's logic** (test the non-UI decision logic, not Tkinter widgets directly — extract a small `CanjeOnlineController` or equivalent plain-Python class the tests drive, following whatever pattern the project uses elsewhere to test Tkinter-adjacent logic)

```python
def test_canje_blocked_when_preconditions_fail(mock_app_with_failed_precondition):
    controller = CanjeOnlineController(mock_app_with_failed_precondition)
    assert controller.puede_canjear() is False

def test_canje_calls_emitir_automaticamente_on_successful_redeem(mock_app, mock_ventas_online):
    mock_ventas_online.redeem_ticket.return_value = {"status": "REDEEMED", "total_paid": 12000}
    controller = CanjeOnlineController(mock_app)
    controller.canjear("VR1ABC")
    mock_app.emitir_automaticamente.assert_called_once()

def test_canje_reports_invoice_result_back_to_backend(mock_app, mock_ventas_online):
    mock_ventas_online.redeem_ticket.return_value = {"status": "REDEEMED", "total_paid": 12000}
    controller = CanjeOnlineController(mock_app)
    controller.canjear("VR1ABC")
    mock_ventas_online.report_invoice.assert_called_once()

def test_canje_shows_already_redeemed_message(mock_app, mock_ventas_online):
    mock_ventas_online.redeem_ticket.side_effect = TicketAlreadyRedeemedError("Entrada ya canjeada")
    controller = CanjeOnlineController(mock_app)
    assert "ya canjeada" in controller.canjear("VR1ABC").lower()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest desktop/tests/test_panel_qr_online.py -v`
Expected: FAIL

- [ ] **Step 4: Implement `CanjeOnlineController` and rebuild `panel_qr_online` from the approved `mock/frames/canje_online.html`**

On `canjear(code)`: call `verificar_condiciones_emision()` first; if it passes, call `ventas_online.redeem_ticket(...)`; on success, acquire the same `emision_en_curso` lock `registrar()` uses, insert a `ventas` row (medio `Webpay`, a new origin marker column or reuse of an existing field — implementer's call, document which in the commit), call `self.emitir_automaticamente(venta_id, total)` unchanged, and once it resolves, call `ventas_online.report_invoice(code, status=..., folio=...)`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest desktop/tests/test_panel_qr_online.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add desktop/romeral.py desktop/tests/test_panel_qr_online.py
git commit -m "feat: replace QR preview panel with real redeem screen"
```

---

### Task 20: "Online" line in the daily cash close

**Files:**
- Modify: `desktop/romeral.py` (cash close query/report, wherever `panel_cierre` and `crear_pdf_cierre` assemble totals)
- Test: `desktop/tests/test_cierre_online.py`

**Interfaces:**
- Consumes: the `ventas` rows with the online origin marker from Task 19.
- Produces: the cash close report shows a distinct "Online" line counting people and boletas from online redemptions, and explicitly excludes their total from expected cash (per CLAUDE.md's business rule).

- [ ] **Step 1: Write failing tests**

```python
def test_cierre_includes_online_line_with_people_and_invoice_count(db_with_online_and_cash_sales):
    resumen = calcular_resumen_cierre(db_with_online_and_cash_sales, fecha="2026-11-23")
    assert resumen["online"]["personas"] == 2
    assert resumen["online"]["boletas"] == 1

def test_cierre_online_total_does_not_add_to_expected_cash(db_with_online_and_cash_sales):
    resumen = calcular_resumen_cierre(db_with_online_and_cash_sales, fecha="2026-11-23")
    assert resumen["efectivo_esperado"] == resumen["efectivo_esperado_sin_online"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest desktop/tests/test_cierre_online.py -v`
Expected: FAIL

- [ ] **Step 3: Add the "Online" aggregation to the cash close calculation, keeping it out of the cash total**

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest desktop/tests/test_cierre_online.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add desktop/romeral.py desktop/tests/test_cierre_online.py
git commit -m "feat: add Online line to daily cash close"
```

---

### Task 21: End-to-end test with fake orders, then one real order

**No new source files — this is a manual verification task.**

- [ ] **Step 1: Stand up a test environment**

Test database, test `EMAIL_*` settings (e.g. Mailhog or console backend), test WooCommerce webhook secret, and — per the brainstorming session's assumption, to confirm with Rodrigo — a Facturacion.cl sandbox for DTE. If no sandbox turns out to exist, stub the SOAP call in this environment instead of hitting `Procesar` for real.

- [ ] **Step 2: Walk one fake order through the whole flow**

Trigger a fake paid-order webhook → confirm the email arrives with a valid QR → scan/manually enter the code in `desktop/`'s redeem screen → confirm the ticket details match → redeem → confirm the sandbox/stubbed invoice flow completes and the folio round-trips to the backend → confirm the cash close shows the Online line.

- [ ] **Step 3: Walk a second fake order through the failure paths**

Confirm: redeeming the same code twice gives the "ya canjeada" message; an expired-season ticket shows "fuera de temporada"; an invoice failure leaves the ticket "canjeada con boleta pendiente" and visible to a supervisor.

- [ ] **Step 4: Get Nico's explicit authorization, then run exactly one real order through the flow**

Only after Steps 1-3 pass cleanly, and only with WooCommerce keys and the real product ID in place (external blocker). This is the only point in the whole plan where a real `Procesar` call to Facturacion.cl is expected.

---

## Self-Review Notes

- **Spec coverage:** every numbered item in `docs/PROYECTO.md` section 12's "Fase 1, completa" list maps to a task: OpenAPI (1), mocks (2), Django+PostgreSQL+models (5-6), webhook+reconciliation (12, 14), QR+email (7, 13), API endpoints (9-11), import (15), VPS install (16-17), desktop redeem screen (18-19), cash close (20), fake-then-real-order test (21). The design doc's three brainstorming resolutions (replicate pre-checks, shared lock, `REFUNDED_AFTER_REDEMPTION`) are each a named step, not a footnote.
- **Review Focus coverage:** confirmed each of the five lines has its test in the task named next to it above.
- **Type/name consistency:** `OnlineTicket.status`/`invoice_status` enums, `ventas_online.py`'s four function names, and `CanjeOnlineController` are used identically wherever they're referenced across tasks.
- **Proportion:** at 21 tasks for a full backend + webhook + email + desktop integration + deployment, this is denser than a small feature plan, but each task is still one component with its own test cycle; no task's steps repeat work another task's Interfaces block already hands over.
