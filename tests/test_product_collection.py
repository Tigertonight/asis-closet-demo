import io
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from PIL import Image

from app import product_collection as pc
from app.product_collection_auth import require_collection_admin
from app import product_collection_auth as auth


@pytest.fixture
def intake(monkeypatch, tmp_path):
    monkeypatch.setattr(pc, 'STORE', tmp_path / 'store')
    monkeypatch.setattr(auth, 'AUTH_DB', tmp_path / 'auth.sqlite3')
    app = FastAPI(); app.include_router(pc.router)
    return app, TestClient(app)


def data(**kwargs):
    result = {k: '不适用' for k, _, kind, _, _ in pc.FIELDS if kind not in {'selling', 'image'}}
    result.update(brand='测试品牌', product_name='测试商品', category='食品', contact='测试联系人', contact_method='test_wechat',
                  image_not_applicable=True, selling_points={k:'不适用' for k, _ in pc.SELLING_FIELDS})
    if isinstance(kwargs.get('selling_points'), dict):
        kwargs['selling_points'] = {**result['selling_points'], **kwargs['selling_points']}
    return {**result, **kwargs}


def image_bytes():
    image = Image.new('RGB', (800, 600), 'white')
    result = io.BytesIO(); image.save(result, 'PNG')
    return result.getvalue()


def submit(c, values=None, image=None, request_id=None):
    body = {'payload': json.dumps(values if values is not None else data(image_not_applicable=image is None)), 'request_id': request_id or str(uuid.uuid4())}
    return c.post('/api/v1/selfit/product-collection', data=body,
                  files={'photo': ('商品.png', image, 'image/png')} if image is not None else None)


def test_submit_persists_all_fields_and_private_original(intake):
    app, c = intake
    values = data(image_not_applicable=False, **{k: ('yes' if kind == 'status' else '1.25' if kind == 'money' else '0' if kind == 'integer' else 'https://example.com/item' if kind == 'url' else '填写内容') for k, _, kind, _, _ in pc.FIELDS if kind not in {'image','selling'}})
    values['selling_points'] = {k: label + '内容' for k, label in pc.SELLING_FIELDS}
    raw = image_bytes(); saved = submit(c, values, raw); assert saved.status_code == 200
    identifier = saved.json()['id']
    for path in ['/product-collection-admin/api/products', '/product-collection-admin/api/products/export.xlsx', f'/product-collection-admin/api/products/{identifier}', f'/product-collection-admin/api/products/{identifier}/image', f'/product-collection-admin/api/products/{identifier}/image?preview=true']:
        assert c.get(path).status_code == 401
        assert c.get(path, headers={'Authorization':'Bearer non-admin-token'}).status_code in (401,403)
    app.dependency_overrides[require_collection_admin] = lambda: {'user_id': 'admin_console'}
    assert c.get('/product-collection-admin/api/products').json()['total'] == 1
    assert c.get('/product-collection-admin/api/products').json()['today'] == 1
    record = c.get(f'/product-collection-admin/api/products/{identifier}'); assert record.json()['data'] == values
    assert record.headers['cache-control'] == 'private, no-store'
    original = c.get(f'/product-collection-admin/api/products/{identifier}/image')
    assert original.content == raw and 'attachment;' in original.headers['content-disposition']
    preview = c.get(f'/product-collection-admin/api/products/{identifier}/image?preview=true')
    with Image.open(io.BytesIO(preview.content)) as img:
        assert img.format == 'JPEG' and max(img.size) == 240
    # Reading via a fresh connection returns the same durable record.
    with pc.database() as db:
        assert db.execute('SELECT count(*) FROM products').fetchone()[0] == 1


def test_idempotency_including_concurrent_retry(intake):
    app, c = intake; key = str(uuid.uuid4()); raw=image_bytes()
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(lambda _:pc.save_submission(key, pc.clean_data(json.dumps(data(image_not_applicable=False))), raw),range(4)))
    assert len({r['id'] for r in responses}) == 1
    assert submit(c, image=raw, request_id=key).status_code == 200
    assert submit(c, data(product_name='changed', image_not_applicable=False), image=raw, request_id=key).status_code == 409
    with pc.database() as db:
        assert db.execute('SELECT count(*) FROM products').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM product_images').fetchone()[0] == 1


@pytest.mark.parametrize('values', [data(brand=' '),data(contact_method=''),data(daily_price='-1'),data(live_price='1.001'),data(stock='1.5'),data(lottery_stock='1000000000'),data(product_url='javascript:alert(1)'),data(live_url='http://u:p@example.com'),data(listed='maybe'),data(selling_points={'unexpected':'x'}),data(brand='a\x00'),data(extra='x'),data(product_id=123),data(selling_points={'features':'x'*1001})])
def test_reject_invalid_fields(intake,values):
    _,c=intake;assert submit(c,values).status_code==422


def test_image_errors_and_no_partial_row(intake, monkeypatch):
    _, c = intake
    assert submit(c, image=b'not a photo').status_code == 422
    assert submit(c, image=b'').status_code == 422
    monkeypatch.setattr(pc, 'MAX_IMAGE_BYTES', 10)
    assert submit(c, image=image_bytes()).status_code == 413
    with pc.database() as db:
        assert db.execute('SELECT count(*) FROM products').fetchone()[0] == 0


def test_pagination_filter_and_export_with_safe_text(intake, monkeypatch):
    app,c=intake; app.dependency_overrides[require_collection_admin]=lambda: {'user_id':'admin_console'}
    submit(c, data(brand='=HYPERLINK("bad")', product_id='00012345678901234567890', daily_price='23.50', live_price='0', stock='12', selling_points={'features':'第一行\n第二行'}, image_not_applicable=False), image=image_bytes())
    submit(c, data(brand='其他品牌'));submit(c, data(brand='100%纯'))
    first=c.get('/product-collection-admin/api/products?limit=2').json();assert first['total']==3 and len(first['items'])==2
    submit(c, data(brand='新到达'))
    second=c.get(f'/product-collection-admin/api/products?limit=2&before_id={first["next_cursor"]}').json()
    assert {x['id'] for x in first['items']}.isdisjoint({x['id'] for x in second['items']})
    assert len(second['items'])==1
    assert c.get('/product-collection-admin/api/products',params={'q':'%'}).json()['filtered']==1
    exported=c.get('/product-collection-admin/api/products/export.xlsx',params={'q':'HYPERLINK'})
    assert exported.status_code==200
    workbook=load_workbook(io.BytesIO(exported.content));ws=workbook.active
    assert list(next(ws.values))[:22]==[f[1] for f in pc.FIELDS]
    assert ws.max_row==2 and ws.max_column==24
    assert ws['A2'].value=='=HYPERLINK("bad")' and ws['A2'].data_type=='s'
    assert ws['E2'].value=='00012345678901234567890' and ws['E2'].data_type=='s'
    assert ws['K2'].value==23.5 and ws['L2'].value==0 and ws['O2'].value==12
    assert '第一行\n第二行' in ws['Q2'].value
    assert len(ws._images)==1
    assert ws.freeze_panes=='C2' and ws.auto_filter.ref=='A1:X2'
    assert c.get('/product-collection-admin/api/products/export.xlsx',params={'q':'not found'}).status_code==200
    monkeypatch.setattr(pc,'MAX_EXPORT_ROWS',2)
    assert c.get('/product-collection-admin/api/products/export.xlsx').status_code==422


def test_routes_schema_and_missing_record(intake):
    app,c=intake
    assert c.get('/selfit/product-collection').status_code==200
    schema=c.get('/api/v1/selfit/product-collection/schema').json()
    assert len(schema['fields'])==22 and len(schema['selling_fields'])==10
    assert '首饰' in schema['dimensions_help']
    app.dependency_overrides[require_collection_admin]=lambda: {'user_id':'admin_console'}
    assert c.get('/product-collection-admin/api/products/99999').status_code==404
    assert c.get('/product-collection-admin/api/products/99999/image').status_code==404


@pytest.mark.parametrize('field', [
    'brand','product_name','category','product_url','product_id','contact','contact_method','operator',
    'live_url','sku','daily_price','live_price','promotion','gifts','stock','lottery_stock','cautions','listed','price_verified','dimensions',
])
def test_every_scalar_field_requires_an_answer(intake, field):
    _, c = intake
    for missing in (True, False):
        values = data()
        if missing:
            del values[field]
        else:
            values[field] = '  '
        assert submit(c, values).status_code == 422


@pytest.mark.parametrize('field', ['introduction','features','differentiation','shelf_life','production_date','celebrity','pregnancy','sensitive_skin','color','flavor'])
def test_every_selling_point_requires_an_answer(intake, field):
    _, c = intake
    for missing in (True, False):
        values = data()
        if missing:
            del values['selling_points'][field]
        else:
            values['selling_points'][field] = '  '
        assert submit(c, values).status_code == 422


def test_image_requires_upload_or_explicit_not_applicable(intake):
    _, c = intake
    assert submit(c, data(image_not_applicable=False)).status_code == 422
    assert submit(c, data(image_not_applicable='true')).status_code == 422
    assert submit(c, data(image_not_applicable=True), image=image_bytes()).status_code == 422
    assert submit(c, data(image_not_applicable=False), image=image_bytes()).status_code == 200
    assert submit(c, data(image_not_applicable=True)).status_code == 200


def test_not_applicable_export_and_legacy_optional_records(intake):
    app,c=intake;app.dependency_overrides[require_collection_admin]=lambda:{'role':'product_collection_admin'}
    # Historical submissions remain readable even though new submissions require all fields.
    legacy = {k:'' for k,_,kind,_,_ in pc.FIELDS if kind not in {'image','selling'}}
    legacy.update(brand='旧品牌',product_name='旧商品',category='食品',contact='甲',contact_method='test',selling_points={k:'' for k,_ in pc.SELLING_FIELDS})
    with pc.database() as db:
        db.execute('INSERT INTO products(request_id,digest,created_at,brand,product_name,category,data) VALUES(?,?,?,?,?,?,?)',
                   (str(uuid.uuid4()),'legacy','2026-10-30T00:00:00+00:00','旧品牌','旧商品','食品',json.dumps(legacy)))
    response=submit(c,data());assert response.status_code==200
    rows=c.get('/product-collection-admin/api/products').json()['items']
    assert rows[0]['image_not_applicable']==1 and rows[1]['image_not_applicable']==0
    assert c.get('/product-collection-admin/api/products/1').json()['data']==legacy
    book=load_workbook(io.BytesIO(c.get('/product-collection-admin/api/products/export.xlsx').content))
    for col in ['D','I','K','L','O','P','R','T','U']:
        assert book.active[f'{col}2'].value=='不适用'
        assert book.active[f'{col}2'].data_type=='s'
    assert book.active['K3'].value is None and book.active['T3'].value=='待确认'
    book.close()
    schema=c.get('/api/v1/selfit/product-collection/schema').json()
    assert all(f['required'] for f in schema['fields']+schema['selling_fields'])
