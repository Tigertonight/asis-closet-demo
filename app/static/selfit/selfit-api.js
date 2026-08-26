(() => {
  const jsonHeaders = { Accept: 'application/json', 'Content-Type': 'application/json' };
  const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
  const uid = (prefix) => `${prefix}_${globalThis.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(16).slice(2)}`}`;

  class SelfitApiError extends Error {
    constructor(message, { code = 'selfit.unknown', status = 0, retryable = false, details = null } = {}) {
      super(message);
      this.name = 'SelfitApiError';
      this.code = code;
      this.status = status;
      this.retryable = retryable;
      this.details = details;
    }
  }

  class SelfitApiClient {
    constructor({ mode = 'mock', baseUrl = '/api/v1/selfit', timeoutMs = 15000, buildMockReport, getAccessToken } = {}) {
      this.mode = mode === 'live' ? 'live' : 'mock';
      this.baseUrl = baseUrl.replace(/\/$/, '');
      this.timeoutMs = timeoutMs;
      this.buildMockReport = buildMockReport;
      this.getAccessToken = typeof getAccessToken === 'function' ? getAccessToken : () => null;
      this.mockSessions = new Map();
      this.mockJobs = new Map();
      this.mockReports = new Map();
    }

    async request(path, { method = 'GET', body, formData, signal, idempotencyKey, timeoutMs = this.timeoutMs } = {}) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort('timeout'), timeoutMs);
      if (signal) signal.addEventListener('abort', () => controller.abort(signal.reason), { once: true });
      const headers = formData ? { Accept: 'application/json' } : { ...jsonHeaders };
      if (idempotencyKey) headers['X-Idempotency-Key'] = idempotencyKey;
      const accessToken = this.getAccessToken();
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
      try {
        const response = await fetch(`${this.baseUrl}${path}`, {
          method, credentials: 'include', headers, signal: controller.signal,
          body: formData || (body === undefined ? undefined : JSON.stringify(body)),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          const error = payload.error || {};
          throw new SelfitApiError(error.message || payload.detail || '这次请求没有完成，请稍后重试。', {
            code: error.code || `http.${response.status}`,
            status: response.status,
            retryable: error.retryable ?? response.status >= 500,
            details: error.details || null,
          });
        }
        return payload;
      } catch (error) {
        if (error instanceof SelfitApiError) throw error;
        if (controller.signal.aborted) throw new SelfitApiError('请求超时，请检查网络后重试。', { code: 'network.timeout', retryable: true });
        throw new SelfitApiError('网络连接失败，请稍后重试。', { code: 'network.unavailable', retryable: true, details: String(error) });
      } finally {
        clearTimeout(timeout);
      }
    }

    createSession(payload = {}) {
      if (this.mode === 'live') return this.request('/sessions', { method: 'POST', body: payload, idempotencyKey: uid('session') });
      const session = { sessionId: uid('ses'), status: 'draft', revision: 1, expiresAt: new Date(Date.now() + 86400000).toISOString(), ...payload };
      this.mockSessions.set(session.sessionId, session);
      return wait(120).then(() => ({ session }));
    }

    getSession(sessionId) {
      if (this.mode === 'live') return this.request(`/sessions/${encodeURIComponent(sessionId)}`);
      const session = this.mockSessions.get(sessionId);
      if (!session) return Promise.reject(new SelfitApiError('会话已失效，请重新开始。', { code: 'session.expired', status: 404 }));
      return Promise.resolve({ session });
    }

    checkPhoto(sessionId, kind, file, { signal } = {}) {
      if (this.mode === 'live') {
        const formData = new FormData();
        formData.append('image', file, file.name);
        return this.request(`/sessions/${encodeURIComponent(sessionId)}/photos/${encodeURIComponent(kind)}`, {
          method: 'POST', formData, signal, idempotencyKey: uid(`photo_${kind}`), timeoutMs: 45000,
        });
      }
      const invalid = /dark|invalid|暗|黑/i.test(file.name);
      const label = kind === 'face' ? '面部照' : '全身照';
      return wait(560).then(() => ({
        revision: this.bumpRevision(sessionId),
        photo: {
          kind, assetId: invalid ? null : uid(`asset_${kind}`), status: invalid ? 'rejected' : 'accepted',
          code: invalid ? 'photo.insufficient_light' : 'photo.accepted',
          message: invalid ? `${label}光线不充足` : `${label} 可用`, issues: invalid ? ['insufficient_light'] : [],
        },
      }));
    }

    saveManualProfile(sessionId, profile) {
      if (this.mode === 'live') return this.patchSession(sessionId, '/profile', { manual: profile });
      return this.mockPatch(sessionId, { manual: profile });
    }

    savePreferences(sessionId, preferences) {
      if (this.mode === 'live') return this.patchSession(sessionId, '/preferences', preferences);
      return this.mockPatch(sessionId, { preferences });
    }

    saveVibe(sessionId, answers) {
      if (this.mode === 'live') return this.patchSession(sessionId, '/vibe', { answers });
      return this.mockPatch(sessionId, { answers });
    }

    patchSession(sessionId, suffix, body) {
      return this.request(`/sessions/${encodeURIComponent(sessionId)}${suffix}`, { method: 'PATCH', body, idempotencyKey: uid('patch') });
    }

    async mockPatch(sessionId, patch) {
      const session = this.requireMockSession(sessionId);
      Object.assign(session, patch, { revision: session.revision + 1 });
      await wait(120);
      return { session: { sessionId, status: session.status, revision: session.revision } };
    }

    createReportJob(sessionId) {
      if (this.mode === 'live') return this.request(`/sessions/${encodeURIComponent(sessionId)}/report-jobs`, { method: 'POST', body: {}, idempotencyKey: uid('report') });
      const session = this.requireMockSession(sessionId);
      const job = { jobId: uid('job'), sessionId, status: 'queued', progress: 0, stage: 'queued', startedAt: Date.now(), reportId: uid('rep') };
      this.mockJobs.set(job.jobId, job);
      const report = this.buildMockReport ? this.buildMockReport(session) : {};
      this.mockReports.set(job.reportId, report);
      return wait(120).then(() => ({ job: { jobId: job.jobId, status: 'queued', progress: 0, pollAfterMs: 350 } }));
    }

    getReportJob(jobId) {
      if (this.mode === 'live') return this.request(`/report-jobs/${encodeURIComponent(jobId)}`);
      const job = this.mockJobs.get(jobId);
      if (!job) return Promise.reject(new SelfitApiError('没有找到报告任务。', { code: 'report.job_not_found', status: 404 }));
      const elapsed = Date.now() - job.startedAt;
      const steps = [
        { at: 0, progress: 25, stage: 'profile' },
        { at: 700, progress: 50, stage: 'inspiration' },
        { at: 1400, progress: 75, stage: 'composition' },
        { at: 2100, progress: 100, stage: 'finalizing' },
      ];
      const current = [...steps].reverse().find((step) => elapsed >= step.at) || steps[0];
      const completed = elapsed >= 2800;
      return Promise.resolve({ job: {
        jobId, status: completed ? 'completed' : 'processing', progress: current.progress, stage: current.stage,
        pollAfterMs: 350, ...(completed ? { reportId: job.reportId, report: this.mockReports.get(job.reportId) } : {}),
      } });
    }

    getReport(reportId) {
      if (this.mode === 'live') return this.request(`/reports/${encodeURIComponent(reportId)}`);
      const report = this.mockReports.get(reportId);
      if (!report) return Promise.reject(new SelfitApiError('没有找到这份报告。', { code: 'report.not_found', status: 404 }));
      return Promise.resolve({ report });
    }

    createShareAsset(reportId, payload) {
      if (this.mode === 'live') return this.request(`/reports/${encodeURIComponent(reportId)}/share-assets`, { method: 'POST', body: payload, idempotencyKey: uid('share') });
      return wait(300).then(() => ({ asset: { assetId: uid('share'), status: 'ready', slideIndex: payload.slideIndex, channel: payload.channel, downloadUrl: null } }));
    }

    requestOutfit(reportId, payload = {}) {
      if (this.mode === 'live') return this.request(`/reports/${encodeURIComponent(reportId)}/outfit-requests`, { method: 'POST', body: payload, idempotencyKey: uid('outfit') });
      return wait(320).then(() => ({ request: { requestId: uid('outfit'), status: 'queued' } }));
    }

    requireMockSession(sessionId) {
      const session = this.mockSessions.get(sessionId);
      if (!session) throw new SelfitApiError('会话已失效，请重新开始。', { code: 'session.expired', status: 404 });
      return session;
    }

    bumpRevision(sessionId) {
      const session = this.requireMockSession(sessionId);
      session.revision += 1;
      return session.revision;
    }
  }

  window.SelfitApi = Object.freeze({
    createClient: (config) => new SelfitApiClient(config),
    SelfitApiError,
  });
})();
