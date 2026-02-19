const path = require("path");
const crypto = require("crypto");
const express = require("express");
const {
  db,
  nowIso,
  toLowerName,
  mapAccount,
  mapProposal,
  mapRole,
  mapListing,
  mapNetworkPost,
  mapNotification,
  mapProfileVisit,
  getAccountByUsername,
  listAccounts,
  addNotification,
  getSetting,
  upsertSetting
} = require("./db");

const app = express();
const PORT = Number(process.env.PORT || 3000);

app.use(express.json({ limit: "1mb" }));

function randomFourDigit() {
  return Math.floor(Math.random() * 9000 + 1000);
}

function readToken(req) {
  const auth = req.headers.authorization;
  if (auth && auth.startsWith("Bearer ")) {
    return auth.slice(7).trim();
  }
  if (req.headers["x-session-token"]) {
    return String(req.headers["x-session-token"]);
  }
  if (req.query.token) {
    return String(req.query.token);
  }
  if (req.body && req.body.token) {
    return String(req.body.token);
  }
  return null;
}

function getSessionUser(token) {
  if (!token) {
    return null;
  }
  const row = db
    .prepare(
      `
        SELECT a.*
        FROM sessions s
        JOIN accounts a ON a.username = s.username
        WHERE s.token = ?
      `
    )
    .get(token);
  return mapAccount(row);
}

function requireAuth(req, res, next) {
  const token = readToken(req);
  const user = getSessionUser(token);
  if (!user) {
    res.status(401).json({ ok: false, message: "Authentication required." });
    return;
  }
  req.authToken = token;
  req.user = user;
  next();
}

function getCoreSettings() {
  return getSetting("core", {
    verificationMethodRatified: false,
    frameworkPublished: false,
    safetyStandardsAdopted: true,
    auditPublished: false
  });
}

function createSession(username) {
  const token = `SE-${crypto.randomUUID()}`;
  db.prepare(
    `
      INSERT INTO sessions (token, username, created_at)
      VALUES (?, ?, ?)
    `
  ).run(token, username, nowIso());
  return token;
}

function createUniqueId(prefix, tableName) {
  let candidate = `${prefix}-${randomFourDigit()}`;
  let loops = 0;
  while (
    db.prepare(`SELECT 1 AS present FROM ${tableName} WHERE id = ?`).get(candidate) &&
    loops < 10
  ) {
    candidate = `${prefix}-${randomFourDigit()}`;
    loops += 1;
  }
  if (loops >= 10) {
    candidate = `${prefix}-${Date.now()}`;
  }
  return candidate;
}

function computeMilestone() {
  const settings = getCoreSettings();
  const accountCounts = db
    .prepare(
      `
      SELECT
        COUNT(*) AS participants,
        SUM(CASE WHEN is_verified_patriot = 1 THEN 1 ELSE 0 END) AS verified
      FROM accounts
    `
    )
    .get();
  const roles = db.prepare("SELECT * FROM assembly_roles ORDER BY id").all();
  const rolesFilled =
    roles.length > 0 && roles.every((role) => typeof role.assigned_to === "string" && role.assigned_to.length > 0);

  const checks = [
    {
      id: "verification",
      label: "Verification method ratified",
      met: Boolean(settings.verificationMethodRatified)
    },
    {
      id: "framework",
      label: "Foundational governance framework published",
      met: Boolean(settings.frameworkPublished)
    },
    {
      id: "roles",
      label: "Founding Assembly roles filled",
      met: rolesFilled
    },
    {
      id: "safety",
      label: "Public safety standards adopted",
      met: Boolean(settings.safetyStandardsAdopted)
    },
    {
      id: "audit",
      label: "Open audit of counts + voting integrity tests",
      met: Boolean(settings.auditPublished)
    }
  ];

  return {
    participantCount: Number(accountCounts.participants || 0),
    verifiedCount: Number(accountCounts.verified || 0),
    goal: 175000000,
    checks,
    completedChecks: checks.filter((item) => item.met).length
  };
}

function canInteractByRule(senderUsername, receiverUsername) {
  const sender = getAccountByUsername(senderUsername);
  const receiver = getAccountByUsername(receiverUsername);
  if (!sender || !receiver) {
    return { ok: false, reason: "Both users must exist." };
  }

  const senderApprovals = Array.isArray(sender.approvedAdults) ? sender.approvedAdults : [];
  const receiverApprovals = Array.isArray(receiver.approvedAdults)
    ? receiver.approvedAdults
    : [];

  if (sender.role === "minor" && receiver.role === "adult") {
    const approved = senderApprovals.some(
      (name) => toLowerName(name) === toLowerName(receiver.username)
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
      (name) => toLowerName(name) === toLowerName(sender.username)
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

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, service: "liquidgov-api" });
});

app.post("/api/auth/register", (req, res) => {
  const username = String(req.body?.username || "").trim();
  const age = Number(req.body?.age);
  const parentLink = String(req.body?.parentLink || "").trim();
  const wantsVerification = Boolean(req.body?.wantsVerification);
  const pledge = Boolean(req.body?.pledge);

  if (username.length < 2) {
    res.status(400).json({ ok: false, message: "Display name must be at least 2 characters." });
    return;
  }
  if (!Number.isFinite(age) || age < 1 || age > 120) {
    res.status(400).json({ ok: false, message: "Please provide a valid age between 1 and 120." });
    return;
  }

  const duplicate = getAccountByUsername(username);
  if (duplicate) {
    res.status(409).json({ ok: false, message: "That display name is already in use." });
    return;
  }

  let parentCanonical = null;
  let isVerifiedPatriot = false;
  let verificationMessage = "Participant account created.";

  if (wantsVerification) {
    if (!pledge) {
      res.status(400).json({
        ok: false,
        message: "To verify now, please confirm the peaceful transition pledge."
      });
      return;
    }

    if (age < 18) {
      if (!parentLink) {
        res.status(400).json({
          ok: false,
          message: "Under 18 accounts need a linked parent/guardian username before verification."
        });
        return;
      }
      const parent = getAccountByUsername(parentLink);
      if (!parent) {
        res.status(400).json({
          ok: false,
          message: "Parent/guardian account not found. Create or link a parent account first."
        });
        return;
      }
      parentCanonical = parent.username;
      isVerifiedPatriot = true;
      verificationMessage = "Verified Patriot (Minor) account created.";
    } else {
      isVerifiedPatriot = true;
      verificationMessage = "Verified Patriot account created.";
    }
  }

  const role = age < 18 ? "minor" : "adult";
  const createdAt = nowIso();
  db.prepare(
    `
      INSERT INTO accounts (
        username,
        lower_username,
        age,
        parent_link,
        approved_adults,
        is_verified_patriot,
        pledge_signed,
        role,
        created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `
  ).run(
    username,
    toLowerName(username),
    age,
    parentCanonical || (parentLink ? parentLink : null),
    JSON.stringify([]),
    isVerifiedPatriot ? 1 : 0,
    pledge ? 1 : 0,
    role,
    createdAt
  );

  const token = createSession(username);
  addNotification(username, `Welcome ${username}. Your account is active.`, "success");

  res.status(201).json({
    ok: true,
    message: verificationMessage,
    token,
    account: getAccountByUsername(username)
  });
});

app.post("/api/auth/login", (req, res) => {
  const username = String(req.body?.username || "").trim();
  const account = getAccountByUsername(username);
  if (!account) {
    res.status(404).json({ ok: false, message: "Account not found." });
    return;
  }
  const token = createSession(account.username);
  res.json({ ok: true, token, account });
});

app.post("/api/auth/logout", (req, res) => {
  const token = readToken(req);
  if (token) {
    db.prepare("DELETE FROM sessions WHERE token = ?").run(token);
  }
  res.json({ ok: true });
});

app.get("/api/session/current", (req, res) => {
  const token = readToken(req);
  const user = getSessionUser(token);
  res.json({ ok: true, user });
});

app.get("/api/accounts", (_req, res) => {
  res.json({ ok: true, accounts: listAccounts() });
});

app.get("/api/stats", (_req, res) => {
  const milestone = computeMilestone();
  res.json({
    ok: true,
    participants: milestone.participantCount,
    verifiedPatriots: milestone.verifiedCount,
    goal: milestone.goal
  });
});

app.get("/api/settings", (_req, res) => {
  res.json({ ok: true, settings: getCoreSettings() });
});

app.patch("/api/settings", requireAuth, (req, res) => {
  const current = getCoreSettings();
  const patch = req.body || {};
  const next = {
    ...current,
    verificationMethodRatified: Boolean(patch.verificationMethodRatified ?? current.verificationMethodRatified),
    frameworkPublished: Boolean(patch.frameworkPublished ?? current.frameworkPublished),
    safetyStandardsAdopted: Boolean(patch.safetyStandardsAdopted ?? current.safetyStandardsAdopted),
    auditPublished: Boolean(patch.auditPublished ?? current.auditPublished)
  };
  upsertSetting("core", next);
  res.json({ ok: true, settings: next });
});

app.get("/api/milestone", (_req, res) => {
  res.json({ ok: true, milestone: computeMilestone() });
});

app.get("/api/proposals", (_req, res) => {
  const rows = db.prepare("SELECT * FROM proposals ORDER BY submitted_at DESC").all();
  res.json({ ok: true, proposals: rows.map(mapProposal) });
});

app.post("/api/proposals", requireAuth, (req, res) => {
  const title = String(req.body?.title || "").trim();
  const category = String(req.body?.category || "Governance").trim();
  const status = String(req.body?.status || "under_review").trim();
  if (!title) {
    res.status(400).json({ ok: false, message: "Title is required." });
    return;
  }

  const id = createUniqueId("P", "proposals");
  const lawReference = status === "implemented" ? `LAW-${randomFourDigit()}` : null;
  const proposal = {
    id,
    title,
    category,
    author: req.user.username,
    submittedAt: nowIso(),
    status,
    lawReference
  };

  db.prepare(
    `
      INSERT INTO proposals (id, title, category, author, submitted_at, status, law_reference)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `
  ).run(
    proposal.id,
    proposal.title,
    proposal.category,
    proposal.author,
    proposal.submittedAt,
    proposal.status,
    proposal.lawReference
  );
  res.status(201).json({ ok: true, proposal });
});

app.get("/api/roles", (_req, res) => {
  const rows = db.prepare("SELECT * FROM assembly_roles ORDER BY id").all();
  res.json({ ok: true, roles: rows.map(mapRole) });
});

app.post("/api/roles/claim", requireAuth, (req, res) => {
  const roleId = String(req.body?.roleId || "").trim();
  const role = db.prepare("SELECT * FROM assembly_roles WHERE id = ?").get(roleId);
  if (!role) {
    res.status(404).json({ ok: false, message: "Role not found." });
    return;
  }
  if (role.assigned_to && toLowerName(role.assigned_to) !== toLowerName(req.user.username)) {
    res.status(409).json({ ok: false, message: "Role already assigned." });
    return;
  }
  db.prepare("UPDATE assembly_roles SET assigned_to = ? WHERE id = ?").run(req.user.username, roleId);
  addNotification(req.user.username, `You claimed the role: ${role.title}.`, "success");
  res.json({ ok: true, message: `${req.user.username} is now ${role.title}.` });
});

app.post("/api/roles/release", requireAuth, (req, res) => {
  const roleId = String(req.body?.roleId || "").trim();
  const role = db.prepare("SELECT * FROM assembly_roles WHERE id = ?").get(roleId);
  if (!role) {
    res.status(404).json({ ok: false, message: "Role not found." });
    return;
  }
  if (!role.assigned_to) {
    res.status(400).json({ ok: false, message: "Role is already vacant." });
    return;
  }
  if (toLowerName(role.assigned_to) !== toLowerName(req.user.username)) {
    res
      .status(403)
      .json({ ok: false, message: "Only the assigned member can release this role." });
    return;
  }
  db.prepare("UPDATE assembly_roles SET assigned_to = NULL WHERE id = ?").run(roleId);
  addNotification(req.user.username, `You released the role: ${role.title}.`, "notice");
  res.json({ ok: true, message: `${role.title} is now vacant.` });
});

app.get("/api/listings", (_req, res) => {
  const rows = db.prepare("SELECT * FROM listings ORDER BY created_at DESC").all();
  res.json({ ok: true, listings: rows.map(mapListing) });
});

app.post("/api/listings", requireAuth, (req, res) => {
  const type = req.body?.type === "trade" ? "trade" : "barter";
  const title = String(req.body?.title || "").trim();
  const details = String(req.body?.details || "").trim();
  const scope = String(req.body?.scope || "Neighborhood");
  if (!title || !details) {
    res.status(400).json({ ok: false, message: "Provide title and details." });
    return;
  }

  const listing = {
    id: createUniqueId("L", "listings"),
    type,
    title,
    details,
    scope,
    author: req.user.username,
    status: "open",
    createdAt: nowIso(),
    closedAt: null
  };

  db.prepare(
    `
      INSERT INTO listings (id, type, title, details, scope, author, status, created_at, closed_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
    `
  ).run(
    listing.id,
    listing.type,
    listing.title,
    listing.details,
    listing.scope,
    listing.author,
    listing.status,
    listing.createdAt
  );

  res.status(201).json({ ok: true, listing });
});

app.post("/api/listings/:listingId/close", requireAuth, (req, res) => {
  const listingId = String(req.params.listingId || "");
  const listing = db.prepare("SELECT * FROM listings WHERE id = ?").get(listingId);
  if (!listing) {
    res.status(404).json({ ok: false, message: "Listing not found." });
    return;
  }
  if (toLowerName(listing.author) !== toLowerName(req.user.username)) {
    res.status(403).json({ ok: false, message: "Only the author can close this listing." });
    return;
  }
  db.prepare("UPDATE listings SET status = 'closed', closed_at = ? WHERE id = ?").run(
    nowIso(),
    listingId
  );
  res.json({ ok: true, message: "Listing closed." });
});

app.get("/api/network-posts", (_req, res) => {
  const rows = db.prepare("SELECT * FROM network_posts ORDER BY created_at DESC").all();
  res.json({ ok: true, posts: rows.map(mapNetworkPost) });
});

app.post("/api/network-posts", requireAuth, (req, res) => {
  const scope = String(req.body?.scope || "Neighborhood");
  const message = String(req.body?.message || "").trim();
  if (!message) {
    res.status(400).json({ ok: false, message: "Write a networking message." });
    return;
  }
  const tags = Array.isArray(req.body?.tags)
    ? req.body.tags.map((item) => String(item).trim().toLowerCase()).filter(Boolean).slice(0, 8)
    : [];
  const post = {
    id: createUniqueId("N", "network_posts"),
    author: req.user.username,
    scope,
    tags,
    message,
    createdAt: nowIso()
  };
  db.prepare(
    `
      INSERT INTO network_posts (id, author, scope, tags, message, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `
  ).run(post.id, post.author, post.scope, JSON.stringify(post.tags), post.message, post.createdAt);
  res.status(201).json({ ok: true, post });
});

app.get("/api/notifications/:username", requireAuth, (req, res) => {
  const username = String(req.params.username || "").trim();
  if (toLowerName(username) !== toLowerName(req.user.username)) {
    res.status(403).json({ ok: false, message: "Can only access your own notifications." });
    return;
  }
  const rows = db
    .prepare("SELECT * FROM notifications WHERE username = ? ORDER BY created_at DESC LIMIT 80")
    .all(req.user.username);
  res.json({ ok: true, notifications: rows.map(mapNotification) });
});

app.post("/api/notifications", requireAuth, (req, res) => {
  const username = String(req.body?.username || req.user.username).trim();
  const message = String(req.body?.message || "").trim();
  const type = String(req.body?.type || "info").trim();
  if (!message) {
    res.status(400).json({ ok: false, message: "Notification message is required." });
    return;
  }
  const target = getAccountByUsername(username);
  if (!target) {
    res.status(404).json({ ok: false, message: "Notification target not found." });
    return;
  }
  addNotification(target.username, message, type);
  res.json({ ok: true });
});

app.post("/api/profile-visits", requireAuth, (req, res) => {
  const profileOwner = String(req.body?.profileOwner || "").trim();
  if (!profileOwner) {
    res.status(400).json({ ok: false, message: "profileOwner is required." });
    return;
  }
  const owner = getAccountByUsername(profileOwner);
  if (!owner) {
    res.status(404).json({ ok: false, message: "Profile owner not found." });
    return;
  }
  if (toLowerName(owner.username) === toLowerName(req.user.username)) {
    res.json({ ok: true, message: "Self-visit ignored." });
    return;
  }

  db.prepare(
    `
      INSERT INTO profile_visits (profile_owner, visitor, visited_at)
      VALUES (?, ?, ?)
    `
  ).run(owner.username, req.user.username, nowIso());
  addNotification(owner.username, `${req.user.username} viewed your profile.`, "notice");
  res.json({ ok: true, message: "Visit logged." });
});

app.get("/api/profile-visits/:username", requireAuth, (req, res) => {
  const username = String(req.params.username || "").trim();
  if (toLowerName(username) !== toLowerName(req.user.username)) {
    res.status(403).json({ ok: false, message: "Can only access your own visitor log." });
    return;
  }
  const rows = db
    .prepare(
      `
        SELECT visitor, visited_at
        FROM profile_visits
        WHERE profile_owner = ?
        ORDER BY visited_at DESC
        LIMIT 50
      `
    )
    .all(req.user.username);
  res.json({ ok: true, visitors: rows.map(mapProfileVisit) });
});

app.post("/api/minor/inspect", requireAuth, (req, res) => {
  const childUsername = String(req.body?.childUsername || "").trim();
  const area = String(req.body?.area || "messages");
  const child = getAccountByUsername(childUsername);
  if (!child || child.role !== "minor") {
    res.status(404).json({ ok: false, message: "Child account not found." });
    return;
  }
  if (
    !child.parentLink ||
    toLowerName(child.parentLink) !== toLowerName(req.user.username)
  ) {
    res.status(403).json({ ok: false, message: "You are not linked as this minor's guardian." });
    return;
  }
  const message = `Parent/guardian ${req.user.username} inspected your ${area} at ${nowIso()}.`;
  addNotification(child.username, message, "notice");
  res.json({ ok: true, message: "Inspection logged and child notified." });
});

app.post("/api/minor/approve-contact", requireAuth, (req, res) => {
  const childUsername = String(req.body?.childUsername || "").trim();
  const adultUsername = String(req.body?.adultUsername || "").trim();
  const child = getAccountByUsername(childUsername);
  const adult = getAccountByUsername(adultUsername);

  if (!child || child.role !== "minor") {
    res.status(404).json({ ok: false, message: "Child account not found." });
    return;
  }
  if (!adult || adult.role !== "adult") {
    res.status(400).json({ ok: false, message: "Approved contact must be an adult account." });
    return;
  }
  if (
    !child.parentLink ||
    toLowerName(child.parentLink) !== toLowerName(req.user.username)
  ) {
    res.status(403).json({ ok: false, message: "You are not linked as this child's guardian." });
    return;
  }

  const approvals = Array.isArray(child.approvedAdults) ? child.approvedAdults.slice() : [];
  if (!approvals.some((name) => toLowerName(name) === toLowerName(adult.username))) {
    approvals.push(adult.username);
    db.prepare("UPDATE accounts SET approved_adults = ? WHERE id = ?").run(
      JSON.stringify(approvals),
      child.id
    );
    addNotification(
      child.username,
      `Parent/guardian ${req.user.username} approved adult contact: ${adult.username}.`,
      "notice"
    );
  }
  res.json({ ok: true, message: `${adult.username} approved for ${child.username}.` });
});

app.get("/api/minor/can-interact", (req, res) => {
  const sender = String(req.query.sender || "").trim();
  const receiver = String(req.query.receiver || "").trim();
  const result = canInteractByRule(sender, receiver);
  res.json(result);
});

app.use(express.static(path.join(__dirname, ".."), { index: "index.html" }));

app.get("/", (_req, res) => {
  res.sendFile(path.join(__dirname, "..", "index.html"));
});

app.listen(PORT, () => {
  console.log(`LiquidGov API server running on http://localhost:${PORT}`);
});
