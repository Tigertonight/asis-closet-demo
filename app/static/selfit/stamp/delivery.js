/* Server-backed delivery for the standalone kiosk. Never forwards secrets to a third party. */
(() => {
  class StampDelivery {
    constructor() { this.revision = 0; }
    setPhoto(bundle) {
      if (this.bundle?.original === bundle.original && JSON.stringify(this.bundle.settings) === JSON.stringify(bundle.settings)) return;
      this.reset();
      this.bundle = bundle;
      this.secret = Array.from(crypto.getRandomValues(new Uint8Array(32)), v => v.toString(16).padStart(2, '0')).join('');
      void this.save();
    }
    async request(url, options = {}) {
      const response = await fetch(url, { ...options, signal: this.controller.signal, cache: 'no-store' });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error?.message || (typeof data.detail === 'string' && data.detail) || '照片暂时未保存，请重试。');
      }
      return response;
    }
    save() {
      if (this.pending) return this.pending;
      if (!this.bundle || this.qrUrl) return Promise.resolve();
      const revision = this.revision;
      this.error = ''; this.loading = true; this.paint();
      this.controller = new AbortController();
      const controller = this.controller;
      const timeout = setTimeout(() => controller.abort(), 60000);
      this.pending = (async () => {
        try {
          if (!this.record) {
            const body = new FormData();
            body.append('original', this.bundle.original, 'original.jpg');
            body.append('final', this.bundle.final, 'stamp.png');
            body.append('scene', this.bundle.scene, 'scene.png');
            body.append('settings', JSON.stringify(this.bundle.settings));
            const record = await (await this.request('/api/v1/selfit/mirror/photos', { method: 'POST', headers: { 'Idempotency-Key': this.secret }, body })).json();
            if (revision !== this.revision) return;
            this.record = record;
          }
          const blob = await (await this.request(`/api/v1/selfit/mirror/photos/${this.record.photoId}/qr`, { headers: { Authorization: `Bearer ${this.secret}` } })).blob();
          if (revision !== this.revision) return;
          this.qrUrl = URL.createObjectURL(blob);
        } catch (e) {
          if (revision !== this.revision) return;
          this.error = e.name === 'AbortError' ? '保存有些久，照片仍在，请重新尝试。' : e instanceof TypeError ? '网络暂时无法连接，照片仍在，请重新尝试。' : e.message;
        } finally {
          clearTimeout(timeout);
          if (revision === this.revision) { this.pending = null; this.loading = false; this.paint(); }
        }
      })();
      return this.pending;
    }
    open() {
      if (!this.bundle) return;
      if (this.dialog) { this.paint(); return; }
      const dialog = document.createElement('dialog'); dialog.className = 'stamp-receive';
      dialog.innerHTML = `<button class="receive-close" aria-label="关闭领图" type="button">×</button><h2>把纪念邮票带走</h2><p>用手机扫码，领取邮票和出片机展示图</p><div class="receive-qr"><img alt="手机扫码领取照片" hidden></div><p class="receive-status" role="status"></p><button class="receive-retry" type="button" hidden>重新尝试</button><p class="receive-expiry"></p><div class="receive-downloads"><button type="button" data-download="final">保存邮票</button><button type="button" data-download="scene">保存展示图</button></div><p class="receive-hint">也可以在本机保存；若浏览器打开图片，请长按保存。</p>`;
      document.body.append(dialog); this.dialog = dialog;
      dialog.querySelector('.receive-close').onclick = () => this.close();
      dialog.addEventListener('cancel', e => { e.preventDefault(); this.close(); });
      dialog.querySelector('.receive-retry').onclick = () => {
        if (this.record && this.record.expiresAt <= Date.now()) { const bundle = this.bundle; this.reset(); this.setPhoto(bundle); this.open(); }
        else void this.save();
      };
      dialog.querySelectorAll('[data-download]').forEach(button => { button.onclick = () => this.download(button.dataset.download); });
      dialog.showModal(); this.paint(); void this.save();
      this.expiryTimer = setInterval(() => this.paint(), 10000);
    }
    paint() {
      if (!this.dialog) return;
      const expired = this.record && this.record.expiresAt <= Date.now();
      const image = this.dialog.querySelector('img');
      image.hidden = !this.qrUrl || !!expired;
      if (!image.hidden && image.src !== this.qrUrl) image.src = this.qrUrl;
      this.dialog.querySelector('.receive-status').textContent = expired ? '领取链接已过期，请重新生成。' : this.error || (this.loading ? '正在保存照片，准备领取二维码…' : '照片已保存，扫码即可领取');
      this.dialog.querySelector('.receive-retry').hidden = !this.error && !expired;
      this.dialog.querySelector('.receive-retry').disabled = !!this.loading;
      this.dialog.querySelector('.receive-expiry').textContent = this.record && !expired ? `领取有效期至 ${new Date(this.record.expiresAt).toLocaleString('zh-CN')}` : '';
    }
    download(kind) {
      const blob = this.bundle?.[kind]; if (!blob) return;
      const url = URL.createObjectURL(blob), link = document.createElement('a');
      link.href = url; link.download = kind === 'scene' ? 'WOKEN-DAY-MACHINE.png' : 'WOKEN-DAY-STAMP.png';
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    }
    close() {
      clearInterval(this.expiryTimer);
      this.dialog?.close(); this.dialog?.remove(); this.dialog = null;
    }
    reset() {
      this.revision++; this.controller?.abort(); this.close();
      if (this.qrUrl) URL.revokeObjectURL(this.qrUrl);
      this.qrUrl = ''; this.record = null; this.bundle = null; this.pending = null; this.loading = false; this.error = '';
    }
  }
  window.StampDelivery = StampDelivery;
})();
