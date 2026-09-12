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

  const MOCK_PHOTO_ANALYSES = {
    face: {
      kind: 'face',
      attributes: {
        skin: {
          label: '中性自然肤', status: 'warn', confidence: 0.72,
          metrics: [
            { key: 'lStar', label: '肤色明度 L*', value: '63.8' },
            { key: 'ita', label: '白皙度 ITA', value: '45.3°' },
            { key: 'undertone', label: '肤色底调', value: '中性' },
          ],
          notes: [{ message: '照片整体有偏色', suggestion: '关闭滤镜、用自然光原图，肤色判断会更准。' }],
        },
        faceShape: {
          label: '圆脸', status: 'pass', confidence: 0.86, runnerUp: { label: '心形脸', score: 0.4 },
          metrics: [
            { key: 'lengthWidth', label: '脸长 / 脸宽', value: '1.074' },
            { key: 'jawCheek', label: '下颌宽 / 颧骨宽', value: '0.787' },
            { key: 'foreheadCheek', label: '额头宽 / 颧骨宽', value: '0.98' },
          ],
          notes: [{ message: '脸部细节略软，已继续分析', suggestion: '这张照片可以先测；更清晰的原图会让结果更稳定。' }],
        },
      },
      notes: [],
    },
    body: {
      kind: 'body',
      attributes: {
        bodyShape: {
          label: '梨型', status: 'pass', confidence: 0.78,
          metrics: [
            { key: 'hipShoulder', label: '胯宽 / 肩宽', value: '1.12' },
            { key: 'waistHip', label: '腰宽 / 胯宽', value: '0.72' },
          ],
          notes: [{ message: '衣服比较宽松，身形判断可能不准', suggestion: '宽松衣物会遮住腰线；穿修身一些的照片会更准。' }],
        },
      },
      notes: [],
    },
  };

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

    async request(path, { method = 'GET', body, formData, signal, idempotencyKey, timeoutMs = this.timeoutMs, blob = false } = {}) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort('timeout'), timeoutMs);
      const onAbort = () => controller.abort(signal.reason);
      if (signal?.aborted) onAbort();
      else if (signal) signal.addEventListener('abort', onAbort, { once: true });
      const headers = formData ? { Accept: 'application/json' } : { ...jsonHeaders };
      if (blob) headers.Accept = 'image/webp,image/*';
      if (idempotencyKey) headers['X-Idempotency-Key'] = idempotencyKey;
      const accessToken = this.getAccessToken();
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
      try {
        const response = await fetch(`${this.baseUrl}${path}`, {
          method, credentials: 'include', headers, signal: controller.signal,
          body: formData || (body === undefined ? undefined : JSON.stringify(body)),
        });
        if (blob && response.ok) return await response.blob();
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
        signal?.removeEventListener('abort', onAbort);
      }
    }

    createSession(payload = {}) {
      if (this.mode === 'live') return this.request('/sessions', { method: 'POST', body: payload, idempotencyKey: uid('session') });
      const session = { sessionId: uid('ses'), status: 'draft', revision: 1, expiresAt: new Date(Date.now() + 86400000).toISOString(), ...payload, requiresGender: Boolean(payload.onboardingMode), gender: null };
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
      const session = this.mockSessions.get(sessionId);
      if (session && !invalid) {
        if (session.requiresGender && !session.gender) return Promise.reject(new SelfitApiError('请先选择性别，再上传照片。'));
        session.photoAnalyses = { ...(session.photoAnalyses || {}), [kind]: MOCK_PHOTO_ANALYSES[kind] };
        delete (session.samplePhotos || {})[kind];
        for (const key of (kind === 'face' ? ['skin', 'faceShape'] : ['bodyShape'])) delete (session.manual || {})[key];
      }
      return wait(560).then(() => ({
        revision: this.bumpRevision(sessionId),
        photo: {
          kind, assetId: invalid ? null : uid(`asset_${kind}`), status: invalid ? 'rejected' : 'accepted',
          code: invalid ? 'photo.insufficient_light' : 'photo.accepted',
          message: invalid ? `${label}光线不充足` : `${label} 可用`, issues: invalid ? ['insufficient_light'] : [],
        },
        ...(invalid ? {} : { analysis: MOCK_PHOTO_ANALYSES[kind] }),
      }));
    }

    useSamplePhoto(sessionId, kind, sampleId, { signal, idempotencyKey = uid(`sample_${kind}`) } = {}) {
      if (this.mode === 'live') {
        return this.request(`/sessions/${encodeURIComponent(sessionId)}/photos/${encodeURIComponent(kind)}/sample`, {
          method: 'POST', body: { sampleId }, signal, idempotencyKey, timeoutMs: 45000,
        });
      }
      const session = this.mockSessions.get(sessionId);
      if (!session || sampleId !== `${session.gender}-${kind}`) return Promise.reject(new SelfitApiError('请按当前选择的性别使用示例照片。'));
      return this.checkPhoto(sessionId, kind, { name: sampleId }, { signal }).then(result => {
        if (!signal?.aborted) session.samplePhotos = { ...(session.samplePhotos || {}), [kind]: sampleId };
        return result;
      });
    }

    getSuit(sessionId) {
      if (this.mode === 'live') return this.request(`/sessions/${encodeURIComponent(sessionId)}/suit`);
      const session = this.mockSessions.get(sessionId) || {};
      const analyses = session.photoAnalyses || {};
      const photoLabels = { face: '面部照', body: '全身照' };
      return Promise.resolve({ revision: session.revision, photos: { face: Boolean(analyses.face), body: Boolean(analyses.body) }, samplePhotos: session.samplePhotos || {}, analyses, features: [
        ['skin', '肤色'], ['faceShape', '脸型'], ['bodyShape', '身材比例'],
      ].map(([key, title]) => {
        const kind = key === 'bodyShape' ? 'body' : 'face';
        const analysis = (analyses[kind] || {}).attributes?.[key] || null;
        const value = session.manual?.[key] || analysis?.label || null;
        const source = session.manual?.[key] ? 'manual' : (analysis ? 'photo' : 'unknown');
        const description = analysis ? '预览模式：以下分析数值为示例数据。'
          : (analyses[kind] ? '照片中还看不清这项特点，你可以手动选择。'
            : `还没有上传${photoLabels[kind]}，上传后可以自动识别；也可以直接手动选择。`);
        return { key, title, value, source, description, advice: '可手动选择更接近自己的特点。' };
      }) });
    }

    getSuitPhoto(sessionId, kind, { signal } = {}) {
      return this.request(`/sessions/${encodeURIComponent(sessionId)}/photos/${encodeURIComponent(kind)}/preview`, { blob: true, signal, timeoutMs: 45000 });
    }

    saveGender(sessionId, gender) {
      if (this.mode === 'live') return this.patchSession(sessionId, '/gender', { gender });
      if (!['female', 'male'].includes(gender)) return Promise.reject(new SelfitApiError('请选择你的性别。'));
      const session = this.mockSessions.get(sessionId);
      for (const [kind, sampleId] of Object.entries(session?.samplePhotos || {})) {
        if (!sampleId.startsWith(`${gender}-`)) {
          delete session.samplePhotos[kind];
          delete (session.photoAnalyses || {})[kind];
          for (const field of (kind === 'face' ? ['skin', 'faceShape'] : ['bodyShape'])) delete (session.manual || {})[field];
        }
      }
      return this.mockPatch(sessionId, { gender });
    }

    saveManualProfile(sessionId, profile) {
      if (this.mode === 'live') return this.patchSession(sessionId, '/profile', { manual: profile });
      return this.mockPatch(sessionId, { manual: { ...this.mockSessions.get(sessionId)?.manual, ...profile } });
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
      if (session.requiresGender && !session.gender) return Promise.reject(new SelfitApiError('请先选择性别，再生成型格报告。'));
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

    getLatestReport() {
      if (this.mode === 'live') return this.request('/reports/latest');
      return Promise.resolve({ report: null });
    }

    getMirrorHandoff(token) {
      return this.request(`/mirror/handoffs/${encodeURIComponent(token)}`);
    }

    claimMirrorHandoff(token) {
      return this.request(`/mirror/handoffs/${encodeURIComponent(token)}/claim`, { method: 'POST', body: {} });
    }

    createShareAsset(reportId, payload) {
      if (this.mode === 'live') return this.request(`/reports/${encodeURIComponent(reportId)}/share-assets`, { method: 'POST', body: payload, idempotencyKey: uid('share') });
      return wait(300).then(() => ({ asset: { assetId: uid('share'), status: 'ready', slideIndex: payload.slideIndex, channel: payload.channel, downloadUrl: null } }));
    }

    createPublicShare(reportId, payload = {}) {
      if (this.mode === 'live') return this.request(`/reports/${encodeURIComponent(reportId)}/public-shares`, { method: 'POST', body: payload, idempotencyKey: uid('public_share') });
      const token = uid('shared_report');
      const origin = window.location.origin;
      return wait(240).then(() => ({ share: {
        shareId: uid('shr'),
        url: `${origin}/s/${token}`,
        thumbnailUrl: `${origin}/s/${token}/cover.png`,
        qrUrl: `${origin}/s/${token}/qr.png`,
        expiresAt: new Date(Date.now() + 7 * 86400000).toISOString(),
      } }));
    }

    getPublicShare(token) {
      if (this.mode === 'live') return this.request(`/public-shares/${encodeURIComponent(token)}`);
      const report = this.buildMockReport ? this.buildMockReport({}) : {};
      return Promise.resolve({ report, share: { expiresAt: new Date(Date.now() + 7 * 86400000).toISOString() } });
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
