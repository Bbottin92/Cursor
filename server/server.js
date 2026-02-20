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
  mapAnnouncement,
  getAccountByUsername,
  listAccounts,
  addNotification,
  addAnnouncement,
  listAnnouncements,
  getSetting,
  upsertSetting
} = require("./db");

const app = express();
const PORT = Number(process.env.PORT || 3000);

app.use(express.json({ limit: "1mb" }));

function randomFourDigit() {
  return Math.floor(Math.random() * 9000 + 1000);
}

function hashPassword(password) {
  return crypto.createHash("sha256").update(String(password || "")).digest("hex");
}

const ADMIN_BOOTSTRAP_USERNAMES = String(process.env.ADMIN_USERNAMES || "Brandon Bottin")
  .split(",")
  .map((item) => toLowerName(item))
  .filter(Boolean);

function isBootstrapAdminUsername(username) {
  return ADMIN_BOOTSTRAP_USERNAMES.includes(toLowerName(username));
}

function ensureBootstrapAdminRecords() {
  if (!ADMIN_BOOTSTRAP_USERNAMES.length) {
    return;
  }
  const placeholders = ADMIN_BOOTSTRAP_USERNAMES.map(() => "?").join(", ");
  db.prepare(`UPDATE accounts SET is_admin = 1 WHERE lower_username IN (${placeholders})`).run(
    ...ADMIN_BOOTSTRAP_USERNAMES
  );
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

function isAdminUser(user) {
  return Boolean(user?.isAdmin) || isBootstrapAdminUsername(user?.username);
}

function requireAdmin(req, res, next) {
  if (!isAdminUser(req.user)) {
    res.status(403).json({ ok: false, message: "Admin access required." });
    return;
  }
  next();
}

function getCoreSettings() {
  return getSetting("core", {
    verificationMethodRatified: false,
    frameworkPublished: false,
    safetyStandardsAdopted: true,
    auditPublished: false,
    legacyParticipantOffset: 0
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
    participantCount:
      Number(accountCounts.participants || 0) + Number(settings.legacyParticipantOffset || 0),
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

function toLegacyUser(account) {
  if (!account) {
    return null;
  }
  return {
    id: account.id,
    name: account.username,
    email: account.email || null,
    is_moderator: account.isModerator ? 1 : 0,
    is_admin: isAdminUser(account) ? 1 : 0,
    trust_level: account.trustLevel || 1,
    credits: account.credits || 0,
    created_at: account.createdAt,
    profile_photo_url: account.profilePhotoUrl || null,
    bio: account.bio || "",
    skills: Array.isArray(account.skills) ? account.skills : [],
    social_services: Array.isArray(account.socialServices) ? account.socialServices : []
  };
}

function getAccountById(id) {
  const row = db.prepare("SELECT * FROM accounts WHERE id = ?").get(Number(id));
  return mapAccount(row);
}

const SOCIAL_SERVICE_CATALOG = [
  { id: "food-support", name: "Food support" },
  { id: "transport-help", name: "Transportation help" },
  { id: "job-assistance", name: "Job assistance" },
  { id: "legal-aid", name: "Legal aid" },
  { id: "housing-support", name: "Housing support" },
  { id: "mental-health", name: "Mental health support" }
];

ensureBootstrapAdminRecords();

function createAccountFromPayload(payload, options = {}) {
  const requireAge = options.requireAge !== false;
  const defaultAge = Number(options.defaultAge || 18);
  const requirePassword = options.requirePassword !== false;
  const username = String(payload?.username || payload?.name || "").trim();
  const emailRaw = payload?.email ? String(payload.email).trim() : "";
  const email = emailRaw ? emailRaw.slice(0, 255) : null;
  const password = String(payload?.password || payload?.password1 || "").trim();
  const passwordConfirmRaw = payload?.password2 ?? payload?.passwordConfirm;
  const passwordConfirm =
    passwordConfirmRaw === undefined || passwordConfirmRaw === null
      ? password
      : String(passwordConfirmRaw).trim();
  const requestedAge = Number(payload?.age);
  const age = Number.isFinite(requestedAge) && requestedAge >= 1 && requestedAge <= 120
    ? requestedAge
    : defaultAge;

  if (username.length < 2) {
    return {
      ok: false,
      status: 400,
      message: "Username must be at least 2 characters."
    };
  }
  if (requirePassword && password.length < 6) {
    return {
      ok: false,
      status: 400,
      message: "Password must be at least 6 characters."
    };
  }
  if (passwordConfirm !== password) {
    return {
      ok: false,
      status: 400,
      message: "Passwords do not match."
    };
  }
  if (requireAge && (!Number.isFinite(requestedAge) || requestedAge < 1 || requestedAge > 120)) {
    return {
      ok: false,
      status: 400,
      message: "Please provide a valid age between 1 and 120."
    };
  }

  const duplicate = getAccountByUsername(username);
  if (duplicate) {
    return { ok: false, status: 409, message: "That username is already in use." };
  }

  const role = "adult";
  const isAdmin = isBootstrapAdminUsername(username);
  const createdAt = nowIso();
  db.prepare(
    `
      INSERT INTO accounts (
        username,
        lower_username,
        email,
        password_hash,
        age,
        parent_link,
        approved_adults,
        is_verified_patriot,
        pledge_signed,
        is_admin,
        role,
        created_at,
        bio,
        skills,
        social_services
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `
  ).run(
    username,
    toLowerName(username),
    email,
    hashPassword(password),
    age,
    null,
    JSON.stringify([]),
    0,
    0,
    isAdmin ? 1 : 0,
    role,
    createdAt,
    "",
    JSON.stringify([]),
    JSON.stringify([])
  );

  const account = getAccountByUsername(username);
  const token = createSession(username);
  addNotification(username, `Welcome ${username}. Your account is active.`, "success");

  return {
    ok: true,
    status: 201,
    message: "Account created.",
    token,
    account
  };
}

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, service: "liquidgov-api" });
});

app.post("/api/auth/register", (req, res) => {
  const result = createAccountFromPayload(req.body || {}, { requireAge: false, defaultAge: 18 });
  if (!result.ok) {
    res.status(result.status).json({ ok: false, message: result.message });
    return;
  }
  res.status(result.status).json({
    ok: true,
    message: result.message,
    token: result.token,
    account: result.account,
    user: toLegacyUser(result.account)
  });
});

// Legacy-compatible signup endpoint used by earlier LiquidGov pages.
app.post("/api/auth/signup", (req, res) => {
  const result = createAccountFromPayload(req.body || {}, { requireAge: false, defaultAge: 18 });
  if (!result.ok) {
    res.status(result.status).json({ error: result.message });
    return;
  }
  res.status(result.status).json({
    token: result.token,
    user: toLegacyUser(result.account)
  });
});

app.post("/api/auth/login", (req, res) => {
  const username = String(req.body?.username || req.body?.name || "").trim();
  const password = String(req.body?.password || "").trim();
  const accountRow = db
    .prepare("SELECT * FROM accounts WHERE lower_username = ?")
    .get(toLowerName(username));
  if (!accountRow) {
    res.status(404).json({ ok: false, message: "Account not found.", error: "Account not found." });
    return;
  }

  if (!accountRow.is_admin && isBootstrapAdminUsername(accountRow.username)) {
    db.prepare("UPDATE accounts SET is_admin = 1 WHERE id = ?").run(accountRow.id);
    accountRow.is_admin = 1;
  }

  const passwordHash = String(accountRow.password_hash || "").trim();
  if (passwordHash && password && hashPassword(password) !== passwordHash) {
      res.status(401).json({
        ok: false,
        message: "Invalid username or password.",
        error: "Invalid username or password."
      });
      return;
  }

  const account = mapAccount(accountRow);
  const token = createSession(account.username);
  res.json({ ok: true, token, account, user: toLegacyUser(account) });
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

// Legacy-compatible auth/me endpoint.
app.get("/api/auth/me", (req, res) => {
  const token = readToken(req);
  if (!token) {
    res.status(401).json({ error: "Access token required" });
    return;
  }
  const user = getSessionUser(token);
  if (!user) {
    res.status(401).json({ error: "Invalid or expired token" });
    return;
  }
  res.json({ user: toLegacyUser(user) });
});

app.post("/api/auth/change-name", requireAuth, (req, res) => {
  const newName = String(req.body?.name || req.body?.new_name || "").trim();
  if (newName.length < 2) {
    res.status(400).json({ error: "New name must be at least 2 characters." });
    return;
  }
  const existing = getAccountByUsername(newName);
  if (existing && Number(existing.id) !== Number(req.user.id)) {
    res.status(409).json({ error: "Display name already in use." });
    return;
  }

  const previousName = req.user.username;
  db.prepare("UPDATE accounts SET username = ?, lower_username = ? WHERE id = ?").run(
    newName,
    toLowerName(newName),
    req.user.id
  );
  db.prepare("UPDATE sessions SET username = ? WHERE username = ?").run(newName, previousName);
  db.prepare("UPDATE announcements SET author_username = ?, author_name = ? WHERE author_username = ?").run(
    newName,
    newName,
    previousName
  );
  res.json({ ok: true, user: toLegacyUser(getAccountById(req.user.id)) });
});

app.post("/api/auth/change-password", requireAuth, (req, res) => {
  const newPassword = String(req.body?.newPassword || req.body?.password || "").trim();
  if (newPassword.length < 6) {
    res.status(400).json({ ok: false, message: "Password must be at least 6 characters." });
    return;
  }
  db.prepare("UPDATE accounts SET password_hash = ? WHERE id = ?").run(
    hashPassword(newPassword),
    req.user.id
  );
  res.json({ ok: true, message: "Password updated." });
});

app.post("/api/auth/delete", requireAuth, (req, res) => {
  db.prepare("DELETE FROM sessions WHERE username = ?").run(req.user.username);
  db.prepare("DELETE FROM accounts WHERE id = ?").run(req.user.id);
  res.json({ ok: true });
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

// Legacy-compatible participant count endpoint.
app.get("/api/stats/participants", (_req, res) => {
  const count = db.prepare("SELECT COUNT(*) AS count FROM accounts").get().count;
  const offset = Number(getCoreSettings().legacyParticipantOffset || 0);
  res.json({ count: Number(count || 0) + offset });
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
    auditPublished: Boolean(patch.auditPublished ?? current.auditPublished),
    legacyParticipantOffset: Number(
      patch.legacyParticipantOffset ?? current.legacyParticipantOffset ?? 0
    )
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

app.patch("/api/proposals/:proposalId", requireAuth, (req, res) => {
  const proposalId = String(req.params.proposalId || "").trim();
  const current = db.prepare("SELECT * FROM proposals WHERE id = ?").get(proposalId);
  if (!current) {
    res.status(404).json({ ok: false, message: "Proposal not found." });
    return;
  }
  const canModerate =
    isAdminUser(req.user) || toLowerName(current.author) === toLowerName(req.user.username);
  if (!canModerate) {
    res.status(403).json({ ok: false, message: "Not permitted to edit this proposal." });
    return;
  }
  const body = req.body || {};
  const nextTitle = String(body.title ?? current.title).trim();
  const nextCategory = String(body.category ?? current.category).trim();
  const nextStatus = String(body.status ?? current.status).trim();
  const nextLawReference =
    body.lawReference === null || body.law_reference === null
      ? null
      : String(body.lawReference ?? body.law_reference ?? current.law_reference ?? "").trim() || null;
  if (!nextTitle) {
    res.status(400).json({ ok: false, message: "Title is required." });
    return;
  }
  db.prepare(
    `
      UPDATE proposals
      SET title = ?, category = ?, status = ?, law_reference = ?
      WHERE id = ?
    `
  ).run(nextTitle, nextCategory, nextStatus, nextLawReference, proposalId);
  const updated = db.prepare("SELECT * FROM proposals WHERE id = ?").get(proposalId);
  res.json({ ok: true, proposal: mapProposal(updated) });
});

app.delete("/api/proposals/:proposalId", requireAuth, (req, res) => {
  const proposalId = String(req.params.proposalId || "").trim();
  const current = db.prepare("SELECT * FROM proposals WHERE id = ?").get(proposalId);
  if (!current) {
    res.status(404).json({ ok: false, message: "Proposal not found." });
    return;
  }
  const canModerate =
    isAdminUser(req.user) || toLowerName(current.author) === toLowerName(req.user.username);
  if (!canModerate) {
    res.status(403).json({ ok: false, message: "Not permitted to delete this proposal." });
    return;
  }
  db.prepare("DELETE FROM proposals WHERE id = ?").run(proposalId);
  res.json({ ok: true, message: "Proposal deleted." });
});

app.get("/api/announcements", (_req, res) => {
  const announcements = listAnnouncements(100);
  res.json({ announcements });
});

app.post("/api/announcements", requireAuth, (req, res) => {
  const title = String(req.body?.title || "").trim();
  const body = String(req.body?.body || "").trim();
  if (!title || !body) {
    res.status(400).json({ ok: false, message: "Title and body are required." });
    return;
  }
  const id = addAnnouncement({
    title,
    body,
    authorUsername: req.user.username,
    authorName: req.user.username
  });
  const created = db.prepare("SELECT * FROM announcements WHERE id = ?").get(id);
  res.status(201).json({ ok: true, announcement: mapAnnouncement(created) });
});

app.patch("/api/announcements/:announcementId", requireAuth, (req, res) => {
  const announcementId = String(req.params.announcementId || "").trim();
  const current = db.prepare("SELECT * FROM announcements WHERE id = ?").get(announcementId);
  if (!current) {
    res.status(404).json({ ok: false, message: "Announcement not found." });
    return;
  }
  const canModerate =
    isAdminUser(req.user) ||
    toLowerName(current.author_username) === toLowerName(req.user.username);
  if (!canModerate) {
    res.status(403).json({ ok: false, message: "Not permitted to edit this announcement." });
    return;
  }
  const body = req.body || {};
  const nextTitle = String(body.title ?? current.title).trim();
  const nextBody = String(body.body ?? current.body).trim();
  if (!nextTitle || !nextBody) {
    res.status(400).json({ ok: false, message: "Title and body are required." });
    return;
  }
  db.prepare(
    `
      UPDATE announcements
      SET title = ?, body = ?, updated_at = ?
      WHERE id = ?
    `
  ).run(nextTitle, nextBody, nowIso(), announcementId);
  const updated = db.prepare("SELECT * FROM announcements WHERE id = ?").get(announcementId);
  res.json({ ok: true, announcement: mapAnnouncement(updated) });
});

app.delete("/api/announcements/:announcementId", requireAuth, (req, res) => {
  const announcementId = String(req.params.announcementId || "").trim();
  const current = db.prepare("SELECT * FROM announcements WHERE id = ?").get(announcementId);
  if (!current) {
    res.status(404).json({ ok: false, message: "Announcement not found." });
    return;
  }
  const canModerate =
    isAdminUser(req.user) ||
    toLowerName(current.author_username) === toLowerName(req.user.username);
  if (!canModerate) {
    res.status(403).json({ ok: false, message: "Not permitted to delete this announcement." });
    return;
  }
  db.prepare("DELETE FROM announcements WHERE id = ?").run(announcementId);
  res.json({ ok: true, message: "Announcement deleted." });
});

// Legacy forum feed compatibility: map proposals as posts.
app.get("/api/forum/posts", (_req, res) => {
  const posts = db
    .prepare(
      `
        SELECT id, category, author, title, submitted_at
        FROM proposals
        ORDER BY submitted_at DESC
        LIMIT 100
      `
    )
    .all()
    .map((row) => ({
      id: row.id,
      category_id: `cat-${String(row.category || "general").toLowerCase().replace(/\s+/g, "-")}`,
      author_id: row.author,
      title: row.title,
      content: row.title,
      is_pinned: 0,
      is_locked: 0,
      is_archived: 0,
      view_count: 0,
      created_at: row.submitted_at,
      updated_at: row.submitted_at,
      author_name: row.author,
      category_name: row.category
    }));
  res.json({ posts });
});

app.get("/api/meetings", (_req, res) => {
  res.json({ meetings: [] });
});

app.get("/api/social-services", (_req, res) => {
  res.json({ services: SOCIAL_SERVICE_CATALOG });
});

app.get("/api/users", requireAuth, (_req, res) => {
  const users = listAccounts().map((account) => toLegacyUser(account));
  res.json({ users });
});

app.get("/api/users/me", requireAuth, (req, res) => {
  res.json({ user: toLegacyUser(req.user) });
});

app.get("/api/users/:id/profile", requireAuth, (req, res) => {
  const account = getAccountById(req.params.id);
  if (!account) {
    res.status(404).json({ error: "User not found" });
    return;
  }
  res.json({ user: toLegacyUser(account) });
});

function patchProfile(target, body) {
  const bio = String(body?.bio ?? target.bio ?? "").slice(0, 1500);
  const profilePhotoUrl = body?.profile_photo_url
    ? String(body.profile_photo_url).slice(0, 500)
    : null;
  const skills = Array.isArray(body?.skills)
    ? body.skills.map((item) => String(item).trim()).filter(Boolean).slice(0, 40)
    : target.skills;
  const socialServices = Array.isArray(body?.social_services)
    ? body.social_services
        .map((item) => String(item).trim())
        .filter(Boolean)
        .slice(0, 40)
    : target.socialServices;

  db.prepare(
    `
      UPDATE accounts
      SET bio = ?, profile_photo_url = ?, skills = ?, social_services = ?
      WHERE id = ?
    `
  ).run(
    bio,
    profilePhotoUrl,
    JSON.stringify(skills),
    JSON.stringify(socialServices),
    target.id
  );
}

app.patch("/api/users/me", requireAuth, (req, res) => {
  const target = getAccountById(req.user.id);
  patchProfile(target, req.body || {});
  const updated = getAccountById(req.user.id);
  res.json({ ok: true, user: toLegacyUser(updated) });
});

app.post("/api/users/me/avatar", requireAuth, (req, res) => {
  // Placeholder uploader compatibility endpoint for legacy UI.
  // In this prototype, frontends should send profile_photo_url via /api/users/me PATCH.
  const target = getAccountById(req.user.id);
  res.json({ ok: true, profile_photo_url: target.profilePhotoUrl || null });
});

app.patch("/api/users/:id", requireAuth, (req, res) => {
  const target = getAccountById(req.params.id);
  if (!target) {
    res.status(404).json({ error: "User not found" });
    return;
  }

  const body = req.body || {};
  const requesterIsAdmin = isAdminUser(req.user);
  const touchesModerator = Object.prototype.hasOwnProperty.call(body, "is_moderator");
  const touchesAdmin = Object.prototype.hasOwnProperty.call(body, "is_admin");

  if (touchesModerator || touchesAdmin) {
    if (!requesterIsAdmin) {
      res.status(403).json({ error: "Admin access required" });
      return;
    }
    if (touchesModerator) {
      db.prepare("UPDATE accounts SET is_moderator = ? WHERE id = ?").run(
        body.is_moderator ? 1 : 0,
        target.id
      );
    }
    if (touchesAdmin) {
      db.prepare("UPDATE accounts SET is_admin = ? WHERE id = ?").run(body.is_admin ? 1 : 0, target.id);
    }
    const updated = getAccountById(target.id);
    res.json({ ok: true, user: toLegacyUser(updated) });
    return;
  }

  if (Number(target.id) !== Number(req.user.id) && !requesterIsAdmin) {
    res.status(403).json({ error: "You can only edit your own profile." });
    return;
  }

  patchProfile(target, body);
  const updated = getAccountById(target.id);
  res.json({ ok: true, user: toLegacyUser(updated) });
});

app.put("/api/users/:id", requireAuth, (req, res) => {
  const target = getAccountById(req.params.id);
  if (!target) {
    res.status(404).json({ error: "User not found" });
    return;
  }
  const requesterIsAdmin = isAdminUser(req.user);
  if (Number(target.id) !== Number(req.user.id) && !requesterIsAdmin) {
    res.status(403).json({ error: "You can only edit your own profile." });
    return;
  }

  patchProfile(target, req.body || {});

  const updated = getAccountById(target.id);
  res.json({ ok: true, user: toLegacyUser(updated) });
});

app.delete("/api/users/:id", requireAuth, requireAdmin, (req, res) => {
  const target = getAccountById(req.params.id);
  if (!target) {
    res.status(404).json({ ok: false, message: "User not found." });
    return;
  }
  db.prepare("DELETE FROM sessions WHERE username = ?").run(target.username);
  db.prepare("DELETE FROM accounts WHERE id = ?").run(target.id);
  res.json({ ok: true, message: `Deleted profile for ${target.username}.` });
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

app.patch("/api/listings/:listingId", requireAuth, (req, res) => {
  const listingId = String(req.params.listingId || "").trim();
  const current = db.prepare("SELECT * FROM listings WHERE id = ?").get(listingId);
  if (!current) {
    res.status(404).json({ ok: false, message: "Listing not found." });
    return;
  }
  const canModerate =
    isAdminUser(req.user) || toLowerName(current.author) === toLowerName(req.user.username);
  if (!canModerate) {
    res.status(403).json({ ok: false, message: "Not permitted to edit this listing." });
    return;
  }
  const body = req.body || {};
  const nextType = body.type === "trade" ? "trade" : body.type === "barter" ? "barter" : current.type;
  const nextTitle = String(body.title ?? current.title).trim();
  const nextDetails = String(body.details ?? current.details).trim();
  const nextScope = String(body.scope ?? current.scope).trim();
  const nextStatus = String(body.status ?? current.status).trim();
  if (!nextTitle || !nextDetails) {
    res.status(400).json({ ok: false, message: "Provide title and details." });
    return;
  }
  const closedAt = nextStatus === "closed" ? nowIso() : null;
  db.prepare(
    `
      UPDATE listings
      SET type = ?, title = ?, details = ?, scope = ?, status = ?, closed_at = ?
      WHERE id = ?
    `
  ).run(nextType, nextTitle, nextDetails, nextScope, nextStatus, closedAt, listingId);
  const updated = db.prepare("SELECT * FROM listings WHERE id = ?").get(listingId);
  res.json({ ok: true, listing: mapListing(updated) });
});

app.delete("/api/listings/:listingId", requireAuth, (req, res) => {
  const listingId = String(req.params.listingId || "").trim();
  const current = db.prepare("SELECT * FROM listings WHERE id = ?").get(listingId);
  if (!current) {
    res.status(404).json({ ok: false, message: "Listing not found." });
    return;
  }
  const canModerate =
    isAdminUser(req.user) || toLowerName(current.author) === toLowerName(req.user.username);
  if (!canModerate) {
    res.status(403).json({ ok: false, message: "Not permitted to delete this listing." });
    return;
  }
  db.prepare("DELETE FROM listings WHERE id = ?").run(listingId);
  res.json({ ok: true, message: "Listing deleted." });
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

app.patch("/api/network-posts/:postId", requireAuth, (req, res) => {
  const postId = String(req.params.postId || "").trim();
  const current = db.prepare("SELECT * FROM network_posts WHERE id = ?").get(postId);
  if (!current) {
    res.status(404).json({ ok: false, message: "Post not found." });
    return;
  }
  const canModerate =
    isAdminUser(req.user) || toLowerName(current.author) === toLowerName(req.user.username);
  if (!canModerate) {
    res.status(403).json({ ok: false, message: "Not permitted to edit this post." });
    return;
  }
  const body = req.body || {};
  const nextScope = String(body.scope ?? current.scope).trim();
  const nextMessage = String(body.message ?? current.message).trim();
  let nextTags;
  if (Array.isArray(body.tags)) {
    nextTags = body.tags.map((item) => String(item).trim().toLowerCase()).filter(Boolean).slice(0, 8);
  } else {
    try {
      const parsed = JSON.parse(current.tags || "[]");
      nextTags = Array.isArray(parsed) ? parsed : [];
    } catch (_error) {
      nextTags = [];
    }
  }
  if (!nextMessage) {
    res.status(400).json({ ok: false, message: "Message cannot be empty." });
    return;
  }
  db.prepare(
    `
      UPDATE network_posts
      SET scope = ?, tags = ?, message = ?
      WHERE id = ?
    `
  ).run(nextScope, JSON.stringify(nextTags), nextMessage, postId);
  const updated = db.prepare("SELECT * FROM network_posts WHERE id = ?").get(postId);
  res.json({ ok: true, post: mapNetworkPost(updated) });
});

app.delete("/api/network-posts/:postId", requireAuth, (req, res) => {
  const postId = String(req.params.postId || "").trim();
  const current = db.prepare("SELECT * FROM network_posts WHERE id = ?").get(postId);
  if (!current) {
    res.status(404).json({ ok: false, message: "Post not found." });
    return;
  }
  const canModerate =
    isAdminUser(req.user) || toLowerName(current.author) === toLowerName(req.user.username);
  if (!canModerate) {
    res.status(403).json({ ok: false, message: "Not permitted to delete this post." });
    return;
  }
  db.prepare("DELETE FROM network_posts WHERE id = ?").run(postId);
  res.json({ ok: true, message: "Post deleted." });
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

app.delete("/api/notifications/:notificationId", requireAuth, requireAdmin, (req, res) => {
  const notificationId = String(req.params.notificationId || "").trim();
  db.prepare("DELETE FROM notifications WHERE id = ?").run(notificationId);
  res.json({ ok: true, message: "Notification deleted." });
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
