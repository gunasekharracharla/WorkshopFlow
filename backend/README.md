# WorkshopFlow backend

FastAPI backend for the WorkshopFlow product overview, attendee registration,
server-verified Razorpay checkout, and admin dashboard. This release is
configured for one organization and one active workshop per deployment; it is
not yet a multi-tenant SaaS.

## Run locally

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
Set-Location backend
python -m uvicorn main:app --reload
```

Open the product overview at `http://127.0.0.1:8000/`, attendee page at
`http://127.0.0.1:8000/events/full-stack-web-development`, admin at
`http://127.0.0.1:8000/admin/`, or API docs at `http://127.0.0.1:8000/docs`.

## Configure before launch

Set real, verified branding and workshop values in the ignored `backend/.env`
or through the owner dashboard. Do not edit `.env.example` with customer data.
Configure Razorpay test credentials for local testing and live credentials only
for a production deployment.

Before collecting attendee information or payments, publish the organizer's
privacy notice and registration/refund terms, then set their HTTPS addresses in
`PRIVACY_POLICY_URL` and `REGISTRATION_TERMS_URL`. The organizer is responsible
for the accuracy and legal suitability of those policy pages.

The admin readiness report also requires production HTTPS, a persistent
database, configured payment verification, and owner confirmation that database
backups have been restore-tested and monitoring/alerts are configured. Set
`DATA_BACKUPS_VERIFIED=true` and `PRODUCTION_MONITORING_CONFIGURED=true` only
after completing those actions; the app does not independently verify them.
Document the manual reconciliation, cancellation, and refund workflow and set
`PAYMENT_OPERATIONS_REVIEWED=true` after it has been reviewed. Refunds are not
automated by this release. Production also requires a non-default admin
username and a unique password of at least 16 characters. Admin Basic
authentication must only be exposed over HTTPS; configure rate limiting at the
edge and set `ADMIN_RATE_LIMITING_CONFIGURED=true` only after it is active.

The public attendee page confirms successful payment and registration in the
browser. It does not send confirmation emails or joining instructions.
Configure an external automation/email provider if attendees must receive
messages, and verify delivery before launch.

## Payment and automation

The server determines the checkout amount and verifies payment status, amount,
currency, order, and signature before confirming a registration. Razorpay
credentials remain server-side. The INR payment path is implemented with
Razorpay.

Payment-success notifications and admin-triggered reminder/workflow events are
queued and delivered through the configured automation webhook. The app does
not itself schedule reminders or send email; those actions must be implemented
in the connected automation provider.

## Migrations and tests

Development SQLite tables are created automatically. For production, run
migrations against the production `DATABASE_URL` before starting the API:

```powershell
Set-Location backend
alembic upgrade head
```

Run the backend tests from the repository root:

```powershell
.\.venv\Scripts\python -m pytest backend -q
```
