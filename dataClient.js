(function initLiquidGovData() {
  const SESSION_KEY = "liquidgov.apiToken";
  const localStore = window.LiquidGovStore;
  let apiReady = false;
  let token = localStorage.getItem(SESSION_KEY) || null;

  async function detectBackend() {
    try {
      const response = await fetch("/api/health", { cache: "no-store" });
      apiReady = response.ok;
    } catch (error) {
      apiReady = false;
    }
    return apiReady;
  }

  function setToken(value) {
    token = value || null;
    if (token) {
      localStorage.setItem(SESSION_KEY, token);
    } else {
      localStorage.removeItem(SESSION_KEY);
    }
  }

  async function request(path, options = {}) {
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {})
    };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(path, { ...options, headers });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = data?.message || `Request failed: ${response.status}`;
      throw new Error(message);
    }
    return data;
  }

  function normalizeLocalSession(sessionValue) {
    if (!sessionValue) {
      return null;
    }
    if (typeof sessionValue === "string") {
      return { username: sessionValue };
    }
    return sessionValue;
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

  const api = {
    async init() {
      await detectBackend();
      return { apiReady };
    },

    isBackendEnabled() {
      return apiReady;
    },

    formatNumber,
    formatDate,

    async getAccounts() {
      if (!apiReady) {
        return localStore.getAccounts();
      }
      const data = await request("/api/accounts");
      return data.accounts || [];
    },

    async getCurrentUser() {
      if (!apiReady) {
        return normalizeLocalSession(localStore.getCurrentUser());
      }
      if (!token) {
        return null;
      }
      try {
        const data = await request("/api/session/current");
        return data.user || null;
      } catch (error) {
        setToken(null);
        return null;
      }
    },

    async setCurrentUser(username) {
      if (!username) {
        if (apiReady && token) {
          try {
            await request("/api/auth/logout", { method: "POST", body: JSON.stringify({}) });
          } catch (error) {
            // Ignore logout failures and clear local token anyway.
          }
        }
        setToken(null);
        localStore.setCurrentUser(null);
        return null;
      }

      if (!apiReady) {
        localStore.setCurrentUser(username);
        return normalizeLocalSession(localStore.getCurrentUser());
      }

      const data = await request("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username })
      });
      setToken(data.token);
      return data.account || null;
    },

    async createAccount(payload) {
      if (!apiReady) {
        return localStore.createAccount(payload);
      }
      try {
        const data = await request("/api/auth/register", {
          method: "POST",
          body: JSON.stringify(payload)
        });
        setToken(data.token);
        return { ok: true, message: data.message, account: data.account };
      } catch (error) {
        return { ok: false, message: error.message };
      }
    },

    async getProposals() {
      if (!apiReady) {
        return localStore.getProposals();
      }
      const data = await request("/api/proposals");
      return data.proposals || [];
    },

    async addProposal({ title, category, author, status = "under_review" }) {
      if (!apiReady) {
        return localStore.addProposal({ title, category, author, status });
      }
      return request("/api/proposals", {
        method: "POST",
        body: JSON.stringify({ title, category, status })
      });
    },

    async getProfileVisitors(profileOwner) {
      if (!apiReady) {
        return localStore.getProfileVisitors(profileOwner);
      }
      const data = await request(`/api/profile-visits/${encodeURIComponent(profileOwner)}`);
      return data.visitors || [];
    },

    async recordProfileVisit(profileOwner, visitor) {
      if (!apiReady) {
        return localStore.recordProfileVisit(profileOwner, visitor);
      }
      return request("/api/profile-visits", {
        method: "POST",
        body: JSON.stringify({ profileOwner })
      });
    },

    async addNotification(username, message, type = "info") {
      if (!apiReady) {
        return localStore.addNotification(username, message, type);
      }
      return request("/api/notifications", {
        method: "POST",
        body: JSON.stringify({ username, message, type })
      });
    },

    async getNotifications(username) {
      if (!apiReady) {
        return localStore.getNotifications(username);
      }
      const data = await request(`/api/notifications/${encodeURIComponent(username)}`);
      return data.notifications || [];
    },

    async inspectMinorActivity(parentUsername, childUsername, area = "messages") {
      if (!apiReady) {
        return localStore.inspectMinorActivity(parentUsername, childUsername, area);
      }
      try {
        const data = await request("/api/minor/inspect", {
          method: "POST",
          body: JSON.stringify({ childUsername, area })
        });
        return { ok: true, message: data.message };
      } catch (error) {
        return { ok: false, message: error.message };
      }
    },

    async approveMinorContact(parentUsername, childUsername, adultUsername) {
      if (!apiReady) {
        return localStore.approveMinorContact(parentUsername, childUsername, adultUsername);
      }
      try {
        const data = await request("/api/minor/approve-contact", {
          method: "POST",
          body: JSON.stringify({ childUsername, adultUsername })
        });
        return { ok: true, message: data.message };
      } catch (error) {
        return { ok: false, message: error.message };
      }
    },

    async canInteract(senderUsername, receiverUsername) {
      if (!apiReady) {
        return localStore.canInteract(senderUsername, receiverUsername);
      }
      try {
        return await request(
          `/api/minor/can-interact?sender=${encodeURIComponent(
            senderUsername
          )}&receiver=${encodeURIComponent(receiverUsername)}`
        );
      } catch (error) {
        return { ok: false, reason: error.message };
      }
    },

    async getAssemblyRoles() {
      if (!apiReady) {
        return localStore.getAssemblyRoles();
      }
      const data = await request("/api/roles");
      return data.roles || [];
    },

    async claimAssemblyRole(roleId, username) {
      if (!apiReady) {
        return localStore.claimAssemblyRole(roleId, username);
      }
      try {
        const data = await request("/api/roles/claim", {
          method: "POST",
          body: JSON.stringify({ roleId })
        });
        return { ok: true, message: data.message };
      } catch (error) {
        return { ok: false, message: error.message };
      }
    },

    async releaseAssemblyRole(roleId, username) {
      if (!apiReady) {
        return localStore.releaseAssemblyRole(roleId, username);
      }
      try {
        const data = await request("/api/roles/release", {
          method: "POST",
          body: JSON.stringify({ roleId })
        });
        return { ok: true, message: data.message };
      } catch (error) {
        return { ok: false, message: error.message };
      }
    },

    async getListings() {
      if (!apiReady) {
        return localStore.getListings();
      }
      const data = await request("/api/listings");
      return data.listings || [];
    },

    async addListing({ type, title, details, scope, author }) {
      if (!apiReady) {
        return localStore.addListing({ type, title, details, scope, author });
      }
      return request("/api/listings", {
        method: "POST",
        body: JSON.stringify({ type, title, details, scope })
      });
    },

    async closeListing(listingId, username) {
      if (!apiReady) {
        return localStore.closeListing(listingId, username);
      }
      try {
        const data = await request(`/api/listings/${encodeURIComponent(listingId)}/close`, {
          method: "POST",
          body: JSON.stringify({})
        });
        return { ok: true, message: data.message };
      } catch (error) {
        return { ok: false, message: error.message };
      }
    },

    async getNetworkPosts() {
      if (!apiReady) {
        return localStore.getNetworkPosts();
      }
      const data = await request("/api/network-posts");
      return data.posts || [];
    },

    async addNetworkPost({ author, scope, tags, message }) {
      if (!apiReady) {
        return localStore.addNetworkPost({ author, scope, tags, message });
      }
      return request("/api/network-posts", {
        method: "POST",
        body: JSON.stringify({ scope, tags, message })
      });
    },

    async getSettings() {
      if (!apiReady) {
        return localStore.getSettings();
      }
      const data = await request("/api/settings");
      return data.settings;
    },

    async updateSettings(patch) {
      if (!apiReady) {
        return localStore.updateSettings(patch);
      }
      const data = await request("/api/settings", {
        method: "PATCH",
        body: JSON.stringify(patch)
      });
      return data.settings;
    },

    async getLaunchMilestoneStatus() {
      if (!apiReady) {
        return localStore.getLaunchMilestoneStatus();
      }
      const data = await request("/api/milestone");
      return data.milestone;
    }
  };

  window.LiquidGovData = api;
})();
