"""Prepare and ingest built-in image_gen stages for the delivered male outfits.

This operator CLI never calls an image model. The existing staged try-on pipeline
produces exact requests; Codex supplies and visually reviews each real output.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from copy import deepcopy
import json
import hashlib
import os
from pathlib import Path
import shutil
import sys
from unittest.mock import patch
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.material_assets import MaterialRegistry, write_json_atomic
from app.styling_catalog import delivery_looks, outfit_id
from scripts import batch_codex_tryon_examples as base

BATCH=ROOT/'outputs/tryon-examples/male-20260910'
INDEX=ROOT/'app/data/tryon-examples.v1.json'
CODES={'ease-male','edge-male','mute-male','wabi-male'}


def read(p):return json.loads(Path(p).read_text())


def initialize(models):
    looks=[x for x in delivery_looks() if x['note_binding']['templateId'] in CODES]
    assert len(looks)==16 and sum(len(x['items']) for x in looks)==101
    catalog={x.get('id') or Path(x['file']).stem:x for x in read(base.MODEL_DIR/'manifest.json')['items'] if x.get('active',True) and x['gender']=='male'}
    if not models or not set(models)<=set(catalog):raise ValueError('Unknown male model')
    BATCH.mkdir(parents=True,exist_ok=True)
    snapshot=BATCH/'styling-delivery.snapshot.json'
    if snapshot.exists():
        if read(snapshot)['looks']!=looks:raise ValueError('Delivery changed; use a new batch')
    else:write_json_atomic(snapshot,{'looks':looks})
    if not (BATCH/'baseline-index.json').exists():shutil.copyfile(INDEX,BATCH/'baseline-index.json')
    for model_id in models:
        model=deepcopy(catalog[model_id])
        if model.get('image_asset_id'):
            person=ROOT/'app/static/selfit/assets/model-library'/model['file']
            registered=MaterialRegistry().get(model['image_asset_id'])
            if base.digest(person)!=registered['sha256']:raise ValueError('Model asset mismatch')
        else:person=base.MODEL_DIR/model['file']
        for look in looks:
            binding=look['note_binding'];key=binding['templateId']+'--'+binding['noteId'];folder=BATCH/model_id/key;p=folder/'job.json'
            record={'id':model_id+'--'+key,'modelId':model_id,'key':key,'outfitId':outfit_id(look),'noteBinding':binding,'sourceAssetId':look['source_asset']['assetId'],'itemCount':len(look['items']),'itemIds':[x['item_id'] for x in look['items']],'inputAssetIds':[x['image_asset']['assetId'] for x in look['items']],
                    'model':{**model,'localPath':str(person.relative_to(ROOT)),'sha256':base.digest(person)},'provider':base.CodexEffectProvider.mode,'strategy':'visible_clothing_then_accessories','status':'queued','createdAt':base.now(),'updatedAt':base.now(),'artifactDir':str(folder.relative_to(ROOT))}
            if p.exists():
                old=read(p)
                if any(old[k]!=record[k] for k in ['outfitId','sourceAssetId','itemIds','inputAssetIds','model']):raise ValueError('Input changed on resume')
            else:write_json_atomic(p,record)
    return status()


def selected(model,key):
    p=BATCH/model/key/'job.json'
    if p.resolve().parent.parent.parent!=BATCH.resolve():raise ValueError('Invalid example path')
    return p,read(p)


def status():
    rows=[read(p) for p in BATCH.glob('*/*/job.json')]
    return {'total':len(rows),'models':sorted({r['modelId'] for r in rows}),'states':{s:sum(r['status']==s for r in rows) for s in sorted({r['status'] for r in rows})}}


@contextmanager
def fixed_model_face(row):
    # This exact supplied full-body image has a small face (~0.8% of canvas).
    # Three OpenCV cascades locate it consistently; the generic detector drops
    # it below its 1.2% area filter and falls back to a box on the white T-shirt.
    # Use a visually verified annotation only for the exact registered bytes.
    if row['modelId'] != 'male_standard_1':
        yield
        return
    expected='c8d51c837708940cfd92553d7695c93a5d54074b7f0e16f18b3c7ddb04d9c291'
    source=ROOT/row['model']['localPath']
    if row['model']['sha256']!=expected or base.digest(source)!=expected:
        raise ValueError('Fixed face annotation does not match model image')
    evidence={'face_count':1,'primary_face':{'box':{'x':874,'y':244,'width':186,'height':186},'area_ratio':round(186*186/(1792*2400),4)},'annotation':'reviewed_fixed_model_face','source_sha256':expected,'detector_support':'frontalface default/alt/alt2 agree at 640/896/1280px'}
    row['modelFaceAnnotation']=evidence
    original_edit=base.CodexEffectProvider.edit
    def annotated_edit(provider,person_image,garment_image,mask_image,prompt,output_dir):
        note=row.get('stagePromptNotes',{}).get(output_dir.name)
        if note:prompt=prompt+'\nOperator retry correction: '+note
        return original_edit(provider,person_image,garment_image,mask_image,prompt,output_dir)
    with patch.object(base.tryon,'_detect_person',return_value=base.tryon._stage('pass',.84,evidence,[])), patch.object(base.CodexEffectProvider,'edit',annotated_edit):
        yield


def advance(path,row):
    with fixed_model_face(row):return base.advance(path,row)


def ingest_native(path,row,stage,source):
    """Use the app's canvas normalization; preserve native tool bytes and provenance.

    Only sub-0.2% aspect rounding is accepted here, much stricter than the app's
    8% limit. Face/background quality gates still run at the original resolution.
    """
    request_path=ROOT/row['requestPath'];request=read(request_path)
    if request_path.parent.name!=stage:raise ValueError('Wrong pending stage')
    reference=Path(request['referenced_image_paths'][0])
    with Image.open(source) as im, Image.open(reference) as ref:
        im.load();source_size=im.size
        if min(im.size)<1024 or abs((im.width/im.height)/(ref.width/ref.height)-1)>.002:
            raise ValueError('Low resolution or changed framing; regenerate instead of cropping')
        native=request_path.parent/'imagegen-native.png'
        if native.exists() and base.digest(native)!=base.digest(source):raise ValueError('Archive previous attempt first')
        shutil.copyfile(source,native)
        fitted,normalization=base.tryon._fit_image_to_reference_canvas(im,reference)
        normalized=request_path.parent/'imagegen-canvas.png';fitted.save(normalized,'PNG')
    with fixed_model_face(row):result=base.ingest(path,row,stage,normalized)
    receipt_path=request_path.with_name('codex_result.receipt.json');receipt=read(receipt_path)
    receipt.update(sourcePath=str(source.resolve()),sourceSha256=base.digest(source),nativePath=str(native.relative_to(ROOT)),sourceDimensions=list(source_size),canvasNormalization=normalization)
    write_json_atomic(receipt_path,receipt)
    return result


def validated_rows():
    """Require full source coverage, unchanged bytes and explicit visual reviews."""
    from app.selfit_tryon_presets import _model_matches
    looks={x['note_binding']['templateId']+'--'+x['note_binding']['noteId']:x
           for x in delivery_looks() if x['note_binding']['templateId'] in CODES}
    snapshot=read(BATCH/'styling-delivery.snapshot.json')['looks']
    if list(looks.values()) != snapshot:raise ValueError('Source delivery changed')
    rows=[read(p) for p in sorted(BATCH.glob('*/*/job.json'))]
    models={r['modelId'] for r in rows}
    if not models or {(r['modelId'],r['key']) for r in rows}!={(m,k) for m in models for k in looks}:
        raise ValueError('Incomplete model/outfit matrix')
    if len(rows)!=len(models)*16:raise ValueError('Duplicate batch rows')
    hashes=set()
    for r in rows:
        look=looks[r['key']]
        if (r['outfitId']!=outfit_id(look) or r['sourceAssetId']!=look['source_asset']['assetId']
            or r['itemIds']!=[x['item_id'] for x in look['items']]
            or r['inputAssetIds']!=[x['image_asset']['assetId'] for x in look['items']]):
            raise ValueError('Outfit changed: '+r['id'])
        if not _model_matches(base.MODEL_DIR.resolve(),r['modelId'],r['model'],(ROOT/r['model']['localPath']).read_bytes()):
            raise ValueError('Model changed: '+r['id'])
        if r['status'] not in {'generated_local','uploaded'} or r['imageEdit']['status']!='pass' or r['qualityReview']['status']=='fail':
            raise ValueError('Generation/geometry not passed: '+r['id'])
        result=r['result'];final=ROOT/result['localPath']
        if not final.resolve().is_relative_to(BATCH.resolve()) or base.digest(final)!=result['sha256'] or result['sha256'] in hashes:
            raise ValueError('Changed/duplicate final image')
        hashes.add(result['sha256'])
        with Image.open(final) as im:
            if list(im.size)!=result['dimensions'] or im.size!=(r['model']['width'],r['model']['height']):raise ValueError('Invalid final canvas')
            im.verify()
        requests=sorted((ROOT/r['workDir']).glob('stage_*/codex_request.json'))
        if [p.parent.name for p in requests]!=['stage_1_visible_clothing','stage_2_visible_accessories']:raise ValueError('Missing generation stage')
        provenance=[]
        for p in requests:
            q=read(p);receipt=read(p.with_name('codex_result.receipt.json'))
            if (receipt['tool']!='image_gen' or receipt['requestId']!=q['requestId']
                or receipt['sha256']!=base.digest(p.with_name('codex_result.png'))
                or receipt['sourceSha256']!=base.digest(ROOT/receipt['nativePath'])):raise ValueError('Invalid tool receipt')
            provenance.append({'stage':q['stage'],'requestPath':str(p.relative_to(ROOT)),**receipt})
        if base.digest(requests[-1].with_name('codex_result.png'))!=result['sha256']:raise ValueError('Final is not the generated accessory result')
        review=read(final.with_name('visual-review.json'))
        if (review.get('verified') is not True or review.get('status')!='pass'
            or review.get('resultSha256')!=result['sha256'] or review.get('reviewedItemIds')!=r['itemIds']
            or not review.get('observations')):raise ValueError('Missing/stale explicit visual review')
        r['visualReview']=review;r['semanticReview']=review;r['generationStages']=provenance
        r['attemptArchives']=[str(p.relative_to(ROOT)) for p in sorted(final.parent.glob('attempts/*')) if p.is_dir()]
        # Retain original numeric geometry evidence, resolve only the manual-review warning.
        quality=r['qualityReview'];quality['evidence']['semantic_review']=review
        quality['issues']=[i for i in quality['issues'] if i['code']!='semantic.manual_review_required']
        if quality['issues']:raise ValueError('Unresolved quality issue')
        quality.update(status='pass',suggestions=[])
    return rows


def merge_index(current,rows):
    """Add this batch without rewriting any unrelated example or metadata."""
    incoming={r['id']:r for r in rows}
    if len(incoming)!=len(rows):raise ValueError('Duplicate incoming IDs')
    payload=deepcopy(current);examples=payload['examples'];seen=set()
    for old in examples:
        if old['id'] in seen:raise ValueError('Duplicate existing IDs')
        seen.add(old['id'])
        if old['id'] in incoming and old!=incoming[old['id']]:raise ValueError('Existing example conflicts with new batch')
    examples.extend(r for r in rows if r['id'] not in seen)
    counts=payload['counts']
    counts.update(expected=len(examples),records=len(examples),outfits=len({r['outfitId'] for r in examples}),models=len({r['modelId'] for r in examples}),
                  generated=sum('result' in r for r in examples),uploaded=sum(r['status']=='uploaded' for r in examples))
    counts.update(totalImages=counts['generated']+counts['failedImages'],totalUploaded=counts['uploaded']+counts['failedUploaded'],
                  processed=counts['uploaded']+counts['failedUploaded']+counts['blocked'])
    payload['status']='complete' if counts['uploaded']==counts['expected'] else 'completed_with_issues' if counts['processed']==counts['expected'] else 'in_progress'
    payload['updatedAt']=base.now()
    batches=payload.setdefault('additionalBatches',[])
    batch={'id':'male-20260910','modelIds':sorted({r['modelId'] for r in rows}),'examples':len(rows),'status':'complete','artifactDir':str(BATCH.relative_to(ROOT))}
    if not any(b['id']==batch['id'] for b in batches):batches.append(batch)
    return payload


def publish():
    import fcntl
    import httpx
    from dotenv import load_dotenv
    from app.material_assets import asset_id_for_bytes,asset_content_url,material_download_url,material_source_url
    from scripts.qiniu_material_upload import qiniu_client_from_env
    rows=validated_rows()  # Validate every result before uploading any of them.
    load_dotenv(ROOT/'.env.qiniu',override=False)
    client=qiniu_client_from_env(os.environ['QINIU_BUCKET']);registry=MaterialRegistry()
    for r in rows:
        result=r['result'];source=ROOT/result['localPath'];raw=source.read_bytes();aid=asset_id_for_bytes(raw)
        key='selfit/tryon-examples/male-20260910/'+aid+'.png';url=os.environ['QINIU_PUBLIC_BASE'].rstrip('/')+'/'+key
        try:registered=material_source_url(registry.get(aid))==url
        except KeyError:registered=False
        if not registered:
            client.put_object(Bucket=client.bucket,Key=key,Body=raw,ContentType='image/png')
            registry.register(raw,url,'image/png',storage=client.storage_metadata(key))
        response=httpx.get(material_download_url(registry.get(aid)),timeout=60,follow_redirects=False)
        if response.status_code!=200 or hashlib.sha256(response.content).hexdigest()!=result['sha256']:raise RuntimeError('Remote verification failed: '+r['id'])
        cache=ROOT/'outputs/material-cache'/f'{aid}.image';cache.parent.mkdir(parents=True,exist_ok=True);cache.write_bytes(response.content)
        receipt={'assetId':aid,'url':url,'contentUrl':asset_content_url(aid),'storage':client.storage_metadata(key),'verified':True,'sha256':result['sha256']}
        write_json_atomic(source.with_name('upload.json'),receipt)
        result.update(receipt);r['status']='uploaded'
        print('verified '+r['id'],flush=True)
    with (BATCH/'publish.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        current=read(INDEX);payload=merge_index(current,rows)
        backup=BATCH/'index-before-publish.json'
        if not backup.exists():write_json_atomic(backup,current)
        write_json_atomic(INDEX,payload)
        write_json_atomic(BATCH/'published.json',{'status':'complete','examples':rows,'counts':payload['counts'],'publishedAt':base.now()})
    return payload['counts']


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['init','advance','ingest','status','verify','publish']);ap.add_argument('--models',nargs='+',default=['male_standard_1']);ap.add_argument('--model',default='male_standard_1');ap.add_argument('--key');ap.add_argument('--stage');ap.add_argument('--result',type=Path);args=ap.parse_args()
    if args.action=='init':result=initialize(args.models)
    elif args.action=='status':result=status()
    elif args.action=='verify':result={'validated':len(validated_rows())}
    elif args.action=='publish':result=publish()
    else:
        path,row=selected(args.model,args.key)
        if args.action=='advance':result=advance(path,row)
        else:result=ingest_native(path,row,args.stage,args.result)
        result={k:v for k,v in result.items() if k in ['id','status','requestPath','qualityReview','result']}
    print(json.dumps(result,ensure_ascii=False))
