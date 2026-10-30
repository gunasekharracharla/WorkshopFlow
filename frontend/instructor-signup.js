const form = document.getElementById("instructorForm");
const statusNode = document.getElementById("formStatus");
const submitButton = document.getElementById("submitButton");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;

  const data = new FormData(form);
  const payload = {
    instructor_name: String(data.get("instructor_name")).trim(),
    instructor_title: String(data.get("instructor_title")).trim(),
    email: String(data.get("email")).trim(),
    organization: String(data.get("organization")).trim() || null,
    workshop_name: String(data.get("workshop_name")).trim(),
    description: String(data.get("description")).trim(),
    learning_points: String(data.get("learning_points")).split(/\r?\n/).map((point) => point.trim()).filter(Boolean),
    website: String(data.get("website")).trim()
  };

  statusNode.textContent = "Saving your application and preparing the preview...";
  submitButton.disabled = true;
  try {
    const response = await fetch("/instructor-applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) {
      const detail = result.detail;
      throw new Error(typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((item) => item.msg).join(" ") : "Could not save your application.");
    }
    if (typeof result.preview_url !== "string" || !/^\/instructor-preview\/[A-Za-z0-9_-]+$/.test(result.preview_url)) {
      throw new Error("The application was saved, but the preview link was not valid. Contact the site administrator.");
    }
    window.location.assign(result.preview_url);
  } catch (error) {
    statusNode.textContent = error.message || "Could not save your application. Please try again.";
    submitButton.disabled = false;
  }
});
