(() => {
  const app = document.querySelector('#mirrorApp');
  const screens = [...document.querySelectorAll('[data-screen]')];
  const video = document.querySelector('#cameraVideo');
  const previewCanvas = document.querySelector('#cameraPreview');
  const captureCanvas = document.querySelector('#captureCanvas');
  const originalCanvas = document.querySelector('#originalCanvas');
  const capturedPhoto = document.querySelector('#capturedPhoto');
  const resultPhoto = document.querySelector('#resultPhoto');
  const startCapture = document.querySelector('#startCapture');
  const countdownNumber = document.querySelector('#countdownNumber');
  const cameraHint = document.querySelector('#cameraHint');
  const toast = document.querySelector('#permissionToast');
  const debugPanel = document.querySelector('#colorDebugPanel');
  const basicControls = document.querySelector('#basicColorControls');
  const hslControls = document.querySelector('#hslColorControls');
  const saveColorGrade = document.querySelector('#saveColorGrade');
  const resetColorGrade = document.querySelector('#resetColorGrade');
  const compareColorGrade = document.querySelector('#compareColorGrade');
  const colorSaveStatus = document.querySelector('#colorSaveStatus');
  const colorGradeVersion = document.querySelector('#colorGradeVersion');
  const config = {
    analysisEndpoint: '/api/v1/selfit/mirror/analyze',
    colorGradeEndpoint: '/api/v1/selfit/mirror/color-grade',
    minimumAnalysisMs: 2600,
    idleTimeoutMs: 60000,
    ...(window.__SELFIT_MIRROR_CONFIG__ || {}),
  };
  const captureCountdownSeconds = 6;
  const hslColorNames = {
    red: '红色', orange: '橙色', yellow: '黄色', green: '绿色', cyan: '青色', blue: '蓝色', purple: '紫色',
  };
  const defaultParameters = {
    exposure: 0, brightness: 0, contrast: 0, highlights: 0, shadows: 0,
    saturation: 0, temperature: 0, tint: 0,
    hsl: Object.fromEntries(Object.keys(hslColorNames).map((color) => [color, { hue: 0, saturation: 0, lightness: 0 }])),
  };
  const controlDefinitions = [
    ['exposure', '曝光', -0.5, 0.5], ['brightness', '亮度', -0.2, 0.2], ['contrast', '对比度', -0.3, 0.3],
    ['shadows', '阴影', -0.3, 0.5], ['highlights', '高光', -0.5, 0.3], ['saturation', '饱和度', -0.3, 0.3],
    ['temperature', '色温', -0.2, 0.2], ['tint', '色调', -0.1, 0.1],
  ];
  const hslDefinitions = [['hue', '色相', -0.1, 0.1], ['saturation', '饱和', -0.3, 0.3], ['lightness', '明度', -0.2, 0.2]];
  const timers = new Set();
  let stream = null;
  let busy = false;
  let countdownRun = 0;
  let analysisRun = 0;
  let originalBlob = null;
  let retouchedBlob = null;
  let originalPhotoUrl = '';
  let retouchedPhotoUrl = '';
  let capturedColorGrade = null;
  let debugMode = false;
  let compareOriginal = false;
  let activeColorGrade = { configId: 'mirro_color_grade', version: 1, updatedAt: null, parameters: structuredClone(defaultParameters) };
  let workingParameters = structuredClone(defaultParameters);
  let renderFrame = 0;
  const tapState = { count: 0, firstAt: 0, lastAt: 0, lockedUntil: 0 };
  const processingTitle = document.querySelector('#processingTitle');
  const processingHint = document.querySelector('#processingHint');
  const processingArt = document.querySelector('#processingArt');
  const qrImage = document.querySelector('#reportQrImage');
  const qrTitle = document.querySelector('#reportQrTitle');
  const qrCode = document.querySelector('#reportCode');
  const retryQrCode = document.querySelector('#retryQrCode');
  const processingStages = [
    { delay: 0, percent: 25, line: '看见你本来的样子', art: '25' },
    { delay: 1100, percent: 50, line: '你不需要成为谁', art: '50' },
    { delay: 2200, percent: 75, line: '只需要更准确地做自己', art: '75' },
  ];

  const clone = (value) => JSON.parse(JSON.stringify(value));
  const mergeParameters = (value = {}) => {
    const merged = clone(defaultParameters);
    Object.keys(merged).filter((key) => key !== 'hsl').forEach((key) => {
      if (Number.isFinite(Number(value[key]))) merged[key] = Number(value[key]);
    });
    Object.keys(merged.hsl).forEach((color) => {
      Object.keys(merged.hsl[color]).forEach((key) => {
        const supplied = value.hsl?.[color]?.[key];
        if (Number.isFinite(Number(supplied))) merged.hsl[color][key] = Number(supplied);
      });
    });
    return merged;
  };
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
    document.documentElement.dataset.mirrorState = name;
    document.body.dataset.mirrorState = name;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', ['home', 'processing'].includes(name) ? '#792a28' : '#797979');
  };
  const notify = (message, duration = 2600) => {
    toast.textContent = message; toast.hidden = false;
    later(() => { toast.hidden = true; }, duration);
  };
  const renderProcessingStage = (stage, animate = true) => {
    app.dataset.processingStage = String(stage.percent);
    processingTitle.textContent = stage.line;
    processingHint.textContent = `${stage.percent}%`;
    processingArt.src = `/static/selfit/assets/mirror-loading-stage-${stage.art}@2x.png`;
    processingArt.dataset.stage = String(stage.percent);
    if (!animate) return;
    processingTitle.animate?.([{ opacity: 0, transform: 'translateY(5px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 360, easing: 'ease-out' });
    processingArt.animate?.([{ opacity: 0, transform: 'translateX(-50%) translateY(5px) scale(.98)' }, { opacity: 1, transform: 'translateX(-50%) translateY(0) scale(1)' }], { duration: 440, easing: 'cubic-bezier(.22,.61,.36,1)' });
  };

  const compileShader = (gl, type, source) => {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source); gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) || 'shader compile failed');
    return shader;
  };
  const createColorRenderer = (targetCanvas) => {
    const gl = targetCanvas.getContext('webgl', { alpha: false, antialias: false, preserveDrawingBuffer: true });
    if (!gl) return null;
    const vertexSource = `attribute vec2 a_position; attribute vec2 a_texCoord; varying vec2 v_texCoord; void main(){gl_Position=vec4(a_position,0.0,1.0);v_texCoord=a_texCoord;}`;
    const fragmentSource = `
      precision mediump float;
      varying vec2 v_texCoord;
      uniform sampler2D u_image;
      uniform vec4 u_uvRect;
      uniform float u_mirror,u_flipY,u_useGrade,u_exposure,u_brightness,u_contrast,u_highlights,u_shadows,u_saturation,u_temperature,u_tint;
      uniform vec3 u_hsl[7];
      vec3 rgbToHsl(vec3 c){
        float maxc=max(max(c.r,c.g),c.b),minc=min(min(c.r,c.g),c.b),h=0.0,s=0.0,l=(maxc+minc)*0.5,d=maxc-minc;
        if(d>0.0001){s=l>0.5?d/(2.0-maxc-minc):d/(maxc+minc);if(maxc==c.r)h=(c.g-c.b)/d+(c.g<c.b?6.0:0.0);else if(maxc==c.g)h=(c.b-c.r)/d+2.0;else h=(c.r-c.g)/d+4.0;h/=6.0;}return vec3(h,s,l);
      }
      float hueToRgb(float p,float q,float t){if(t<0.0)t+=1.0;if(t>1.0)t-=1.0;if(t<1.0/6.0)return p+(q-p)*6.0*t;if(t<0.5)return q;if(t<2.0/3.0)return p+(q-p)*(2.0/3.0-t)*6.0;return p;}
      vec3 hslToRgb(vec3 hsl){if(hsl.y<0.0001)return vec3(hsl.z);float q=hsl.z<0.5?hsl.z*(1.0+hsl.y):hsl.z+hsl.y-hsl.z*hsl.y;float p=2.0*hsl.z-q;return vec3(hueToRgb(p,q,hsl.x+1.0/3.0),hueToRgb(p,q,hsl.x),hueToRgb(p,q,hsl.x-1.0/3.0));}
      float hueCenter(int i){if(i==0)return 0.0;if(i==1)return 0.08333;if(i==2)return 0.16667;if(i==3)return 0.33333;if(i==4)return 0.5;if(i==5)return 0.66667;return 0.83333;}
      void main(){
        vec2 sourceCoord=v_texCoord;if(u_flipY>0.5)sourceCoord.y=1.0-sourceCoord.y;vec2 uv=u_uvRect.xy+sourceCoord*u_uvRect.zw;if(u_mirror>0.5)uv.x=u_uvRect.x+u_uvRect.z-(uv.x-u_uvRect.x);vec3 color=texture2D(u_image,uv).rgb;
        if(u_useGrade>0.5){
          color*=pow(2.0,u_exposure);color+=vec3(u_brightness);color=(color-0.5)*(1.0+u_contrast)+0.5;
          float lum=dot(color,vec3(0.2126,0.7152,0.0722)),sw=1.0-smoothstep(0.05,0.62,lum),hw=smoothstep(0.38,0.98,lum);
          color+=u_shadows*sw*(u_shadows>=0.0?(1.0-color):color)*0.7;color+=u_highlights*hw*(u_highlights>=0.0?(1.0-color):color)*0.7;
          lum=dot(color,vec3(0.2126,0.7152,0.0722));color=mix(vec3(lum),color,1.0+u_saturation);color+=vec3(u_temperature*0.12+u_tint*0.08,-u_tint*0.08,-u_temperature*0.12+u_tint*0.08);
          vec3 hsl=rgbToHsl(clamp(color,0.0,1.0)),adjustment=vec3(0.0);for(int i=0;i<7;i++){float d=abs(hsl.x-hueCenter(i));d=min(d,1.0-d);adjustment+=u_hsl[i]*(1.0-smoothstep(0.035,0.12,d));}
          hsl.x=fract(hsl.x+adjustment.x+1.0);hsl.y=clamp(hsl.y+adjustment.y,0.0,1.0);hsl.z=clamp(hsl.z+adjustment.z,0.0,1.0);color=hslToRgb(hsl);
        }gl_FragColor=vec4(clamp(color,0.0,1.0),1.0);
      }`;
    try {
      const program = gl.createProgram();
      gl.attachShader(program, compileShader(gl, gl.VERTEX_SHADER, vertexSource));
      gl.attachShader(program, compileShader(gl, gl.FRAGMENT_SHADER, fragmentSource));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || 'shader link failed');
      gl.useProgram(program);
      const vertices = new Float32Array([-1,-1,0,0,1,-1,1,0,-1,1,0,1,1,1,1,1]);
      const buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);
      const position = gl.getAttribLocation(program, 'a_position'), texCoord = gl.getAttribLocation(program, 'a_texCoord');
      gl.enableVertexAttribArray(position); gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 16, 0);
      gl.enableVertexAttribArray(texCoord); gl.vertexAttribPointer(texCoord, 2, gl.FLOAT, false, 16, 8);
      const texture = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);
      const names = ['uvRect','mirror','flipY','useGrade','exposure','brightness','contrast','highlights','shadows','saturation','temperature','tint'];
      const locations = Object.fromEntries(names.map((name) => [name, gl.getUniformLocation(program, `u_${name}`)])); locations.hsl=gl.getUniformLocation(program,'u_hsl[0]');
      const coverRect = (source) => {
        const width=source.videoWidth||source.naturalWidth||source.width||targetCanvas.width,height=source.videoHeight||source.naturalHeight||source.height||targetCanvas.height,sourceRatio=width/height,targetRatio=targetCanvas.width/targetCanvas.height;
        if(sourceRatio>targetRatio){const w=targetRatio/sourceRatio;return[(1-w)/2,0,w,1];}const h=sourceRatio/targetRatio;return[0,(1-h)/2,1,h];
      };
      return { render(source, parameters, useGrade = true, flipY = false) {
        if(!source)return false;gl.viewport(0,0,targetCanvas.width,targetCanvas.height);gl.bindTexture(gl.TEXTURE_2D,texture);try{gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,source);}catch{return false;}
        const grade=mergeParameters(parameters);gl.uniform4fv(locations.uvRect,coverRect(source));gl.uniform1f(locations.mirror,1);gl.uniform1f(locations.flipY,flipY?1:0);gl.uniform1f(locations.useGrade,useGrade?1:0);
        names.filter((name)=>!['uvRect','mirror','flipY','useGrade'].includes(name)).forEach((name)=>gl.uniform1f(locations[name],grade[name]));
        const hslValues=Object.keys(hslColorNames).flatMap((color)=>[grade.hsl[color].hue,grade.hsl[color].saturation,grade.hsl[color].lightness]);gl.uniform3fv(locations.hsl,new Float32Array(hslValues));gl.drawArrays(gl.TRIANGLE_STRIP,0,4);return true;
      }};
    } catch (error) { console.warn('Mirro color renderer unavailable', error); return null; }
  };
  const previewRenderer = createColorRenderer(previewCanvas);
  const captureRenderer = createColorRenderer(captureCanvas);
  const renderPreview = () => {
    const source=video.classList.contains('is-ready')&&video.videoWidth?video:null,parameters=debugMode?workingParameters:activeColorGrade.parameters;
    const rendered=previewRenderer?.render(source,parameters,!compareOriginal);previewCanvas.classList.toggle('is-ready',Boolean(rendered));renderFrame=window.requestAnimationFrame(renderPreview);
  };
  renderPreview();

  const createControl = (path,label,min,max) => {
    const row=document.createElement('div');row.className='color-control';const inputId=`grade-${path.replaceAll('.','-')}`;
    row.innerHTML=`<label for="${inputId}">${label}</label><input id="${inputId}" type="range" min="${min}" max="${max}" step="0.01" data-grade-path="${path}"><output for="${inputId}">0.00</output>`;return row;
  };
  controlDefinitions.forEach((definition)=>basicControls.append(createControl(...definition)));
  Object.entries(hslColorNames).forEach(([color,label])=>{const group=document.createElement('div');group.className='hsl-group';group.innerHTML=`<strong>${label}</strong>`;hslDefinitions.forEach(([name,itemLabel,min,max])=>group.append(createControl(`hsl.${color}.${name}`,itemLabel,min,max)));hslControls.append(group);});
  const getPathValue=(object,path)=>path.split('.').reduce((value,key)=>value[key],object);
  const setPathValue=(object,path,value)=>{const keys=path.split('.'),last=keys.pop(),target=keys.reduce((current,key)=>current[key],object);target[last]=value;};
  const formatValue=(value)=>`${value>0?'+':''}${Number(value).toFixed(2)}`;
  const syncControls=()=>document.querySelectorAll('[data-grade-path]').forEach((input)=>{const value=getPathValue(workingParameters,input.dataset.gradePath);input.value=String(value);input.nextElementSibling.textContent=formatValue(value);});
  const setDirtyState=()=>{const dirty=JSON.stringify(workingParameters)!==JSON.stringify(activeColorGrade.parameters);saveColorGrade.disabled=!dirty;colorSaveStatus.textContent=dirty?'有未保存的调整':'已是生效配置';colorSaveStatus.classList.toggle('is-dirty',dirty);colorSaveStatus.classList.remove('is-error');};
  const updateVersionLabel=()=>{colorGradeVersion.textContent=`自然光感 · v${activeColorGrade.version}`;};
  document.querySelectorAll('[data-grade-path]').forEach((input)=>input.addEventListener('input',()=>{const value=Number(input.value);setPathValue(workingParameters,input.dataset.gradePath,value);input.nextElementSibling.textContent=formatValue(value);setDirtyState();}));
  const loadColorGrade=async()=>{try{const response=await fetch(config.colorGradeEndpoint,{cache:'no-store'});if(!response.ok)throw new Error('load failed');const payload=await response.json();activeColorGrade={...payload,parameters:mergeParameters(payload.parameters)};if(!debugMode)workingParameters=clone(activeColorGrade.parameters);updateVersionLabel();syncControls();setDirtyState();}catch{activeColorGrade.parameters=mergeParameters(activeColorGrade.parameters);}};
  void loadColorGrade();

  const stopCamera=()=>{stream?.getTracks().forEach((track)=>track.stop());stream=null;video.srcObject=null;video.classList.remove('is-ready');};
  const isCameraRequestActive=()=>app.dataset.state==='camera-loading'||(debugMode&&app.dataset.state==='countdown');
  const startCamera=async(runId)=>{
    if(stream&&video.classList.contains('is-ready'))return true;if(!navigator.mediaDevices?.getUserMedia){cameraHint.textContent='当前设备不支持摄像头';notify('当前设备不支持摄像头');return false;}let requestedStream=null;
    try{requestedStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:{ideal:1080},height:{ideal:1920}},audio:false});if(runId!==countdownRun||!isCameraRequestActive()){requestedStream.getTracks().forEach((track)=>track.stop());return false;}stream=requestedStream;video.srcObject=stream;await video.play();if(runId!==countdownRun||!isCameraRequestActive()){requestedStream.getTracks().forEach((track)=>track.stop());if(stream===requestedStream)stopCamera();return false;}video.classList.add('is-ready');cameraHint.textContent='请正对镜面，保持自然站姿';return true;}
    catch{requestedStream?.getTracks().forEach((track)=>track.stop());cameraHint.textContent='未获得摄像头权限';notify('请在浏览器设置中允许摄像头后重试');return false;}
  };
  const coverCrop=(source,target)=>{const width=source.width||source.videoWidth||source.naturalWidth,height=source.height||source.videoHeight||source.naturalHeight,sourceRatio=width/height,targetRatio=target.width/target.height;let sx=0,sy=0,sw=width,sh=height;if(sourceRatio>targetRatio){sw=height*targetRatio;sx=(width-sw)/2;}else{sh=width/targetRatio;sy=(height-sh)/2;}return{sx,sy,sw,sh};};
  const drawOriginalFrame=(source,target,filter='none')=>{const context=target.getContext('2d'),crop=coverCrop(source,target);context.save();context.clearRect(0,0,target.width,target.height);context.translate(target.width,0);context.scale(-1,1);context.filter=filter;context.drawImage(source,crop.sx,crop.sy,crop.sw,crop.sh,0,0,target.width,target.height);context.restore();};
  const canvasBlob=(target)=>new Promise((resolve,reject)=>target.toBlob((blob)=>blob?resolve(blob):reject(new Error('encode failed')),'image/jpeg',0.92));
  const clearPhotoUrls=()=>{if(originalPhotoUrl)URL.revokeObjectURL(originalPhotoUrl);if(retouchedPhotoUrl)URL.revokeObjectURL(retouchedPhotoUrl);originalPhotoUrl='';retouchedPhotoUrl='';};
  const capture=async()=>{
    const liveSource=video.classList.contains('is-ready')&&video.videoWidth?video:null;if(!liveSource)throw new Error('camera not ready');const snapshot=await createImageBitmap(liveSource);drawOriginalFrame(snapshot,originalCanvas);const rendered=captureRenderer?.render(snapshot,activeColorGrade.parameters,true,true);
    if(!rendered){const grade=activeColorGrade.parameters,brightness=Math.max(0.5,1+grade.brightness+grade.exposure*0.35);drawOriginalFrame(snapshot,captureCanvas,`brightness(${brightness}) contrast(${1+grade.contrast}) saturate(${1+grade.saturation})`);}snapshot.close?.();
    [originalBlob,retouchedBlob]=await Promise.all([canvasBlob(originalCanvas),canvasBlob(captureCanvas)]);clearPhotoUrls();originalPhotoUrl=URL.createObjectURL(originalBlob);retouchedPhotoUrl=URL.createObjectURL(retouchedBlob);capturedColorGrade={configId:activeColorGrade.configId,version:activeColorGrade.version,parameters:clone(activeColorGrade.parameters)};capturedPhoto.src=retouchedPhotoUrl;resultPhoto.src=retouchedPhotoUrl;stopCamera();show('confirm');busy=false;
  };
  const runCountdown=async()=>{if(busy||debugMode)return;busy=true;clearTimers();const runId=++countdownRun;show('camera-loading');const ready=await startCamera(runId);if(!ready){if(runId===countdownRun){busy=false;later(()=>show('home'),900);}return;}countdownNumber.textContent=String(captureCountdownSeconds);show('countdown');for(let elapsed=1;elapsed<captureCountdownSeconds;elapsed+=1){later(()=>{if(runId===countdownRun)countdownNumber.textContent=String(captureCountdownSeconds-elapsed);},elapsed*1000);}later(()=>{if(runId!==countdownRun||debugMode)return;capture().catch(()=>{busy=false;notify('拍摄失败，请重新尝试');show('home');});},captureCountdownSeconds*1000);};
  const parameterHash=async(parameters)=>{if(!crypto.subtle)return null;const bytes=new TextEncoder().encode(JSON.stringify(parameters)),digest=await crypto.subtle.digest('SHA-256',bytes);return[...new Uint8Array(digest)].map((byte)=>byte.toString(16).padStart(2,'0')).join('');};
  const processPhoto=async()=>{
    if(busy)return;busy=true;clearTimers();show('processing');const runId=++analysisRun,renderStage=(stage)=>{if(runId===analysisRun)renderProcessingStage(stage);};renderStage(processingStages[0]);processingStages.slice(1).forEach((stage)=>later(()=>renderStage(stage),stage.delay));let responseData=null;
    if(config.analysisEndpoint&&originalBlob&&retouchedBlob){try{const hash=await parameterHash(capturedColorGrade?.parameters||{}),metadata={colorGrade:{configId:capturedColorGrade?.configId||'mirro_color_grade',version:capturedColorGrade?.version||1,parameterHash:hash}},body=new FormData();body.append('original',originalBlob,'mirror-capture-original.jpg');body.append('retouched',retouchedBlob,'mirror-capture-retouched.jpg');body.append('metadata',JSON.stringify(metadata));const response=await fetch(config.analysisEndpoint,{method:'POST',body});if(!response.ok)throw new Error('analysis failed');responseData=await response.json();}catch{notify('二维码生成失败，可以重新尝试');}}
    if(runId!==analysisRun)return;later(()=>{if(runId!==analysisRun)return;show('result');const qrUrl=responseData?.qrImageUrl||config.qrImageUrl;retryQrCode.hidden=Boolean(qrUrl);qrImage.hidden=!qrUrl;if(qrUrl){qrImage.src=qrUrl;qrTitle.textContent='手机扫码继续';const expiresAt=Date.parse(responseData?.expiresAt||'');const updateExpiry=()=>{if(app.dataset.state!=='result')return;const remaining=Math.max(0,Math.ceil((expiresAt-Date.now())/1000)),minutes=String(Math.floor(remaining/60)).padStart(2,'0'),seconds=String(remaining%60).padStart(2,'0');qrCode.textContent=remaining>0?`${minutes}:${seconds} 内有效`:'二维码已过期';if(remaining>0)later(updateExpiry,1000);else{qrImage.hidden=true;retryQrCode.hidden=false;}};updateExpiry();const pollStatus=async()=>{if(app.dataset.state!=='result'||!responseData?.statusUrl)return;try{const response=await fetch(responseData.statusUrl,{cache:'no-store'}),payload=await response.json();if(payload.handoff?.status==='claimed'){qrTitle.textContent='已保存到手机';qrCode.textContent='手机上将继续 like 与 vibe';qrImage.classList.add('is-claimed');later(reset,2600);return;}}catch{}later(pollStatus,1500);};later(pollStatus,1500);}else{qrTitle.textContent='生成失败';qrCode.textContent='检查网络后重新生成';}busy=false;delete app.dataset.processingStage;later(reset,Number(config.idleTimeoutMs)||60000);},Math.max(3500,config.minimumAnalysisMs||0));
  };

  const enterDebugMode=async()=>{if(!['home','countdown'].includes(app.dataset.state))return;countdownRun+=1;analysisRun+=1;clearTimers();busy=false;debugMode=true;compareOriginal=false;app.dataset.debug='true';debugPanel.hidden=false;compareColorGrade.setAttribute('aria-pressed','false');compareColorGrade.textContent='查看原生';workingParameters=clone(activeColorGrade.parameters);syncControls();setDirtyState();updateVersionLabel();show('countdown');const runId=++countdownRun;await startCamera(runId);if(!previewRenderer){colorSaveStatus.textContent='当前浏览器不支持实时调色';colorSaveStatus.classList.add('is-error');}};
  const exitDebugMode=()=>{countdownRun+=1;clearTimers();debugMode=false;compareOriginal=false;busy=false;workingParameters=clone(activeColorGrade.parameters);app.removeAttribute('data-debug');debugPanel.hidden=true;stopCamera();show('home');};
  const toggleDebugMode=()=>debugMode?exitDebugMode():void enterDebugMode();
  const handleDebugTap=()=>{const now=Date.now();if(now<tapState.lockedUntil)return;const expired=!tapState.count||now-tapState.firstAt>2000||now-tapState.lastAt>600;if(expired){tapState.count=1;tapState.firstAt=now;}else tapState.count+=1;tapState.lastAt=now;if(tapState.count===5){tapState.count=0;tapState.lockedUntil=now+1000;toggleDebugMode();}};
  document.querySelectorAll('[data-debug-trigger]').forEach((trigger)=>{trigger.addEventListener('click',handleDebugTap);trigger.setAttribute('role','button');});
  compareColorGrade.addEventListener('click',()=>{compareOriginal=!compareOriginal;compareColorGrade.setAttribute('aria-pressed',String(compareOriginal));compareColorGrade.textContent=compareOriginal?'恢复调色':'查看原生';});
  resetColorGrade.addEventListener('click',()=>{workingParameters=clone(activeColorGrade.parameters);syncControls();setDirtyState();});
  saveColorGrade.addEventListener('click',async()=>{if(saveColorGrade.disabled)return;saveColorGrade.disabled=true;saveColorGrade.textContent='保存中…';colorSaveStatus.textContent='正在更新生效配置';try{const response=await fetch(config.colorGradeEndpoint,{method:'PUT',headers:{'Content-Type':'application/json','If-Match':String(activeColorGrade.version)},body:JSON.stringify({parameters:workingParameters})}),payload=await response.json();if(!response.ok)throw new Error(payload.error?.message||'保存失败');activeColorGrade={...payload,parameters:mergeParameters(payload.parameters)};workingParameters=clone(activeColorGrade.parameters);updateVersionLabel();syncControls();setDirtyState();colorSaveStatus.textContent='已保存，当前效果已生效';}catch(error){colorSaveStatus.textContent=error.message||'保存失败，请重试';colorSaveStatus.classList.add('is-error');saveColorGrade.disabled=false;}finally{saveColorGrade.textContent='保存并生效';}});
  const reset=()=>{countdownRun+=1;analysisRun+=1;clearTimers();stopCamera();busy=false;delete app.dataset.processingStage;startCapture.disabled=false;startCapture.removeAttribute('aria-disabled');toast.hidden=true;qrImage.hidden=true;qrImage.removeAttribute('src');qrImage.classList.remove('is-claimed');retryQrCode.hidden=true;originalBlob=null;retouchedBlob=null;capturedColorGrade=null;clearPhotoUrls();show('home');void loadColorGrade();};
  startCapture.addEventListener('click',runCountdown);document.querySelector('#retakePhoto').addEventListener('click',runCountdown);document.querySelector('#confirmPhoto').addEventListener('click',processPhoto);retryQrCode.addEventListener('click',processPhoto);document.querySelector('#returnHome').addEventListener('click',reset);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)debugMode?exitDebugMode():reset();});window.addEventListener('beforeunload',()=>{stopCamera();window.cancelAnimationFrame(renderFrame);});
  const previewParams=new URLSearchParams(window.location.search);if(previewParams.get('preview')==='processing'){const previewPercent=Number(previewParams.get('stage'))||25,previewStage=processingStages.find((stage)=>stage.percent===previewPercent)||processingStages[0];show('processing');renderProcessingStage(previewStage,false);}if(previewParams.get('preview')==='debug')void enterDebugMode();
})();
