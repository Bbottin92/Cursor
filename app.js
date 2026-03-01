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
    activePortrait: null,
    isAdmin: false,
    promptShownSession: {},
    groupMessages: [
      "System: Welcome to the group channel.",
      "System: Keep discussion constructive and solution-focused."
    ]
  };
  const ONBOARDING_PROGRESS_KEY = "nusaOnboardingProgress";

  function loadOnboardingProgressMap() {
    try {
      const raw = window.localStorage.getItem(ONBOARDING_PROGRESS_KEY);
      if (!raw) {
        return {};
      }
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (error) {
      return {};
    }
  }

  function saveOnboardingProgressMap(map) {
    try {
      window.localStorage.setItem(
        ONBOARDING_PROGRESS_KEY,
        JSON.stringify(map || {})
      );
    } catch (error) {
      // Ignore storage write failures; onboarding can still work in-memory.
    }
  }

  state.onboardingProgressByUser = loadOnboardingProgressMap();

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
  const onboardingSuccess = el("onboardingSuccess");
  const onboardingJumpButtons = Array.from(
    document.querySelectorAll("[data-onboard-action]")
  );

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
  const adminCard = el("adminCard");
  const adminUserSelect = el("adminUserSelect");
  const grantModeratorBtn = el("grantModeratorBtn");
  const revokeModeratorBtn = el("revokeModeratorBtn");
  const deleteProfileBtn = el("deleteProfileBtn");
  const adminResult = el("adminResult");

  const portraitTrigger = el("portraitTrigger");
  const portraitPreview = el("portraitPreview");
  const portraitDialog = el("portraitDialog");
  const portraitCanvas = el("portraitCanvas");
  const portraitClose = el("portraitClose");
  const portraitSave = el("portraitSave");
  const portraitClear = el("portraitClear");
  const portraitResult = el("portraitResult");
  const brushColorInput = el("brushColor");
  const brushShadeInput = el("brushShade");
  const brushSizeInput = el("brushSize");
  const feedbackPromptDialog = el("feedbackPromptDialog");
  const feedbackProblem = el("feedbackProblem");
  const feedbackSolution = el("feedbackSolution");
  const feedbackPromptEnable = el("feedbackPromptEnable");
  const feedbackPromptClose = el("feedbackPromptClose");
  const feedbackPromptSend = el("feedbackPromptSend");
  const feedbackPromptResult = el("feedbackPromptResult");
  const dashboardTabButtons = Array.from(
    document.querySelectorAll("[data-dashboard-tab]")
  );
  const dashboardPanels = Array.from(
    document.querySelectorAll("[data-dashboard-panel]")
  );

  const FEEDBACK_PROMPT_COOLDOWN_MS = 24 * 60 * 60 * 1000;
  const dashboardHashToTab = {
    proposalCard: "proposals",
    tabProposalsPanel: "proposals",
    messagesCard: "messages",
    tabMessagesPanel: "messages",
    adminCard: "transparency",
    tabTransparencyPanel: "transparency",
    proposals: "proposals",
    messages: "messages"
  };

  function setActiveDashboardTab(tabName) {
    const fallbackTab = dashboardTabButtons[0]?.dataset.dashboardTab || "proposals";
    const targetTab = dashboardPanels.some(
      (panel) => panel.dataset.dashboardPanel === tabName
    )
      ? tabName
      : fallbackTab;

    dashboardTabButtons.forEach((button) => {
      const isActive = button.dataset.dashboardTab === targetTab;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-selected", String(isActive));
      button.setAttribute("tabindex", isActive ? "0" : "-1");
    });

    dashboardPanels.forEach((panel) => {
      const isActive = panel.dataset.dashboardPanel === targetTab;
      panel.hidden = !isActive;
      panel.classList.toggle("active", isActive);
    });
  }

  function applyHashTabSelection() {
    const rawHash = String(window.location.hash || "").replace(/^#/, "");
    const mappedTab = dashboardHashToTab[rawHash];
    if (!mappedTab) {
      return;
    }
    setActiveDashboardTab(mappedTab);
    const target = document.getElementById(rawHash);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function setOnboardingItem(itemEl, done) {
    itemEl.classList.toggle("done", done);
    const status = itemEl.querySelector("strong");
    status.textContent = done ? "Done" : "Pending";
  }

  function getOnboardingStatus() {
    const doneAccount = Boolean(state.activeUsername);
    const doneScope = Boolean(state.activeUsername && state.activeScope);
    const doneProposal = Boolean(state.postedProposal);
    const doneMessage = Boolean(state.sentMessage);
    const completed = doneAccount && doneScope && doneProposal && doneMessage;
    return {
      doneAccount,
      doneScope,
      doneProposal,
      doneMessage,
      completed
    };
  }

  function persistActiveUserOnboardingProgress() {
    if (!state.activeUsername) {
      return;
    }
    const key = String(state.activeUsername).toLowerCase();
    state.onboardingProgressByUser[key] = {
      postedProposal: Boolean(state.postedProposal),
      sentMessage: Boolean(state.sentMessage),
      updatedAt: new Date().toISOString()
    };
    saveOnboardingProgressMap(state.onboardingProgressByUser);
  }

  async function maybePromptAfterOnboardingCompletion() {
    if (!state.activeUsername || !getOnboardingStatus().completed) {
      return;
    }
    const account = await findAccount(state.activeUsername);
    if (!account) {
      return;
    }
    await maybeShowFeedbackPrompt(account);
  }

  function renderOnboarding() {
    const status = getOnboardingStatus();
    setOnboardingItem(onboardAccount, status.doneAccount);
    setOnboardingItem(onboardScope, status.doneScope);
    setOnboardingItem(onboardProposal, status.doneProposal);
    setOnboardingItem(onboardMessage, status.doneMessage);
    onboardingProgress.textContent = `${
      [
        status.doneAccount,
        status.doneScope,
        status.doneProposal,
        status.doneMessage
      ].filter(Boolean).length
    }/4`;
    if (onboardingSuccess) {
      onboardingSuccess.hidden = !status.completed;
    }
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

  function initialsFor(name) {
    const parts = String(name || "Guest")
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2);
    if (!parts.length) {
      return "G";
    }
    return parts.map((item) => item[0].toUpperCase()).join("");
  }

  function fillCircleBackground(ctx, canvas) {
    const radius = canvas.width / 2;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.beginPath();
    ctx.arc(radius, radius, radius - 1, 0, Math.PI * 2);
    ctx.clip();
    const gradient = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
    gradient.addColorStop(0, "#15274d");
    gradient.addColorStop(1, "#203768");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.restore();
  }

  function drawPortraitPlaceholder(canvas, label) {
    if (!canvas) {
      return;
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }
    fillCircleBackground(ctx, canvas);
    const text = initialsFor(label);
    ctx.save();
    ctx.fillStyle = "#a2edff";
    ctx.font = `700 ${Math.floor(canvas.width * 0.34)}px Inter, Segoe UI, Tahoma, Arial, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, canvas.width / 2, canvas.height / 2);
    ctx.restore();
  }

  function drawPortraitImage(canvas, dataUrl, fallbackLabel) {
    if (!canvas) {
      return;
    }
    if (!dataUrl) {
      drawPortraitPlaceholder(canvas, fallbackLabel);
      return;
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }
    const image = new Image();
    image.onload = () => {
      fillCircleBackground(ctx, canvas);
      ctx.save();
      ctx.beginPath();
      ctx.arc(canvas.width / 2, canvas.height / 2, canvas.width / 2 - 1, 0, Math.PI * 2);
      ctx.clip();
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      ctx.restore();
    };
    image.onerror = () => {
      drawPortraitPlaceholder(canvas, fallbackLabel);
    };
    image.src = dataUrl;
  }

  function normalizeHexColor(value) {
    const hex = String(value || "").trim();
    return /^#[0-9a-fA-F]{6}$/.test(hex) ? hex : "#57d5ff";
  }

  function adjustedBrushColor() {
    const hex = normalizeHexColor(brushColorInput?.value);
    const shade = Number(brushShadeInput?.value || 50);
    const rgb = [1, 3, 5].map((idx) => parseInt(hex.slice(idx, idx + 2), 16));
    const clamp = (n) => Math.max(0, Math.min(255, n));
    const mix = (base, target, factor) => clamp(Math.round(base + (target - base) * factor));
    let out;
    if (shade < 50) {
      const factor = shade / 50;
      out = rgb.map((channel) => mix(0, channel, factor));
    } else if (shade > 50) {
      const factor = (shade - 50) / 50;
      out = rgb.map((channel) => mix(channel, 255, factor));
    } else {
      out = rgb;
    }
    return `rgb(${out[0]}, ${out[1]}, ${out[2]})`;
  }

  function clearPortraitEditor() {
    if (!portraitCanvas) {
      return;
    }
    const ctx = portraitCanvas.getContext("2d");
    if (!ctx) {
      return;
    }
    fillCircleBackground(ctx, portraitCanvas);
    drawPortraitPlaceholder(portraitCanvas, state.activeUsername || "Guest");
  }

  function loadPortraitIntoEditor(dataUrl) {
    if (!portraitCanvas) {
      return;
    }
    if (!dataUrl) {
      clearPortraitEditor();
      return;
    }
    const ctx = portraitCanvas.getContext("2d");
    if (!ctx) {
      return;
    }
    const image = new Image();
    image.onload = () => {
      fillCircleBackground(ctx, portraitCanvas);
      ctx.save();
      ctx.beginPath();
      ctx.arc(
        portraitCanvas.width / 2,
        portraitCanvas.height / 2,
        portraitCanvas.width / 2 - 1,
        0,
        Math.PI * 2
      );
      ctx.clip();
      ctx.drawImage(image, 0, 0, portraitCanvas.width, portraitCanvas.height);
      ctx.restore();
    };
    image.onerror = () => {
      clearPortraitEditor();
    };
    image.src = dataUrl;
  }

  function exportPortraitDataUrl() {
    if (!portraitCanvas) {
      return null;
    }
    const output = document.createElement("canvas");
    output.width = portraitCanvas.width;
    output.height = portraitCanvas.height;
    const ctx = output.getContext("2d");
    if (!ctx) {
      return null;
    }
    ctx.beginPath();
    ctx.arc(output.width / 2, output.height / 2, output.width / 2 - 1, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(portraitCanvas, 0, 0);
    return output.toDataURL("image/png");
  }

  function paintAtPointer(event) {
    if (!portraitCanvas) {
      return;
    }
    const ctx = portraitCanvas.getContext("2d");
    if (!ctx) {
      return;
    }
    const rect = portraitCanvas.getBoundingClientRect();
    const scaleX = portraitCanvas.width / rect.width;
    const scaleY = portraitCanvas.height / rect.height;
    const x = (event.clientX - rect.left) * scaleX;
    const y = (event.clientY - rect.top) * scaleY;
    const radius = portraitCanvas.width / 2 - 1;
    const centerX = portraitCanvas.width / 2;
    const centerY = portraitCanvas.height / 2;
    const distance = Math.hypot(x - centerX, y - centerY);
    if (distance > radius) {
      return;
    }
    ctx.save();
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.clip();
    ctx.fillStyle = adjustedBrushColor();
    ctx.beginPath();
    ctx.arc(x, y, Number(brushSizeInput?.value || 10), 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  async function renderPortraitFromAccount() {
    const account = state.activeUsername ? await findAccount(state.activeUsername) : null;
    state.activePortrait = account?.profilePhotoUrl || null;
    drawPortraitImage(portraitPreview, state.activePortrait, state.activeUsername || "Guest");
  }

  async function renderAdminPanel() {
    if (!adminCard) {
      return;
    }
    adminCard.classList.toggle("active", Boolean(state.isAdmin));
    if (!state.isAdmin) {
      adminResult.textContent = "";
      return;
    }
    const accounts = await getAccounts();
    if (!accounts.length) {
      adminUserSelect.innerHTML = '<option value="">No profiles</option>';
      return;
    }
    adminUserSelect.innerHTML = accounts
      .map((item) => {
        const tags = [item.isAdmin ? "Admin" : "", item.isModerator ? "Moderator" : ""]
          .filter(Boolean)
          .join(" / ");
        const suffix = tags ? ` - ${tags}` : "";
        return `<option value="${item.id}">${item.username}${suffix}</option>`;
      })
      .join("");
  }

  function shouldShowFeedbackPrompt(account) {
    if (!account || !account.username) {
      return false;
    }
    if (!getOnboardingStatus().completed) {
      return false;
    }
    const key = String(account.username).toLowerCase();
    if (state.promptShownSession[key]) {
      return false;
    }
    if (account.promptOptOut) {
      return false;
    }
    const lastSeen = Date.parse(account.promptLastSeen || "");
    if (Number.isFinite(lastSeen) && Date.now() - lastSeen < FEEDBACK_PROMPT_COOLDOWN_MS) {
      return false;
    }
    return true;
  }

  async function maybeShowFeedbackPrompt(account) {
    if (!feedbackPromptDialog || !shouldShowFeedbackPrompt(account)) {
      return;
    }
    const key = String(account.username).toLowerCase();
    state.promptShownSession[key] = true;
    feedbackProblem.value = "";
    feedbackSolution.value = "";
    feedbackPromptEnable.checked = true;
    feedbackPromptResult.textContent = "";

    // Start 24-hour cooldown when the prompt appears.
    await data.markFeedbackPromptSeen(account.username, { optOut: false });

    if (typeof feedbackPromptDialog.showModal === "function") {
      feedbackPromptDialog.showModal();
    } else {
      feedbackPromptDialog.setAttribute("open", "true");
    }
  }

  function closeFeedbackDialogUi() {
    if (!feedbackPromptDialog) {
      return;
    }
    if (typeof feedbackPromptDialog.close === "function") {
      feedbackPromptDialog.close();
    } else {
      feedbackPromptDialog.removeAttribute("open");
    }
  }

  async function setActiveUser(username, { skipAuthSync = false } = {}) {
    if (!username) {
      state.activeUsername = null;
      state.activePortrait = null;
      state.isAdmin = false;
      state.postedProposal = false;
      state.sentMessage = false;
      currentUsername.textContent = "Guest";
      currentBadge.textContent = "Participant";
      visitorLogBody.innerHTML = "<tr><td colspan='2'>Sign in to view visitor logs.</td></tr>";
      notificationsBody.innerHTML = "<tr><td colspan='2'>Sign in to view notifications.</td></tr>";
      drawPortraitPlaceholder(portraitPreview, "Guest");
      await renderAdminPanel();
      renderOnboarding();
      return;
    }

    const account = await findAccount(username);
    if (!account) {
      await setActiveUser(null, { skipAuthSync: true });
      return;
    }

    if (!skipAuthSync) {
      try {
        await data.setCurrentUser(account.username);
      } catch (error) {
        await setActiveUser(null, { skipAuthSync: true });
        return;
      }
    }

    state.activeUsername = account.username;
    state.isAdmin = Boolean(account.isAdmin);
    const userProgress =
      state.onboardingProgressByUser[String(account.username).toLowerCase()] || {};
    state.postedProposal = Boolean(userProgress.postedProposal);
    state.sentMessage = Boolean(userProgress.sentMessage);
    currentUsername.textContent = account.username;
    currentBadge.textContent = state.isAdmin
      ? "Admin"
      : account.isVerifiedPatriot
        ? "Verified Patriot"
        : "Participant";

    await renderNotifications();
    await renderVisitorLog();
    await renderPortraitFromAccount();
    await renderAdminPanel();
    renderOnboarding();
    await maybePromptAfterOnboardingCompletion();
  }

  function renderScope() {
    scopeSelect.value = state.activeScope;
    scopeHint.textContent = scopes[state.activeScope];
    renderOnboarding();
  }

  function jumpToOnboardingAction(action) {
    if (action === "account") {
      document.getElementById("my-profile")?.scrollIntoView({
        behavior: "smooth",
        block: "start"
      });
      accountSwitcher.focus();
      return;
    }
    if (action === "scope") {
      document.getElementById("my-profile")?.scrollIntoView({
        behavior: "smooth",
        block: "start"
      });
      scopeSelect.focus();
      return;
    }
    if (action === "proposal") {
      setActiveDashboardTab("proposals");
      const target = document.getElementById("proposalCard");
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
      painPointInput.focus();
      return;
    }
    if (action === "message") {
      setActiveDashboardTab("messages");
      const target = document.getElementById("messagesCard");
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
      dmRecipient.focus();
    }
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
    persistActiveUserOnboardingProgress();
    renderOnboarding();
    proposalResult.textContent = "Proposal submitted.";
    await renderArchive();
    await maybePromptAfterOnboardingCompletion();
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
    persistActiveUserOnboardingProgress();
    renderOnboarding();
    dmResult.textContent = "Message sent.";
    await renderNotifications();
    await maybePromptAfterOnboardingCompletion();
  });

  groupSendBtn.addEventListener("click", async () => {
    if (!state.activeUsername || !groupInput.value.trim()) {
      return;
    }
    state.groupMessages.unshift(`${state.activeUsername}: ${groupInput.value.trim()}`);
    groupInput.value = "";
    state.sentMessage = true;
    persistActiveUserOnboardingProgress();
    renderOnboarding();
    renderGroupMessages();
    await maybePromptAfterOnboardingCompletion();
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

  let isPaintingPortrait = false;
  if (portraitCanvas) {
    portraitCanvas.addEventListener("pointerdown", (event) => {
      isPaintingPortrait = true;
      portraitCanvas.setPointerCapture?.(event.pointerId);
      paintAtPointer(event);
    });
    portraitCanvas.addEventListener("pointermove", (event) => {
      if (!isPaintingPortrait) {
        return;
      }
      paintAtPointer(event);
    });
    const stopPaint = (event) => {
      isPaintingPortrait = false;
      portraitCanvas.releasePointerCapture?.(event.pointerId);
    };
    portraitCanvas.addEventListener("pointerup", stopPaint);
    portraitCanvas.addEventListener("pointercancel", stopPaint);
    portraitCanvas.addEventListener("pointerleave", () => {
      isPaintingPortrait = false;
    });
  }

  portraitTrigger?.addEventListener("click", async () => {
    portraitResult.textContent = "";
    if (!state.activeUsername) {
      portraitResult.textContent = "Choose an account first.";
      return;
    }
    await renderPortraitFromAccount();
    loadPortraitIntoEditor(state.activePortrait);
    if (typeof portraitDialog.showModal === "function") {
      portraitDialog.showModal();
    } else {
      portraitDialog.setAttribute("open", "true");
    }
  });

  portraitClose?.addEventListener("click", () => {
    if (typeof portraitDialog.close === "function") {
      portraitDialog.close();
    } else {
      portraitDialog.removeAttribute("open");
    }
  });

  portraitSave?.addEventListener("click", async () => {
    if (!state.activeUsername) {
      portraitResult.textContent = "Choose an account first.";
      return;
    }
    const portraitDataUrl = exportPortraitDataUrl();
    const result = await data.setProfilePortrait(state.activeUsername, portraitDataUrl);
    portraitResult.textContent = result.message || "Portrait saved.";
    await renderPortraitFromAccount();
  });

  portraitClear?.addEventListener("click", async () => {
    if (!state.activeUsername) {
      portraitResult.textContent = "Choose an account first.";
      return;
    }
    clearPortraitEditor();
    const result = await data.setProfilePortrait(state.activeUsername, null);
    portraitResult.textContent = result.message || "Portrait cleared.";
    await renderPortraitFromAccount();
  });

  grantModeratorBtn?.addEventListener("click", async () => {
    if (!state.isAdmin) {
      adminResult.textContent = "Admin access required.";
      return;
    }
    const userId = adminUserSelect.value;
    if (!userId) {
      adminResult.textContent = "Choose a profile.";
      return;
    }
    const result = await data.updateUserAccess(userId, { is_moderator: true });
    adminResult.textContent = result.message;
    await renderAccountOptions();
    await renderAdminPanel();
  });

  revokeModeratorBtn?.addEventListener("click", async () => {
    if (!state.isAdmin) {
      adminResult.textContent = "Admin access required.";
      return;
    }
    const userId = adminUserSelect.value;
    if (!userId) {
      adminResult.textContent = "Choose a profile.";
      return;
    }
    const result = await data.updateUserAccess(userId, { is_moderator: false });
    adminResult.textContent = result.message;
    await renderAccountOptions();
    await renderAdminPanel();
  });

  deleteProfileBtn?.addEventListener("click", async () => {
    if (!state.isAdmin) {
      adminResult.textContent = "Admin access required.";
      return;
    }
    const userId = adminUserSelect.value;
    if (!userId) {
      adminResult.textContent = "Choose a profile.";
      return;
    }
    const result = await data.deleteProfile(userId);
    adminResult.textContent = result.message;
    await renderAccountOptions();
    await renderMetrics();
    const selectedUser = await findAccount(state.activeUsername);
    if (!selectedUser) {
      await setActiveUser(null, { skipAuthSync: true });
    } else {
      await renderAdminPanel();
    }
  });

  feedbackPromptClose?.addEventListener("click", async () => {
    if (!state.activeUsername) {
      closeFeedbackDialogUi();
      return;
    }
    const optOut = !feedbackPromptEnable.checked;
    if (optOut) {
      await data.markFeedbackPromptSeen(state.activeUsername, { optOut: true });
    }
    closeFeedbackDialogUi();
  });

  feedbackPromptSend?.addEventListener("click", async () => {
    if (!state.activeUsername) {
      feedbackPromptResult.textContent = "Choose an account first.";
      return;
    }
    const problem = feedbackProblem.value.trim();
    const solution = feedbackSolution.value.trim();
    const optOut = !feedbackPromptEnable.checked;
    const result = await data.submitFeedbackPrompt(state.activeUsername, {
      problem,
      solution,
      optOut
    });
    feedbackPromptResult.textContent = result.message || "Saved.";
    if (!result.ok) {
      return;
    }
    await renderAccountOptions();
    await renderAdminPanel();
    setTimeout(() => {
      closeFeedbackDialogUi();
    }, 320);
  });

  dashboardTabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setActiveDashboardTab(button.dataset.dashboardTab);
    });
  });
  onboardingJumpButtons.forEach((button) => {
    button.addEventListener("click", () => {
      jumpToOnboardingAction(button.dataset.onboardAction);
    });
  });
  window.addEventListener("hashchange", applyHashTabSelection);

  await renderMetrics();
  await renderAccountOptions();
  await renderAnnouncements();
  await renderArchive();
  renderScope();
  renderGroupMessages();
  setActiveDashboardTab("proposals");
  applyHashTabSelection();
  drawPortraitPlaceholder(portraitPreview, "Guest");

  const session = await data.getCurrentUser();
  await setActiveUser(session ? session.username : accountSwitcher.value, {
    skipAuthSync: Boolean(session)
  });
});
