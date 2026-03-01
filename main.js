document.addEventListener("DOMContentLoaded", async () => {
  const data = window.LiquidGovData;
  await data.init();

  const participantCurrent = document.getElementById("participantCurrent");
  const openSignup = document.getElementById("openSignup");
  const openSignupSecondary = document.getElementById("openSignupSecondary");
  const signupDialog = document.getElementById("signupDialog");
  const signupForm = document.getElementById("signupForm");
  const signupResult = document.getElementById("signupResult");
  const closeSignup = document.getElementById("closeSignup");
  const implementedPreview = document.getElementById("implementedPreview");
  const archivedPreview = document.getElementById("archivedPreview");
  const publicAnnouncementsPreview = document.getElementById("publicAnnouncementsPreview");
  const joinLinks = Array.from(document.querySelectorAll("[data-open-signup='true']"));

  async function updateCounter() {
    const participantCount = await data.getParticipantCount();
    participantCurrent.textContent = data.formatNumber(participantCount);
  }

  async function renderArchivePreview() {
    const proposals = await data.getProposals();
    const implemented = proposals.filter((item) => item.status === "implemented").slice(0, 4);
    const archived = proposals.filter((item) => item.status === "archived").slice(0, 4);

    implementedPreview.innerHTML = implemented
      .map(
        (item) =>
          `<li><strong>${item.title}</strong> by ${item.author} · ${item.lawReference || "Pending law id"}</li>`
      )
      .join("");

    archivedPreview.innerHTML = archived
      .map(
        (item) =>
          `<li><strong>${item.title}</strong> by ${item.author} · ${data.formatDate(item.submittedAt)}</li>`
      )
      .join("");
  }

  async function renderAnnouncementPreview() {
    const announcements = (await data.getAnnouncements()).slice(0, 5);
    if (!announcements.length) {
      publicAnnouncementsPreview.innerHTML = "<li>No announcements published yet.</li>";
      return;
    }
    publicAnnouncementsPreview.innerHTML = announcements
      .map(
        (item) =>
          `<li><strong>${item.title}</strong> · ${item.author_name || item.author_username || "Unknown"}<br />${item.body}</li>`
      )
      .join("");
  }

  function openSignupDialog() {
    signupResult.textContent = "";
    if (typeof signupDialog.showModal === "function") {
      signupDialog.showModal();
      return;
    }
    signupDialog.setAttribute("open", "true");
  }

  function closeSignupDialog() {
    if (typeof signupDialog.close === "function") {
      signupDialog.close();
      return;
    }
    signupDialog.removeAttribute("open");
  }

  openSignup.addEventListener("click", openSignupDialog);
  if (openSignupSecondary) {
    openSignupSecondary.addEventListener("click", openSignupDialog);
  }
  joinLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      openSignupDialog();
    });
  });
  closeSignup.addEventListener("click", closeSignupDialog);

  signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(signupForm);
    const payload = {
      username: formData.get("username"),
      password: formData.get("password")
    };

    const result = await data.createAccount(payload);
    signupResult.textContent = result.message;

    if (!result.ok) {
      return;
    }

    await updateCounter();
    signupForm.reset();
    setTimeout(() => {
      closeSignupDialog();
      window.location.href = "app.html";
    }, 650);
  });

  signupDialog.addEventListener("click", (event) => {
    const dialogBounds = signupDialog.getBoundingClientRect();
    const clickedInDialog =
      dialogBounds.top <= event.clientY &&
      event.clientY <= dialogBounds.top + dialogBounds.height &&
      dialogBounds.left <= event.clientX &&
      event.clientX <= dialogBounds.left + dialogBounds.width;

    if (!clickedInDialog) {
      closeSignupDialog();
    }
  });

  await updateCounter();
  await renderArchivePreview();
  await renderAnnouncementPreview();

  if (window.location.hash === "#join") {
    openSignupDialog();
  }
});
