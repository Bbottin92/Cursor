(function initLiquidGovStore() {
  const STORE = {
    accounts: "liquidgov.accounts",
    proposals: "liquidgov.proposals",
    session: "liquidgov.session",
    profileViews: "liquidgov.profileViews",
    notifications: "liquidgov.notifications",
    roles: "liquidgov.roles",
    listings: "liquidgov.listings",
    networkPosts: "liquidgov.networkPosts",
    settings: "liquidgov.settings",
    announcements: "liquidgov.announcements"
  };

  const defaultProposals = [
    {
      id: "P-1001",
      title: "Transparent vote receipt dashboard",
      category: "Governance",
      author: "Ari-Founder",
      submittedAt: "2026-02-01T12:10:00Z",
      status: "implemented",
      lawReference: "LAW-0007"
    },
    {
      id: "P-1002",
      title: "Neighborhood barter board",
      category: "Trade",
      author: "Nova72",
      submittedAt: "2026-02-08T16:00:00Z",
      status: "implemented",
      lawReference: "LAW-0012"
    },
    {
      id: "P-1003",
      title: "Mandatory weekly 6-hour livestream meetings",
      category: "Process",
      author: "RigidFlow",
      submittedAt: "2026-02-11T09:50:00Z",
      status: "archived",
      lawReference: null
    }
  ];

  const defaultAssemblyRoles = [
    { id: "R-1", title: "Coordinator / Facilitator", assignedTo: null },
    { id: "R-2", title: "Secretary / Records", assignedTo: null },
    { id: "R-3", title: "Treasury / Finance", assignedTo: null },
    { id: "R-4", title: "Tech Steward", assignedTo: null },
    { id: "R-5", title: "Governance Steward", assignedTo: null },
    { id: "R-6", title: "Community Steward", assignedTo: null },
    { id: "R-7", title: "Ethics & Safety Steward", assignedTo: null }
  ];

  const defaultListings = [
    {
      id: "L-9001",
      type: "barter",
      title: "Offer: plumbing help for web design",
      details: "Can help with basic plumbing in exchange for logo + landing page polish.",
      scope: "Neighborhood",
      author: "Nova72",
      status: "open",
      createdAt: "2026-02-10T14:00:00Z"
    },
    {
      id: "L-9002",
      type: "trade",
      title: "Need: livestream mic setup",
      details: "Seeking affordable used setup for chapter meetings.",
      scope: "Town",
      author: "Ari-Founder",
      status: "open",
      createdAt: "2026-02-12T19:22:00Z"
    }
  ];

  const defaultNetworkPosts = [
    {
      id: "N-4001",
      author: "Ari-Founder",
      scope: "National",
      tags: ["governance", "voluntarism"],
      message: "Looking for chapter organizers with policy writing experience.",
      createdAt: "2026-02-15T11:30:00Z"
    }
  ];

  const defaultAnnouncements = [
    {
      id: "A-1001",
      title: "Welcome to NUSA",
      body: "This is the initial announcement channel. Official NUSA updates will appear here.",
      author_name: "System",
      author_username: "system",
      created_at: "2026-02-20T00:00:00Z",
      updated_at: "2026-02-20T00:00:00Z"
    }
  ];

  const defaultSettings = {
    verificationMethodRatified: false,
    frameworkPublished: false,
    safetyStandardsAdopted: true,
    auditPublished: false,
    legacyParticipantOffset: 0
  };

  const ADMIN_USERNAMES = ["brandon bottin"];

  function read(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function write(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function ensureSeededProposals() {
    const existing = read(STORE.proposals, null);
    if (!existing || !Array.isArray(existing) || existing.length === 0) {
      write(STORE.proposals, defaultProposals);
    }
  }

  function ensureSeededRoles() {
    const existing = read(STORE.roles, null);
    if (!existing || !Array.isArray(existing) || existing.length === 0) {
      write(STORE.roles, defaultAssemblyRoles);
    }
  }

  function ensureSeededListings() {
    const existing = read(STORE.listings, null);
    if (!existing || !Array.isArray(existing) || existing.length === 0) {
      write(STORE.listings, defaultListings);
    }
  }

  function ensureSeededNetworkPosts() {
    const existing = read(STORE.networkPosts, null);
    if (!existing || !Array.isArray(existing) || existing.length === 0) {
      write(STORE.networkPosts, defaultNetworkPosts);
    }
  }

  function ensureSettings() {
    const existing = read(STORE.settings, null);
    if (!existing || typeof existing !== "object") {
      write(STORE.settings, defaultSettings);
    }
  }

  function ensureSeededAnnouncements() {
    const existing = read(STORE.announcements, null);
    if (!existing || !Array.isArray(existing) || existing.length === 0) {
      write(STORE.announcements, defaultAnnouncements);
    }
  }

  function getAccounts() {
    const accounts = read(STORE.accounts, []);
    let changed = false;
    for (const account of accounts) {
      if (isBootstrapAdmin(account.username) && !account.isAdmin) {
        account.isAdmin = true;
        changed = true;
      }
      if (typeof account.isModerator !== "boolean") {
        account.isModerator = Boolean(account.isModerator);
        changed = true;
      }
    }
    if (changed) {
      saveAccounts(accounts);
    }
    return accounts;
  }

  function saveAccounts(accounts) {
    write(STORE.accounts, accounts);
  }

  function getCurrentUser() {
    return read(STORE.session, null);
  }

  function setCurrentUser(username) {
    if (!username) {
      localStorage.removeItem(STORE.session);
      return;
    }
    write(STORE.session, { username });
  }

  function normalizeName(name) {
    return String(name || "").trim().toLowerCase();
  }

  function isBootstrapAdmin(username) {
    return ADMIN_USERNAMES.includes(normalizeName(username));
  }

  function createAccount(payload) {
    const accounts = getAccounts();
    const username = String(payload.username || "").trim();
    const password = String(payload.password || "").trim();

    if (username.length < 2) {
      return { ok: false, message: "Username must be at least 2 characters." };
    }
    if (password.length < 6) {
      return { ok: false, message: "Password must be at least 6 characters." };
    }

    const duplicate = accounts.find(
      (item) => normalizeName(item.username) === normalizeName(username)
    );
    if (duplicate) {
      return { ok: false, message: "That username is already in use." };
    }

    const account = {
      id: crypto.randomUUID(),
      username,
      password,
      age: 18,
      parentLink: null,
      approvedAdults: [],
      isModerator: false,
      isAdmin: isBootstrapAdmin(username),
      isVerifiedPatriot: false,
      pledgeSigned: false,
      profilePhotoUrl: null,
      createdAt: new Date().toISOString(),
      role: "adult"
    };

    accounts.push(account);
    saveAccounts(accounts);
    setCurrentUser(username);
    addNotification(username, `Welcome ${username}. Your account is active.`, "success");

    return { ok: true, message: "Account created.", account };
  }

  function getProposals() {
    ensureSeededProposals();
    return read(STORE.proposals, []);
  }

  function saveProposals(items) {
    write(STORE.proposals, items);
  }

  function addProposal({ title, category, author, status = "under_review" }) {
    const proposals = getProposals();
    proposals.unshift({
      id: `P-${Math.floor(Math.random() * 9000 + 1000)}`,
      title,
      category,
      author,
      submittedAt: new Date().toISOString(),
      status,
      lawReference: status === "implemented" ? `LAW-${Math.floor(Math.random() * 9999)}` : null
    });
    saveProposals(proposals);
  }

  function getAssemblyRoles() {
    ensureSeededRoles();
    return read(STORE.roles, []);
  }

  function saveAssemblyRoles(items) {
    write(STORE.roles, items);
  }

  function claimAssemblyRole(roleId, username) {
    const account = getAccounts().find(
      (item) => normalizeName(item.username) === normalizeName(username)
    );
    if (!account) {
      return { ok: false, message: "Account not found." };
    }
    const roles = getAssemblyRoles();
    const role = roles.find((item) => item.id === roleId);
    if (!role) {
      return { ok: false, message: "Role not found." };
    }
    if (role.assignedTo && normalizeName(role.assignedTo) !== normalizeName(username)) {
      return { ok: false, message: "Role already assigned." };
    }
    role.assignedTo = username;
    saveAssemblyRoles(roles);
    addNotification(username, `You claimed the role: ${role.title}.`, "success");
    return { ok: true, message: `${username} is now ${role.title}.` };
  }

  function releaseAssemblyRole(roleId, username) {
    const roles = getAssemblyRoles();
    const role = roles.find((item) => item.id === roleId);
    if (!role) {
      return { ok: false, message: "Role not found." };
    }
    if (!role.assignedTo) {
      return { ok: false, message: "Role is already vacant." };
    }
    if (normalizeName(role.assignedTo) !== normalizeName(username)) {
      return { ok: false, message: "Only the assigned member can release this role." };
    }
    role.assignedTo = null;
    saveAssemblyRoles(roles);
    addNotification(username, `You released the role: ${role.title}.`, "notice");
    return { ok: true, message: `${role.title} is now vacant.` };
  }

  function getListings() {
    ensureSeededListings();
    return read(STORE.listings, []);
  }

  function saveListings(items) {
    write(STORE.listings, items);
  }

  function addListing({ type, title, details, scope, author }) {
    const listings = getListings();
    listings.unshift({
      id: `L-${Math.floor(Math.random() * 9000 + 1000)}`,
      type: type === "trade" ? "trade" : "barter",
      title: String(title || "").trim(),
      details: String(details || "").trim(),
      scope: scope || "Neighborhood",
      author,
      status: "open",
      createdAt: new Date().toISOString()
    });
    saveListings(listings);
  }

  function closeListing(listingId, username) {
    const listings = getListings();
    const target = listings.find((item) => item.id === listingId);
    if (!target) {
      return { ok: false, message: "Listing not found." };
    }
    if (normalizeName(target.author) !== normalizeName(username)) {
      return { ok: false, message: "Only the author can close this listing." };
    }
    target.status = "closed";
    target.closedAt = new Date().toISOString();
    saveListings(listings);
    return { ok: true, message: "Listing closed." };
  }

  function getNetworkPosts() {
    ensureSeededNetworkPosts();
    return read(STORE.networkPosts, []);
  }

  function saveNetworkPosts(items) {
    write(STORE.networkPosts, items);
  }

  function addNetworkPost({ author, scope, tags, message }) {
    const posts = getNetworkPosts();
    posts.unshift({
      id: `N-${Math.floor(Math.random() * 9000 + 1000)}`,
      author,
      scope: scope || "Neighborhood",
      tags: Array.isArray(tags) ? tags : [],
      message: String(message || "").trim(),
      createdAt: new Date().toISOString()
    });
    saveNetworkPosts(posts);
  }

  function getSettings() {
    ensureSettings();
    return read(STORE.settings, defaultSettings);
  }

  function getAnnouncements() {
    ensureSeededAnnouncements();
    return read(STORE.announcements, []);
  }

  function saveAnnouncements(items) {
    write(STORE.announcements, items);
  }

  function addAnnouncement({ title, body, authorName, authorUsername }) {
    const announcements = getAnnouncements();
    announcements.unshift({
      id: `A-${Math.floor(Math.random() * 9000 + 1000)}`,
      title: String(title || "").trim(),
      body: String(body || "").trim(),
      author_name: String(authorName || authorUsername || "Unknown"),
      author_username: String(authorUsername || "unknown"),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    });
    saveAnnouncements(announcements);
  }

  function updateSettings(patch) {
    const current = getSettings();
    const next = { ...current, ...patch };
    write(STORE.settings, next);
    return next;
  }

  function getLaunchMilestoneStatus() {
    const settings = getSettings();
    const accounts = getAccounts();
    const roles = getAssemblyRoles();
    const rolesFilled = roles.every((role) => Boolean(role.assignedTo));
    const participantCount = accounts.length + Number(settings.legacyParticipantOffset || 0);
    const verifiedCount = accounts.filter((item) => item.isVerifiedPatriot).length;
    const checks = [
      {
        id: "verification",
        label: "Verification method ratified",
        met: settings.verificationMethodRatified
      },
      {
        id: "framework",
        label: "Foundational governance framework published",
        met: settings.frameworkPublished
      },
      {
        id: "roles",
        label: "Founding Assembly roles filled",
        met: rolesFilled
      },
      {
        id: "safety",
        label: "Public safety standards adopted",
        met: settings.safetyStandardsAdopted
      },
      {
        id: "audit",
        label: "Open audit of counts + voting integrity tests",
        met: settings.auditPublished
      }
    ];
    return {
      participantCount,
      verifiedCount,
      goal: 175000000,
      checks,
      completedChecks: checks.filter((item) => item.met).length
    };
  }

  function getVisitorMap() {
    return read(STORE.profileViews, {});
  }

  function saveVisitorMap(value) {
    write(STORE.profileViews, value);
  }

  function recordProfileVisit(profileOwner, visitor) {
    if (!profileOwner || !visitor || profileOwner === visitor) {
      return;
    }
    const all = getVisitorMap();
    const row = all[profileOwner] || [];
    row.unshift({
      visitor,
      visitedAt: new Date().toISOString()
    });
    all[profileOwner] = row.slice(0, 50);
    saveVisitorMap(all);
  }

  function getProfileVisitors(profileOwner) {
    const all = getVisitorMap();
    return all[profileOwner] || [];
  }

  function setProfilePortrait(username, dataUrl) {
    const accounts = getAccounts();
    const account = accounts.find(
      (item) => normalizeName(item.username) === normalizeName(username)
    );
    if (!account) {
      return { ok: false, message: "Account not found." };
    }
    account.profilePhotoUrl = dataUrl || null;
    saveAccounts(accounts);
    return { ok: true, message: dataUrl ? "Portrait saved." : "Portrait cleared." };
  }

  function updateUserAccess(userId, patch = {}) {
    const accounts = getAccounts();
    const target = accounts.find((item) => String(item.id) === String(userId));
    if (!target) {
      return { ok: false, message: "User not found." };
    }
    if (Object.prototype.hasOwnProperty.call(patch, "is_moderator")) {
      target.isModerator = Boolean(patch.is_moderator);
    }
    if (Object.prototype.hasOwnProperty.call(patch, "is_admin")) {
      target.isAdmin = Boolean(patch.is_admin);
    }
    saveAccounts(accounts);
    return { ok: true, message: "Access updated.", user: target };
  }

  function deleteProfile(userId) {
    const accounts = getAccounts();
    const idx = accounts.findIndex((item) => String(item.id) === String(userId));
    if (idx < 0) {
      return { ok: false, message: "User not found." };
    }
    const [removed] = accounts.splice(idx, 1);
    saveAccounts(accounts);
    const session = getCurrentUser();
    if (session?.username && normalizeName(session.username) === normalizeName(removed.username)) {
      setCurrentUser(null);
    }
    return { ok: true, message: `Deleted profile for ${removed.username}.` };
  }

  function getNotificationMap() {
    return read(STORE.notifications, {});
  }

  function saveNotificationMap(value) {
    write(STORE.notifications, value);
  }

  function addNotification(username, message, type = "info") {
    if (!username || !message) {
      return;
    }
    const all = getNotificationMap();
    const row = all[username] || [];
    row.unshift({
      id: crypto.randomUUID(),
      message,
      type,
      createdAt: new Date().toISOString()
    });
    all[username] = row.slice(0, 80);
    saveNotificationMap(all);
  }

  function getNotifications(username) {
    const all = getNotificationMap();
    return all[username] || [];
  }

  function inspectMinorActivity(parentUsername, childUsername, area = "messages") {
    const accounts = getAccounts();
    const child = accounts.find(
      (item) => normalizeName(item.username) === normalizeName(childUsername)
    );
    if (!child || child.role !== "minor") {
      return { ok: false, message: "Child account not found." };
    }
    if (
      !child.parentLink ||
      normalizeName(child.parentLink) !== normalizeName(parentUsername)
    ) {
      return { ok: false, message: "You are not linked as this minor's guardian." };
    }

    const timestamp = new Date().toISOString();
    addNotification(
      child.username,
      `Parent/guardian ${parentUsername} inspected your ${area} at ${formatDate(timestamp)}.`,
      "notice"
    );
    return { ok: true, message: "Inspection logged and child notified." };
  }

  function approveMinorContact(parentUsername, childUsername, adultUsername) {
    const accounts = getAccounts();
    const child = accounts.find(
      (item) => normalizeName(item.username) === normalizeName(childUsername)
    );
    const adult = accounts.find(
      (item) => normalizeName(item.username) === normalizeName(adultUsername)
    );

    if (!child || child.role !== "minor") {
      return { ok: false, message: "Child account not found." };
    }
    if (!adult || adult.role !== "adult") {
      return { ok: false, message: "Approved contact must be an adult account." };
    }
    if (
      !child.parentLink ||
      normalizeName(child.parentLink) !== normalizeName(parentUsername)
    ) {
      return { ok: false, message: "You are not linked as this child's guardian." };
    }

    const list = Array.isArray(child.approvedAdults) ? child.approvedAdults : [];
    if (!list.some((name) => normalizeName(name) === normalizeName(adult.username))) {
      list.push(adult.username);
      child.approvedAdults = list;
      saveAccounts(accounts);
      addNotification(
        child.username,
        `Parent/guardian ${parentUsername} approved adult contact: ${adult.username}.`,
        "notice"
      );
    }
    return { ok: true, message: `${adult.username} approved for ${child.username}.` };
  }

  function canInteract(senderUsername, receiverUsername) {
    const accounts = getAccounts();
    const sender = accounts.find(
      (item) => normalizeName(item.username) === normalizeName(senderUsername)
    );
    const receiver = accounts.find(
      (item) => normalizeName(item.username) === normalizeName(receiverUsername)
    );

    if (!sender || !receiver) {
      return { ok: false, reason: "Both users must exist." };
    }

    const senderApprovals = Array.isArray(sender.approvedAdults) ? sender.approvedAdults : [];
    const receiverApprovals = Array.isArray(receiver.approvedAdults)
      ? receiver.approvedAdults
      : [];

    if (sender.role === "minor" && receiver.role === "adult") {
      const approved = senderApprovals.some(
        (name) => normalizeName(name) === normalizeName(receiver.username)
      );
      return approved
        ? { ok: true }
        : {
            ok: false,
            reason: "Minor-to-adult interaction blocked unless guardian-approved."
          };
    }

    if (sender.role === "adult" && receiver.role === "minor") {
      const approved = receiverApprovals.some(
        (name) => normalizeName(name) === normalizeName(sender.username)
      );
      return approved
        ? { ok: true }
        : {
            ok: false,
            reason: "Adult-to-minor interaction blocked unless guardian-approved."
          };
    }

    return { ok: true };
  }

  function formatNumber(value) {
    return new Intl.NumberFormat("en-US").format(Number(value || 0));
  }

  function formatDate(value) {
    const dt = new Date(value);
    return new Intl.DateTimeFormat("en-US", {
      dateStyle: "medium",
      timeStyle: "short"
    }).format(dt);
  }

  ensureSeededProposals();
  ensureSeededRoles();
  ensureSeededListings();
  ensureSeededNetworkPosts();
  ensureSettings();
  ensureSeededAnnouncements();

  window.LiquidGovStore = {
    getAccounts,
    saveAccounts,
    getCurrentUser,
    setCurrentUser,
    createAccount,
    getProposals,
    addProposal,
    getAssemblyRoles,
    claimAssemblyRole,
    releaseAssemblyRole,
    getListings,
    addListing,
    closeListing,
    getNetworkPosts,
    addNetworkPost,
    getAnnouncements,
    addAnnouncement,
    getSettings,
    updateSettings,
    getLaunchMilestoneStatus,
    formatNumber,
    formatDate,
    recordProfileVisit,
    getProfileVisitors,
    setProfilePortrait,
    updateUserAccess,
    deleteProfile,
    addNotification,
    getNotifications,
    inspectMinorActivity,
    approveMinorContact,
    canInteract
  };
})();
