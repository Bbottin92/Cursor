document.addEventListener("DOMContentLoaded", async () => {
  const data = window.LiquidGovData;
  await data.init();

  const scopes = {
    Neighborhood: "Local block-level issues and opportunities.",
    Town: "Town-level projects, events, and policy proposals.",
    State: "State-level initiatives and chapter coordination.",
    National: "National strategy, policy, and movement updates.",
    International: "Global observers and allied network conversations."
  };

  const state = {
    activeUsername: null,
    activeScope: "Neighborhood",
    postedProposal: false,
    sentMessage: false,
    groupMessages: [
      "System: Welcome to the group channel.",
      "System: Keep discussion constructive and solution-focused."
    ]
  };

  function el(id) {
    return document.getElementById(id);
  }

  const currentUsername = el("currentUsername");
  const currentBadge = el("currentBadge");
  const accountSwitcher = el("accountSwitcher");
  const useAccountBtn = el("useAccountBtn");
  const logoutBtn = el("logoutBtn");
  const scopeSelect = el("scopeSelect");
  const scopeHint = el("scopeHint");
  const participantsCount = el("participantsCount");
  const verifiedCount = el("verifiedCount");

  const onboardAccount = el("onboardAccount");
  const onboardScope = el("onboardScope");
  const onboardProposal = el("onboardProposal");
  const onboardMessage = el("onboardMessage");
  const onboardingProgress = el("onboardingProgress");

  const announcementForm = el("announcementForm");
  const announcementTitle = el("announcementTitle");
  const announcementBody = el("announcementBody");
  const announcementResult = el("announcementResult");
  const announcementsList = el("announcementsList");

  const proposalForm = el("proposalForm");
  const painPointInput = el("painPointInput");
  const solutionInput = el("solutionInput");
  const proposalCategory = el("proposalCategory");
  const proposalResult = el("proposalResult");
  const archiveTableBody = el("archiveTableBody");

  const dmRecipient = el("dmRecipient");
  const dmInput = el("dmInput");
  const dmSendBtn = el("dmSendBtn");
  const dmResult = el("dmResult");
  const groupInput = el("groupInput");
  const groupSendBtn = el("groupSendBtn");
  const groupStream = el("groupStream");

  const profileDirectory = el("profileDirectory");
  const visitProfileBtn = el("visitProfileBtn");
  const visitorLogBody = el("visitorLogBody");
  const notificationsBody = el("notificationsBody");

  function setOnboardingItem(itemEl, done) {
    itemEl.classList.toggle("done", done);
    const status = itemEl.querySelector("strong");
    status.textContent = done ? "Done" : "Pending";
  }

  function renderOnboarding() {
    const doneAccount = Boolean(state.activeUsername);
    const doneScope = Boolean(state.activeScope);
    const doneProposal = Boolean(state.postedProposal);
    const doneMessage = Boolean(state.sentMessage);
    setOnboardingItem(onboardAccount, doneAccount);
    setOnboardingItem(onboardScope, doneScope);
    setOnboardingItem(onboardProposal, doneProposal);
    setOnboardingItem(onboardMessage, doneMessage);
    onboardingProgress.textContent = `${
      [doneAccount, doneScope, doneProposal, doneMessage].filter(Boolean).length
    }/4`;
  }

  async function getAccounts() {
    return data.getAccounts();
  }

  async function findAccount(username) {
    const accounts = await getAccounts();
    return accounts.find(
      (item) => item.username.toLowerCase() === String(username || "").toLowerCase()
    );
  }

  async function renderMetrics() {
    const accounts = await getAccounts();
    const verified = accounts.filter((item) => item.isVerifiedPatriot).length;
    const participantCount = await data.getParticipantCount();
    participantsCount.textContent = data.formatNumber(participantCount);
    verifiedCount.textContent = data.formatNumber(verified);
  }

  async function renderAccountOptions() {
    const accounts = await getAccounts();
    const options = accounts
      .map((item) => {
        const tag = item.isVerifiedPatriot ? "Verified Patriot" : "Participant";
        return `<option value="${item.username}">${item.username} (${tag})</option>`;
      })
      .join("");

    accountSwitcher.innerHTML = options || '<option value="">No accounts yet</option>';
    profileDirectory.innerHTML = options || '<option value="">No accounts yet</option>';
  }

  async function setActiveUser(username, { skipAuthSync = false } = {}) {
    if (!username) {
      state.activeUsername = null;
      currentUsername.textContent = "Guest";
      currentBadge.textContent = "Participant";
      visitorLogBody.innerHTML = "<tr><td colspan='2'>Sign in to view visitor logs.</td></tr>";
      notificationsBody.innerHTML = "<tr><td colspan='2'>Sign in to view notifications.</td></tr>";
      renderOnboarding();
      return;
    }

    const account = await findAccount(username);
    if (!account) {
      await setActiveUser(null, { skipAuthSync: true });
      return;
    }

    if (!skipAuthSync) {
      await data.setCurrentUser(account.username);
    }

    state.activeUsername = account.username;
    currentUsername.textContent = account.username;
    currentBadge.textContent = account.isVerifiedPatriot ? "Verified Patriot" : "Participant";

    await renderNotifications();
    await renderVisitorLog();
    renderOnboarding();
  }

  function renderScope() {
    scopeSelect.value = state.activeScope;
    scopeHint.textContent = scopes[state.activeScope];
    renderOnboarding();
  }

  async function renderAnnouncements() {
    const items = (await data.getAnnouncements()).slice(0, 12);
    if (!items.length) {
      announcementsList.innerHTML = "<li>No announcements yet.</li>";
      return;
    }
    announcementsList.innerHTML = items
      .map(
        (item) =>
          `<li><strong>${item.title}</strong> · ${item.author_name || item.author_username || "Unknown"}<br />${item.body}</li>`
      )
      .join("");
  }

  async function renderArchive() {
    const proposals = (await data.getProposals())
      .slice()
      .sort((a, b) => new Date(b.submittedAt) - new Date(a.submittedAt))
      .slice(0, 25);
    archiveTableBody.innerHTML = proposals
      .map((item) => {
        const status =
          item.status === "implemented"
            ? "Implemented"
            : item.status === "archived"
              ? "Archived"
              : "Under Review";
        return `
          <tr>
            <td>${data.formatDate(item.submittedAt)}</td>
            <td>${item.author}</td>
            <td>${item.title}</td>
            <td>${status}</td>
          </tr>
        `;
      })
      .join("");
  }

  async function renderNotifications() {
    if (!state.activeUsername) {
      return;
    }
    const notifications = await data.getNotifications(state.activeUsername);
    if (!notifications.length) {
      notificationsBody.innerHTML = "<tr><td colspan='2'>No notifications yet.</td></tr>";
      return;
    }
    notificationsBody.innerHTML = notifications
      .slice(0, 12)
      .map(
        (entry) =>
          `<tr><td>${data.formatDate(entry.createdAt)}</td><td>${entry.message}</td></tr>`
      )
      .join("");
  }

  async function renderVisitorLog() {
    if (!state.activeUsername) {
      return;
    }
    const visitors = await data.getProfileVisitors(state.activeUsername);
    if (!visitors.length) {
      visitorLogBody.innerHTML = "<tr><td colspan='2'>No visitors logged yet.</td></tr>";
      return;
    }
    visitorLogBody.innerHTML = visitors
      .slice(0, 12)
      .map(
        (entry) =>
          `<tr><td>${entry.visitor}</td><td>${data.formatDate(entry.visitedAt)}</td></tr>`
      )
      .join("");
  }

  function renderGroupMessages() {
    groupStream.innerHTML = state.groupMessages.map((line) => `<li>${line}</li>`).join("");
  }

  announcementForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    announcementResult.textContent = "";
    if (!state.activeUsername) {
      announcementResult.textContent = "Choose an account first.";
      return;
    }
    const title = announcementTitle.value.trim();
    const body = announcementBody.value.trim();
    if (!title || !body) {
      announcementResult.textContent = "Provide both title and message.";
      return;
    }
    await data.addAnnouncement({
      title,
      body,
      authorName: state.activeUsername,
      authorUsername: state.activeUsername
    });
    announcementTitle.value = "";
    announcementBody.value = "";
    announcementResult.textContent = "Announcement posted.";
    await renderAnnouncements();
  });

  proposalForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    proposalResult.textContent = "";
    if (!state.activeUsername) {
      proposalResult.textContent = "Choose an account first.";
      return;
    }
    const pain = painPointInput.value.trim();
    const solution = solutionInput.value.trim();
    if (!pain || !solution) {
      proposalResult.textContent = "Provide both pain point and solution.";
      return;
    }

    await data.addProposal({
      title: `${pain.slice(0, 58)} -> ${solution.slice(0, 58)}`,
      category: proposalCategory.value,
      author: state.activeUsername,
      status: "under_review"
    });
    painPointInput.value = "";
    solutionInput.value = "";
    state.postedProposal = true;
    renderOnboarding();
    proposalResult.textContent = "Proposal submitted.";
    await renderArchive();
  });

  dmSendBtn.addEventListener("click", async () => {
    dmResult.textContent = "";
    if (!state.activeUsername) {
      dmResult.textContent = "Choose an account first.";
      return;
    }
    const recipient = dmRecipient.value.trim();
    const message = dmInput.value.trim();
    if (!recipient || !message) {
      dmResult.textContent = "Provide recipient and message.";
      return;
    }
    const permission = await data.canInteract(state.activeUsername, recipient);
    if (!permission.ok) {
      dmResult.textContent = permission.reason;
      return;
    }

    await data.addNotification(
      state.activeUsername,
      `DM sent to ${recipient}: "${message.slice(0, 60)}"`,
      "info"
    );
    await data.addNotification(
      recipient,
      `DM received from ${state.activeUsername}: "${message.slice(0, 60)}"`,
      "info"
    );
    dmInput.value = "";
    state.sentMessage = true;
    renderOnboarding();
    dmResult.textContent = "Message sent.";
    await renderNotifications();
  });

  groupSendBtn.addEventListener("click", () => {
    if (!state.activeUsername || !groupInput.value.trim()) {
      return;
    }
    state.groupMessages.unshift(`${state.activeUsername}: ${groupInput.value.trim()}`);
    groupInput.value = "";
    state.sentMessage = true;
    renderOnboarding();
    renderGroupMessages();
  });

  useAccountBtn.addEventListener("click", async () => {
    const selected = accountSwitcher.value;
    if (!selected) {
      return;
    }
    await setActiveUser(selected);
    await renderAccountOptions();
  });

  logoutBtn.addEventListener("click", async () => {
    await data.setCurrentUser(null);
    await setActiveUser(null, { skipAuthSync: true });
  });

  scopeSelect.addEventListener("change", () => {
    state.activeScope = scopeSelect.value;
    renderScope();
  });

  visitProfileBtn.addEventListener("click", async () => {
    if (!state.activeUsername) {
      return;
    }
    const target = profileDirectory.value;
    if (!target || target === state.activeUsername) {
      return;
    }
    await data.recordProfileVisit(target, state.activeUsername);
    await renderVisitorLog();
    await renderNotifications();
  });

  await renderMetrics();
  await renderAccountOptions();
  await renderAnnouncements();
  await renderArchive();
  renderScope();
  renderGroupMessages();

  const session = await data.getCurrentUser();
  await setActiveUser(session ? session.username : accountSwitcher.value, {
    skipAuthSync: Boolean(session)
  });
});
