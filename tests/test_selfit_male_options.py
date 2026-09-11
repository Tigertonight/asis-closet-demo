"""Male manual choices round-trip through both authenticated editor endpoints."""
import unittest
from app import selfit_onboarding as onboarding
from app.selfit_recommend import resolve_suit_profile
from app.selfit_suit import suit_summary, FALLBACK_UNCLEAR
from test_selfit_manual_provenance import USER, isolated_client, photo_session, make_data

OPTIONS = {
    'skin': ['冷白肤','暖白肤','中性自然肤','橄榄肤','暖黄肤','小麦色'],
    'faceShape': ['方脸','菱形脸','倒三角脸','椭圆脸','圆脸'],
    'bodyShape': ['梯形','三角形','倒三角形','矩形','椭圆形'],
}

class MaleManualOptionsTests(unittest.TestCase):
    def test_every_option_round_trips_in_onboarding_and_report_snapshot(self):
        with isolated_client() as client:
            session = photo_session()
            session['gender'] = 'male'
            onboarding._write_store(make_data(session, onboarding._profile_snapshot(session)))
            base = '/api/v1/selfit/sessions/' + session['session_id']
            for field, values in OPTIONS.items():
                for value in values:
                    with self.subTest(field=field, value=value):
                        saved = client.patch(base + '/profile', json={'manual': {field: value}})
                        self.assertEqual(saved.status_code, 200, saved.text)
                        feature = next(f for f in client.get(base + '/suit').json()['features'] if f['key'] == field)
                        self.assertEqual(feature['value'], value)
                        self.assertEqual(feature['source'], 'manual')
                        self.assertNotEqual(feature['description'], FALLBACK_UNCLEAR)
                        current = onboarding._load_store()['sessions'][0]
                        snapshot = onboarding._profile_snapshot(current)
                        self.assertEqual(snapshot['manual'][field], value)
                        self.assertEqual(snapshot['manualOverrides'][field], value)
                        self.assertEqual(snapshot['gender'], 'male')

    def test_every_option_round_trips_in_profile_and_gender_survives_session_expiry(self):
        with isolated_client() as client:
            session = photo_session()
            session['gender'] = 'male'
            onboarding._write_store(make_data(session, onboarding._profile_snapshot(session)))
            for field, values in OPTIONS.items():
                for value in values:
                    current = client.get('/api/v1/selfit/me/profile').json()['profile']
                    saved = client.patch('/api/v1/selfit/me/profile', headers={'If-Match': str(current['revision'])},
                                         json={'reportId': 'rep_provenance', 'manual': {field: value}})
                    self.assertEqual(saved.status_code, 200, saved.text)
                    profile = saved.json()['profile']
                    self.assertEqual(profile['manual'][field], value)
                    self.assertEqual(profile['manualOverrides'][field], value)
                    self.assertEqual(profile['gender'], 'male')
            data = onboarding._load_store()
            data['sessions'] = []
            onboarding._write_store(data)
            profile = client.get('/api/v1/selfit/me/profile').json()['profile']
            self.assertEqual(profile['gender'], 'male')
            self.assertEqual(profile['manual']['bodyShape'], '椭圆形')
            self.assertEqual(profile['manualOverrides']['bodyShape'], '椭圆形')

    def test_female_photo_classification_and_invalid_values_are_unchanged(self):
        session = photo_session()
        session['gender'] = 'female'
        self.assertEqual(resolve_suit_profile(session), {'skin':'暖黄肤','face_shape':'椭圆脸','body_shape':'矩型'})
        self.assertTrue(all(f['source'] == 'photo' for f in suit_summary(session)['features']))
        self.assertEqual(onboarding._validate_manual({'bodyShape':'not-a-shape'}).status_code,422)
        self.assertEqual(onboarding._validate_manual({'gender':'male'}).status_code,422)

if __name__ == '__main__':
    unittest.main()
