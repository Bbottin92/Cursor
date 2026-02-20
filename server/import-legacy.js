const crypto = require("crypto");
const {
  db,
  nowIso,
  toLowerName,
  getSetting,
  upsertSetting
} = require("./db");

const LEGACY_BASE = process.env.LEGACY_BASE || "https://liquidgov.us";
const LEGACY_TOKEN = process.env.LEGACY_TOKEN || "";

function stableId(prefix, input) {
  const digest = crypto.createHash("sha1").update(String(input)).digest("hex").slice(0, 16);
  return `${prefix}-${digest}`;
}

async function fetchJson(path, { auth = false } = {}) {
  const headers = {};
  if (auth && LEGACY_TOKEN) {
    headers.Authorization = `Bearer ${LEGACY_TOKEN}`;
  }
  const response = await fetch(`${LEGACY_BASE}${path}`, { headers });
  if (!response.ok) {
    throw new Error(`${path} failed (${response.status})`);
  }
  return response.json();
}

function upsertAnnouncement(item) {
  const title = String(item.title || "").trim();
  const body = String(item.body || item.message || "").trim();
  if (!title || !body) {
    return false;
  }
  const createdAt = item.created_at || nowIso();
  const id = item.id || stableId("ALEG", `${title}|${createdAt}|${body.slice(0, 80)}`);
  const existing = db.prepare("SELECT id FROM announcements WHERE id = ?").get(id);
  if (existing) {
    return false;
  }
  db.prepare(
    `
      INSERT INTO announcements (id, title, body, author_username, author_name, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `
  ).run(
    id,
    title,
    body,
    String(item.author_username || item.author_name || "legacy"),
    String(item.author_name || item.author_username || "Legacy"),
    createdAt,
    item.updated_at || createdAt
  );
  return true;
}

function upsertProposalFromPost(post) {
  const title = String(post.title || "").trim();
  if (!title) {
    return false;
  }
  const id = String(post.id || stableId("PLEG", `${title}|${post.created_at || nowIso()}`));
  const existing = db.prepare("SELECT id FROM proposals WHERE id = ?").get(id);
  if (existing) {
    return false;
  }
  const category = String(post.category_name || "Legacy");
  db.prepare(
    `
      INSERT INTO proposals (id, title, category, author, submitted_at, status, law_reference)
      VALUES (?, ?, ?, ?, ?, ?, NULL)
    `
  ).run(
    id,
    title,
    category,
    String(post.author_name || post.author_id || "legacy-user"),
    post.created_at || nowIso(),
    "under_review"
  );
  return true;
}

function upsertAccountFromLegacy(user) {
  const username = String(user.name || user.username || "").trim();
  if (!username) {
    return false;
  }
  const lower = toLowerName(username);
  const existing = db.prepare("SELECT id FROM accounts WHERE lower_username = ?").get(lower);
  if (existing) {
    return false;
  }
  const createdAt = user.created_at || nowIso();
  const trustLevel = Number(user.trust_level || 1);
  const credits = Number(user.credits || 0);
  const isModerator = user.is_moderator ? 1 : 0;
  const skills = Array.isArray(user.skills)
    ? user.skills.map((item) => String(item).trim()).filter(Boolean).slice(0, 40)
    : [];
  const socialServices = Array.isArray(user.social_services)
    ? user.social_services.map((item) => String(item).trim()).filter(Boolean).slice(0, 40)
    : [];
  const bio = String(user.bio || "").slice(0, 1500);
  const profilePhotoUrl = user.profile_photo_url ? String(user.profile_photo_url).slice(0, 500) : null;
  const email = user.email ? String(user.email).slice(0, 255) : null;

  db.prepare(
    `
      INSERT INTO accounts (
        username, lower_username, email, age, parent_link, approved_adults,
        is_verified_patriot, pledge_signed, role, created_at, profile_photo_url,
        bio, skills, social_services, is_moderator, trust_level, credits
      ) VALUES (?, ?, ?, ?, NULL, '[]', 0, 0, 'adult', ?, ?, ?, ?, ?, ?, ?, ?)
    `
  ).run(
    username,
    lower,
    email,
    30,
    createdAt,
    profilePhotoUrl,
    bio,
    JSON.stringify(skills),
    JSON.stringify(socialServices),
    isModerator,
    trustLevel,
    credits
  );

  return true;
}

async function run() {
  let announcementsAdded = 0;
  let postsAdded = 0;
  let usersAdded = 0;
  let offsetApplied = 0;

  try {
    const announcementRes = await fetchJson("/api/announcements");
    const announcements = Array.isArray(announcementRes.announcements)
      ? announcementRes.announcements
      : [];
    for (const row of announcements) {
      if (upsertAnnouncement(row)) {
        announcementsAdded += 1;
      }
    }
  } catch (error) {
    console.error(`Announcement import skipped: ${error.message}`);
  }

  try {
    const postRes = await fetchJson("/api/forum/posts");
    const posts = Array.isArray(postRes.posts) ? postRes.posts : [];
    for (const post of posts) {
      if (upsertProposalFromPost(post)) {
        postsAdded += 1;
      }
    }
  } catch (error) {
    console.error(`Forum import skipped: ${error.message}`);
  }

  if (LEGACY_TOKEN) {
    try {
      const userRes = await fetchJson("/api/users", { auth: true });
      const users = Array.isArray(userRes.users) ? userRes.users : [];
      for (const user of users) {
        if (upsertAccountFromLegacy(user)) {
          usersAdded += 1;
        }
      }
    } catch (error) {
      console.error(`Account import skipped: ${error.message}`);
    }
  } else {
    console.log("No LEGACY_TOKEN provided. Account import skipped.");
  }

  try {
    const participantRes = await fetchJson("/api/stats/participants");
    const legacyCount = Number(participantRes.count || 0);
    const localCount = Number(
      db.prepare("SELECT COUNT(*) AS count FROM accounts").get().count || 0
    );
    if (legacyCount > localCount) {
      const core = getSetting("core", {});
      offsetApplied = legacyCount - localCount;
      upsertSetting("core", { ...core, legacyParticipantOffset: offsetApplied });
    }
  } catch (error) {
    console.error(`Participant offset check skipped: ${error.message}`);
  }

  console.log(
    `Legacy import complete: ${usersAdded} accounts, ${announcementsAdded} announcements, ${postsAdded} posts, offset ${offsetApplied}.`
  );
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
