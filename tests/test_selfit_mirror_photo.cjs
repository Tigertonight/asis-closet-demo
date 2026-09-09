const assert = require('node:assert/strict');
const {detectSolidFrame, createPresenter} = require('../app/static/selfit-tryon/mirror-photo.js');

function pixels({left=14, right=14, top=3, bottom=3, alpha=255}={}) {
  const width=100, height=150, data=new Uint8ClampedArray(width*height*4);
  for(let y=0;y<height;y++) for(let x=0;x<width;x++) {
    const border=x<left || x>=width-right || y<top || y>=height-bottom;
    data.set(border ? [240,235,230,alpha] : [90+x%20,70+y%30,60,255], (y*width+x)*4);
  }
  return {width,height,data};
}

const framed=pixels(), original=framed.data.slice();
assert.deepEqual(detectSolidFrame(framed), {x:.14,y:.02,width:.72,height:.96,background:'rgb(100,85,60)'});
assert.deepEqual(framed.data,original,'Detection cannot mutate original pixels');
for(const input of [pixels({left:0}), pixels({top:0}), pixels({right:5}),
  pixels({left:30,right:30}), pixels({top:25,bottom:25}), pixels({alpha:0}),
  pixels({left:0,right:0,top:0,bottom:0}), pixels({left:100})]) {
  assert.equal(detectSolidFrame(input),null,'Uncertain borders must retain the original');
}
const gradient=pixels();
gradient.data[40*4] -= 10;
assert.equal(detectSolidFrame(gradient),null,'Nonuniform outer edges cannot be cropped');
const edgeSubject=pixels();
edgeSubject.data[(70*100)*4]=25;
assert.equal(detectSolidFrame(edgeSubject),null,'An edge-touching subject cannot be cropped');

function generatedFrame({left=14,right=14,top=0,bottom=0,gradient=false}={}) {
  const width=100,height=150,data=new Uint8ClampedArray(width*height*4);
  for(let y=0;y<height;y++) for(let x=0;x<width;x++) {
    const border=x<left || x>=width-right || y<top || y>=height-bottom;
    const noise=(x*3+y*7)%5-2;
    const distance=Math.max(0,Math.min(x-left,width-right-1-x));
    const rgb=gradient ? [248-distance*.5,246-distance*.5,242-distance*.5]
      : border ? [248+noise,246+noise,242+noise] : [232+x%3,220+y%3,215];
    data.set([...rgb,255],(y*width+x)*4);
  }
  return {width,height,data};
}
const sideFrame=generatedFrame(), sideOriginal=sideFrame.data.slice();
const sideCrop=detectSolidFrame(sideFrame);
assert.equal(sideCrop.x,.15);
assert.equal(sideCrop.width,.7);
assert.equal(sideCrop.y,0);
assert.equal(sideCrop.height,1,'Side-border removal retains the complete head-to-foot extent');
assert.deepEqual(sideFrame.data,sideOriginal,'Generated originals remain unchanged');
const horizontalCrop=detectSolidFrame(generatedFrame({left:0,right:0,top:6,bottom:6}));
assert.equal(horizontalCrop.x,0);
assert.equal(horizontalCrop.width,1);
assert.equal(horizontalCrop.y,7/150);
assert.equal(horizontalCrop.height,136/150);
assert(detectSolidFrame(generatedFrame({top:6,bottom:6})),'Noisy four-sided frames are also recognized');
for (const input of [generatedFrame({left:0}), generatedFrame({right:5}),
  generatedFrame({top:6}), generatedFrame({gradient:true})])
  assert.equal(detectSolidFrame(input),null,'Unpaired borders and gradual studio lighting must be preserved');
const noisyEdgeSubject=generatedFrame();
noisyEdgeSubject.data[(70*100)*4]=30;
assert.equal(detectSolidFrame(noisyEdgeSubject),null,'Even a small subject at the edge blocks trimming');

function harness({tainted=false, width=100, height=150, framed=true, sourcePixels, area='.mirror-photo-frame'}={}) {
  const images=[], revoked=[], timers=new Map(); let nextTimer=0, blobs=0;
  class Image {
    constructor() { this.naturalWidth=width;this.naturalHeight=height;images.push(this); }
  }
  const presenter=createPresenter({Image,
    setTimeout:fn=>{timers.set(++nextTimer,fn);return nextTimer;},
    clearTimeout:id=>timers.delete(id),
    document:{createElement:()=>({
      getContext:()=>({drawImage(){},getImageData(){if(tainted)throw Error('SecurityError');return sourcePixels || (framed ? pixels() : pixels({left:0,right:0,top:0,bottom:0}));}}),
      toBlob:done=>done({}),
    })},
    URL:{createObjectURL:()=>`blob:preview-${++blobs}`,revokeObjectURL:url=>revoked.push(url)},
  });
  const frame={style:{},dataset:{}}, photo={isConnected:true,style:{},dataset:{},closest:selector=>selector.split(', ').includes(area) ? frame : null};
  return {presenter,images,revoked,timers,frame,photo};
}

(async()=>{
  const h=harness();
  h.presenter.show(h.photo,'/original-a.png');
  h.presenter.show(h.photo,'/original-b.png');
  h.images[1].onload(); await Promise.resolve();
  assert.equal(h.photo.src,'blob:preview-1');
  assert.equal(h.frame.dataset.trimmed,'true');
  assert.equal(h.frame.dataset.fit,'height');
  assert.equal(h.frame.style.backgroundColor,undefined,'The sizing container cannot expose a solid letterbox');
  assert.equal(h.photo.style.backgroundColor,'rgb(100,85,60)');
  h.images[0].onload(); await Promise.resolve();
  assert.equal(h.photo.src,'blob:preview-1','Late previews cannot overwrite the chosen photo');
  assert.equal(h.photo.dataset.mirrorSource,'/original-b.png');
  h.presenter.show(h.photo,'/original-a.png'); await Promise.resolve();
  assert.equal(h.photo.src,'blob:preview-2','Comparison reuses the same framing per source');
  assert.equal(h.images.length,2,'Decoded previews are cached');
  h.presenter.clear(); await Promise.resolve();
  assert.deepEqual(h.revoked.sort(),['blob:preview-1','blob:preview-2']);
  assert.equal(h.timers.size,0);

  const viewer=harness({area:'.result-viewer-photo-area'});
  viewer.presenter.show(viewer.photo,'/original-model.png',{fit:'contain'});
  viewer.images[0].onload(); await Promise.resolve();
  assert.equal(viewer.frame.dataset.trimmed,'true','The expanded model removes the same source border as the mirror');
  assert.equal(viewer.frame.dataset.fit,'contain','The viewer retains the entire trimmed photo, including both sides');
  assert.equal(viewer.photo.src,'blob:preview-1');
  assert.equal(viewer.photo.dataset.mirrorSource,'/original-model.png','Original model inputs remain unchanged');
  const mirrorFrame={style:{},dataset:{}}, mirrorPhoto={isConnected:true,style:{},dataset:{},closest:()=>mirrorFrame};
  viewer.presenter.show(mirrorPhoto,'/original-model.png'); await Promise.resolve();
  assert.equal(mirrorPhoto.src,viewer.photo.src,'Mirror and viewer reuse the same cached border trim');
  assert.equal(mirrorFrame.dataset.fit,'height','Viewer fitting does not alter the cached mirror fitting');
  assert.equal(viewer.images.length,1);
  viewer.presenter.clear(); await Promise.resolve();

  const result=harness({framed:false});
  result.presenter.show(result.photo,'/tryon-result.png');
  result.images[0].onload(); await Promise.resolve();
  assert.equal(result.frame.dataset.trimmed,'false');
  assert.equal(result.frame.dataset.fit,'height','An unframed portrait uses the same vertical fit as the trimmed model');
  assert.equal(result.photo.src,'/tryon-result.png','Display fitting must not rewrite the result file');

  const borderedResult=harness({sourcePixels:generatedFrame()});
  borderedResult.presenter.show(borderedResult.photo,'/tryon-result-with-side-borders.png');
  borderedResult.images[0].onload(); await Promise.resolve();
  assert.equal(borderedResult.frame.dataset.trimmed,'true');
  assert.equal(borderedResult.frame.dataset.fit,'height');
  assert.equal(borderedResult.photo.src,'blob:preview-1');
  assert.equal(borderedResult.photo.dataset.mirrorSource,'/tryon-result-with-side-borders.png');

  for (const [width,height] of [[150,100],[100,100],[0,0]]) {
    const wide=harness({width,height,framed:false});
    wide.presenter.show(wide.photo,'/wide-photo.png');
    wide.images[0].onload(); await Promise.resolve();
    assert.equal(wide.frame.dataset.fit,'contain','Wide or unknown images retain complete-image fitting');
  }

  const cors=harness({tainted:true});
  cors.presenter.show(cors.photo,'https://external.example/photo.jpg');
  cors.images[0].onload(); await Promise.resolve();
  assert.equal(cors.photo.src,'https://external.example/photo.jpg');
  assert.equal(cors.frame.dataset.trimmed,'false');

  const slow=harness();
  slow.presenter.show(slow.photo,'/slow.jpg');
  slow.timers.values().next().value(); await Promise.resolve();
  assert.equal(slow.photo.src,'/slow.jpg','Timeout retains the original');
  assert.equal(slow.frame.dataset.fit,'contain','Unknown dimensions cannot enable width clipping');
  assert.equal(slow.images[0].onload,null);

  const bounded=harness();
  for(let i=0;i<15;i++) {
    bounded.presenter.show(bounded.photo,`/model-${i}.jpg`);
    bounded.images[i].onload(); await Promise.resolve();
  }
  assert.equal(bounded.revoked.length,3,'Only twelve previews remain cached');
  bounded.presenter.clear(); await Promise.resolve();
  assert.equal(new Set(bounded.revoked).size,15,'All previews are released on cleanup');
  console.log('Mirror photo framing, original fallback, comparison races and cache cleanup: passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
