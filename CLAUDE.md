# CLAUDE.md

Permanent context for Claude Code in this repository. Read `docs/PROYECTO.md` before planning or writing code: it is the approved design and the single source of truth for decisions. If something here conflicts with it, `docs/PROYECTO.md` wins.

## Project in one paragraph

romeralQRAccess is the ticketing and entry system for Valle del Romeral, a water park in Chile owned by Rodrigo. Online tickets are sold in WooCommerce (WordPress, Webpay Plus). Our backend is the source of truth for tickets: it receives paid orders by webhook, creates one ticket per order with a QR code, emails it to the buyer, and exposes an API so the gate application can look up a ticket, redeem it once (atomically) and record the boleta folio. Every boleta (DTE 39) is issued by Facturacion.cl, never by us. The gate runs Rodrigo's desktop app (Python, Tkinter, SQLite, Windows), which already issues and prints real boletas.

## Phases

1. Phase 1 (now, this week): Django backend on a VPS with the online ticket and QR flow, plus the redeem screen in the gate app.
2. Phase 2 (during the season): professionalize the desktop app (structure, tests, logs, Windows .exe, faster issuance). This week only the foundation.
3. Phase 3 (after the season): full cloud platform (Bootstrap 5 cashier, React admin and statistics).

## Stack

- Backend: Python, Django 6.1 (move to 6.2 LTS when released), Django Ninja for the API, PostgreSQL.
- API contract: OpenAPI in `docs/api/openapi.yaml`, written before the code. Spanish guide in `docs/api/README.md`.
- Server: Hostgator VPS Snappy 2000 NVMe 4, AlmaLinux 9, no cPanel. Nginx, Gunicorn, Let's Encrypt.
- Desktop app: Python 3.12, Tkinter, SQLite, zeep (SOAP to Facturacion.cl), PyMuPDF, SumatraPDF for printing.
- Scanner: USB 2D barcode gun in keyboard mode.

## Repository layout

- `docs/` project documentation in Spanish. `docs/api/` API contract and guide. `docs/plans/` implementation plans.
- `mock/ROMERAL_v2_10_19/` Rodrigo's app as it runs in production today. Read only. Never edit it.
- `mock/ROMERAL_v2_9_0/` older version, historical reference only.
- `mock/frames/` static HTML mocks, built and approved before coding any screen or email.
- `backend/` Django project (Phases 1 and 3).
- `desktop/` the professionalized desktop app (Phase 2), starting as a copy of `mock/ROMERAL_v2_10_19/`.
- `admin/` React admin (Phase 3).
- `deploy/` VPS setup and backup scripts.

## Working rules

- Do not assume. If a decision is not in `docs/PROYECTO.md`, ask Nico before choosing technology, libraries, data model changes or behavior.
- Mock first: any new screen or email starts as a static HTML file in `mock/frames/` and is approved before implementation.
- Test first for business logic: redemption, ticket states, webhook signature, season validity, totals.
- Never issue real boletas or call Facturacion.cl `Procesar` in production from tests or scripts. Real issuance needs Nico's explicit approval each time.
- Never commit credentials, `.env` files, SQLite databases, CAF files or anything from `ROMERAL_Datos`.
- The gate app is in live use during the season. Changes to `desktop/` ship in small, separately tested releases, and the previous version must stay installable.
- Rodrigo's SQLite data on the gate PC holds real sales and cash closes. Any schema change needs a migration that preserves it.

## Language and style

- Code, identifiers, commit messages and code comments: English.
- User interface: Spanish only.
- Documentation in `docs/` and READMEs: Spanish.
- Write like a careful human engineer. Plain, direct sentences. No emojis, no decorative symbols, no filler, no marketing tone. Comments explain why, not what.
- Python follows PEP 8, checked with ruff. Tests with pytest.

## Business rules that code must respect

- A ticket is redeemed once, in full, for all its people. No partial redemption, no re-entry.
- Online tickets are valid for the season they were bought in. The season end date is a setting, not a constant.
- The boleta for an online ticket is issued at redemption, for the total paid, payment method Webpay.
- QR content: only an opaque random code with prefix `VR1`, uppercase letters and digits only (scanner keyboard layouts can corrupt symbols). Store only its SHA-256 hash.
- Store the minimum personal data: buyer name and email.
- Free kids' entries are counted but not charged.
- The online redemptions get their own line in the daily cash close and do not add to expected cash.
