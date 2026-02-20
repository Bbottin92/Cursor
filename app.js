document.addEventListener("DOMContentLoaded", async () => {
  const data = window.LiquidGovData;
  await data.init();

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
  const milestoneCompleted = document.getElementById("milestoneCompleted");
  const milestoneFill = document.getElementById("milestoneFill");
  const milestoneChecks = document.getElementById("milestoneChecks");
  const toggleVerificationMethod = document.getElementById("toggleVerificationMethod");
  const toggleFrameworkPublished = document.getElementById("toggleFrameworkPublished");
  const toggleAuditPublished = document.getElementById("toggleAuditPublished");
  const roleSelector = document.getElementById("roleSelector");
  const claimRoleBtn = document.getElementById("claimRoleBtn");
  const releaseRoleBtn = document.getElementById("releaseRoleBtn");
  const roleResult = document.getElementById("roleResult");
  const roleList = document.getElementById("roleList");
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
  const announcementForm = document.getElementById("announcementForm");
  const announcementTitle = document.getElementById("announcementTitle");
  const announcementBody = document.getElementById("announcementBody");
  const announcementResult = document.getElementById("announcementResult");
  const announcementsList = document.getElementById("announcementsList");
  const painPointInput = document.getElementById("painPointInput");
  const solutionInput = document.getElementById("solutionInput");
  const proposalCategory = document.getElementById("proposalCategory");
  const proposalResult = document.getElementById("proposalResult");
  const archiveTableBody = document.getElementById("archiveTableBody");
  const listingForm = document.getElementById("listingForm");
  const listingType = document.getElementById("listingType");
  const listingTitle = document.getElementById("listingTitle");
  const listingDetails = document.getElementById("listingDetails");
  const listingResult = document.getElementById("listingResult");
  const listingTableBody = document.getElementById("listingTableBody");
  const networkForm = document.getElementById("networkForm");
  const networkTags = document.getElementById("networkTags");
  const networkMessage = document.getElementById("networkMessage");
  const networkResult = document.getElementById("networkResult");
  const networkList = document.getElementById("networkList");
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

  async function getAccounts() {
    return data.getAccounts();
  }

  async function findAccount(username) {
    const accounts = await getAccounts();
    return accounts.find(
      (item) => item.username.toLowerCase() === String(username || "").toLowerCase()
    );
  }

  async function refreshMetrics() {
    const accounts = await getAccounts();
    const participantCount = await data.getParticipantCount();
    const verifiedTotal = accounts.filter((item) => item.isVerifiedPatriot).length;
    participantsCount.textContent = data.formatNumber(participantCount);
    verifiedCount.textContent = data.formatNumber(verifiedTotal);
    profileVerifiedCounter.textContent = data.formatNumber(verifiedTotal);
  }

  async function renderLaunchMilestone() {
    const milestone = await data.getLaunchMilestoneStatus();
    milestoneCompleted.textContent = String(milestone.completedChecks);
    milestoneFill.style.width = `${(milestone.completedChecks / 5) * 100}%`;
    milestoneChecks.innerHTML = milestone.checks
      .map((item) => {
        const labelClass = item.met ? "done" : "todo";
        const labelText = item.met ? "Met" : "Pending";
        return `
          <div class="check-item">
            <span>${item.label}</span>
            <strong class="${labelClass}">${labelText}</strong>
          </div>
        `;
      })
      .join("");

    const settings = await data.getSettings();
    toggleVerificationMethod.checked = Boolean(settings.verificationMethodRatified);
    toggleFrameworkPublished.checked = Boolean(settings.frameworkPublished);
    toggleAuditPublished.checked = Boolean(settings.auditPublished);
  }

  async function renderRoles() {
    const roles = await data.getAssemblyRoles();
    roleSelector.innerHTML = roles
      .map((role) => `<option value="${role.id}">${role.title}</option>`)
      .join("");

    roleList.innerHTML = roles
      .map((role) => {
        const assignee = role.assignedTo ? role.assignedTo : "Vacant";
        return `<li>${role.title}: <strong>${assignee}</strong></li>`;
      })
      .join("");
  }

  async function renderListings() {
    const listings = await data.getListings();
    listingTableBody.innerHTML = listings
      .slice(0, 20)
      .map((item) => {
        const tagClass = item.status === "open" ? "status-under-review" : "status-archived";
        const label = item.status === "open" ? "Open" : "Closed";
        return `
          <tr>
            <td>${item.type}</td>
            <td>${item.title}</td>
            <td>${item.author}</td>
            <td><span class="status-tag ${tagClass}">${label}</span></td>
          </tr>
        `;
      })
      .join("");
  }

  async function renderNetworkPosts() {
    const posts = await data.getNetworkPosts();
    networkList.innerHTML = posts
      .slice(0, 20)
      .map((post) => {
        const tags = post.tags.length ? `#${post.tags.join(" #")}` : "No tags";
        return `<li><strong>${post.author}</strong> (${post.scope}) · ${tags}<br />${post.message}</li>`;
      })
      .join("");
  }

  async function renderAccountSelectors() {
    const accounts = await getAccounts();
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

  async function setActiveUser(username, options = {}) {
    const { skipAuthSync = false } = options;
    if (!username) {
      activeUsername = null;
      currentUsername.textContent = "Guest";
      currentBadge.textContent = "Participant";
      avatarInitial.textContent = "G";
      visitorLogBody.innerHTML = '<tr><td colspan="2">Sign in to view logs.</td></tr>';
      notificationsBody.innerHTML = '<tr><td colspan="2">Sign in to view notifications.</td></tr>';
      return;
    }

    const account = await findAccount(username);
    if (!account) {
      await setActiveUser(null, { skipAuthSync: true });
      return;
    }

    activeUsername = account.username;
    if (!skipAuthSync) {
      try {
        await data.setCurrentUser(account.username);
      } catch (error) {
        roleResult.textContent = error.message;
      }
    }

    currentUsername.textContent = account.username;
    avatarInitial.textContent = account.username.slice(0, 1).toUpperCase();

    if (account.isVerifiedPatriot && account.role === "minor") {
      currentBadge.textContent = "Verified Patriot (Minor)";
    } else if (account.isVerifiedPatriot) {
      currentBadge.textContent = "Verified Patriot";
    } else {
      currentBadge.textContent = "Participant";
    }

    await renderVisitorLog();
    await renderNotifications();
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

  async function renderArchive() {
    const proposals = (await data.getProposals())
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
            <td><span class="status-tag ${statusClass}">${statusLabel}</span></td>
            <td>${item.lawReference || "-"}</td>
          </tr>
        `;
      })
      .join("");
  }

  async function renderAnnouncements() {
    const announcements = (await data.getAnnouncements()).slice(0, 12);
    if (!announcements.length) {
      announcementsList.innerHTML = "<li>No announcements yet.</li>";
      return;
    }
    announcementsList.innerHTML = announcements
      .map(
        (item) =>
          `<li><strong>${item.title}</strong> · ${item.author_name || item.author_username || "Unknown"}<br />${item.body}</li>`
      )
      .join("");
  }

  async function renderVisitorLog() {
    if (!activeUsername) {
      return;
    }
    const visitors = await data.getProfileVisitors(activeUsername);
    if (!visitors.length) {
      visitorLogBody.innerHTML = "<tr><td colspan='2'>No profile visitors logged yet.</td></tr>";
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

  async function renderNotifications() {
    if (!activeUsername) {
      return;
    }
    const notes = await data.getNotifications(activeUsername);
    if (!notes.length) {
      notificationsBody.innerHTML =
        "<tr><td colspan='2'>No notifications yet for this account.</td></tr>";
      return;
    }
    notificationsBody.innerHTML = notes
      .slice(0, 15)
      .map(
        (entry) =>
          `<tr><td>${data.formatDate(entry.createdAt)}</td><td>${entry.message}</td></tr>`
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

  announcementForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    announcementResult.textContent = "";
    if (!activeUsername) {
      announcementResult.textContent = "Select an account first.";
      return;
    }

    const title = announcementTitle.value.trim();
    const body = announcementBody.value.trim();
    if (!title || !body) {
      announcementResult.textContent = "Provide both title and message.";
      return;
    }

    try {
      await data.addAnnouncement({
        title,
        body,
        authorName: activeUsername,
        authorUsername: activeUsername
      });
      announcementResult.textContent = "Announcement posted.";
      announcementTitle.value = "";
      announcementBody.value = "";
      await renderAnnouncements();
    } catch (error) {
      announcementResult.textContent = error.message;
    }
  });

  proposalForm.addEventListener("submit", async (event) => {
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
    await data.addProposal({
      title: combinedTitle,
      category,
      author: activeUsername,
      status: "under_review"
    });
    proposalResult.textContent = "Proposal submitted to archive with author credit.";
    painPointInput.value = "";
    solutionInput.value = "";
    await renderArchive();
  });

  dmSendBtn.addEventListener("click", async () => {
    dmResult.textContent = "";
    if (!activeUsername || !dmInput.value.trim()) {
      return;
    }
    const recipient = dmRecipient.value.trim();
    if (!recipient) {
      dmResult.textContent = "Add a recipient username.";
      return;
    }
    const permission = await data.canInteract(activeUsername, recipient);
    if (!permission.ok) {
      dmResult.textContent = permission.reason;
      return;
    }

    await data.addNotification(
      activeUsername,
      `DM sent to ${recipient}: "${dmInput.value.trim().slice(0, 60)}"`,
      "info"
    );
    await data.addNotification(
      recipient,
      `DM received from ${activeUsername}: "${dmInput.value.trim().slice(0, 60)}"`,
      "info"
    );
    dmInput.value = "";
    dmResult.textContent = "Message delivered.";
    await renderNotifications();
  });

  audioSendBtn.addEventListener("click", async () => {
    if (!activeUsername || !audioNoteInput.value.trim()) {
      return;
    }
    await data.addNotification(activeUsername, "Audio message submitted.", "info");
    audioNoteInput.value = "";
    await renderNotifications();
  });

  startVideoBtn.addEventListener("click", async () => {
    if (!activeUsername) {
      return;
    }
    await data.addNotification(activeUsername, "1:1 video room token generated.", "info");
    await renderNotifications();
  });

  startGroupVideoBtn.addEventListener("click", async () => {
    if (!activeUsername) {
      return;
    }
    await data.addNotification(activeUsername, "Group video room opened.", "info");
    await renderNotifications();
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

  useAccountBtn.addEventListener("click", async () => {
    const selected = accountSwitcher.value;
    if (!selected) {
      return;
    }
    await setActiveUser(selected);
    await renderAccountSelectors();
  });

  logoutBtn.addEventListener("click", async () => {
    await data.setCurrentUser(null);
    await setActiveUser(null, { skipAuthSync: true });
  });

  visitProfileBtn.addEventListener("click", async () => {
    if (!activeUsername) {
      return;
    }
    const target = profileDirectory.value;
    if (!target || target === activeUsername) {
      return;
    }
    await data.recordProfileVisit(target, activeUsername);
    await renderVisitorLog();
    await renderNotifications();
  });

  inspectBtn.addEventListener("click", async () => {
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
    const result = await data.inspectMinorActivity(activeUsername, child, inspectArea.value);
    inspectResult.textContent = result.message;
    if (result.ok) {
      await data.addNotification(activeUsername, `Inspection logged for ${child}.`, "notice");
      await renderNotifications();
    }
  });

  approveContactBtn.addEventListener("click", async () => {
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
    const result = await data.approveMinorContact(activeUsername, child, adult);
    approveResult.textContent = result.message;
    if (result.ok) {
      await data.addNotification(activeUsername, `Approved ${adult} for ${child}.`, "notice");
      await renderNotifications();
    }
  });

  [toggleVerificationMethod, toggleFrameworkPublished, toggleAuditPublished].forEach(
    (checkbox) => {
      checkbox.addEventListener("change", async () => {
        await data.updateSettings({
          verificationMethodRatified: toggleVerificationMethod.checked,
          frameworkPublished: toggleFrameworkPublished.checked,
          auditPublished: toggleAuditPublished.checked
        });
        await renderLaunchMilestone();
      });
    }
  );

  claimRoleBtn.addEventListener("click", async () => {
    roleResult.textContent = "";
    if (!activeUsername) {
      roleResult.textContent = "Select an account first.";
      return;
    }
    const roleId = roleSelector.value;
    const result = await data.claimAssemblyRole(roleId, activeUsername);
    roleResult.textContent = result.message;
    await renderRoles();
    await renderLaunchMilestone();
    await renderNotifications();
  });

  releaseRoleBtn.addEventListener("click", async () => {
    roleResult.textContent = "";
    if (!activeUsername) {
      roleResult.textContent = "Select an account first.";
      return;
    }
    const roleId = roleSelector.value;
    const result = await data.releaseAssemblyRole(roleId, activeUsername);
    roleResult.textContent = result.message;
    await renderRoles();
    await renderLaunchMilestone();
    await renderNotifications();
  });

  listingForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    listingResult.textContent = "";
    if (!activeUsername) {
      listingResult.textContent = "Select an account first.";
      return;
    }
    const title = listingTitle.value.trim();
    const details = listingDetails.value.trim();
    if (!title || !details) {
      listingResult.textContent = "Provide title and details.";
      return;
    }
    await data.addListing({
      type: listingType.value,
      title,
      details,
      scope: activeScope,
      author: activeUsername
    });
    listingResult.textContent = "Listing posted.";
    listingTitle.value = "";
    listingDetails.value = "";
    await renderListings();
  });

  networkForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    networkResult.textContent = "";
    if (!activeUsername) {
      networkResult.textContent = "Select an account first.";
      return;
    }
    const message = networkMessage.value.trim();
    if (!message) {
      networkResult.textContent = "Write a networking message.";
      return;
    }
    const tags = networkTags.value
      .split(",")
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean)
      .slice(0, 7);

    await data.addNetworkPost({
      author: activeUsername,
      scope: activeScope,
      tags,
      message
    });
    networkResult.textContent = "Networking post published.";
    networkTags.value = "";
    networkMessage.value = "";
    await renderNetworkPosts();
  });

  await refreshMetrics();
  await renderLaunchMilestone();
  await renderRoles();
  await renderAccountSelectors();
  renderScopes();
  renderScopePanel();
  await renderAnnouncements();
  await renderArchive();
  await renderListings();
  await renderNetworkPosts();
  renderGroupStream();
  renderProfileTheme();

  const session = await data.getCurrentUser();
  await setActiveUser(session ? session.username : accountSwitcher.value, {
    skipAuthSync: Boolean(session)
  });
});
