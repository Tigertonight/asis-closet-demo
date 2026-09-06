"""Compare CUA screenshots against five original Figma UI exports.
Excludes only native status-bar band (y<54) and transparent device corners.
Does not treat low global pixel error as proof of interactive correctness.
"""
from pathlib import Path
import json
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance
ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'docs/audits/20260905-tryon-figma'
NAMES = ['mirror-model', 'mirror-styling', 'closet', 'inspiration', 'detail']
metrics = {}
for name in NAMES:
    source=Image.open(AUDIT/'source'/f'{name}.png').convert('RGBA')
    actual=Image.open(AUDIT/f'{name}-actual.png').convert('RGB')
    if actual.size != source.size:
        raise ValueError(f'{name}: screenshot must be 393x852, got {actual.size}')
    a=np.asarray(source)[:,:,:3].astype(float); b=np.asarray(actual).astype(float)
    mask=np.asarray(source)[:,:,3]>250; mask[:54]=False
    diff=np.abs(a-b); error=diff.mean(axis=2)
    metrics[name]={'mean_absolute_error_0_255':round(float(diff[mask].mean()),3),'pixels_with_max_channel_error_at_most_16_percent':round(float((diff.max(axis=2)[mask]<=16).mean()*100),2),'evaluated_pixels':int(mask.sum()),'excluded':'status bar y<54 and transparent Figma device corners','regions':{}}
    for region,box in {'hero':(0,54,393,510),'controls':(0,510,393,743),'navigation':(0,743,393,852)}.items():
        x,y,w,h=box; mm=mask[y:h,x:w]; d=diff[y:h,x:w];metrics[name]['regions'][region]=round(float(d[mm].mean()),3)
    heat=np.zeros_like(a,dtype=np.uint8);heat[:,:,0]=np.clip(error*6,0,255);heat[:,:,1]=np.clip(error*1.2,0,90);heat[~mask]=[240,240,240]
    comparison=Image.new('RGB',(393*3,886),'white');comparison.paste(source.convert('RGB'),(0,34));comparison.paste(actual,(393,34));comparison.paste(Image.fromarray(heat),(786,34));draw=ImageDraw.Draw(comparison)
    for i,title in enumerate(['FIGMA SOURCE','IMPLEMENTATION','ABSOLUTE DIFFERENCE x6']):draw.text((i*393+12,10),title,fill='black')
    comparison.save(AUDIT/f'{name}-comparison.png')
(AUDIT/'pixel-metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
print(json.dumps(metrics,indent=2))
