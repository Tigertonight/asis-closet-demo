(() => {
  const key = 'selfit.mirrorClient.v1';
  const valid = value => typeof value === 'string' && value.length === 35 && /^mc_[a-f0-9]{32}$/.test(value);
  let id = null;
  try { const saved = localStorage.getItem(key); if (valid(saved)) id = saved; } catch (_) {}
  if (!id) {
    try {
      const bytes = new Uint8Array(16);
      globalThis.crypto.getRandomValues(bytes);
      id = 'mc_' + Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
      try { localStorage.setItem(key, id); } catch (_) { /* Page-scoped when storage is unavailable. */ }
    } catch (_) { /* Diagnostics must not prevent viewing or saving a photo. */ }
  }
  // Random first-party browser identifier, never a hardware/XHS ID or credential.
  globalThis.SelfitMirrorClient = Object.freeze({ id,
    headers: () => id ? { 'X-Selfit-Client-Id': id } : {},
  });
})();
