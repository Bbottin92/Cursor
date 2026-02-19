document.addEventListener("DOMContentLoaded", () => {
  const store = window.LiquidGovStore;

  const scopes = {
    Neighborhood: {
      summary: "Hyper-local issues, nearby resources, and street-level collaboration.",
      pins: ["Community watchboard", "Local trade exchange", "Shared tools hub"]
    },
    Town: {
      summary: "Townwide proposals, school board notes, and civic priorities.",
      pins: ["Town hall livestream", "Civic signal trends", "Emergency resource map"]
    },
    State: {
      summary: "Statewide policy clusters, chapter growth, and regional events.",
      pins: ["Chapter growth heatmap", "State proposal ranking", "Volunteer network"]
    },
    National: {
      summary: "National policy discussion, transparency scorecards, and assembly planning.",
      pins: ["National launch metrics", "Founding assembly agenda", "Constitution drafts"]
    },
    International: {
      summary: "Global observer channels and cooperative civics experimentation.",
      pins: ["Sister movement hubs", "Global dialogue circles", "Translation commons"]
    }
  };

  let activeScope = "Neighborhood";
  let activeUsername = null;

  const currentUsername = document.getElementById("currentUsername");
  const currentBadge = document.getElementById("currentBadge");
  const avatarInitial = document.getElementById("avatarInitial");
  const profileVerifiedCounter = document.getElementById("profileVerifiedCounter");
  const participantsCount = document.getElementById("participantsCount");
  const verifiedCount = document.getElementById("verifiedCount");
  const accountSwitcher = document.getElementById("accountSwitcher");
  const useAccountBtn = document.getElementById("useAccountBtn");
  const logoutBtn = document.getElementById("logoutBtn");
  const scopeChips = document.getElementById("scopeChips");
  const scopeName = document.getElementById("scopeName");
  const scopeSummary = document.getElementById("scopeSummary");
  const scopePins = document.getElementById("scopePins");
  const mapTitle = document.getElementById("mapTitle");
  const profileDirectory = document.getElementById("profileDirectory");
  const visitProfileBtn = document.getElementById("visitProfileBtn");
  const visitorLogBody = document.getElementById("visitorLogBody");
  const notificationsBody = document.getElementById("notificationsBody");
  const proposalForm = document.getElementById("proposalForm");
  const painPointInput = document.getElementById("painPointInput");
  const solutionInput = document.getElementById("solutionInput");
  const proposalCategory = document.getElementById("proposalCategory");
  const proposalResult = document.getElementById("proposalResult");
  const archiveTableBody = document.getElementById("archiveTableBody");
  const groupInput = document.getElementById("groupInput");
  const groupSendBtn = document.getElementById("groupSendBtn");
  const groupStream = document.getElementById("groupStream");
  const dmRecipient = document.getElementById("dmRecipient");
  const dmInput = document.getElementById("dmInput");
  const dmResult = document.getElementById("dmResult");
  const audioNoteInput = document.getElementById("audioNoteInput");
  const dmSendBtn = document.getElementById("dmSendBtn");
  const audioSendBtn = document.getElementById("audioSendBtn");
  const startVideoBtn = document.getElementById("startVideoBtn");
  const startGroupVideoBtn = document.getElementById("startGroupVideoBtn");
  const profileHtmlInput = document.getElementById("profileHtmlInput");
  const profilePreview = document.getElementById("profilePreview");
  const renderProfileBtn = document.getElementById("renderProfileBtn");
  const inspectBtn = document.getElementById("inspectBtn");
  const childInspectName = document.getElementById("childInspectName");
  const inspectArea = document.getElementById("inspectArea");
  const inspectResult = document.getElementById("inspectResult");
  const approveChildName = document.getElementById("approveChildName");
  const approveAdultName = document.getElementById("approveAdultName");
  const approveContactBtn = document.getElementById("approveContactBtn");
  const approveResult = document.getElementById("approveResult");

  const groupMessages = [
    "System: Welcome to the group channel.",
    "System: Keep discussion constructive and solution-focused."
  ];

  function getAccounts() {
    return store.getAccounts();
  }

  function findAccount(username) {
    const accounts = getAccounts();
    return accounts.find(
      (item) => item.username.toLowerCase() === String(username || "").toLowerCase()
    );
  }

  function refreshMetrics() {
    const accounts = getAccounts();
    const verifiedTotal = accounts.filter((item) => item.isVerifiedPatriot).length;
    participantsCount.textContent = store.formatNumber(accounts.length);
    verifiedCount.textContent = store.formatNumber(verifiedTotal);
    profileVerifiedCounter.textContent = store.formatNumber(verifiedTotal);
  }

  function renderAccountSelectors() {
    const accounts = getAccounts();
    const options = accounts.length
      ? accounts
          .map((item) => {
            const tag = item.isVerifiedPatriot ? "Verified Patriot" : "Participant";
            return `<option value="${item.username}">${item.username} (${tag})</option>`;
          })
          .join("")
      : '<option value="">No accounts yet</option>';

    accountSwitcher.innerHTML = options;
    profileDirectory.innerHTML = options;
  }

  function setActiveUser(username) {
    if (!username) {
      activeUsername = null;
      currentUsername.textContent = "Guest";
      currentBadge.textContent = "Participant";
      avatarInitial.textContent = "G";
      visitorLogBody.innerHTML = '<tr><td colspan="2">Sign in to view logs.</td></tr>';
      notificationsBody.innerHTML = '<tr><td colspan="2">Sign in to view notifications.</td></tr>';
      return;
    }

    const account = findAccount(username);
    if (!account) {
      setActiveUser(null);
      return;
    }

    activeUsername = account.username;
    store.setCurrentUser(account.username);
    currentUsername.textContent = account.username;
    avatarInitial.textContent = account.username.slice(0, 1).toUpperCase();

    if (account.isVerifiedPatriot && account.role === "minor") {
      currentBadge.textContent = "Verified Patriot (Minor)";
    } else if (account.isVerifiedPatriot) {
      currentBadge.textContent = "Verified Patriot";
    } else {
      currentBadge.textContent = "Participant";
    }

    renderVisitorLog();
    renderNotifications();
  }

  function renderScopes() {
    const keys = Object.keys(scopes);
    scopeChips.innerHTML = keys
      .map((name) => {
        const activeClass = name === activeScope ? "chip active" : "chip";
        return `<button type="button" class="${activeClass}" data-scope="${name}">${name}</button>`;
      })
      .join("");

    scopeChips.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        activeScope = button.dataset.scope;
        renderScopes();
        renderScopePanel();
      });
    });
  }

  function renderScopePanel() {
    const scope = scopes[activeScope];
    mapTitle.textContent = `${activeScope} Scope Map`;
    scopeName.textContent = activeScope;
    scopeSummary.textContent = scope.summary;
    scopePins.innerHTML = scope.pins.map((item) => `<li>${item}</li>`).join("");
  }

  function renderArchive() {
    const proposals = store
      .getProposals()
      .slice()
      .sort((a, b) => new Date(b.submittedAt) - new Date(a.submittedAt));

    archiveTableBody.innerHTML = proposals
      .map((item) => {
        const statusClass =
          item.status === "implemented"
            ? "status-implemented"
            : item.status === "archived"
              ? "status-archived"
              : "status-under-review";
        const statusLabel =
          item.status === "implemented" ? "Implemented" : item.status === "archived" ? "Archived" : "Under Review";
        return `
          <tr>
            <td>${store.formatDate(item.submittedAt)}</td>
            <td>${item.author}</td>
            <td>${item.title}</td>
            <td><span class="status-tag ${statusClass}">${statusLabel}</span></td>
            <td>${item.lawReference || "-"}</td>
          </tr>
        `;
      })
      .join("");
  }

  function renderVisitorLog() {
    if (!activeUsername) {
      return;
    }
    const visitors = store.getProfileVisitors(activeUsername);
    if (!visitors.length) {
      visitorLogBody.innerHTML = "<tr><td colspan='2'>No profile visitors logged yet.</td></tr>";
      return;
    }
    visitorLogBody.innerHTML = visitors
      .slice(0, 12)
      .map(
        (entry) =>
          `<tr><td>${entry.visitor}</td><td>${store.formatDate(entry.visitedAt)}</td></tr>`
      )
      .join("");
  }

  function renderNotifications() {
    if (!activeUsername) {
      return;
    }
    const notes = store.getNotifications(activeUsername);
    if (!notes.length) {
      notificationsBody.innerHTML =
        "<tr><td colspan='2'>No notifications yet for this account.</td></tr>";
      return;
    }
    notificationsBody.innerHTML = notes
      .slice(0, 15)
      .map(
        (entry) =>
          `<tr><td>${store.formatDate(entry.createdAt)}</td><td>${entry.message}</td></tr>`
      )
      .join("");
  }

  function renderGroupStream() {
    groupStream.innerHTML = groupMessages.map((item) => `<li>${item}</li>`).join("");
  }

  function renderProfileTheme() {
    const html = profileHtmlInput.value || "";
    const frame = `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8" />
        <style>
          body { margin: 0; font-family: Arial, sans-serif; color: #ecf1ff; background: #1a2240; padding: 0.8rem; }
          a { color: #57d5ff; }
        </style>
      </head>
      <body>
        ${html}
      </body>
      </html>
    `;
    profilePreview.srcdoc = frame;
  }

  proposalForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!activeUsername) {
      proposalResult.textContent = "Select an account first.";
      return;
    }
    const painPoint = painPointInput.value.trim();
    const solution = solutionInput.value.trim();
    const category = proposalCategory.value;
    if (!painPoint || !solution) {
      proposalResult.textContent = "Please provide both pain point and solution.";
      return;
    }

    const combinedTitle = `${painPoint.slice(0, 58)} -> ${solution.slice(0, 58)}`;
    store.addProposal({
      title: combinedTitle,
      category,
      author: activeUsername,
      status: "under_review"
    });
    proposalResult.textContent = "Proposal submitted to archive with author credit.";
    painPointInput.value = "";
    solutionInput.value = "";
    renderArchive();
  });

  dmSendBtn.addEventListener("click", () => {
    dmResult.textContent = "";
    if (!activeUsername || !dmInput.value.trim()) {
      return;
    }
    const recipient = dmRecipient.value.trim();
    if (!recipient) {
      dmResult.textContent = "Add a recipient username.";
      return;
    }
    const permission = store.canInteract(activeUsername, recipient);
    if (!permission.ok) {
      dmResult.textContent = permission.reason;
      return;
    }

    store.addNotification(
      activeUsername,
      `DM sent to ${recipient}: "${dmInput.value.trim().slice(0, 60)}"`,
      "info"
    );
    store.addNotification(
      recipient,
      `DM received from ${activeUsername}: "${dmInput.value.trim().slice(0, 60)}"`,
      "info"
    );
    dmInput.value = "";
    dmResult.textContent = "Message delivered.";
    renderNotifications();
  });

  audioSendBtn.addEventListener("click", () => {
    if (!activeUsername || !audioNoteInput.value.trim()) {
      return;
    }
    store.addNotification(activeUsername, "Audio message submitted.", "info");
    audioNoteInput.value = "";
    renderNotifications();
  });

  startVideoBtn.addEventListener("click", () => {
    if (!activeUsername) {
      return;
    }
    store.addNotification(activeUsername, "1:1 video room token generated.", "info");
    renderNotifications();
  });

  startGroupVideoBtn.addEventListener("click", () => {
    if (!activeUsername) {
      return;
    }
    store.addNotification(activeUsername, "Group video room opened.", "info");
    renderNotifications();
  });

  groupSendBtn.addEventListener("click", () => {
    if (!activeUsername || !groupInput.value.trim()) {
      return;
    }
    groupMessages.unshift(`${activeUsername}: ${groupInput.value.trim()}`);
    groupInput.value = "";
    renderGroupStream();
  });

  renderProfileBtn.addEventListener("click", renderProfileTheme);

  useAccountBtn.addEventListener("click", () => {
    const selected = accountSwitcher.value;
    if (!selected) {
      return;
    }
    setActiveUser(selected);
    renderAccountSelectors();
  });

  logoutBtn.addEventListener("click", () => {
    store.setCurrentUser(null);
    setActiveUser(null);
  });

  visitProfileBtn.addEventListener("click", () => {
    if (!activeUsername) {
      return;
    }
    const target = profileDirectory.value;
    if (!target || target === activeUsername) {
      return;
    }
    store.recordProfileVisit(target, activeUsername);
    store.addNotification(target, `${activeUsername} viewed your profile.`, "notice");
    renderVisitorLog();
    renderNotifications();
  });

  inspectBtn.addEventListener("click", () => {
    inspectResult.textContent = "";
    if (!activeUsername) {
      inspectResult.textContent = "Sign in as the guardian account first.";
      return;
    }
    const child = childInspectName.value.trim();
    if (!child) {
      inspectResult.textContent = "Provide child username.";
      return;
    }
    const result = store.inspectMinorActivity(activeUsername, child, inspectArea.value);
    inspectResult.textContent = result.message;
    if (result.ok) {
      store.addNotification(activeUsername, `Inspection logged for ${child}.`, "notice");
      renderNotifications();
    }
  });

  approveContactBtn.addEventListener("click", () => {
    approveResult.textContent = "";
    if (!activeUsername) {
      approveResult.textContent = "Sign in as the guardian account first.";
      return;
    }
    const child = approveChildName.value.trim();
    const adult = approveAdultName.value.trim();
    if (!child || !adult) {
      approveResult.textContent = "Provide both child and adult usernames.";
      return;
    }
    const result = store.approveMinorContact(activeUsername, child, adult);
    approveResult.textContent = result.message;
    if (result.ok) {
      store.addNotification(activeUsername, `Approved ${adult} for ${child}.`, "notice");
      renderNotifications();
    }
  });

  refreshMetrics();
  renderAccountSelectors();
  renderScopes();
  renderScopePanel();
  renderArchive();
  renderGroupStream();
  renderProfileTheme();

  const session = store.getCurrentUser();
  setActiveUser(session ? session.username : accountSwitcher.value);
});
