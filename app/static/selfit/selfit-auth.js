(() => {
  const AUTH_STORAGE_KEY = 'selfit.auth.session.v1';
  const jsonHeaders = { Accept: 'application/json', 'Content-Type': 'application/json' };
  const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
  const mockId = (value) => `mock_${String(value || 'invite').replace(/\D/g, '').slice(-6) || 'invite'}`;

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

    readStoredSession() {
      try {
        const stored = JSON.parse(sessionStorage.getItem(AUTH_STORAGE_KEY) || 'null');
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
      sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(this.session));
      return this.session;
    }

    clear() {
      this.session = null;
      sessionStorage.removeItem(AUTH_STORAGE_KEY);
    }

    async request(path, { method = 'GET', body, token, timeoutMs = this.timeoutMs } = {}) {
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

    async restore() {
      const stored = this.readStoredSession();
      if (!stored) return null;
      if (this.mode === 'mock') {
        this.session = stored;
        return stored;
      }
      try {
        const result = await this.request('/me', { token: stored.accessToken });
        this.session = { ...stored, user: result.user || stored.user };
        sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(this.session));
        return this.session;
      } catch {
        this.clear();
        return null;
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
        user: { user_id: mockId(phone), phone_e164: `+86${phone}`, status: 'active' },
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
        user: { user_id: mockId(phone), phone_e164: `+86${phone}`, status: 'active' },
      });
    }

    async verifyInvite(inviteCode) {
      if (this.mode === 'live') {
        const payload = await this.request('/invite/verify', { method: 'POST', body: { invite_code: inviteCode } });
        return this.persist(payload);
      }
      await wait(360);
      if (String(inviteCode || '').trim().length < 4) throw new SelfitAuthError('请输入有效的邀请码', { code: 'auth.invite_invalid', status: 400 });
      return this.persist({
        access_token: `mock_invite_${Date.now()}`,
        expires_in_seconds: 86400,
        user: { user_id: mockId(inviteCode), phone_e164: null, status: 'active' },
      });
    }
  }

  window.SelfitAuth = Object.freeze({
    createClient: (config) => new SelfitAuthClient(config),
    SelfitAuthError,
    storageKey: AUTH_STORAGE_KEY,
  });
})();
