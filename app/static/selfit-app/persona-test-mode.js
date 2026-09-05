/* A preview-only state machine. No profile, report or URL writes. */
(function (root) {
  function create(typeIds) {
    const allowed = new Set(typeIds);
    let enabled = false, typeId = "", taps = [];
    return {
      get enabled() { return enabled; },
      get typeId() { return typeId; },
      tap(tab, now, defaultType) {
        if (tab !== "me") { taps = []; return false; }
        taps = taps.filter(time => now - time <= 5000);
        taps.push(now);
        if (taps.length < 5) return false;
        taps = [];
        enabled = !enabled;
        typeId = enabled ? (allowed.has(defaultType) ? defaultType : typeIds[0] || "") : "";
        return true;
      },
      select(next) {
        if (!enabled || !allowed.has(next)) return false;
        typeId = next;
        return true;
      },
      restore(saved) {
        enabled = saved?.enabled === true && allowed.has(saved.typeId);
        typeId = enabled ? saved.typeId : "";
        taps = [];
      },
      snapshot() { return { enabled, typeId }; }
    };
  }
  root.SelfitPersonaTest = { create };
  if (typeof module !== "undefined" && module.exports) module.exports = { create };
})(typeof window !== "undefined" ? window : globalThis);
