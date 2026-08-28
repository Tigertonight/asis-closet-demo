(function () {
  var root = document.documentElement;
  var frame = 0;

  function addCapability(name, supported) {
    root.classList.add((supported ? 'has-' : 'no-') + name);
  }

  function syncViewport() {
    frame = 0;
    var viewport = window.visualViewport;
    var height = viewport && viewport.height ? viewport.height : window.innerHeight;
    var width = viewport && viewport.width ? viewport.width : window.innerWidth;
    if (height) root.style.setProperty('--visual-viewport-height', Math.round(height) + 'px');
    if (width) root.style.setProperty('--visual-viewport-width', Math.round(width) + 'px');
  }

  function requestViewportSync() {
    if (frame) return;
    frame = window.requestAnimationFrame ? window.requestAnimationFrame(syncViewport) : window.setTimeout(syncViewport, 16);
  }

  addCapability('visual-viewport', Boolean(window.visualViewport));
  addCapability('native-dialog', Boolean(window.HTMLDialogElement && window.HTMLDialogElement.prototype.showModal));
  syncViewport();
  window.addEventListener('resize', requestViewportSync, false);
  window.addEventListener('orientationchange', requestViewportSync, false);
  window.addEventListener('pageshow', requestViewportSync, false);
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', requestViewportSync, false);
    window.visualViewport.addEventListener('scroll', requestViewportSync, false);
  }

  var webp = new Image();
  webp.onload = webp.onerror = function () {
    addCapability('webp', webp.width === 1);
  };
  webp.src = 'data:image/webp;base64,UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEAAUAmJaQAA3AA/v89WAAAAA==';
}());
