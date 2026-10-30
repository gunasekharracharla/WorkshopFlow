# WorkshopFlow

WorkshopFlow is a configurable workshop registration and operations product with a FastAPI backend, Razorpay payments, and an admin dashboard. The product overview is served at `/`; the attendee-facing workshop page is separate at `/events/full-stack-web-development`.

## Sellable product summary

WorkshopFlow is currently delivered as a configured, single-organization deployment for trainers, coaches, educators, and learning businesses. It helps organizers publish a branded workshop page, collect registrations, verify Razorpay payments, track capacity, and connect external follow-up automations.

### What you are selling

This release is a configured implementation for one organization and one active workshop per deployment. It helps businesses:
- publish a professional workshop page after setup and content verification
- collect registrations and reduce manual admin effort
- accept online payments safely through Razorpay
- manage seat availability and workshop status
- connect reminder and follow-up workflows through an external automation service
- brand the experience to their own name, colors, and instructor identity

### Who buys it

- independent coaches and trainers
- bootcamps and learning studios
- community event organizers
- agencies building workshop funnels for clients
- educators selling paid masterclasses and training sessions

### Product offer

Offer this as a packaged solution:
- brand setup and workshop configuration
- registration and payment flow setup
- admin dashboard and participant management
- workshop analytics and export tools
- optional setup of an external automation/reminder provider
- deployment and production hardening
- support and maintenance plan

### Why it sells

Because it solves a real business problem: turning a workshop idea into a paid, organized, reliable event funnel without custom development. It gives customers a premium experience without the cost of building a full custom ticketing or course platform from scratch.

### Sales positioning

Position the product as:
- White-label workshop registration platform
- Branded event sales and booking system
- Training business checkout and automation system
- Event funnel for coaches and educators

Not as:
- a generic website builder
- a full enterprise event marketplace
- a universal ticketing platform

## Project structure

```text
full-stack-workshop/
├── backend/
│   ├── alembic/
│   ├── alembic.ini
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── payment.py
│   ├── requirements.txt
│   ├── schemas.py
│   ├── .env.example
│   ├── test_main.py
│   ├── test_registration.py
│   └── test_security_hardening.py
├── frontend/
│   ├── admin/
│   ├── app.js
│   ├── countries.js
│   ├── index.html
│   ├── product.html
│   ├── README.md
│   ├── portfolio.css
│   └── styles.css
├── scripts/
│   └── generate_countries.py
├── README.md
├── .gitignore
└── requirements.txt
```

## Installation

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
```

## Environment

Copy the sample environment file and configure your own values:

```bash
copy backend\.env.example backend\.env
```

Then fill in:

- Public brand and instructor values (`BRAND_NAME`, `BRAND_MARK`,
  `BRAND_ACCENT_COLOR`, `INSTRUCTOR_NAME`, `INSTRUCTOR_TITLE`,
  `INSTRUCTOR_BIO`, `INSTRUCTOR_EMAIL`)
- Public HTTPS policy pages (`PRIVACY_POLICY_URL`, `REGISTRATION_TERMS_URL`)
- Workshop defaults (`WORKSHOP_NAME`, `WORKSHOP_DATE`, `WORKSHOP_PRICE`,
  `MAX_SEATS`)
- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`
- `RAZORPAY_WEBHOOK_SECRET`
- `N8N_WEBHOOK_URL`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `DATABASE_URL`
- `FRONTEND_URLS` (comma-separated; production requires explicit HTTPS origins)
- `REGISTRATION_ROLES` (comma-separated role choices)
- `DATA_BACKUPS_VERIFIED` and `PRODUCTION_MONITORING_CONFIGURED` (set to `true`
  only after the actual backup/restore and monitoring setup has been verified)
- `PAYMENT_OPERATIONS_REVIEWED` (set to `true` only after documenting the
  reconciliation, cancellation, and refund process; refunds are not automated)
- `ADMIN_RATE_LIMITING_CONFIGURED` (set to `true` only after rate limiting for
  the admin API is enabled at the hosting edge)

Do not commit the real `.env` file.

## Product requirements and roadmap

The following requirements and architecture sections describe product goals.
They are not a claim that every listed feature exists in the current release.

### 1. Product overview

This product is a **white-label workshop registration system** built to help trainers, coaches, educators, and learning businesses sell seats to live events or workshops online. It combines a branded landing page, attendee registration flow, secure payment handling, admin controls, and backend automation into one installable system.

The current product is positioned as a focused B2B/B2C event-conversion tool, not as a full multi-tenant SaaS platform. It is ideal for one-client-at-a-time deployments and can be packaged as a client-ready implementation.

### 2. Problem statement

Many small training businesses still manage registration manually using disconnected tools:
- one landing page for event info
- one form for registration capture
- one payment method or manual bank transfer
- a spreadsheet for attendance tracking
- manual reminder messages and follow-ups

This creates operational friction, lost conversions, and inconsistent customer experience. The product solves this by providing a single branded workflow that turns interest into confirmed registrations and payments.

### 3. Product vision

To create a simple, trustworthy, and brandable workshop sales system that lets businesses:
- publish a polished event page
- accept real registrations
- accept secure payments
- control event status and pricing
- automate post-payment communications
- reduce manual admin work

### 4. Target market

Primary buyers:
- independent trainers and coaches
- bootcamp and workshop hosts
- academies and learning studios
- agency partners selling workshop setup
- corporate learning vendors and community educators

Primary use cases:
- paid workshop registration
- live cohort enrollment
- webinar or masterclass ticketing
- professional learning events
- digital product + workshop bundles

### 5. Target users

#### 5.1 Event owner / admin
Needs:
- edit workshop details quickly
- update pricing, date, capacity, and schedule
- control open/closed registration
- view payment and registration status
- manage branding and instructor information

#### 5.2 Attendee
Needs:
- understand the offer clearly
- register without friction
- know the price and schedule
- complete a trusted payment flow
- see payment/registration confirmation on screen and receive organizer instructions through the configured communication process

#### 5.3 Agency / implementation partner
Needs:
- white-label configuration per client
- simple deployment process
- secure environment handling
- low custom development effort

### 6. Product goals

- Make it easy to launch a workshop sales page in a few steps
- Reduce manual registration coordination and payment handling
- Make each installation look branded and premium
- Provide admin confidence with operational visibility
- Ensure secure payments and verified backend logic
- Support automation for follow-up workflows and reminders

### 7. Non-goals for the current MVP

The current scope does not include:
- multi-tenant SaaS platform architecture
- full marketplace or event marketplace features
- enterprise SSO and complex role hierarchies
- global multi-currency support by default
- advanced CRM integrations out of the box
- massive scale event ticketing
- full refund automation and dispute resolution

### 8. Functional requirements

#### 8.1 Public-facing workshop page
- Render a branded workshop landing page with title, description, schedule, and fee
- Display workshop availability and seat count
- Show instructor and brand details from configured settings
- Support a registration call-to-action and CTA navigation
- Show learning points and event summary clearly

#### 8.2 Registration flow
- Validate required attendee details: name, email, WhatsApp, role, experience
- Normalize and validate phone numbers
- Reject invalid or duplicate registrations per workshop
- Prevent registration when seats are full or closed
- Return a server-generated payment token for secure next-step flow

#### 8.3 Payment flow
- Backend determines final price; client never sets it directly
- Create Razorpay order server-side
- Verify order, payment, amount, and signature on backend
- Accept only valid captured or authorized payment status
- Prevent duplicate verification and repeated success processing
- Persist secure payment metadata and audit status

#### 8.4 Workshop and branding administration
- Update workshop name, date, time, venue/platform, price, and capacity
- Update registration status as open or closed
- Manage description and learning points
- Update brand name, colors, instructor information, and role choices
- Persist branding settings in the database and serve them through public config APIs
- Keep private meeting details hidden from public API responses

#### 8.5 Automation and communication
- Queue payment-success and reminder events in an outbox
- Support delivered and retried webhook events
- Generate email drafts for key templates
- Allow admin actions to trigger automation flows
- Provide a readiness checklist for deployment and production setup

Current scope: the application does not send email or WhatsApp messages itself.
Payment notifications and reminder/workflow requests depend on an external
automation endpoint; email drafts in the admin are not sent automatically.

#### 8.6 Admin reporting and monitoring
- View participant registrations
- View workshop stats and seat counts
- Review notification and automation status
- Review workshop change history
- View production readiness checks without exposing secrets

### 9. Non-functional requirements

#### 9.1 Security
- Store secrets server-side only
- Validate webhook signatures before processing any payment event
- Use HTTPS in production
- Use secure admin authentication with HTTP Basic over HTTPS only
- Never expose Razorpay secret or admin credentials to the browser
- Protect against duplicate payments and duplicate registrations

#### 9.2 Reliability
- Payment verification must be idempotent
- Outbox pattern should retry failed automation events
- Session and record updates must maintain data consistency
- Application must gracefully handle partial failures in automation delivery

#### 9.3 Performance
- Page loads should remain fast for a single workshop or small event volume
- Admin actions should be responsive for standard registration counts
- The app should support small-to-medium registrant volumes without major optimization work

#### 9.4 Scalability
- The architecture should support future multi-workshop and multi-client expansion
- Data model should allow a future move to multi-tenant onboarding and billing
- The public API and admin APIs should remain consistent as product scope grows

### 10. Business requirements

- The product must be attractive to small and mid-sized training businesses
- The configuration process must be simple enough for non-technical owners
- The product should feel premium and white-labeled for each buyer
- Setup should not require custom development for common use cases
- The solution should be packageable as a service offering and recurring support contract

### 11. Acceptance criteria

These are target acceptance criteria; the roadmap below distinguishes current
capabilities from work that remains.

#### MVP acceptance
- A user can view a branded workshop page and see price, date, and seat status
- A user can complete registration with valid inputs
- The user can pay online using Razorpay checkout
- The backend verifies payment before marking success
- Admin can update core workshop and branding settings
- Admin can inspect registrations and workshop stats
- The product warns when deployment configuration is incomplete
- Automation events are queued and retried safely when the external service is unavailable

#### Commercial acceptance
- A client can brand the product with their own identity and content
- A client can launch a workshop without custom code changes
- A partner can deploy the system in a secure production environment
- Support and maintenance can be sold as part of an implementation package

### 12. Product roadmap

#### Phase 1: MVP / sellable launch package
- Single-organization branding and workshop configuration
- Attendee registration and server-verified Razorpay INR payments
- Seat tracking and registration status controls
- Admin participant view, CSV export, and operational summary
- External automation webhook/outbox and email draft tools
- Production readiness checklist; hosting setup, policies, backup, monitoring,
  rate limiting, and payment operations still require deployment work

#### Phase 2: growth features
- richer analytics dashboard
- discount codes
- direct email/WhatsApp reminder delivery or a documented integration package
- multiple workshops per installation
- workshop templates and duplication

#### Phase 3: business platform
- multi-tenant support
- multiple client domains and brands
- role-based access control
- billing and subscription management
- custom data collection and CRM exports

### 13. Revenue and pricing model

Recommended model:
- one-time setup fee for branding and deployment
- monthly hosting and support fee
- optional per-workshop add-on package
- optional automation and integration support packages

This model is more practical than pure SaaS in the early stage because the onboarding and deployment effort is part of the product value.

### 14. Recommended positioning

The product should be sold as:
- white-label workshop registration system
- training business event funnel
- workshop booking platform for coaches and educators
- branded registration and payment automation for live learning events

It should not be positioned as a general event ticketing platform or a fully generalized SaaS marketplace.

### 15. Product summary

The current release is a focused, configurable single-organization product
implementation with workshop registration, verified Razorpay payment handling,
and admin tools. It is not production-ready until deployment-specific
configuration, policies, security controls, backup/restore, monitoring, and
payment/refund operations are completed. It is not multi-tenant SaaS.

## Future architecture blueprint (not implemented)

### 1. Product transformation

The current project is best viewed as the MVP of a broader workshop commerce platform. The objective is to evolve it from a single branded workshop app into a reusable software product that supports many customers, many events, and operational automation.

### 2. Sellable product definition

Product name direction: "WorkshopFlow", "EventLaunch", "CourseSeat", or similar

Core promise:
- help trainers and learning businesses sell seats to workshops quickly
- provide a branded sales page with low friction
- automate registrations, payments, and reminders
- reduce manual admin workload

### 3. Product modules

#### Public storefront module
- branded landing page
- event listing and detail pages
- schedule and pricing display
- CTA buttons, testimonials, FAQs
- booking and registration form

#### Registration & attendee management
- attendee profile capture
- role selection and validation
- duplicate protection
- seat availability management
- registration status tracking
- attendee export

#### Payment & revenue module
- Razorpay / Stripe support
- order creation and verification
- payment status tracking
- coupon support
- refund workflows
- revenue and conversion reporting

#### Admin & operations module
- event creation and editing
- event status control
- seat limits and pricing updates
- participant dashboard
- email and reminder triggers
- reporting and export tools

#### Automation & communication module
- payment success workflows
- reminder scheduling
- email and WhatsApp follow-ups
- webhook triggers to external systems
- retryable outbox event processing

#### Branding & tenant module
- per-customer branding
- custom domains
- instructor profiles
- color schemes and logo assets
- access control for admin users

### 4. Multi-tenant architecture

The product should evolve to a multi-tenant structure where each customer has:
- their own brand settings
- their own admin users and permissions
- their own workshop catalog
- their own attendee and payment data
- their own domains or custom URLs

Key entities:
- Tenant
- User
- Role
- Brand
- Workshop/Event
- Registration
- Payment
- Notification
- Audit Log
- Domain
- Billing Plan

### 5. Recommended technical architecture

#### Frontend
- React / Next.js for scalable admin and public experiences
- static or server-rendered public pages
- reusable component library for workshop pages

#### API layer
- FastAPI service for core business logic
- separate endpoints for public, admin, and automation flows
- versioned API structure for future growth

#### Data layer
- PostgreSQL for production
- SQLAlchemy ORM for app access
- Redis for job queues and caching
- object storage for uploaded assets and branding media

#### Background jobs
- Celery / RQ for reminder automation and email dispatch
- outbox pattern for event reliability
- retry queue with exponential backoff

#### Integrations
- Razorpay and Stripe (future readiness)
- SendGrid / Resend / Postmark
- Twilio / WhatsApp / messaging services
- webhooks to CRM and automation tools
- analytics providers

### 6. Security architecture

Required for real product deployment:
- tenant isolation at the database and API layer
- role-based access control (RBAC)
- HTTPS only in production
- secrets stored in environment variables or secret manager
- webhook signature verification
- payment verification strictly on backend
- rate limiting and payload validation
- audit logs for admin actions
- secure session management and token handling

### 7. Roadmap to full product maturity

#### Phase 1: Productize the MVP
- multiple workshop management per tenant
- attendee export to CSV
- payment and revenue summaries
- branding customizations and instructor fields
- reminder email automation
- admin analytics

#### Phase 2: Growth features
- discount codes and coupons
- multiple time slots / multiple sessions
- template-based workshop setup
- attendance tracking and check-in
- cohort management and group registrations

#### Phase 3: Scale to platform
- multi-tenant SaaS architecture
- billing and subscription management
- partner/customer onboarding
- support desk and admin role hierarchy
- advanced integrations and automation

#### Phase 4: Enterprise and expansion
- CRM integrations
- SSO and advanced permissions
- custom registration fields
- broader payment methods
- high-volume event operations and reporting

### 8. Pricing and packaging strategy

The best early pricing model is not pure SaaS subscription only. Use a hybrid merchant model:

- Setup/setup fee
- Monthly platform fee
- Workshop or event package fee
- Support and maintenance fee
- Automation add-on fee
- White-label customization fee

Example packages:
- Starter: single workshop, branding, setup, dashboard
- Growth: multiple workshops, analytics, automations
- Agency: multi-client management, partner dashboard
- Enterprise: advanced integrations, compliance, SLA

### 9. Sales positioning

Position the product as:
- white-label workshop registration and payment platform
- event sales engine for coaches and educators
- workshop booking platform for training businesses
- branded registration system for live learning experiences

Avoid positioning it as:
- a generic event marketplace
- a generic website builder
- a ticketing platform for all event use cases

### 10. Final product recommendation

This app can be sold today as a configured implementation for one organization at a time. It is not a self-service, multi-tenant SaaS: tenant isolation, customer accounts, subscription billing, and multi-workshop management are not implemented. Payment-success notifications and reminders require an external automation service; this app does not send email directly.

## Run backend

From the project root, start the backend from its directory:

```powershell
cd backend
python -m uvicorn main:app --reload
```

The app is available at:

- `http://127.0.0.1:8000/` — WorkshopFlow product overview
- `http://127.0.0.1:8000/events/full-stack-web-development` — attendee registration page
- `http://127.0.0.1:8000/admin/`
- `http://127.0.0.1:8000/docs`

Before accepting real registrations, configure a real workshop and organizer
profile, Razorpay live credentials, HTTPS policy URLs, a persistent database,
verified backups and restore procedures, production monitoring, and the
automation provider if attendee follow-ups are required. The admin readiness
checklist reports these items; backup and monitoring status are owner-confirmed
through environment settings, not independently verified by the app. Production
also requires a non-default admin username and a unique password of at least
16 characters. The admin API uses HTTP Basic authentication and must only be
exposed behind HTTPS; deploy rate limiting at the edge.
When `APP_ENV=production`, the app keeps public registration unavailable and
rejects new registrations/checkout until the required readiness checks pass.
Payment verification and provider webhooks stay available for already-created
payment attempts.
Successful checkout confirms the seat in the browser; it does not send an
attendee confirmation email or joining instructions. Configure and verify an
external communication provider if messages are part of the customer promise.

## Testing

```bash
pytest -v
```

## Production security

- Use HTTPS in production.
- Never commit `.env` files.
- Never expose the Razorpay secret to the browser.
- Never hardcode admin credentials.
- Rotate any payment or webhook keys that were used for local testing before
  handing the deployment to a client. Store production credentials only in the
  deployment environment or secret manager.
- Do not ship participant database files.
- Use database migrations for schema changes.

## Database behavior

The application creates a fresh SQLite development database automatically when needed. A committed sample database is not included in the source package. Production deployments should use a managed database and run migrations before serving traffic. Production startup does not create or alter the schema automatically.

## Payment flow

```text
Frontend -> POST /register -> Backend validates -> payment session token -> Create Razorpay order -> Checkout -> server-side Razorpay validation -> Mark SUCCESS -> durable n8n outbox
```

The backend always determines the amount. The browser never supplies `amount`, `currency`, or payment status. Payment sessions use opaque server-generated tokens, and the backend validates the Razorpay order, payment, amount, currency, and capture state before marking success.

## Admin authentication

Admin APIs require HTTP Basic auth using the environment variables `ADMIN_USERNAME` and `ADMIN_PASSWORD`. This must only be used over HTTPS in production.

## Security note

Admin authentication and Razorpay secret verification must be used over HTTPS in production. HTTP Basic Auth must never be exposed over unencrypted HTTP in production.

## n8n and webhook notes

- The n8n webhook is called only after payment verification succeeds.
- Payment success is not reversed if n8n is temporarily unavailable.
- Notification delivery is stored in an outbox and retried with exponential backoff.
- Webhook signatures are validated before processing payment events.
- Webhook event IDs are persisted and duplicate delivery is ignored transactionally.

## Local development

A fresh development database is created automatically when SQLite is used. The app does not delete a user's production database automatically.

## Migration support

The project includes an initial Alembic migration to represent the current schema. Run migrations with:

```bash
cd backend
alembic upgrade head
```

Run `alembic upgrade head` against the production `DATABASE_URL` before starting the API. The hardening migration preserves existing participant rows and converts legacy rupee amounts to integer paise in `amount_paise`. The branding-settings migration persists owner-edited brand and instructor details for the installation.
The latest migration renames the original workshop to the full-stack workshop and updates its registration references without deleting participant records.

For PostgreSQL, use a URL such as `postgresql+psycopg://user:password@host/database`.
