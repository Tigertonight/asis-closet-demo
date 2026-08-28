(function () {
  var root = document.documentElement;
  var frame = 0;
  var focusTimer = 0;
  var stableHeight = 0;
  var stableWidth = 0;

  function addCapability(name, supported) {
    root.classList.add((supported ? 'has-' : 'no-') + name);
  }

  function isEditable(element) {
    if (!element || element.nodeType !== 1) return false;
    var tagName = element.tagName;
    if (tagName === 'TEXTAREA' || element.isContentEditable) return true;
    if (tagName !== 'INPUT') return false;
    var inputType = (element.getAttribute('type') || 'text').toLowerCase();
    return ['email', 'number', 'password', 'search', 'tel', 'text', 'url'].indexOf(inputType) !== -1;
  }

  function readViewport() {
    var viewport = window.visualViewport;
    return {
      height: viewport && viewport.height ? viewport.height : window.innerHeight,
      width: viewport && viewport.width ? viewport.width : window.innerWidth,
      offsetTop: viewport && viewport.offsetTop ? viewport.offsetTop : 0,
    };
  }

  function syncStableViewport(height, width, force) {
    if (!height) return;
    var widthChanged = stableWidth && width && Math.abs(width - stableWidth) > 80;
    if (force || !stableHeight || widthChanged) stableHeight = Math.round(height);
    else stableHeight = Math.max(stableHeight, Math.round(height));
    if (width) stableWidth = Math.round(width);
    root.style.setProperty('--app-viewport-height', stableHeight + 'px');
  }

  function syncViewport(forceStable) {
    frame = 0;
    var viewport = readViewport();
    var height = viewport.height;
    var width = viewport.width;
    var hasEditableFocus = isEditable(document.activeElement);
    var layoutHeight = Math.max(window.innerHeight || 0, height || 0);

    if (!hasEditableFocus) syncStableViewport(layoutHeight, width, Boolean(forceStable));
    else if (!stableHeight) syncStableViewport(layoutHeight, width, true);

    if (height) root.style.setProperty('--visual-viewport-height', Math.round(height) + 'px');
    if (width) root.style.setProperty('--visual-viewport-width', Math.round(width) + 'px');
    root.style.setProperty('--visual-viewport-offset-top', Math.round(viewport.offsetTop) + 'px');

    var keyboardThreshold = Math.max(120, stableHeight * 0.18);
    var keyboardOpen = hasEditableFocus && stableHeight - height > keyboardThreshold;
    root.classList.toggle('has-editable-focus', hasEditableFocus);
    root.classList.toggle('is-keyboard-open', keyboardOpen);
  }

  function requestViewportSync(forceStable) {
    if (frame) return;
    var callback = function () { syncViewport(forceStable); };
    frame = window.requestAnimationFrame ? window.requestAnimationFrame(callback) : window.setTimeout(callback, 16);
  }

  function restoreDocumentOrigin() {
    if (window.scrollX || window.scrollY) window.scrollTo(0, 0);
  }

  function handleFocusIn(event) {
    if (!isEditable(event.target)) return;
    window.clearTimeout(focusTimer);
    var viewport = readViewport();
    syncStableViewport(Math.max(window.innerHeight || 0, viewport.height || 0), viewport.width, false);
    root.classList.add('has-editable-focus');
    restoreDocumentOrigin();
    requestViewportSync(false);
    focusTimer = window.setTimeout(function () {
      restoreDocumentOrigin();
      requestViewportSync(false);
    }, 320);
  }

  function handleFocusOut() {
    window.clearTimeout(focusTimer);
    focusTimer = window.setTimeout(function () {
      if (isEditable(document.activeElement)) return;
      root.classList.remove('has-editable-focus');
      root.classList.remove('is-keyboard-open');
      restoreDocumentOrigin();
      requestViewportSync(false);
      window.setTimeout(function () {
        restoreDocumentOrigin();
        requestViewportSync(false);
      }, 320);
    }, 80);
  }

  function handleOrientationChange() {
    if (isEditable(document.activeElement)) return;
    stableHeight = 0;
    stableWidth = 0;
    window.setTimeout(function () { requestViewportSync(true); }, 120);
  }

  addCapability('visual-viewport', Boolean(window.visualViewport));
  addCapability('native-dialog', Boolean(window.HTMLDialogElement && window.HTMLDialogElement.prototype.showModal));
  syncViewport(true);
  window.addEventListener('resize', function () { requestViewportSync(false); }, false);
  window.addEventListener('orientationchange', handleOrientationChange, false);
  window.addEventListener('pageshow', function () { requestViewportSync(true); }, false);
  window.addEventListener('scroll', function () {
    if (root.classList.contains('has-editable-focus')) restoreDocumentOrigin();
  }, false);
  document.addEventListener('focusin', handleFocusIn, false);
  document.addEventListener('focusout', handleFocusOut, false);
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', function () { requestViewportSync(false); }, false);
    window.visualViewport.addEventListener('scroll', function () { requestViewportSync(false); }, false);
  }

  var webp = new Image();
  webp.onload = webp.onerror = function () {
    addCapability('webp', webp.width === 1);
  };
  webp.src = 'data:image/webp;base64,UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEAAUAmJaQAA3AA/v89WAAAAA==';
}());
