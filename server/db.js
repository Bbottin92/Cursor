const path = require("path");
const crypto = require("crypto");
const Database = require("better-sqlite3");

const dbPath = path.join(__dirname, "..", "data", "liquidgov.db");
const db = new Database(dbPath);

db.pragma("journal_mode = WAL");

db.exec(`
  CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    lower_username TEXT NOT NULL UNIQUE,
    age INTEGER NOT NULL,
    parent_link TEXT,
    approved_adults TEXT NOT NULL DEFAULT '[]',
    is_verified_patriot INTEGER NOT NULL DEFAULT 0,
    pledge_signed INTEGER NOT NULL DEFAULT 0,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    author TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    status TEXT NOT NULL,
    law_reference TEXT
  );

  CREATE TABLE IF NOT EXISTS assembly_roles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    assigned_to TEXT
  );

  CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    details TEXT NOT NULL,
    scope TEXT NOT NULL,
    author TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    closed_at TEXT
  );

  CREATE TABLE IF NOT EXISTS network_posts (
    id TEXT PRIMARY KEY,
    author TEXT NOT NULL,
    scope TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS profile_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_owner TEXT NOT NULL,
    visitor TEXT NOT NULL,
    visited_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    message TEXT NOT NULL,
    type TEXT NOT NULL,
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
  );
`);

function toLowerName(name) {
  return String(name || "").trim().toLowerCase();
}

function nowIso() {
  return new Date().toISOString();
}

function mapAccount(row) {
  if (!row) {
    return null;
  }
  let approvedAdults = [];
  try {
    approvedAdults = JSON.parse(row.approved_adults || "[]");
    if (!Array.isArray(approvedAdults)) {
      approvedAdults = [];
    }
  } catch (error) {
    approvedAdults = [];
  }

  return {
    id: row.id,
    username: row.username,
    age: row.age,
    parentLink: row.parent_link,
    approvedAdults,
    isVerifiedPatriot: Boolean(row.is_verified_patriot),
    pledgeSigned: Boolean(row.pledge_signed),
    role: row.role,
    createdAt: row.created_at
  };
}

function mapProposal(row) {
  return {
    id: row.id,
    title: row.title,
    category: row.category,
    author: row.author,
    submittedAt: row.submitted_at,
    status: row.status,
    lawReference: row.law_reference
  };
}

function mapRole(row) {
  return {
    id: row.id,
    title: row.title,
    assignedTo: row.assigned_to
  };
}

function mapListing(row) {
  return {
    id: row.id,
    type: row.type,
    title: row.title,
    details: row.details,
    scope: row.scope,
    author: row.author,
    status: row.status,
    createdAt: row.created_at,
    closedAt: row.closed_at
  };
}

function mapNetworkPost(row) {
  let tags = [];
  try {
    tags = JSON.parse(row.tags || "[]");
    if (!Array.isArray(tags)) {
      tags = [];
    }
  } catch (error) {
    tags = [];
  }

  return {
    id: row.id,
    author: row.author,
    scope: row.scope,
    tags,
    message: row.message,
    createdAt: row.created_at
  };
}

function mapNotification(row) {
  return {
    id: row.id,
    username: row.username,
    message: row.message,
    type: row.type,
    createdAt: row.created_at
  };
}

function mapProfileVisit(row) {
  return {
    visitor: row.visitor,
    visitedAt: row.visited_at
  };
}

function getAccountByUsername(username) {
  const row = db
    .prepare("SELECT * FROM accounts WHERE lower_username = ?")
    .get(toLowerName(username));
  return mapAccount(row);
}

function listAccounts() {
  const rows = db.prepare("SELECT * FROM accounts ORDER BY created_at ASC").all();
  return rows.map(mapAccount);
}

function upsertSetting(key, value) {
  db.prepare(
    `
      INSERT INTO settings (key, value)
      VALUES (?, ?)
      ON CONFLICT(key) DO UPDATE SET value = excluded.value
    `
  ).run(key, JSON.stringify(value));
}

function getSetting(key, fallback) {
  const row = db.prepare("SELECT value FROM settings WHERE key = ?").get(key);
  if (!row) {
    return fallback;
  }
  try {
    return JSON.parse(row.value);
  } catch (error) {
    return fallback;
  }
}

function addNotification(username, message, type = "info") {
  const id = `NT-${crypto.randomUUID()}`;
  db.prepare(
    `
      INSERT INTO notifications (id, username, message, type, created_at)
      VALUES (?, ?, ?, ?, ?)
    `
  ).run(id, username, message, type, nowIso());
}

function seedProposals() {
  const hasRows = db.prepare("SELECT COUNT(*) AS count FROM proposals").get().count > 0;
  if (hasRows) {
    return;
  }

  const seedRows = [
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

  const stmt = db.prepare(
    `
      INSERT INTO proposals (id, title, category, author, submitted_at, status, law_reference)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `
  );
  const tx = db.transaction((rows) => {
    for (const row of rows) {
      stmt.run(
        row.id,
        row.title,
        row.category,
        row.author,
        row.submittedAt,
        row.status,
        row.lawReference
      );
    }
  });
  tx(seedRows);
}

function seedRoles() {
  const hasRows = db.prepare("SELECT COUNT(*) AS count FROM assembly_roles").get().count > 0;
  if (hasRows) {
    return;
  }

  const roles = [
    { id: "R-1", title: "Coordinator / Facilitator" },
    { id: "R-2", title: "Secretary / Records" },
    { id: "R-3", title: "Treasury / Finance" },
    { id: "R-4", title: "Tech Steward" },
    { id: "R-5", title: "Governance Steward" },
    { id: "R-6", title: "Community Steward" },
    { id: "R-7", title: "Ethics & Safety Steward" }
  ];

  const stmt = db.prepare(
    "INSERT INTO assembly_roles (id, title, assigned_to) VALUES (?, ?, NULL)"
  );
  const tx = db.transaction((rows) => {
    for (const row of rows) {
      stmt.run(row.id, row.title);
    }
  });
  tx(roles);
}

function seedListings() {
  const hasRows = db.prepare("SELECT COUNT(*) AS count FROM listings").get().count > 0;
  if (hasRows) {
    return;
  }

  const rows = [
    {
      id: "L-9001",
      type: "barter",
      title: "Offer: plumbing help for web design",
      details:
        "Can help with basic plumbing in exchange for logo + landing page polish.",
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

  const stmt = db.prepare(
    `
      INSERT INTO listings (id, type, title, details, scope, author, status, created_at, closed_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
    `
  );
  const tx = db.transaction((items) => {
    for (const item of items) {
      stmt.run(
        item.id,
        item.type,
        item.title,
        item.details,
        item.scope,
        item.author,
        item.status,
        item.createdAt
      );
    }
  });
  tx(rows);
}

function seedNetworkPosts() {
  const hasRows = db.prepare("SELECT COUNT(*) AS count FROM network_posts").get().count > 0;
  if (hasRows) {
    return;
  }

  db.prepare(
    `
      INSERT INTO network_posts (id, author, scope, tags, message, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `
  ).run(
    "N-4001",
    "Ari-Founder",
    "National",
    JSON.stringify(["governance", "voluntarism"]),
    "Looking for chapter organizers with policy writing experience.",
    "2026-02-15T11:30:00Z"
  );
}

function seedSettings() {
  const defaults = {
    verificationMethodRatified: false,
    frameworkPublished: false,
    safetyStandardsAdopted: true,
    auditPublished: false
  };

  const current = getSetting("core", null);
  if (!current) {
    upsertSetting("core", defaults);
  }
}

seedProposals();
seedRoles();
seedListings();
seedNetworkPosts();
seedSettings();

module.exports = {
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
};
