(function () {
  var root = document.documentElement;
  var frame = 0;
  var focusTimer = 0;
  var stableHeight = 0;
  var stableWidth = 0;
  var restoreWaiters = [];

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
    var isDismissingKeyboard = root.classList.contains('is-keyboard-dismissing');
    var layoutHeight = Math.max(window.innerHeight || 0, height || 0);

    if (!hasEditableFocus) syncStableViewport(layoutHeight, width, Boolean(forceStable));
    else if (!stableHeight) syncStableViewport(layoutHeight, width, true);

    if (height) root.style.setProperty('--visual-viewport-height', Math.round(height) + 'px');
    if (width) root.style.setProperty('--visual-viewport-width', Math.round(width) + 'px');
    root.style.setProperty('--visual-viewport-offset-top', Math.round(viewport.offsetTop) + 'px');

    var keyboardThreshold = Math.max(120, stableHeight * 0.18);
    var keyboardOpen = hasEditableFocus && stableHeight - height > keyboardThreshold;
    root.classList.toggle('has-editable-focus', hasEditableFocus || isDismissingKeyboard);
    root.classList.toggle('is-keyboard-open', keyboardOpen || (isDismissingKeyboard && root.classList.contains('is-keyboard-open')));
  }

  function requestViewportSync(forceStable) {
    if (frame) return;
    var callback = function () { syncViewport(forceStable); };
    frame = window.requestAnimationFrame ? window.requestAnimationFrame(callback) : window.setTimeout(callback, 16);
  }

  function restoreDocumentOrigin() {
    if (window.scrollX || window.scrollY) window.scrollTo(0, 0);
  }

  function viewportHasRestored() {
    var viewport = readViewport();
    if (!stableHeight || !viewport.height) return true;
    return stableHeight - viewport.height < Math.max(48, stableHeight * 0.08);
  }

  function clearEditableState() {
    root.classList.remove('has-editable-focus');
    root.classList.remove('is-keyboard-open');
    root.classList.remove('is-keyboard-dismissing');
    restoreDocumentOrigin();
    requestViewportSync(false);
  }

  function waitForViewportRestore(timeout) {
    return new Promise(function (resolve) {
      var startedAt = Date.now();
      var done = false;
      var check;
      var finish = function () {
        if (done) return;
        done = true;
        restoreWaiters = restoreWaiters.filter(function (waiter) { return waiter !== check; });
        clearEditableState();
        resolve();
      };
      check = function () {
        if (viewportHasRestored() || Date.now() - startedAt >= timeout) finish();
      };
      restoreWaiters.push(check);
      check();
      if (!done) window.setTimeout(finish, timeout);
    });
  }

  function notifyViewportWaiters() {
    restoreWaiters.slice().forEach(function (waiter) { waiter(); });
  }

  function dismissKeyboard() {
    var activeElement = document.activeElement;
    if (!isEditable(activeElement) && !root.classList.contains('is-keyboard-open')) return Promise.resolve();
    window.clearTimeout(focusTimer);
    root.classList.add('is-keyboard-dismissing');
    if (isEditable(activeElement) && activeElement.blur) activeElement.blur();
    restoreDocumentOrigin();
    requestViewportSync(false);
    return waitForViewportRestore(700);
  }

  function handleFocusIn(event) {
    if (!isEditable(event.target)) return;
    window.clearTimeout(focusTimer);
    root.classList.remove('is-keyboard-dismissing');
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
    root.classList.add('is-keyboard-dismissing');
    focusTimer = window.setTimeout(function () {
      if (isEditable(document.activeElement)) return;
      if (!restoreWaiters.length) void waitForViewportRestore(700);
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
  window.addEventListener('resize', function () { requestViewportSync(false); notifyViewportWaiters(); }, false);
  window.addEventListener('orientationchange', handleOrientationChange, false);
  window.addEventListener('pageshow', function () { requestViewportSync(true); }, false);
  window.addEventListener('scroll', function () {
    if (root.classList.contains('has-editable-focus')) restoreDocumentOrigin();
  }, false);
  document.addEventListener('focusin', handleFocusIn, false);
  document.addEventListener('focusout', handleFocusOut, false);
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', function () { requestViewportSync(false); notifyViewportWaiters(); }, false);
    window.visualViewport.addEventListener('scroll', function () { requestViewportSync(false); notifyViewportWaiters(); }, false);
  }

  window.SelfitViewport = Object.freeze({ dismissKeyboard: dismissKeyboard });

  var webp = new Image();
  webp.onload = webp.onerror = function () {
    addCapability('webp', webp.width === 1);
  };
  webp.src = 'data:image/webp;base64,UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEAAUAmJaQAA3AA/v89WAAAAA==';
}());
