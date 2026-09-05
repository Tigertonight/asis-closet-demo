/* Only visible cards earn exposure. No profile data or persisted UI state. */
(function(root) {
  function create({onExposure, Observer = root.IntersectionObserver, clock = root, document = root.document}) {
    const timers = new Map(), ratios = new Map(), sent = new Set(), nodes = new Set();
    function cancel(node) { if (timers.has(node)) clock.clearTimeout(timers.get(node)); timers.delete(node); }
    function schedule(node) {
      cancel(node);
      if (document.hidden || (ratios.get(node) || 0) < .5 || sent.has(node)) return;
      timers.set(node, clock.setTimeout(async () => {
        timers.delete(node);
        if (!node.isConnected || document.hidden || (ratios.get(node) || 0) < .5 || sent.has(node)) return;
        sent.add(node);
        try {
          const ok = await onExposure(node, {visible_ratio: ratios.get(node), visible_ms: 1000});
          if (ok === false) sent.delete(node);
        } catch (_) { sent.delete(node); }
      }, 1000));
    }
    const observer = new Observer(entries => entries.forEach(entry => {
      ratios.set(entry.target, entry.isIntersecting ? entry.intersectionRatio : 0);
      schedule(entry.target);
    }), {threshold: [0, .5, 1]});
    const visibility = () => nodes.forEach(node => schedule(node));
    document.addEventListener('visibilitychange', visibility);
    return {
      observe(node) { if (!nodes.has(node)) { nodes.add(node); observer.observe(node); } },
      disconnect() { nodes.forEach(cancel); observer.disconnect(); document.removeEventListener('visibilitychange', visibility); nodes.clear(); }
    };
  }
  root.SelfitFeedExposure = {create};
  if (typeof module !== 'undefined' && module.exports) module.exports = {create};
})(typeof window !== 'undefined' ? window : globalThis);
