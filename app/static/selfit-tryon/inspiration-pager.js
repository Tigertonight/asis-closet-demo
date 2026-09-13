/* Warm one upcoming batch near the viewport; never block browsing on images. */
(function (global) {
  let observer = null, watchVersion = 0, catalog = null;
  let active = 0;
  const queue = [], seen = new Set();
  function disconnect() {
    watchVersion++;
    observer?.disconnect();
    observer = null;
  }
  function reset() {
    disconnect();
    queue.length = 0;
    seen.clear();
    catalog = null;
  }
  function pump() {
    while (active < 4 && queue.length) {
      const photo = new global.Image();
      active++;
      photo.decoding = 'async';
      photo.fetchPriority = 'low';
      let finished = false;
      const finish = () => {
        if (finished) return;
        finished = true;
        photo.onload = photo.onerror = null;
        active--;
        pump();
      };
      photo.onload = photo.onerror = finish;
      photo.src = queue.shift();
    }
  }
  function preload(urls) {
    for (const url of urls) {
      if (!url || seen.has(url)) continue;
      seen.add(url);
      queue.push(url);
    }
    pump();
  }
  function watch({root, sentinel, context, onMore}) {
    disconnect();
    if (catalog !== context) {
      queue.length = 0;
      seen.clear();
      catalog = context;
    }
    // The visible button remains a keyboard and older-browser fallback.
    if (!sentinel || !global.IntersectionObserver) return;
    const version = watchVersion;
    observer = new global.IntersectionObserver(entries => {
      if (version !== watchVersion || !sentinel.isConnected || !entries.some(entry => entry.isIntersecting)) return;
      disconnect();
      onMore();
    }, {root, rootMargin: `${Math.max(200, root.clientHeight || 800)}px 0px`, threshold: 0});
    observer.observe(sentinel);
  }
  global.SelfitInspirationPager = {watch, preload, reset};
})(typeof window === 'undefined' ? globalThis : window);
