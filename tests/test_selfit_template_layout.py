"""Keep builder auto-layout aligned with published outfit templates."""
import json
import subprocess

import pytest
from app.outfit_layout import outfit_box, vertical_align

@pytest.mark.parametrize('slots', [
    ['top', 'bottom', 'shoes'], ['dress', 'bag', 'accessory'],
    ['outer', 'top', 'skirt', 'shoes', 'bag'],
])
def test_builder_matches_template(slots):
    pieces = [dict(id=str(i), category=slot, aspect=0.6+i*0.17) for i,slot in enumerate(slots)]
    script = "const {templateLayout}=require('./app/static/selfit-tryon/outfit-layout.js');console.log(JSON.stringify(templateLayout(JSON.parse(process.argv[1]))));"
    result = json.loads(subprocess.check_output(['node','-e',script,json.dumps(pieces)],text=True))
    for item, actual in zip(pieces,result):
        slot = 'accessory_1' if item['category']=='accessory' else item['category']
        x1,y1,x2,y2 = outfit_box(slot,slots)
        w=min(x2-x1,(y2-y1)*item['aspect']);h=w/item['aspect']
        align=vertical_align(slot,slots)
        y=y2-h if align=='end' else y1 if align=='start' else y1+(y2-y1-h)/2
        assert actual['x'] == pytest.approx((x1+(x2-x1-w)/2)/12)
        assert actual['y'] == pytest.approx(y/15)
        assert actual['w'] == pytest.approx(w/12)
        assert actual['h'] == pytest.approx(h/15)
