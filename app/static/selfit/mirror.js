(() => {
  const app = document.querySelector('#mirrorApp');
  const screens = [...document.querySelectorAll('[data-screen]')];
  const video = document.querySelector('#cameraVideo');
  const canvas = document.querySelector('#captureCanvas');
  const capturedPhoto = document.querySelector('#capturedPhoto');
  const resultPhoto = document.querySelector('#resultPhoto');
  const startCapture = document.querySelector('#startCapture');
  const countdownNumber = document.querySelector('#countdownNumber');
  const cameraHint = document.querySelector('#cameraHint');
  const toast = document.querySelector('#permissionToast');
  const config = window.__SELFIT_MIRROR_CONFIG__ || {};
  const timers = new Set();
  let stream = null;
  let photoUrl = '';
  let busy = false;
  let countdownRun = 0;
  let analysisRun = 0;

  const fitCanvas = () => {
    const scale = Math.min(window.innerWidth / 393, window.innerHeight / 698);
    app.style.setProperty('--mirror-scale', String(scale));
  };
  fitCanvas();
  window.addEventListener('resize', fitCanvas, { passive: true });

  const later = (callback, delay) => {
    const timer = window.setTimeout(() => { timers.delete(timer); callback(); }, delay);
    timers.add(timer);
    return timer;
  };
  const clearTimers = () => { timers.forEach(window.clearTimeout); timers.clear(); };
  const show = (name) => {
    screens.forEach((screen) => {
      const active = screen.dataset.screen === name;
      screen.classList.toggle('is-active', active);
      screen.setAttribute('aria-hidden', String(!active));
      screen.inert = !active;
    });
    app.dataset.state = name;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', ['home', 'processing'].includes(name) ? '#792a28' : '#797979');
  };
  const notify = (message, duration = 2600) => {
    toast.textContent = message; toast.hidden = false;
    later(() => { toast.hidden = true; }, duration);
  };
  const stopCamera = () => {
    stream?.getTracks().forEach((track) => track.stop());
    stream = null; video.srcObject = null; video.classList.remove('is-ready');
  };
  const startCamera = async (runId) => {
    if (!navigator.mediaDevices?.getUserMedia) {
      cameraHint.textContent = '当前设备不支持摄像头，已进入演示模式';
      return false;
    }
    let requestedStream = null;
    try {
      requestedStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1080 }, height: { ideal: 1920 } }, audio: false,
      });
      if (runId !== countdownRun || app.dataset.state !== 'countdown') {
        requestedStream.getTracks().forEach((track) => track.stop());
        return false;
      }
      stream = requestedStream;
      video.srcObject = stream;
      await video.play();
      if (runId !== countdownRun || app.dataset.state !== 'countdown') {
        requestedStream.getTracks().forEach((track) => track.stop());
        if (stream === requestedStream) stopCamera();
        return false;
      }
      video.classList.add('is-ready');
      cameraHint.textContent = '请正对镜面，保持自然站姿';
      return true;
    } catch (error) {
      requestedStream?.getTracks().forEach((track) => track.stop());
      cameraHint.textContent = '未获得摄像头权限，已进入演示模式';
      notify('可在浏览器设置中允许摄像头；本次仍可体验完整流程');
      return false;
    }
  };
  const capture = async () => {
    const context = canvas.getContext('2d');
    const source = video.classList.contains('is-ready') && video.videoWidth ? video : document.querySelector('.camera-fallback');
    if (source === video) {
      const sourceRatio = video.videoWidth / video.videoHeight;
      const targetRatio = canvas.width / canvas.height;
      let sx = 0; let sy = 0; let sw = video.videoWidth; let sh = video.videoHeight;
      if (sourceRatio > targetRatio) { sw = video.videoHeight * targetRatio; sx = (video.videoWidth - sw) / 2; }
      else { sh = video.videoWidth / targetRatio; sy = (video.videoHeight - sh) / 2; }
      context.save(); context.translate(canvas.width, 0); context.scale(-1, 1);
      context.drawImage(video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height); context.restore();
    } else {
      const image = source;
      const iw = image.naturalWidth || 520; const ih = image.naturalHeight || 520;
      const cropWidth = Math.min(iw, ih * canvas.width / canvas.height);
      context.filter = 'brightness(1.07) saturate(.94)';
      context.drawImage(image, (iw - cropWidth) / 2, 0, cropWidth, ih, 0, 0, canvas.width, canvas.height);
      context.filter = 'none';
    }
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', .9));
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    photoUrl = URL.createObjectURL(blob);
    capturedPhoto.src = photoUrl; resultPhoto.src = photoUrl;
    stopCamera(); show('confirm'); busy = false;
  };
  const runCountdown = () => {
    if (busy) return;
    busy = true; clearTimers();
    const runId = ++countdownRun;
    show('countdown');
    countdownNumber.textContent = '3';
    void startCamera(runId);
    later(() => { if (runId === countdownRun) countdownNumber.textContent = '2'; }, 1000);
    later(() => { if (runId === countdownRun) countdownNumber.textContent = '1'; }, 2000);
    later(() => {
      if (runId !== countdownRun) return;
      capture().catch(() => { busy = false; notify('拍摄失败，请重新尝试'); show('home'); });
    }, 3000);
  };
  const processPhoto = async () => {
    if (busy) return;
    busy = true; clearTimers(); show('processing');
    const runId = ++analysisRun;
    const title = document.querySelector('#processingTitle');
    const hint = document.querySelector('#processingHint');
    const stages = [
      [0, '25%'],
      [650, '50%'],
      [1300, '75%'],
      [1950, '100%'],
    ];
    title.textContent = '正在分析中';
    stages.forEach(([delay, percent]) => later(() => { hint.textContent = percent; }, delay));
    let responseData = null;
    if (config.analysisEndpoint && photoUrl) {
      try {
        const blob = await (await fetch(photoUrl)).blob();
        const body = new FormData(); body.append('photo', blob, 'mirror-capture.jpg');
        const response = await fetch(config.analysisEndpoint, { method: 'POST', body });
        if (!response.ok) throw new Error('analysis failed');
        responseData = await response.json();
      } catch (error) { notify('在线分析暂时不可用，先为你展示示例结果'); }
    }
    if (runId !== analysisRun) return;
    later(() => {
      if (runId !== analysisRun) return;
      const qrImage = document.querySelector('#reportQrImage');
      const qrUrl = responseData?.qrImageUrl || config.qrImageUrl;
      if (qrUrl) { qrImage.src = qrUrl; qrImage.hidden = false; document.querySelector('#reportCode').textContent = '微信扫码查看'; }
      show('result'); busy = false;
      later(reset, Number(config.idleTimeoutMs) || 60000);
    }, Math.max(2600, config.minimumAnalysisMs || 0));
  };
  const reset = () => {
    countdownRun += 1;
    analysisRun += 1;
    clearTimers();
    stopCamera();
    busy = false;
    startCapture.disabled = false;
    startCapture.removeAttribute('aria-disabled');
    toast.hidden = true;
    show('home');
  };

  startCapture.addEventListener('click', runCountdown);
  document.querySelector('#retakePhoto').addEventListener('click', runCountdown);
  document.querySelector('#confirmPhoto').addEventListener('click', processPhoto);
  document.querySelector('#returnHome').addEventListener('click', reset);
  document.addEventListener('visibilitychange', () => { if (document.hidden) reset(); });
  window.addEventListener('beforeunload', stopCamera);
})();
