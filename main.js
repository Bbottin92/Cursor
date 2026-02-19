document.addEventListener("DOMContentLoaded", () => {
  const store = window.LiquidGovStore;
  const participantCurrent = document.getElementById("participantCurrent");
  const openSignup = document.getElementById("openSignup");
  const signupDialog = document.getElementById("signupDialog");
  const signupForm = document.getElementById("signupForm");
  const signupResult = document.getElementById("signupResult");
  const closeSignup = document.getElementById("closeSignup");
  const implementedPreview = document.getElementById("implementedPreview");
  const archivedPreview = document.getElementById("archivedPreview");

  function updateCounter() {
    const accounts = store.getAccounts();
    participantCurrent.textContent = store.formatNumber(accounts.length);
  }

  function renderArchivePreview() {
    const proposals = store.getProposals();
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
          `<li><strong>${item.title}</strong> by ${item.author} · ${store.formatDate(item.submittedAt)}</li>`
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
  closeSignup.addEventListener("click", closeSignupDialog);

  signupForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(signupForm);
    const payload = {
      username: formData.get("username"),
      age: Number(formData.get("age")),
      parentLink: formData.get("parentLink"),
      wantsVerification: formData.get("wantsVerification") === "on",
      pledge: formData.get("pledge") === "on"
    };

    const result = store.createAccount(payload);
    signupResult.textContent = result.message;

    if (!result.ok) {
      return;
    }

    updateCounter();
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

  updateCounter();
  renderArchivePreview();
});
