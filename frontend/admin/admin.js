let participants = [];
let automationEvents = [];
let dashboardConnected = false;
let adminAuthorization = "";
const API_BASE = window.WORKSHOP_API_BASE || (window.location.protocol === "file:" || window.location.port === "5500" ? "http://127.0.0.1:8000" : "");

const credentials = () => adminAuthorization || btoa(`${document.getElementById("username").value}:${document.getElementById("password").value}`);

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#039;"
}[character]));

const request = async (path, options = {}) => {
  const response = await fetch(API_BASE + path, {
    ...options,
    headers: {
      Authorization: `Basic ${credentials()}`,
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.detail;
    const message = typeof detail === "string"
      ? detail
      : Array.isArray(detail)
        ? detail.map((item) => item.msg || JSON.stringify(item)).join(", ")
        : detail
          ? JSON.stringify(detail)
          : "Admin request failed";
    throw new Error(message);
  }

  return response.json();
};

const normalizeToIndiaTime = (value) => {
  if (!value) return "—";
  const cleaned = String(value).trim();
  const iso = cleaned.includes("T") ? cleaned : cleaned.replace(" ", "T");
  const withTimezone = /[+-]\d{2}:\d{2}$/.test(iso) || iso.endsWith("Z") ? iso : `${iso}+05:30`;
  const date = new Date(withTimezone);
  if (Number.isNaN(date.getTime())) return cleaned;
  return date.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour12: true });
};

const render = () => {
  const search = document.getElementById("search").value.toLowerCase();
  const status = document.getElementById("statusFilter").value;
  const role = document.getElementById("roleFilter").value;
  const filtered = participants.filter((row) => (!search || `${row.name} ${row.email}`.toLowerCase().includes(search)) && (!status || row.payment_status === status) && (!role || row.role === role));

  if (!filtered.length) {
    document.getElementById("participants").innerHTML = `
      <tr class="empty-row">
        <td colspan="6">${participants.length ? "No registrations match the current filters." : "No registrations have been recorded for this workshop yet."}</td>
      </tr>
    `;
    document.getElementById("registrationCount").textContent = participants.length
      ? "No records match these filters"
      : "0 attendee records";
    return;
  }

  document.getElementById("participants").innerHTML = filtered.map((row) => {
    const registeredAt = normalizeToIndiaTime(row.registered_at);
    const paymentClass = row.payment_status === "SUCCESS" ? "status-success" : row.payment_status === "FAILED" ? "status-failed" : "status-pending";
    const actions = row.payment_status === "SUCCESS"
      ? `<div class="automation-actions">
          <button class="button button-dark" type="button" data-participant-action="initiate" data-participant-id="${escapeHtml(row.id)}">Start workflow</button>
          <button class="button button-outline" type="button" data-participant-action="reminder" data-participant-id="${escapeHtml(row.id)}">24h reminder</button>
          <button class="button button-outline" type="button" data-participant-action="draft" data-participant-id="${escapeHtml(row.id)}">Draft email</button>
        </div>`
      : `<span class="automation-help">Available after verified payment</span>`;
    return `
      <tr>
        <td><span class="participant-name">${escapeHtml(row.name)}</span><span class="participant-email">${escapeHtml(row.email)}</span><span class="participant-phone">${escapeHtml(row.whatsapp)}</span></td>
        <td>${escapeHtml(row.role)}</td>
        <td><span class="status-badge ${paymentClass}">${escapeHtml(row.payment_status)}</span></td>
        <td>₹${escapeHtml(row.amount)}</td>
        <td>${escapeHtml(registeredAt)}</td>
        <td>${actions}</td>
      </tr>
    `;
  }).join("");
  document.getElementById("registrationCount").textContent = `${filtered.length} of ${participants.length} attendee${participants.length === 1 ? "" : "s"}`;
};

const renderAutomationEvents = () => {
  const body = document.getElementById("automationEvents");
  if (!automationEvents.length) {
    body.innerHTML = `<tr class="empty-row"><td colspan="7">No automation events yet.</td></tr>`;
    return;
  }
  body.innerHTML = automationEvents.map((event) => {
    const sentAt = event.sent_at ? normalizeToIndiaTime(event.sent_at) : "—";
    const statusClass = event.status === "SENT" ? "status-success" : event.status === "FAILED" ? "status-failed" : "status-pending";
    const participant = participants.find((row) => String(row.id) === String(event.participant_id));
    const retry = event.status === "FAILED"
      ? `<button class="button button-outline" type="button" data-retry-event="${escapeHtml(event.id)}">Retry delivery</button>`
      : "—";
    return `<tr>
      <td>${escapeHtml(event.event_type)}</td>
      <td>${participant ? `${escapeHtml(participant.name)}<span class="participant-email">#${escapeHtml(event.participant_id)}</span>` : `Attendee #${escapeHtml(event.participant_id)}`}</td>
      <td><span class="status-badge ${statusClass}">${escapeHtml(event.status)}</span></td>
      <td>${escapeHtml(event.attempt_count)}</td>
      <td>${escapeHtml(event.last_error || "—")}</td>
      <td>${escapeHtml(sentAt)}</td>
      <td>${retry}</td>
    </tr>`;
  }).join("");
};

const loadAutomation = async () => {
  const [status, events] = await Promise.all([
    request("/admin/automation/status"),
    request("/admin/automation/events?limit=100")
  ]);
  automationEvents = events;
  const statusNode = document.getElementById("automationStatus");
  statusNode.textContent = status.webhook_configured
    ? `Automation webhook configured · ${status.pending} pending · ${status.failed} failed · ${status.sent} sent`
    : "Automation webhook is not configured. Set AUTOMATION_WEBHOOK_URL in the backend environment.";
  document.getElementById("automationSentCount").textContent = status.sent;
  document.getElementById("automationPendingCount").textContent = status.pending;
  document.getElementById("automationFailedCount").textContent = status.failed;
  document.getElementById("webhookDetail").textContent = status.webhook_configured ? "Configured" : "Needs setup";
  document.getElementById("webhookDetail").closest(".connection-row").classList.toggle("connected", status.webhook_configured);
  renderAutomationEvents();
};

const fillBrandingForm = (branding) => {
  document.getElementById("brandName").value = branding.brand_name || "";
  document.getElementById("brandMark").value = branding.brand_mark || "";
  document.getElementById("brandAccentColor").value = branding.brand_accent_color || "#6b5bdd";
  document.getElementById("brandColorValue").textContent = branding.brand_accent_color || "#6b5bdd";
  document.getElementById("instructorName").value = branding.instructor_name || "";
  document.getElementById("instructorTitle").value = branding.instructor_title || "";
  document.getElementById("instructorBio").value = branding.instructor_bio || "";
  document.getElementById("instructorEmail").value = branding.instructor_email || "";
  document.getElementById("registrationRoles").value = (branding.registration_roles || []).join("\n");
};

const renderReadiness = (readiness) => {
  const requiredRemaining = readiness.required_unresolved_count
    ?? readiness.checks.filter((check) => check.required && check.status !== "ready").length;
  const warningCount = readiness.warning_count
    ?? readiness.checks.filter((check) => check.status === "warning").length;
  const badge = document.getElementById("readinessBadge");
  badge.textContent = readiness.go_live_ready
    ? "Required checks complete"
    : `${requiredRemaining} required item${requiredRemaining === 1 ? "" : "s"} remaining`;
  badge.className = `status-badge ${readiness.go_live_ready ? "status-success" : "status-pending"}`;
  document.getElementById("readinessSummary").textContent = warningCount
    ? `${requiredRemaining} required item${requiredRemaining === 1 ? "" : "s"} need attention. ${warningCount} warning${warningCount === 1 ? "" : "s"} are also listed below.`
    : readiness.go_live_ready
      ? "All required production checks are ready."
      : `${requiredRemaining} required item${requiredRemaining === 1 ? "" : "s"} need attention before production registration can open.`;
  document.getElementById("readinessChecks").innerHTML = readiness.checks.map((check) => {
    const mark = check.status === "ready" ? "✓" : check.status === "warning" ? "!" : "×";
    return `<li class="readiness-item ${escapeHtml(check.status)}">
      <span class="readiness-mark" aria-hidden="true">${mark}</span>
      <span class="readiness-copy"><strong>${escapeHtml(check.label)}${check.required ? " · Required" : " · Optional"}</strong><small>${escapeHtml(check.detail)}</small></span>
    </li>`;
  }).join("");
};

const setLoadingState = (isLoading) => {
  const buttons = [
    document.getElementById("loadButton"),
    document.getElementById("refreshButton"),
    document.getElementById("exportButton"),
    document.getElementById("clearFiltersButton"),
    document.getElementById("refreshAutomationButton"),
    document.getElementById("saveWorkshopButton"),
    document.getElementById("saveBrandingButton"),
    document.getElementById("disconnectButton")
  ];

  buttons.forEach((button) => {
    if (button) {
      button.disabled = isLoading || !dashboardConnected ||
        (button.id === "exportButton" && !participants.length);
      if (button.id === "loadButton") button.disabled = isLoading;
    }
  });
  document.querySelectorAll("#workshopSettingsForm input, #workshopSettingsForm select, #workshopSettingsForm textarea")
    .forEach((field) => { field.disabled = isLoading || !dashboardConnected; });
  document.querySelectorAll("#brandingSettingsForm input, #brandingSettingsForm textarea")
    .forEach((field) => { field.disabled = isLoading || !dashboardConnected; });
  document.getElementById("brandAccentColor").disabled = isLoading || !dashboardConnected;
  document.getElementById("password").disabled = isLoading;
  document.getElementById("username").disabled = isLoading;
};

const updateLastUpdated = () => {
  const node = document.getElementById("lastUpdated");
  if (!node) return;
  node.textContent = `Last updated: ${new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true })}`;
};

const workshopForm = () => ({
  workshop_name: document.getElementById("workshopName").value,
  slug: document.getElementById("workshopSlug").value,
  workshop_date: document.getElementById("workshopDate").value,
  start_time: document.getElementById("startTime").value,
  end_time: document.getElementById("endTime").value,
  timezone: document.getElementById("workshopTimezone").value,
  price_paise: Number(document.getElementById("workshopPriceRupees").value) * 100,
  max_seats: Number(document.getElementById("maxSeats").value),
  registration_status: document.getElementById("registrationStatus").value,
  mode: document.getElementById("workshopMode").value,
  meeting_platform: document.getElementById("meetingPlatform").value || null,
  meeting_id: document.getElementById("meetingId").value || null,
  meeting_url: document.getElementById("meetingUrl").value || null,
  description: document.getElementById("workshopDescription").value,
  learning_points: document.getElementById("learningPoints").value.split("\n").map((value) => value.trim()).filter(Boolean)
});

const brandingForm = () => ({
  brand_name: document.getElementById("brandName").value,
  brand_mark: document.getElementById("brandMark").value,
  brand_accent_color: document.getElementById("brandAccentColor").value,
  instructor_name: document.getElementById("instructorName").value,
  instructor_title: document.getElementById("instructorTitle").value,
  instructor_bio: document.getElementById("instructorBio").value,
  instructor_email: document.getElementById("instructorEmail").value,
  registration_roles: document.getElementById("registrationRoles").value.split("\n").map((role) => role.trim()).filter(Boolean)
});

const fillWorkshopForm = (workshop) => {
  document.getElementById("workshopName").value = workshop.workshop_name || workshop.name || "";
  document.getElementById("workshopSlug").value = workshop.slug || "";
  const date = workshop.workshop_date || workshop.date || "";
  const toTimeInput = (value) => {
    const match = String(value || "").match(/^(\d{1,2}):(\d{2})\s*(AM|PM)?$/i);
    if (!match) return "";
    let hour = Number(match[1]);
    const minute = match[2];
    const meridiem = (match[3] || "").toUpperCase();
    if (meridiem === "PM" && hour < 12) hour += 12;
    if (meridiem === "AM" && hour === 12) hour = 0;
    return `${String(hour).padStart(2, "0")}:${minute}`;
  };
  document.getElementById("workshopDate").value = /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : "";
  document.getElementById("startTime").value = toTimeInput(workshop.start_time);
  document.getElementById("endTime").value = toTimeInput(workshop.end_time);
  document.getElementById("workshopTimezone").value = workshop.timezone || "Asia/Kolkata";
  document.getElementById("workshopPriceRupees").value = workshop.price_paise != null ? Number(workshop.price_paise) / 100 : Number(workshop.price || 0);
  document.getElementById("maxSeats").value = workshop.max_seats || "";
  document.getElementById("registrationStatus").value = workshop.registration_status || "REGISTRATION_OPEN";
  document.getElementById("workshopMode").value = workshop.mode || "";
  document.getElementById("meetingPlatform").value = workshop.meeting_platform || "";
  document.getElementById("meetingId").value = workshop.meeting_id || "";
  document.getElementById("meetingUrl").value = workshop.meeting_url || "";
  document.getElementById("workshopDescription").value = workshop.description || "";
  document.getElementById("learningPoints").value = (workshop.learning_points || []).join("\n");
};

const clearFilters = () => {
  document.getElementById("search").value = "";
  document.getElementById("statusFilter").value = "";
  document.getElementById("roleFilter").value = "";
  render();
};

const loadDashboard = async () => {
  const message = document.getElementById("message");
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;
  if (username && password) adminAuthorization = btoa(`${username}:${password}`);
  if (!adminAuthorization) {
    message.textContent = "Enter your admin username and password to connect.";
    document.getElementById("username").focus();
    return;
  }
  setLoadingState(true);
  message.textContent = "Connecting to your workshop...";

  try {
    const [summary, rows, workshop, adminWorkshop, branding, readiness] = await Promise.all([
      request("/admin/summary"),
      request("/participants"),
      request("/workshop"),
      request("/admin/workshop"),
      request("/admin/branding"),
      request("/admin/product/readiness")
    ]);

    participants = rows;
    fillWorkshopForm(adminWorkshop);
    fillBrandingForm(branding);
    dashboardConnected = true;
    const roles = [...new Set(participants.map((row) => row.role))].sort();
    document.getElementById("roleFilter").innerHTML = `<option value="">All roles</option>${roles.map((role) => `<option>${escapeHtml(role)}</option>`).join("")}`;
    const stats = document.getElementById("stats");
    const revenue = new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0
    }).format(summary.revenue || 0);
    stats.innerHTML = [
      ["Total registrations", summary.total_registrations, "All workshop sign-ups", "▤"],
      ["Payments received", summary.successful_payments, "Verified by the payment provider", "✓"],
      ["Pending payments", summary.pending_payments, "Awaiting payment confirmation", "◷"],
      ["Verified revenue", revenue, "Successful payments only", "₹"]
    ].map(([label, value, note, icon], index) => `
      <article class="stat-card${index === 0 ? " stat-highlight" : ""}">
        <div class="stat-label"><span>${label}</span><span class="stat-icon">${icon}</span></div>
        <strong>${escapeHtml(value)}</strong><small>${note}</small>
      </article>
    `).join("");
    document.getElementById("overviewWorkshopName").textContent = summary.workshop_name;
    const scheduleDate = new Date(`${adminWorkshop.date || adminWorkshop.workshop_date}T00:00:00`);
    const formattedDate = Number.isNaN(scheduleDate.getTime())
      ? (adminWorkshop.date || adminWorkshop.workshop_date || "Date not set")
      : scheduleDate.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
    document.getElementById("overviewWorkshopSchedule").textContent =
      `${formattedDate} · ${workshop.time || "Time not set"} · ${adminWorkshop.timezone || ""}`;
    document.getElementById("overviewWorkshopSeats").textContent =
      `${summary.available_seats} seats left · ${summary.successful_payments}/${summary.max_seats} paid`;
    const statusBadge = document.getElementById("workshopStatusBadge");
    statusBadge.textContent = String(summary.registration_status || "UNKNOWN").replaceAll("_", " ");
    statusBadge.className = `status-badge ${summary.registration_status === "REGISTRATION_OPEN" ? "status-success" : "status-neutral"}`;
    document.getElementById("dashboardTitle").textContent = "Good to have you here.";
    document.getElementById("apiStatus").className = "connection-pill connected";
    document.getElementById("apiStatus").innerHTML = '<span class="connection-dot"></span>Connected';
    document.getElementById("apiDetail").textContent = "Connected";
    document.getElementById("apiDetail").closest(".connection-row").classList.add("connected");
    document.getElementById("databaseDetail").textContent = "Connected";
    document.getElementById("databaseDetail").closest(".connection-row").classList.add("connected");
    document.getElementById("dataStatus").textContent = "All systems synced";
    document.getElementById("connectHelp").textContent = "Live attendee, payment and workshop data is connected to your backend.";
    document.getElementById("settingsLock").textContent = "Settings are editable";
    document.getElementById("brandingLock").textContent = "Brand profile is editable";
    document.getElementById("disconnectButton").hidden = false;
    document.getElementById("password").value = "";

    render();
    await loadAutomation();
    renderReadiness(readiness);
    updateLastUpdated();
    message.textContent = "";
  } catch (error) {
    if (!dashboardConnected) {
      adminAuthorization = "";
      document.getElementById("apiStatus").className = "connection-pill disconnected";
      document.getElementById("apiStatus").innerHTML = '<span class="connection-dot"></span>Connection failed';
      document.getElementById("apiDetail").textContent = "Connection failed";
      document.getElementById("dataStatus").textContent = "Unavailable";
      document.getElementById("readinessBadge").textContent = "Unable to check";
      document.getElementById("readinessSummary").textContent = "The launch checklist could not be loaded. Refresh to try again.";
    }
    message.textContent = error.message;
  } finally {
    setLoadingState(false);
    document.getElementById("exportButton").disabled = !dashboardConnected || !participants.length;
  }
};

document.getElementById("passwordToggle").addEventListener("click", () => {
  const passwordInput = document.getElementById("password");
  const toggle = document.getElementById("passwordToggle");
  const isHidden = passwordInput.type === "password";
  passwordInput.type = isHidden ? "text" : "password";
  toggle.textContent = isHidden ? "🙈" : "👁";
  toggle.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
});

document.getElementById("adminLoginForm").addEventListener("submit", (event) => {
  event.preventDefault();
  loadDashboard();
});
document.getElementById("refreshButton").addEventListener("click", loadDashboard);
document.getElementById("disconnectButton").addEventListener("click", () => {
  adminAuthorization = "";
  dashboardConnected = false;
  participants = [];
  automationEvents = [];
  document.getElementById("password").value = "";
  document.getElementById("username").value = "";
  document.getElementById("apiStatus").className = "connection-pill";
  document.getElementById("apiStatus").innerHTML = '<span class="connection-dot"></span>Not connected';
  document.getElementById("apiDetail").textContent = "Not connected";
  document.getElementById("databaseDetail").textContent = "Not connected";
  document.getElementById("webhookDetail").textContent = "Not checked";
  document.getElementById("dataStatus").textContent = "Waiting";
  document.getElementById("readinessBadge").textContent = "Connect to check";
  document.getElementById("readinessSummary").textContent = "Connect the dashboard to review required launch items and warnings.";
  document.getElementById("readinessChecks").innerHTML = '<li class="readiness-empty">Connect the dashboard to check production setup.</li>';
  document.getElementById("participants").innerHTML = '<tr class="empty-row"><td colspan="6">Connect to load registration records.</td></tr>';
  document.getElementById("automationEvents").innerHTML = '<tr class="empty-row"><td colspan="7">Connect to load delivery activity.</td></tr>';
  document.getElementById("registrationCount").textContent = "No records loaded";
  document.getElementById("message").textContent = "You are disconnected. Live attendee data has been cleared from this page.";
  document.getElementById("disconnectButton").hidden = true;
  document.getElementById("settingsLock").textContent = "Connect to edit";
  document.getElementById("brandingLock").textContent = "Connect to edit";
  setLoadingState(false);
});
document.getElementById("refreshAutomationButton").addEventListener("click", async () => {
  const message = document.getElementById("message");
  message.textContent = "Refreshing automation delivery log...";
  try {
    await loadAutomation();
    message.textContent = "";
  } catch (error) {
    message.textContent = error.message;
  }
});
document.getElementById("workshopSettingsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = document.getElementById("workshopMessage");
  message.textContent = "Saving...";
  try {
    await request("/admin/workshop", { method: "PUT", body: JSON.stringify(workshopForm()) });
    message.textContent = "Workshop settings saved.";
    await loadDashboard();
  } catch (error) {
    message.textContent = error.message;
  }
});
document.getElementById("brandingSettingsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = document.getElementById("brandingMessage");
  message.textContent = "Saving brand profile...";
  try {
    await request("/admin/branding", { method: "PUT", body: JSON.stringify(brandingForm()) });
    message.textContent = "Brand and instructor profile saved.";
    document.documentElement.style.setProperty("--purple", document.getElementById("brandAccentColor").value);
    await loadDashboard();
  } catch (error) {
    message.textContent = error.message;
  }
});
document.getElementById("clearFiltersButton").addEventListener("click", clearFilters);
document.getElementById("exportButton").addEventListener("click", () => {
  if (!participants.length) return;
  const headers = ["name", "email", "whatsapp", "role", "experience", "amount", "payment_status", "registered_at"];
  const csv = [headers.join(","), ...participants.map((row) => headers.map((key) => JSON.stringify(row[key] ?? "")).join(","))].join("\n");

  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  link.download = "workshop-participants.csv";
  link.click();
  URL.revokeObjectURL(link.href);
});

const emailDraftDialog = document.getElementById("emailDraftDialog");
let emailDraftParticipantId = null;

const loadEmailDraft = async () => {
  if (!emailDraftParticipantId) return;
  const template = document.getElementById("emailTemplate").value;
  const draft = await request(
    `/admin/participants/${encodeURIComponent(emailDraftParticipantId)}/email-draft?template=${encodeURIComponent(template)}`,
    { method: "POST" }
  );
  document.getElementById("emailDraftTo").textContent = `To: ${draft.to} · Draft only; not sent`;
  document.getElementById("emailSubject").value = draft.subject;
  document.getElementById("emailBody").value = draft.body;
};

document.getElementById("participants").addEventListener("click", async (event) => {
  const actionButton = event.target.closest("[data-participant-action]");
  if (!actionButton) return;
  const participantId = actionButton.dataset.participantId;
  const action = actionButton.dataset.participantAction;
  if (action === "draft") {
    emailDraftParticipantId = participantId;
    document.getElementById("emailSubject").value = "";
    document.getElementById("emailBody").value = "Generating draft...";
    emailDraftDialog.showModal();
    try {
      await loadEmailDraft();
    } catch (error) {
      document.getElementById("emailBody").value = error.message;
    }
    return;
  }

  const message = document.getElementById("message");
  actionButton.disabled = true;
  try {
    const path = action === "reminder"
      ? `/admin/participants/${encodeURIComponent(participantId)}/reminder/schedule`
      : `/admin/participants/${encodeURIComponent(participantId)}/automation/initiate`;
    const result = await request(path, { method: "POST" });
    message.textContent = `${result.event_type} event: ${result.status.toLowerCase()}.`;
    await loadAutomation();
  } catch (error) {
    message.textContent = error.message;
    try {
      await loadAutomation();
    } catch (refreshError) {
      message.textContent = `${error.message} Delivery log refresh failed: ${refreshError.message}`;
    }
  } finally {
    actionButton.disabled = false;
  }
});

document.getElementById("automationEvents").addEventListener("click", async (event) => {
  const retryButton = event.target.closest("[data-retry-event]");
  if (!retryButton) return;
  retryButton.disabled = true;
  const message = document.getElementById("message");
  try {
    const result = await request(`/admin/automation/events/${encodeURIComponent(retryButton.dataset.retryEvent)}/retry`, { method: "POST" });
    message.textContent = `Automation event ${result.status.toLowerCase()}.`;
    await loadAutomation();
  } catch (error) {
    message.textContent = error.message;
    try {
      await loadAutomation();
    } catch (refreshError) {
      message.textContent = `${error.message} Delivery log refresh failed: ${refreshError.message}`;
    }
  } finally {
    retryButton.disabled = false;
  }
});

document.getElementById("emailTemplate").addEventListener("change", async () => {
  try {
    await loadEmailDraft();
  } catch (error) {
    document.getElementById("emailBody").value = error.message;
  }
});
document.getElementById("brandAccentColor").addEventListener("input", (event) => {
  document.getElementById("brandColorValue").textContent = event.target.value;
});
const closeEmailDraft = () => emailDraftDialog.close();
document.getElementById("closeEmailDraftButton").addEventListener("click", closeEmailDraft);
document.getElementById("closeEmailDraftFooter").addEventListener("click", closeEmailDraft);
document.getElementById("copyEmailDraftButton").addEventListener("click", async () => {
  const message = `${document.getElementById("emailSubject").value}\n\n${document.getElementById("emailBody").value}`;
  try {
    await navigator.clipboard.writeText(message);
    document.getElementById("message").textContent = "Email draft copied to clipboard. It has not been sent.";
  } catch (error) {
    document.getElementById("message").textContent = `Could not copy draft: ${error.message}`;
  }
});

document.querySelectorAll("#search, #statusFilter, #roleFilter").forEach((control) => control.addEventListener("input", render));

window.addEventListener("DOMContentLoaded", () => {
  setLoadingState(false);
});

document.querySelectorAll(".side-nav .nav-link").forEach((link) => {
  link.addEventListener("click", () => {
    document.querySelectorAll(".side-nav .nav-link").forEach((item) => item.classList.remove("active"));
    link.classList.add("active");
  });
});
