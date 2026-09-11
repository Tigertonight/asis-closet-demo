import copy
import pytest
from scripts.batch_male_tryon_presets import merge_index


def test_merge_retains_unrelated_examples_and_legacy_failures():
    old={'examples':[{'id':'old','modelId':'female','outfitId':'old-look','status':'uploaded','result':{'sha256':'old'}}],
         'counts':{'failedImages':37,'failedUploaded':37,'blocked':4,'failed':37},'sourceSnapshot':{'original':True}}
    before=copy.deepcopy(old)
    male={'id':'male-new','modelId':'male','outfitId':'new-look','status':'uploaded','result':{'sha256':'new'}}
    result=merge_index(old,[male])
    assert old==before
    assert result['examples'][0]==before['examples'][0]
    assert result['sourceSnapshot']==before['sourceSnapshot']
    assert result['counts']['failed']==37 and result['counts']['blocked']==4
    assert result['counts']['uploaded']==2
    assert len(merge_index(result,[male])['examples'])==2
    with pytest.raises(ValueError,match='conflicts'):
        merge_index(result,[{**male,'result':{'sha256':'changed'}}])
