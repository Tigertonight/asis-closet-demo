(() => {
  // v1 存在 sessionStorage（关浏览器即丢）；v2 迁到 localStorage，
  // 配合 30 天滑动续期 + 静默重登，内测评委等效永久登录。
  const AUTH_STORAGE_KEY = 'selfit.auth.session.v2';
  const LEGACY_AUTH_STORAGE_KEY = 'selfit.auth.session.v1';
  const DEVICE_STORAGE_KEY = 'selfit.device.v1';
  const INVITE_CRED_KEY = 'selfit.auth.invite.v1';
  const jsonHeaders = { Accept: 'application/json', 'Content-Type': 'application/json' };
  const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
  const mockId = (value) => `mock_${String(value || 'invite').replace(/\D/g, '').slice(-6) || 'invite'}`;

  const randomDeviceId = () => {
    const bytes = new Uint8Array(16);
    (window.crypto || window.msCrypto).getRandomValues(bytes);
    return Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');
  };

  class SelfitAuthError extends Error {
    constructor(message, { code = 'auth.unknown', status = 0 } = {}) {
      super(message);
      this.name = 'SelfitAuthError';
      this.code = code;
      this.status = status;
    }
  }

  class SelfitAuthClient {
    constructor({ mode = 'mock', baseUrl = '/auth', timeoutMs = 15000 } = {}) {
      this.mode = mode === 'live' ? 'live' : 'mock';
      this.baseUrl = baseUrl.replace(/\/$/, '');
      this.timeoutMs = timeoutMs;
      this.session = null;
    }

    get accessToken() { return this.session?.accessToken || null; }
    get user() { return this.session?.user || null; }

    deviceId() {
      try {
        let id = localStorage.getItem(DEVICE_STORAGE_KEY);
        if (!id) {
          id = randomDeviceId();
          localStorage.setItem(DEVICE_STORAGE_KEY, id);
        }
        return id;
      } catch { return randomDeviceId(); }
    }

    readInviteCredentials() {
      try { return JSON.parse(localStorage.getItem(INVITE_CRED_KEY) || 'null'); } catch { return null; }
    }

    storeInviteCredentials(inviteCode) {
      try {
        localStorage.setItem(INVITE_CRED_KEY, JSON.stringify({ invite_code: String(inviteCode || '').trim(), device_id: this.deviceId() }));
      } catch { /* 无痕模式下静默重登不可用，登录态仍按 token 有效期保持。 */ }
    }

    readStoredSession() {
      try {
        // 旧版迁移：把 v1（sessionStorage）搬到 v2（localStorage）后清理旧键。
        const legacy = sessionStorage.getItem(LEGACY_AUTH_STORAGE_KEY);
        if (legacy && !localStorage.getItem(AUTH_STORAGE_KEY)) {
          localStorage.setItem(AUTH_STORAGE_KEY, legacy);
          sessionStorage.removeItem(LEGACY_AUTH_STORAGE_KEY);
        }
      } catch { /* ignore */ }
      try {
        const stored = JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY) || 'null');
        if (!stored?.accessToken || (stored.expiresAt && Date.parse(stored.expiresAt) <= Date.now())) return null;
        return stored;
      } catch { return null; }
    }

    persist(payload) {
      const expiresIn = Number(payload.expires_in_seconds || 86400);
      this.session = {
        accessToken: payload.access_token,
        expiresAt: new Date(Date.now() + expiresIn * 1000).toISOString(),
        user: payload.user || null,
      };
      try { localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(this.session)); } catch { /* 无痕模式下本次会话内仍可用。 */ }
      return this.session;
    }

    clear() {
      this.session = null;
      try {
        localStorage.removeItem(AUTH_STORAGE_KEY);
        localStorage.removeItem(INVITE_CRED_KEY);
        sessionStorage.removeItem(LEGACY_AUTH_STORAGE_KEY);
      } catch { /* ignore */ }
    }

    async request(path, { method = 'GET', body, token, timeoutMs = this.timeoutMs, allowRelogin = true } = {}) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      const headers = { ...jsonHeaders };
      if (token) headers.Authorization = `Bearer ${token}`;
      try {
        const response = await fetch(`${this.baseUrl}${path}`, {
          method,
          credentials: 'include',
          headers,
          signal: controller.signal,
          body: body === undefined ? undefined : JSON.stringify(body),
        });
        if (response.status === 401 && allowRelogin && this.mode === 'live' && !path.startsWith('/invite/verify')) {
          // 静默重登：token 过期/丢失时，用本地保存的邀请码 + 设备标识无感换新 token。
          const creds = this.readInviteCredentials();
          if (creds?.invite_code) {
            const refreshed = await this.request('/invite/verify', {
              method: 'POST',
              body: { invite_code: creds.invite_code, device_id: creds.device_id || this.deviceId() },
              allowRelogin: false,
              timeoutMs,
            });
            this.persist(refreshed);
            return this.request(path, { method, body, token: refreshed.access_token, timeoutMs, allowRelogin: false });
          }
        }
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new SelfitAuthError(payload.detail || payload.error?.message || '登录没有完成，请重试。', {
            code: payload.error?.code || `http.${response.status}`,
            status: response.status,
          });
        }
        return payload;
      } catch (error) {
        if (error instanceof SelfitAuthError) throw error;
        if (controller.signal.aborted) throw new SelfitAuthError('请求超时，请检查网络后重试。', { code: 'network.timeout' });
        throw new SelfitAuthError('网络连接失败，请稍后重试。', { code: 'network.unavailable' });
      } finally {
        clearTimeout(timeout);
      }
    }

    async ensureVisitor() {
      const stored = this.readStoredSession();
      if (stored) { this.session = stored; return stored; }
      if (this.mode === 'mock') return null;
      return this.persist(await this.request('/guest', { method: 'POST' }));
    }

    async restore() {
      const stored = this.readStoredSession();
      if (!stored) return null;
      if (this.mode === 'mock') {
        this.session = stored;
        return stored;
      }
      try {
        // 401 时 request 内部会先用邀请码静默重登，再重放 /me。
        const result = await this.request('/me', { token: stored.accessToken });
        this.session = { ...stored, accessToken: this.accessToken || stored.accessToken, user: result.user || stored.user };
        try { localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(this.session)); } catch { /* ignore */ }
        return this.session;
      } catch (error) {
        // 网络抖动不丢登录态；确认 401（且静默重登也没救回来）才清理。
        if (error instanceof SelfitAuthError && error.status === 401) { this.clear(); return null; }
        this.session = stored;
        return stored;
      }
    }

    async startPhone(phone) {
      if (this.mode === 'live') return this.request('/phone/start', { method: 'POST', body: { phone } });
      await wait(280);
      return { status: 'sent', phone_e164: `+86${phone}`, expires_in_seconds: 600, dev_code: '0000' };
    }

    async directPhone(phone) {
      if (this.mode === 'live') {
        const payload = await this.request('/phone/direct', { method: 'POST', body: { phone } });
        return this.persist(payload);
      }
      await wait(360);
      return this.persist({
        access_token: `mock_phone_${Date.now()}`,
        expires_in_seconds: 86400,
        user: { user_id: mockId(phone), phone_e164: `+86${phone}`, status: 'active', beta_qualified: false },
      });
    }

    async verifyPhone(phone, code) {
      if (this.mode === 'live') {
        const payload = await this.request('/phone/verify', { method: 'POST', body: { phone, code } });
        return this.persist(payload);
      }
      await wait(360);
      if (!['0000', '0001'].includes(String(code))) throw new SelfitAuthError('验证码不正确', { code: 'auth.code_invalid', status: 400 });
      return this.persist({
        access_token: `mock_phone_${Date.now()}`,
        expires_in_seconds: 86400,
        user: { user_id: mockId(phone), phone_e164: `+86${phone}`, status: 'active', beta_qualified: false },
      });
    }

    async verifyInvite(inviteCode) {
      if (this.mode === 'live') {
        const payload = await this.request('/invite/verify', {
          method: 'POST',
          body: { invite_code: inviteCode, device_id: this.deviceId() },
        });
        this.storeInviteCredentials(inviteCode);
        return this.persist(payload);
      }
      await wait(360);
      if (String(inviteCode || '').trim().length < 4) throw new SelfitAuthError('请输入有效的邀请码', { code: 'auth.invite_invalid', status: 400 });
      this.storeInviteCredentials(inviteCode);
      return this.persist({
        access_token: `mock_invite_${Date.now()}`,
        expires_in_seconds: 86400,
        user: { user_id: mockId(inviteCode), phone_e164: null, status: 'active', beta_qualified: true },
      });
    }

    async bindPhone(phone) {
      if (this.mode === 'live') {
        const payload = await this.request('/bind-phone', {
          method: 'POST',
          body: { phone, device_id: this.deviceId() },
          token: this.accessToken,
        });
        if (this.session) this.session = { ...this.session, user: payload.user || this.session.user };
        try { localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(this.session)); } catch { /* ignore */ }
        return payload;
      }
      await wait(360);
      if (this.session) this.session = { ...this.session, user: { ...this.session.user, phone_e164: `+86${phone}` } };
      return { status: 'ok', merged: false, user: this.session?.user || null };
    }

    async upgradeInvite(inviteCode) {
      if (this.mode === 'live') {
        const payload = await this.request('/invite/upgrade', {
          method: 'POST',
          body: { invite_code: inviteCode, device_id: this.deviceId() },
          token: this.accessToken,
        });
        this.storeInviteCredentials(inviteCode);
        if (this.session) this.session = { ...this.session, user: payload.user || this.session.user };
        try { localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(this.session)); } catch { /* ignore */ }
        return payload;
      }
      await wait(360);
      if (String(inviteCode || '').trim().length < 4) throw new SelfitAuthError('请输入有效的邀请码', { code: 'auth.invite_invalid', status: 400 });
      if (this.session) this.session = { ...this.session, user: { ...this.session.user, beta_qualified: true } };
      return { status: 'ok', user: this.session?.user || null };
    }
  }

  window.SelfitAuth = Object.freeze({
    createClient: (config) => new SelfitAuthClient(config),
    SelfitAuthError,
    storageKey: AUTH_STORAGE_KEY,
  });
})();
