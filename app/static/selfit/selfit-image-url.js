/* Keep display requests separate from generation inputs and original downloads. */
(function (root) {
  root.SelfitImageURL = function (source, options = {}) {
    if (!source) return '';
    try {
      const url = new URL(source, root.location.href);
      if (url.origin !== root.location.origin || !/^https?:$/.test(url.protocol)) return source;
      const supported = /^\/api\/v1\/material-assets\/asset_[0-9a-f]{64}\/content$/.test(url.pathname)
        || /^\/(?:user-assets|tryon-outputs|closet-outputs|tryon-models|qa-photos|demo-assets|fixture-images)\//.test(url.pathname)
        || url.pathname === '/xhs-image'
        || (/^\/static\//.test(url.pathname) && /\.(?:png|jpe?g|webp)$/i.test(url.pathname));
      if (supported) url.searchParams.set('format', options.original ? 'original' : 'webp');
      return url.href;
    } catch (_) { return source; }
  };
})(window);
