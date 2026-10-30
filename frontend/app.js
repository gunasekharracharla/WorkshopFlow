const API_BASE = window.WORKSHOP_API_BASE || (window.location.protocol === "file:" || window.location.port === "5500" ? "http://127.0.0.1:8000" : "");
let WORKSHOP_NAME = "WorkshopFlow Launch Workshop";
let BRAND_NAME = "WorkshopFlow";
let WORKSHOP_DATE = "Loading...";
let WORKSHOP_TIME = "Loading...";
let WORKSHOP_FEE = 0;
let WORKSHOP_FEE_TEXT = "Loading...";
let workshopConfigReady = false;
let currentParticipantId = null;
let currentPaymentToken = null;

const RAZORPAY_CHECKOUT_URL = "https://checkout.razorpay.com/v1/checkout.js";
let ALLOWED_ROLES = [
  "Backend Developer",
  "Frontend Developer",
  "Full-Stack Developer",
  "Web Designer",
  "Other",
  "Student/Fresher"
];

const form = document.getElementById("registrationForm");
const payButton = document.getElementById("payButton");
const statusBox = document.getElementById("status");
const successState = document.getElementById("successState");
const failureState = document.getElementById("failureState");
const cancelState = document.getElementById("cancelState");
const retryPaymentButton = document.getElementById("retryPaymentBtn");
const returnToPaymentButton = document.getElementById("returnToPaymentBtn");
const workshopReadout = document.getElementById("workshopReadout");
const workshopDateValue = document.getElementById("workshopDateValue");
const heroWorkshopDate = document.getElementById("heroWorkshopDate");
const heroDateValue = document.getElementById("heroDateValue");
const heroSeatsValue = document.getElementById("heroSeatsValue");
const successDate = document.getElementById("successDate");
const successParticipantId = document.getElementById("successParticipantId");
const successFee = document.getElementById("successFee");
const successParticipantName = document.getElementById("successParticipantName");
const successPaymentStatus = document.getElementById("successPaymentStatus");
const detailsWorkshopDate = document.getElementById("detailsWorkshopDate");
const detailsWorkshopFee = document.getElementById("detailsWorkshopFee");
const workshopDescription = document.getElementById("workshopDescription");
const workshopHeroDescription = document.getElementById("workshopHeroDescription");
const workshopMode = document.getElementById("workshopMode");
const learningPointsList = document.getElementById("learningPoints");
const valueBandFee = document.getElementById("valueBandFee");
const valueBandButtonFee = document.getElementById("valueBandButtonFee");
const heroFeeValue = document.getElementById("heroFeeValue");

function setWorkshopDetails() {
  const reads = document.querySelectorAll("[data-workshop-name]");
  reads.forEach((element) => {
    element.textContent = WORKSHOP_NAME;
  });

  if (workshopReadout) workshopReadout.textContent = WORKSHOP_NAME;
  if (workshopDateValue) workshopDateValue.textContent = WORKSHOP_DATE;
  if (heroWorkshopDate) heroWorkshopDate.textContent = WORKSHOP_DATE;
  if (successDate) successDate.textContent = WORKSHOP_DATE;
  if (detailsWorkshopDate) detailsWorkshopDate.textContent = WORKSHOP_DATE;
  document.querySelectorAll("[data-workshop-time]").forEach((node) => {
    node.textContent = WORKSHOP_TIME;
  });
  const feeNodes = document.querySelectorAll("#workshopFeeValue, #workshopFeeBadge");
  feeNodes.forEach((node) => {
    node.textContent = WORKSHOP_FEE_TEXT;
  });
  if (successFee) successFee.textContent = WORKSHOP_FEE_TEXT;
  if (detailsWorkshopFee) detailsWorkshopFee.textContent = WORKSHOP_FEE_TEXT;
  if (valueBandFee) valueBandFee.textContent = WORKSHOP_FEE_TEXT;
  if (valueBandButtonFee) valueBandButtonFee.textContent = WORKSHOP_FEE_TEXT;
  if (heroFeeValue) heroFeeValue.textContent = WORKSHOP_FEE_TEXT;
}

async function loadWorkshopConfig() {
  try {
    const config = await api("/workshop");
    WORKSHOP_NAME = config.name;
    document.title = `${BRAND_NAME} | ${WORKSHOP_NAME}`;
    WORKSHOP_DATE = config.date;
    WORKSHOP_TIME = config.time;
    WORKSHOP_FEE = config.price;
    WORKSHOP_FEE_TEXT = new Intl.NumberFormat("en-IN", { style: "currency", currency: config.currency, maximumFractionDigits: 0 }).format(config.price);
    workshopConfigReady = config.registration_open;
    const parsedDate = new Date(`${config.date}T00:00:00`);
    const displayDate = Number.isNaN(parsedDate.getTime())
      ? config.date
      : parsedDate.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
    if (heroDateValue) heroDateValue.textContent = `${displayDate} · ${config.time}`;
    if (heroSeatsValue) {
      heroSeatsValue.textContent = config.registration_open
        ? `${config.available_seats} of ${config.max_seats} available`
        : config.available_seats === 0
          ? "Fully booked"
          : "Registration closed";
    }
    const workshopInput = document.querySelector('input[name="workshop"]');
    if (workshopInput) workshopInput.value = WORKSHOP_NAME;
    if (workshopDescription && config.description) workshopDescription.textContent = config.description;
    if (workshopHeroDescription && config.description) workshopHeroDescription.textContent = config.description;
    if (workshopMode && config.mode) workshopMode.textContent = config.mode;
    if (learningPointsList && Array.isArray(config.learning_points) && config.learning_points.length) {
      learningPointsList.replaceChildren(...config.learning_points.map((point, index) => {
        const item = document.createElement("article");
        item.className = "build-item";
        const number = document.createElement("span");
        number.className = "build-index";
        number.textContent = String(index + 1).padStart(2, "0");
        const content = document.createElement("div");
        const heading = document.createElement("h3");
        heading.textContent = point;
        content.append(heading);
        const arrow = document.createElement("span");
        arrow.className = "build-arrow";
        arrow.setAttribute("aria-hidden", "true");
        arrow.textContent = "↗";
        item.append(number, content, arrow);
        return item;
      }));
    }
    setWorkshopDetails();
    updateButtonText(false);
    if (!config.registration_open) {
      setStatus(config.registration_message || "Registration is currently unavailable.", "error");
    }
  } catch (_) {
    workshopConfigReady = false;
    updateButtonText(false);
    setStatus("Workshop details could not be loaded. Please try again.", "error");
  }
}

async function loadPublicConfig() {
  try {
    const config = await api("/public-config");
    const siteName = String(config.brand_name || "").trim();
    const mark = String(config.brand_mark || "").trim();
    const instructorName = String(config.instructor_name || "").trim();
    const instructorTitle = String(config.instructor_title || "").trim();
    const instructorBio = String(config.instructor_bio || "").trim();
    const email = String(config.instructor_email || "").trim();
    const accent = String(config.brand_accent_color || "");
    const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) && !email.toLowerCase().endsWith("example.com");
    const roles = Array.isArray(config.registration_roles)
      ? [...new Set(config.registration_roles.map((role) => String(role).trim()).filter(Boolean))]
      : [];

    if (!siteName || !instructorName || !instructorTitle || !instructorBio || roles.length === 0) {
      throw new Error("Public site configuration is incomplete.");
    }
    if (!/^#[0-9a-f]{6}$/i.test(accent)) {
      throw new Error("Public brand accent color is invalid.");
    }

    BRAND_NAME = siteName;
    document.title = `${BRAND_NAME} | ${WORKSHOP_NAME}`;
    document.documentElement.style.setProperty("--purple", accent);
    document.querySelectorAll("[data-brand-name]").forEach((node) => {
      node.textContent = siteName;
    });
    document.querySelectorAll("[data-brand-mark]").forEach((node) => {
      node.textContent = mark || siteName.slice(0, 2).toUpperCase();
    });
    document.querySelectorAll("[data-instructor-name]").forEach((node) => {
      node.textContent = instructorName;
    });
    document.querySelectorAll("[data-instructor-title]").forEach((node) => {
      node.textContent = instructorTitle;
    });
    document.querySelectorAll("[data-instructor-bio]").forEach((node) => {
      node.textContent = instructorBio;
    });
    document.querySelectorAll("[data-instructor-email]").forEach((node) => {
      if (emailValid) {
        node.href = `mailto:${email}`;
        node.setAttribute("aria-label", `Email ${instructorName}`);
        node.hidden = false;
      } else {
        node.hidden = true;
      }
    });
    const policyLinks = [
      ["[data-privacy-url]", config.privacy_policy_url],
      ["[data-registration-terms-url]", config.registration_terms_url]
    ];
    let configuredPolicyCount = 0;
    policyLinks.forEach(([selector, value]) => {
      const link = document.querySelector(selector);
      if (!link || typeof value !== "string" || !value) return;
      const policyUrl = new URL(value, window.location.href);
      if (policyUrl.protocol === "https:" || policyUrl.protocol === "http:") {
        link.href = policyUrl.href;
        link.hidden = false;
        configuredPolicyCount += 1;
      }
    });
    const policyNotice = document.getElementById("policyNotice");
    if (policyNotice) policyNotice.hidden = configuredPolicyCount === policyLinks.length;
    const roleSelect = document.getElementById("role");
    if (roleSelect) {
      ALLOWED_ROLES = roles;
      roleSelect.replaceChildren(new Option("Select your role", ""));
      roles.forEach((role) => roleSelect.add(new Option(role, role)));
    }
  } catch (error) {
    console.error("Could not load public branding configuration.", error);
    const policyNotice = document.getElementById("policyNotice");
    if (policyNotice) {
      policyNotice.textContent = "Privacy and registration policy links could not be verified. Do not submit personal information until you can review them.";
      policyNotice.hidden = false;
    }
  }
}

const mobileMenuToggle = document.getElementById("mobileMenuToggle");
const mainNav = document.getElementById("mainNav");
mobileMenuToggle?.addEventListener("click", () => {
  const isOpen = mainNav.classList.toggle("is-open");
  mobileMenuToggle.setAttribute("aria-expanded", String(isOpen));
});
mainNav?.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", () => {
    mainNav.classList.remove("is-open");
    mobileMenuToggle?.setAttribute("aria-expanded", "false");
  });
});

function setStatus(message, type = "") {
  if (!statusBox) return;
  statusBox.textContent = message;
  statusBox.className = "status" + (message ? ` show ${type}` : "");
}

function hideStatePanels() {
  if (form) form.hidden = false;
  [successState, failureState, cancelState].forEach((panel) => {
    if (!panel) return;
    panel.hidden = true;
    panel.classList.add("hidden");
  });
}

function setPanelVisible(panel, visible) {
  if (!panel) return;
  panel.hidden = !visible;
  panel.classList.toggle("hidden", !visible);
}

/* ---------- Payment button state (consent gating + double-click protection) ---------- */
const termsCheckbox = document.getElementById("terms");
let isBusy = false;

function syncPayButton() {
  if (!payButton) return;
  payButton.disabled = isBusy || !workshopConfigReady || !(termsCheckbox && termsCheckbox.checked);
  payButton.classList.toggle("is-processing", isBusy);
}

function updateButtonText(processing = false) {
  if (!payButton) return;
  isBusy = processing;
  payButton.textContent = processing
    ? "Processing..."
    : workshopConfigReady
      ? `Secure My Seat — ${WORKSHOP_FEE_TEXT}`
      : "Registration unavailable";
  syncPayButton();
}

/* ---------- Inline field errors ---------- */
const FIELD_CONTROL_IDS = { name: "name", email: "email", country: "countryButton", whatsapp: "whatsapp", role: "role", experience: "experience", terms: "terms" };
const DUPLICATE_EMAIL_MESSAGE = "This email address is already registered for this workshop.";
const DUPLICATE_WHATSAPP_MESSAGE = "This WhatsApp number is already registered for this workshop.";

function setFieldError(field, message = "") {
  const errorNode = document.getElementById(`${field}Error`);
  const control = document.getElementById(FIELD_CONTROL_IDS[field] || field);
  if (errorNode) {
    errorNode.textContent = message;
    errorNode.hidden = !message;
  }
  if (control) {
    control.classList.toggle("is-invalid", Boolean(message));
    if (message) control.setAttribute("aria-invalid", "true");
    else control.removeAttribute("aria-invalid");
  }
  if (field === "whatsapp") document.getElementById("phoneInputWrap")?.classList.toggle("is-invalid", Boolean(message));
}

function clearAllFieldErrors() {
  Object.keys(FIELD_CONTROL_IDS).forEach((field) => setFieldError(field, ""));
}

function hasFieldError(field) {
  const errorNode = document.getElementById(`${field}Error`);
  return Boolean(errorNode && !errorNode.hidden);
}

function focusField(field) {
  const control = document.getElementById(FIELD_CONTROL_IDS[field] || field);
  if (!control) return;
  control.focus({ preventScroll: true });
  control.scrollIntoView?.({ block: "center", behavior: "smooth" });
}

/* ---------- Countries, flags and search ---------- */
const FALLBACK_COUNTRIES = [["IN", "India", "91", "[6-9]\\d{9}", "8123456789"]];
const DEFAULT_COUNTRY = "IN";
const COUNTRY_ALIASES = {
  US: "usa america", GB: "uk britain england scotland wales", AE: "uae emirates dubai", KR: "korea", KP: "korea",
  CZ: "czech", TR: "turkey", MM: "burma", CI: "ivory", CD: "congo drc", CG: "congo", NL: "holland", VA: "holy",
  TL: "east", SZ: "swaziland", CV: "cabo", RU: "russian", MO: "macao", VI: "usvi", PS: "palestinian", SA: "ksa"
};
const COUNTRIES_WITH_THE = new Set(["US", "GB", "AE", "NL", "PH", "BS", "GM", "CD", "CG", "CF", "KY", "FK", "MH", "SB", "TC", "VG", "VI", "CC", "CK", "FO", "MP"]);

function normalizeSearchText(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}

const COUNTRIES = (Array.isArray(window.WORKSHOP_COUNTRIES) && window.WORKSHOP_COUNTRIES.length ? window.WORKSHOP_COUNTRIES : FALLBACK_COUNTRIES)
  .map(([iso, name, dial, pattern, example]) => ({ iso, name, dial, pattern, example, key: normalizeSearchText(name), alias: COUNTRY_ALIASES[iso] || "" }));
const COUNTRY_BY_ISO = Object.fromEntries(COUNTRIES.map((country) => [country.iso, country]));
let selectedCountry = COUNTRY_BY_ISO[DEFAULT_COUNTRY] || COUNTRIES[0];
let flagEmojiSupported = true;

function flagEmoji(iso) {
  return String.fromCodePoint(...[...iso.toUpperCase()].map((char) => 127397 + char.charCodeAt(0)));
}

/* Windows desktop browsers cannot draw flag emoji (they show letters such as "IN"); detect that and use small flag images instead. */
function detectFlagEmojiSupport() {
  try {
    const canvas = document.createElement("canvas");
    canvas.width = 40;
    canvas.height = 32;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return true;
    ctx.textBaseline = "top";
    ctx.font = "26px sans-serif";
    ctx.fillText(flagEmoji("IN"), 0, 0);
    const pixels = ctx.getImageData(0, 0, 40, 32).data;
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i + 3] > 0 && (Math.abs(pixels[i] - pixels[i + 1]) > 20 || Math.abs(pixels[i + 1] - pixels[i + 2]) > 20)) return true;
    }
    return false;
  } catch (_) {
    return true;
  }
}

function createFlagNode(iso) {
  if (flagEmojiSupported) {
    const span = document.createElement("span");
    span.className = "flag";
    span.textContent = flagEmoji(iso);
    span.setAttribute("aria-hidden", "true");
    return span;
  }
  const img = document.createElement("img");
  const code = iso.toLowerCase();
  img.className = "flag-img";
  img.alt = "";
  img.width = 20;
  img.height = 15;
  img.loading = "lazy";
  img.src = `https://flagcdn.com/w20/${code}.png`;
  img.srcset = `https://flagcdn.com/w40/${code}.png 2x`;
  img.addEventListener("error", () => { img.style.visibility = "hidden"; });
  return img;
}

/* Numbers are checked against every country that shares the selected calling code (e.g. +1 = US, Canada, Caribbean; +44 = UK, Jersey, Guernsey, Isle of Man),
   because people in those places often pick the neighbouring country. Numbers from a different calling code are still rejected. */
const dialRegexCache = {};
function countryRegex(country) {
  if (!dialRegexCache[country.dial]) {
    const patterns = COUNTRIES.filter((item) => item.dial === country.dial && item.pattern).map((item) => item.pattern);
    try {
      dialRegexCache[country.dial] = new RegExp(`^(?:${patterns.join("|")})$`);
    } catch (_) {
      dialRegexCache[country.dial] = /^\d{4,14}$/;
    }
  }
  return dialRegexCache[country.dial];
}

function searchCountries(query) {
  const q = normalizeSearchText(query).replace(/^\+/, "");
  if (!q) return COUNTRIES;
  const numeric = /^\d+$/.test(q);
  const scored = [];
  COUNTRIES.forEach((country) => {
    const iso = country.iso.toLowerCase();
    const words = country.key.split(/[^a-z0-9]+/).filter(Boolean);
    const aliasWords = country.alias ? country.alias.split(" ") : [];
    let score = 0;
    if (iso === q) score = 100;
    else if (aliasWords.includes(q)) score = 95;
    else if (numeric && country.dial === q) score = 90;
    else if (country.key.startsWith(q)) score = 80;
    else if (words.some((word) => word.startsWith(q))) score = 70;
    else if (aliasWords.some((word) => word.startsWith(q))) score = 60;
    else if (numeric && country.dial.startsWith(q)) score = 55;
    else if (country.key.includes(q)) score = 40;
    if (score) scored.push([score, country]);
  });
  scored.sort((a, b) => b[0] - a[0]); // stable: ties keep the alphabetical order
  return scored.map((entry) => entry[1]);
}

/* ---------- WhatsApp number validation (country aware) ---------- */
const whatsappInput = document.getElementById("whatsapp");
const phoneCodeNode = document.getElementById("phoneCode");
let whatsappTouched = false;

/* Obvious artificial full numbers: all the same digit (1111111111) or a full ascending/descending run (1234567890, 9876543210). */
function isArtificialNumber(national) {
  if (national.length < 7) return false;
  if (/^(\d)\1+$/.test(national)) return true;
  let ascending = true;
  let descending = true;
  for (let i = 1; i < national.length; i += 1) {
    const step = (Number(national[i]) - Number(national[i - 1]) + 10) % 10;
    if (step !== 1) ascending = false;
    if (step !== 9) descending = false;
    if (!ascending && !descending) return false;
  }
  return true;
}

function whatsappErrorMessage(country) {
  return `Please enter a valid WhatsApp number for ${COUNTRIES_WITH_THE.has(country.iso) ? "the " : ""}${country.name}.`;
}

function checkWhatsapp(rawValue, country) {
  const raw = String(rawValue || "").trim();
  if (!raw) return { valid: false, empty: true };
  if (/[^\d\s\-().+]/.test(raw) || (raw.includes("+") && !raw.startsWith("+"))) return { valid: false };

  let digits = raw.replace(/\D/g, "");
  const international = raw.startsWith("+") || raw.startsWith("00");
  if (international) {
    digits = raw.startsWith("+") ? digits : digits.slice(2);
    if (!digits.startsWith(country.dial)) return { valid: false }; // the number belongs to a different country
    digits = digits.slice(country.dial.length);
  }
  const candidates = [digits, digits.replace(/^0/, "")];
  if (!international && digits.startsWith(country.dial)) {
    const withoutCode = digits.slice(country.dial.length);
    candidates.push(withoutCode, withoutCode.replace(/^0/, ""));
  }
  const matcher = countryRegex(country);
  const national = candidates.find((candidate) => candidate && matcher.test(candidate));
  if (!national || isArtificialNumber(national)) return { valid: false };
  return { valid: true, national, e164: `+${country.dial}${national}` };
}

function validateWhatsappField() {
  const result = checkWhatsapp(whatsappInput?.value, selectedCountry);
  if (result.valid) setFieldError("whatsapp", "");
  else setFieldError("whatsapp", result.empty ? "Please enter your WhatsApp number." : whatsappErrorMessage(selectedCountry));
  return result;
}

/* ---------- Country picker (searchable, keyboard accessible) ---------- */
const countryPicker = document.getElementById("countryPicker");
const countryHidden = document.getElementById("country");
const countryButton = document.getElementById("countryButton");
const countryButtonLabel = document.getElementById("countryButtonLabel");
const countryPanel = document.getElementById("countryPanel");
const countrySearch = document.getElementById("countrySearch");
const countryList = document.getElementById("countryList");
const countryEmpty = document.getElementById("countryEmpty");
let visibleCountries = [];
let activeCountryIndex = -1;

function updateCountryDisplay() {
  const country = selectedCountry;
  if (countryHidden) countryHidden.value = country.iso;
  if (countryButtonLabel) countryButtonLabel.replaceChildren(createFlagNode(country.iso), document.createTextNode(`${country.name} (+${country.dial})`));
  if (phoneCodeNode) phoneCodeNode.replaceChildren(createFlagNode(country.iso), document.createTextNode(`+${country.dial}`));
  if (whatsappInput) whatsappInput.placeholder = country.example || "";
}

function setActiveCountry(index, scroll = true) {
  const items = countryList ? countryList.children : [];
  if (items[activeCountryIndex]) items[activeCountryIndex].classList.remove("is-active");
  activeCountryIndex = index;
  const current = items[index];
  if (current) {
    current.classList.add("is-active");
    countrySearch?.setAttribute("aria-activedescendant", current.id);
    if (scroll) current.scrollIntoView?.({ block: "nearest" });
  } else {
    countrySearch?.removeAttribute("aria-activedescendant");
  }
}

function renderCountryList(query = "") {
  if (!countryList) return;
  visibleCountries = searchCountries(query);
  const fragment = document.createDocumentFragment();
  visibleCountries.forEach((country) => {
    const item = document.createElement("li");
    item.id = `country-option-${country.iso}`;
    item.dataset.iso = country.iso;
    item.setAttribute("role", "option");
    item.setAttribute("aria-selected", String(country.iso === selectedCountry.iso));
    item.append(createFlagNode(country.iso), document.createTextNode(`${country.name} (+${country.dial})`));
    fragment.appendChild(item);
  });
  countryList.replaceChildren(fragment);
  if (countryEmpty) countryEmpty.hidden = visibleCountries.length > 0;
  activeCountryIndex = -1;
  const start = query.trim() ? 0 : visibleCountries.findIndex((country) => country.iso === selectedCountry.iso);
  setActiveCountry(visibleCountries.length ? Math.max(0, start) : -1);
}

function openCountryPanel() {
  if (!countryPanel || !countryPanel.hidden) return;
  countryPanel.hidden = false;
  countryButton.setAttribute("aria-expanded", "true");
  countrySearch.value = "";
  renderCountryList("");
  countrySearch.focus({ preventScroll: true });
  countryPanel.scrollIntoView?.({ block: "nearest" });
}

function closeCountryPanel(returnFocus = false) {
  if (!countryPanel || countryPanel.hidden) return;
  countryPanel.hidden = true;
  countryButton.setAttribute("aria-expanded", "false");
  if (returnFocus) countryButton.focus({ preventScroll: true });
}

function selectCountry(iso, { focusPhone = false } = {}) {
  const country = COUNTRY_BY_ISO[iso];
  if (!country) return;
  selectedCountry = country;
  updateCountryDisplay();
  setFieldError("country", "");
  if (whatsappInput && whatsappInput.value.trim()) validateWhatsappField(); // re-check the number against the new country
  else if (hasFieldError("whatsapp")) setFieldError("whatsapp", "");
  closeCountryPanel(!focusPhone);
  if (focusPhone) whatsappInput?.focus({ preventScroll: true });
}

function initCountryPicker() {
  if (!countryPicker || !countryButton || !countryPanel || !countrySearch || !countryList) return;
  flagEmojiSupported = detectFlagEmojiSupport();
  updateCountryDisplay();

  countryButton.addEventListener("click", () => (countryPanel.hidden ? openCountryPanel() : closeCountryPanel(true)));
  countryButton.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      openCountryPanel();
    }
  });
  countrySearch.addEventListener("input", () => renderCountryList(countrySearch.value));
  countrySearch.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (visibleCountries.length) setActiveCountry(Math.min(activeCountryIndex + 1, visibleCountries.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (visibleCountries.length) setActiveCountry(Math.max(activeCountryIndex - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const country = visibleCountries[activeCountryIndex];
      if (country) selectCountry(country.iso, { focusPhone: true });
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeCountryPanel(true);
    } else if (event.key === "Tab") {
      closeCountryPanel(false);
    }
  });
  countryList.addEventListener("mousedown", (event) => event.preventDefault()); // keep focus in the search box
  countryList.addEventListener("click", (event) => {
    const item = event.target.closest("li[data-iso]");
    if (item) selectCountry(item.dataset.iso, { focusPhone: true });
  });
  document.addEventListener("pointerdown", (event) => {
    if (!countryPanel.hidden && !countryPicker.contains(event.target)) closeCountryPanel(false);
  });
}

/* ---------- Form validation ---------- */
function validateRegistrationForm() {
  const formData = new FormData(form);
  const errors = [];

  const name = String(formData.get("name") || "").trim();
  if (name.length < 2) errors.push(["name", "Please enter your full name."]);

  const email = String(formData.get("email") || "").trim().toLowerCase();
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.push(["email", "Please enter a valid email address."]);

  if (!selectedCountry) errors.push(["country", "Please select your country."]);

  const phone = checkWhatsapp(whatsappInput?.value, selectedCountry);
  if (!phone.valid) errors.push(["whatsapp", phone.empty ? "Please enter your WhatsApp number." : whatsappErrorMessage(selectedCountry)]);

  const role = String(formData.get("role") || "").trim();
  if (!ALLOWED_ROLES.includes(role)) errors.push(["role", "Please select your current role."]);

  const experience = String(formData.get("experience") || "").trim();
  if (experience && !/^\d{1,2}$/.test(experience)) errors.push(["experience", "Please select your years of experience."]);

  if (!termsCheckbox || !termsCheckbox.checked) errors.push(["terms", "Please confirm the registration terms before proceeding to payment."]);

  clearAllFieldErrors();
  errors.forEach(([field, message]) => setFieldError(field, message));
  if (errors.length) return { valid: false, firstField: errors[0][0] };

  const workshop = String(formData.get("workshop") || "").trim();
  if (workshop !== WORKSHOP_NAME) return { valid: false, globalMessage: "Workshop selection is invalid." };

  return { valid: true, payload: { name, email, whatsapp: phone.e164, role, experience, workshop: WORKSHOP_NAME } };
}

function initFormEnhancements() {
  termsCheckbox?.addEventListener("change", () => {
    if (termsCheckbox.checked) setFieldError("terms", "");
    syncPayButton();
  });
  document.getElementById("name")?.addEventListener("input", () => setFieldError("name", ""));
  document.getElementById("email")?.addEventListener("input", () => setFieldError("email", ""));
  document.getElementById("role")?.addEventListener("change", () => setFieldError("role", ""));
  document.getElementById("experience")?.addEventListener("change", () => setFieldError("experience", ""));

  whatsappInput?.addEventListener("input", () => {
    whatsappTouched = true;
    const cleaned = whatsappInput.value.replace(/[^\d\s\-().+]/g, "");
    if (cleaned !== whatsappInput.value) whatsappInput.value = cleaned;
    if (hasFieldError("whatsapp")) validateWhatsappField(); // only re-check while an error is showing, so it clears as soon as the number is valid
  });
  whatsappInput?.addEventListener("blur", () => {
    if (whatsappInput.value.trim() || whatsappTouched) validateWhatsappField();
  });

  form?.addEventListener("reset", () => {
    setTimeout(() => {
      selectedCountry = COUNTRY_BY_ISO[DEFAULT_COUNTRY] || COUNTRIES[0];
      whatsappTouched = false;
      updateCountryDisplay();
      closeCountryPanel(false);
      clearAllFieldErrors();
      syncPayButton();
    }, 0);
  });
  window.addEventListener("pageshow", syncPayButton); // browsers may restore a ticked checkbox on back/forward
}

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(API_BASE + path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options
    });
  } catch (_) {
    throw new ApiError("We couldn't reach the server. Please check your connection and try again.", 0, "");
  }

  let data = {};
  try {
    data = await response.json();
  } catch (_) {
    data = {};
  }

  if (!response.ok) {
    throw new ApiError(friendlyApiError(response.status, data.detail), response.status, data.detail);
  }

  return data;
}

function friendlyApiError(statusCode, detail = "") {
  const text = typeof detail === "string" ? detail : "";
  if (statusCode === 409) {
    if (/email address is already registered/i.test(text)) return DUPLICATE_EMAIL_MESSAGE;
    if (/whatsapp number is already registered/i.test(text)) return DUPLICATE_WHATSAPP_MESSAGE;
    return text.includes("already") ? "This registration is already confirmed." : "Registration is currently unavailable. Please try again.";
  }
  if (statusCode === 502) return "Payment setup is unavailable. Add valid Razorpay TEST MODE keys in backend/.env, then try again.";
  if (statusCode === 404) return "We couldn't find this registration. Please start again.";
  if (statusCode >= 500) return "We're having trouble completing this request. Please try again shortly.";
  if (/payment/i.test(text)) return "We couldn't complete the payment. Your registration is still saved.";
  return "Please check your details and try again.";
}

function showFormState() {
  if (form) form.hidden = false;
  setPanelVisible(successState, false);
  setPanelVisible(failureState, false);
  setPanelVisible(cancelState, false);
  setStatus("");
  updateButtonText(false);
}

function showSuccessState(participant) {
  if (form) form.hidden = true;
  setPanelVisible(successState, true);
  setPanelVisible(failureState, false);
  setPanelVisible(cancelState, false);
  if (successParticipantId) successParticipantId.textContent = String(participant.id);
  if (successParticipantName) successParticipantName.textContent = participant.name || "participant";
  if (successPaymentStatus) successPaymentStatus.textContent = participant.payment_status || "SUCCESS";
  if (successFee && participant.amount) successFee.textContent = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(participant.amount);
  setStatus("");
}

function showFailureState() {
  if (form) form.hidden = true;
  setPanelVisible(successState, false);
  setPanelVisible(failureState, true);
  setPanelVisible(cancelState, false);
  setStatus("");
}

function showCancelledState() {
  if (form) form.hidden = true;
  setPanelVisible(successState, false);
  setPanelVisible(failureState, false);
  setPanelVisible(cancelState, true);
  setStatus("");
}

retryPaymentButton?.addEventListener("click", () => {
  if (isBusy) return;
  if (currentParticipantId) {
    showFormState();
    startPayment(currentParticipantId, { payment_token: currentPaymentToken });
  } else {
    form.reset();
    showFormState();
  }
});

returnToPaymentButton?.addEventListener("click", () => {
  if (isBusy) return;
  if (currentParticipantId) {
    showFormState();
    startPayment(currentParticipantId, { payment_token: currentPaymentToken });
  } else {
    form.reset();
    showFormState();
  }
});

function ensureRazorpayLoaded() {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) {
      resolve();
      return;
    }

    const existingScript = document.querySelector(`script[src="${RAZORPAY_CHECKOUT_URL}"]`);
    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(), { once: true });
      existingScript.addEventListener("error", () => reject(new Error("Razorpay Checkout script failed to load.")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.src = RAZORPAY_CHECKOUT_URL;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Razorpay Checkout script failed to load."));
    document.head.appendChild(script);
  });
}

async function startPayment(participantId, participantDetails = {}) {
  updateButtonText(true);
  setStatus("Creating secure payment order...", "");
  try {
    const order = await api("/payment/create", {
      method: "POST",
      body: JSON.stringify({ participant_id: participantId, payment_token: participantDetails.payment_token })
    });

    await ensureRazorpayLoaded();
    if (!window.Razorpay) throw new Error("Razorpay Checkout did not load.");

    const razorpay = new Razorpay({
      key: order.key_id,
      amount: Number(order.amount) * 100,
      currency: order.currency,
      name: BRAND_NAME,
      description: WORKSHOP_NAME,
      order_id: order.razorpay_order_id,
      prefill: participantDetails,
      notes: { participant_id: String(participantId), workshop: WORKSHOP_NAME },
      theme: { color: getComputedStyle(document.documentElement).getPropertyValue("--purple").trim() || "#6b5bdd" },
      modal: { ondismiss: () => { showCancelledState(); updateButtonText(false); } },
      handler: async (response) => {
        try {
          setStatus("Payment received. Verifying payment securely...", "");
          const verified = await api("/payment/verify", { method: "POST", body: JSON.stringify(response) });
          showSuccessState(verified.participant);
          form.reset();
          currentParticipantId = null;
          currentPaymentToken = null;
        } catch (_) {
          showFailureState();
          setStatus("Payment could not be completed. Your registration is still saved.", "error");
        } finally {
          updateButtonText(false);
        }
      }
    });
    razorpay.on("payment.failed", () => {
      showFailureState();
      setStatus("Payment could not be completed. Your registration is still saved.", "error");
      updateButtonText(false);
    });
    razorpay.open();
  } catch (err) {
    setStatus(err.message || "Something went wrong. Please try again.", "error");
    updateButtonText(false);
  }
}

/* Show a registration API error next to the field it belongs to (duplicate email / WhatsApp, server-side validation). */
function handleRegistrationError(err) {
  const detail = err && err.detail;
  if (err && err.status === 409 && typeof detail === "string") {
    if (/email address is already registered/i.test(detail)) {
      setFieldError("email", DUPLICATE_EMAIL_MESSAGE);
      focusField("email");
      return;
    }
    if (/whatsapp number is already registered/i.test(detail)) {
      setFieldError("whatsapp", DUPLICATE_WHATSAPP_MESSAGE);
      focusField("whatsapp");
      return;
    }
  }
  if (err && err.status === 422 && Array.isArray(detail)) {
    const messages = {
      name: "Please enter your full name.",
      email: "Please enter a valid email address.",
      whatsapp: whatsappErrorMessage(selectedCountry),
      role: "Please select your current role.",
      experience: "Please select your years of experience."
    };
    let firstField = null;
    detail.forEach((item) => {
      const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : null;
      if (field && messages[field]) {
        setFieldError(field, messages[field]);
        firstField = firstField || field;
      }
    });
    if (firstField) {
      setStatus("");
      focusField(firstField);
      return;
    }
  }
  setStatus((err && err.message) || "Something went wrong. Please try again.", "error");
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (isBusy) return; // ignore double clicks / repeated submits while a request is running

  if (!workshopConfigReady) {
    setStatus("Workshop details are still loading or registration is closed.", "error");
    return;
  }

  const result = validateRegistrationForm();
  if (!result.valid) {
    setStatus(result.globalMessage || "", result.globalMessage ? "error" : "");
    if (result.firstField) focusField(result.firstField);
    return;
  }

  const payload = result.payload;

  updateButtonText(true);
  setStatus("Registering your details...", "");

  try {
    const participant = await api("/register", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    currentParticipantId = participant.id;
    currentPaymentToken = participant.payment_token;
    setStatus("");
    await startPayment(participant.id, { name: payload.name, email: payload.email, contact: payload.whatsapp, payment_token: participant.payment_token });
  } catch (err) {
    setStatus("");
    handleRegistrationError(err);
    updateButtonText(false);
  }
});

setWorkshopDetails();
initCountryPicker();
initFormEnhancements();
hideStatePanels();
updateButtonText(false);
loadWorkshopConfig();
loadPublicConfig();
