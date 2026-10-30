const token = window.location.pathname.split("/").filter(Boolean).pop();
const title = document.getElementById("previewTitle");

async function loadPreview() {
  if (!token || !/^[A-Za-z0-9_-]+$/.test(token)) {
    title.textContent = "This preview link is invalid.";
    return;
  }

  try {
    const response = await fetch(`/instructor-applications/${encodeURIComponent(token)}`);
    const application = await response.json();
    if (!response.ok) {
      throw new Error(typeof application.detail === "string" ? application.detail : "Preview unavailable.");
    }
    title.textContent = application.workshop_name;
    document.title = `${application.workshop_name} | Draft preview`;
    document.getElementById("previewDescription").textContent = application.description;
    document.getElementById("previewInstructor").textContent = `${application.instructor_name} · ${application.instructor_title}`;
    if (application.organization) {
      document.getElementById("previewOrganization").textContent = ` · ${application.organization}`;
    }
    const learningList = document.getElementById("previewLearning");
    application.learning_points.forEach((point) => {
      const item = document.createElement("li");
      item.textContent = point;
      learningList.append(item);
    });
  } catch (error) {
    title.textContent = error.message || "This preview could not be loaded.";
  }
}

loadPreview();
