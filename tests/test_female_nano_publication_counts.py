import pytest

from scripts.publish_female_nano_presets import index_counts


def test_counts_distinguish_usable_images_archived_failures_and_missing_jobs():
    rows = [
        {'id': 'a', 'outfitId': 'one', 'modelId': 'female', 'status': 'uploaded', 'result': {'verified': True}},
        {'id': 'b', 'outfitId': 'one', 'modelId': 'male', 'status': 'uploaded', 'result': {'verified': True}},
        {'id': 'c', 'outfitId': 'two', 'modelId': 'female', 'status': 'failed_quality', 'failedResult': {'verified': True}},
        {'id': 'd', 'outfitId': 'three', 'modelId': 'female', 'status': 'blocked_moderation'},
        {'id': 'e', 'outfitId': 'four', 'modelId': 'female', 'status': 'running'},
    ]
    assert index_counts(rows, expected=8) == {
        'expected': 8, 'records': 5, 'outfits': 4, 'models': 2,
        'generated': 2, 'uploaded': 2, 'failed': 2, 'failedImages': 1,
        'failedUploaded': 1, 'blocked': 1, 'pending': 4,
        'totalImages': 3, 'totalUploaded': 3, 'processed': 4,
    }


def test_complete_counts_do_not_leave_old_failures_or_pending_totals():
    row = {'id': 'a', 'outfitId': 'one', 'modelId': 'female', 'status': 'uploaded', 'result': {'verified': True}}
    result = index_counts([row], expected=1)
    assert result['uploaded'] == result['generated'] == result['totalImages'] == result['totalUploaded'] == 1
    assert result['failed'] == result['failedImages'] == result['failedUploaded'] == result['pending'] == result['blocked'] == 0
    with pytest.raises(AssertionError):
        index_counts([row, row], expected=2)
