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
  const processingTitle = document.querySelector('#processingTitle');
  const processingHint = document.querySelector('#processingHint');
  const processingArt = document.querySelector('#processingArt');
  const processingStages = [
    { delay: 0, percent: 25, line: '看见你本来的样子', art: '25' },
    { delay: 1100, percent: 50, line: '你不需要成为谁', art: '50' },
    { delay: 2200, percent: 75, line: '只需要更准确地做自己', art: '75' },
  ];

  const fitCanvas = () => {
    const scale = Math.min(window.innerWidth / 393, window.innerHeight / 746);
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
  const renderProcessingStage = (stage, animate = true) => {
    app.dataset.processingStage = String(stage.percent);
    processingTitle.textContent = stage.line;
    processingHint.textContent = `${stage.percent}%`;
    processingArt.src = `/static/selfit/assets/mirror-loading-stage-${stage.art}@2x.png`;
    processingArt.dataset.stage = String(stage.percent);
    if (!animate) return;
    processingTitle.animate?.([
      { opacity: 0, transform: 'translateY(5px)' },
      { opacity: 1, transform: 'translateY(0)' },
    ], { duration: 360, easing: 'ease-out' });
    processingArt.animate?.([
      { opacity: 0, transform: 'translateX(-50%) translateY(5px) scale(.98)' },
      { opacity: 1, transform: 'translateX(-50%) translateY(0) scale(1)' },
    ], { duration: 440, easing: 'cubic-bezier(.22,.61,.36,1)' });
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
    countdownNumber.textContent = '6';
    void startCamera(runId);
    [5, 4, 3, 2, 1].forEach((n, i) => {
      later(() => { if (runId === countdownRun) countdownNumber.textContent = String(n); }, (i + 1) * 1000);
    });
    later(() => {
      if (runId !== countdownRun) return;
      capture().catch(() => { busy = false; notify('拍摄失败，请重新尝试'); show('home'); });
    }, 6000);
  };
  const processPhoto = async () => {
    if (busy) return;
    busy = true; clearTimers(); show('processing');
    const runId = ++analysisRun;
    const renderStage = (stage) => {
      if (runId !== analysisRun) return;
      renderProcessingStage(stage);
    };
    renderStage(processingStages[0]);
    processingStages.slice(1).forEach((stage) => later(() => renderStage(stage), stage.delay));
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
      show('result'); busy = false; delete app.dataset.processingStage;
      later(reset, Number(config.idleTimeoutMs) || 60000);
    }, Math.max(3500, config.minimumAnalysisMs || 0));
  };
  const reset = () => {
    countdownRun += 1;
    analysisRun += 1;
    clearTimers();
    stopCamera();
    busy = false;
    delete app.dataset.processingStage;
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

  const previewParams = new URLSearchParams(window.location.search);
  if (previewParams.get('preview') === 'processing') {
    const previewPercent = Number(previewParams.get('stage')) || 25;
    const previewStage = processingStages.find((stage) => stage.percent === previewPercent) || processingStages[0];
    show('processing');
    renderProcessingStage(previewStage, false);
  }
})();
