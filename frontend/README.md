# WorkshopFlow web app

This project is a white-label workshop registration platform built for coaches,
trainers, and learning businesses. It combines a polished landing page,
registration capture, secure payment verification, and admin controls in one
FastAPI-powered product.

## Run locally

From the project root, start FastAPI from the backend directory:

```powershell
cd backend
python -m uvicorn main:app --reload
```

Then open `http://127.0.0.1:8000/` for the WorkshopFlow product overview.
The attendee-facing workshop page is served at
`http://127.0.0.1:8000/events/full-stack-web-development`; `/events/ai-power-hour`
remains available as a legacy route. The admin dashboard is at `/admin/`.

## Personalize before publishing

Update the temporary profile and workshop content:

- Copy `backend/.env.example` to `backend/.env`; never edit the example file
  with customer values. Set verified brand and instructor details in the
  deployment's ignored `.env`.
- Configure the workshop name, schedule, fee, registration status, description,
  delivery mode, and learning points in the admin dashboard.
- Configure installation-specific brand and instructor details in `backend/.env`
  using the `BRAND_*` and `INSTRUCTOR_*` variables.
- Configure attendee role choices with `REGISTRATION_ROLES` in `backend/.env`.
- Publish the organizer's privacy notice and registration/refund terms, then
  configure their HTTPS URLs with `PRIVACY_POLICY_URL` and
  `REGISTRATION_TERMS_URL`.
- Set `DATA_BACKUPS_VERIFIED=true` only after a real database backup restore
  test, and `PRODUCTION_MONITORING_CONFIGURED=true` only after monitoring and
  alerts are live. These are owner confirmations, not automated checks.
- Document payment reconciliation, cancellations, and refunds; refunds are not
  automated. Set `PAYMENT_OPERATIONS_REVIEWED=true` only after the process is
  reviewed.
- Configure edge rate limiting for the admin API and set
  `ADMIN_RATE_LIMITING_CONFIGURED=true` only after it is active.

The attendee registration form loads its workshop details from `GET /workshop` and
continues through the server-verified Razorpay payment flow. The backend
validates the submitted role against the available registration options.
Public branding is loaded from `GET /public-config`; that response contains no
payment secrets. Only configured privacy and terms links are displayed.
The current Razorpay flow is configured for INR. Set `AUTOMATION_WEBHOOK_URL`
in the backend `.env` to connect n8n or another webhook-compatible automation
service. Payment-success events are sent automatically; admins can manually
initiate a workflow or schedule a 24-hour reminder from the dashboard. The
automation provider must schedule and send reminders; this app only generates
email drafts and does not send emails itself. After checkout, the page confirms
the verified payment and registration on screen; it does not send attendees a
confirmation email or meeting instructions.
When registration is closed, the public API supplies a safe attendee-facing
reason and the checkout action remains unavailable. The page also warns visitors
when privacy or registration policy links are missing.

The admin dashboard includes a secrets-free production readiness checklist.
It distinguishes unresolved required items from warning checks.
It blocks a "ready" result until organizer policies, production infrastructure,
backups, and monitoring are configured or owner-confirmed. Configure the
legal policy pages for the organizer's jurisdiction and actual refund process;
the application does not provide legal advice or invent a refund policy.
In `APP_ENV=production`, the public page reports registration unavailable and
the API blocks new registrations and checkout until all required readiness
checks pass. Existing payment verification and provider webhooks remain
available to finish and reconcile already-started payments.
Owners can update workshop, white-label branding, instructor, and registration
role settings; the latter are persisted in the configured database. Payment
provider keys, database URLs, webhook URLs, and admin credentials remain
server-side and must be configured in the hosting provider's environment or
secret manager.
