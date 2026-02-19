(function initLiquidGovStore() {
  const STORE = {
    accounts: "liquidgov.accounts",
    proposals: "liquidgov.proposals",
    session: "liquidgov.session",
    profileViews: "liquidgov.profileViews",
    notifications: "liquidgov.notifications"
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

  function getAccounts() {
    return read(STORE.accounts, []);
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

  function createAccount(payload) {
    const accounts = getAccounts();
    const username = String(payload.username || "").trim();
    const age = Number(payload.age);
    const parentLink = String(payload.parentLink || "").trim();
    const wantsVerification = Boolean(payload.wantsVerification);
    const pledge = Boolean(payload.pledge);

    if (username.length < 2) {
      return { ok: false, message: "Display name must be at least 2 characters." };
    }
    if (!Number.isFinite(age) || age < 1 || age > 120) {
      return { ok: false, message: "Please provide a valid age between 1 and 120." };
    }

    const duplicate = accounts.find(
      (item) => normalizeName(item.username) === normalizeName(username)
    );
    if (duplicate) {
      return { ok: false, message: "That display name is already in use." };
    }

    let isVerifiedPatriot = false;
    let verificationMessage = "Participant account created.";

    if (wantsVerification) {
      if (!pledge) {
        return {
          ok: false,
          message: "To verify now, please confirm the peaceful transition pledge."
        };
      }

      if (age < 18) {
        if (!parentLink) {
          return {
            ok: false,
            message:
              "Under 18 accounts need a linked parent/guardian username before verification."
          };
        }
        const parent = accounts.find(
          (item) => normalizeName(item.username) === normalizeName(parentLink)
        );
        if (!parent) {
          return {
            ok: false,
            message:
              "Parent/guardian account not found. Create or link a parent account first."
          };
        }
        isVerifiedPatriot = true;
        verificationMessage = "Verified Patriot (Minor) account created.";
      } else {
        isVerifiedPatriot = true;
        verificationMessage = "Verified Patriot account created.";
      }
    }

    const account = {
      id: crypto.randomUUID(),
      username,
      age,
      parentLink: parentLink || null,
      approvedAdults: [],
      isVerifiedPatriot,
      pledgeSigned: pledge,
      createdAt: new Date().toISOString(),
      role: age < 18 ? "minor" : "adult"
    };

    accounts.push(account);
    saveAccounts(accounts);
    setCurrentUser(username);
    addNotification(username, `Welcome ${username}. Your account is active.`, "success");

    return { ok: true, message: verificationMessage, account };
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

  window.LiquidGovStore = {
    getAccounts,
    saveAccounts,
    getCurrentUser,
    setCurrentUser,
    createAccount,
    getProposals,
    addProposal,
    formatNumber,
    formatDate,
    recordProfileVisit,
    getProfileVisitors,
    addNotification,
    getNotifications,
    inspectMinorActivity,
    approveMinorContact,
    canInteract
  };
})();
