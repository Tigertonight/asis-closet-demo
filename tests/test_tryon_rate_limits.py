import unittest
from unittest.mock import patch

from app.ops import InMemoryRateLimiter, _matching_rule


class TryonRateLimitTests(unittest.TestCase):
    def test_browsing_uses_separate_bucket(self):
        for path in (
            '/selfit/try-on/report-outfits', '/selfit/try-on/report-outfits/random',
            '/selfit/try-on/wardrobe', '/selfit/try-on/models',
            '/selfit/try-on/inspiration-notes', '/selfit/try-on/inspiration-topics',
            '/try-on/capabilities',
        ):
            for method in ('GET', 'HEAD'):
                with self.subTest(path=path, method=method):
                    self.assertEqual(_matching_rule(path, method).name, 'tryon_read')

    def test_job_polling_keeps_its_own_bucket(self):
        self.assertEqual(_matching_rule('/selfit/try-on/jobs/example', 'GET').name,
                         'tryon_job_status')

    def test_writes_keep_upload_protection(self):
        for path in ('/selfit/try-on/jobs', '/closet/import/upload', '/analyze'):
            self.assertEqual(_matching_rule(path, 'POST').name, 'upload')

    @patch.dict('os.environ', {'SELFIT_UPLOAD_RATE_LIMIT': '2', 'SELFIT_TRYON_READ_RATE_LIMIT': '70'})
    def test_reads_do_not_exhaust_uploads_and_remain_limited(self):
        limiter = InMemoryRateLimiter()
        read = _matching_rule('/selfit/try-on/models', 'GET')
        upload = _matching_rule('/selfit/try-on/jobs', 'POST')
        for _ in range(70):
            self.assertTrue(limiter.check('user:test', read)[0])
        self.assertFalse(limiter.check('user:test', read)[0])
        self.assertTrue(limiter.check('user:test', upload)[0])
        self.assertTrue(limiter.check('user:test', upload)[0])
        self.assertFalse(limiter.check('user:test', upload)[0])


if __name__ == '__main__':
    unittest.main()
