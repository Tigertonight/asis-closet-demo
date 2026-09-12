"""Isolated regression tests; never read or change the local user's records."""
import copy
import unittest
from unittest.mock import patch

from app import selfit_onboarding as onboarding, selfit_report
from test_selfit_manual_provenance import USER, isolated_client, photo_session, make_data


class GenderFlowTests(unittest.TestCase):
    def test_new_flow_does_not_restore_old_samples_even_after_selecting_gender(self):
        with isolated_client() as client:
            old = photo_session()
            data = make_data(old, onboarding._profile_snapshot(old))
            onboarding._write_store(data)
            created = client.post('/api/v1/selfit/sessions', json={'onboardingMode': 'new'}).json()['session']
            self.assertIsNone(created['gender'])
            self.assertTrue(created['requiresGender'])
            url = '/api/v1/selfit/sessions/' + created['sessionId']
            for gender in (None, 'female', 'male'):
                if gender:
                    saved = client.patch(url + '/gender', json={'gender': gender})
                    self.assertEqual(saved.status_code, 200)
                    self.assertEqual(client.get(url).json()['session']['gender'], gender)
                summary = client.get(url + '/suit').json()
                self.assertEqual(summary['photos'], {'face': False, 'body': False})
                self.assertTrue(all(not item['value'] for item in summary['features']))
                self.assertEqual(client.get(url + '/photos/face/preview').status_code, 404)
            # Historical photos and reports are intact.
            stored = onboarding._load_store()
            self.assertEqual(len(stored['reports']), 1)
            self.assertEqual(stored['sessions'][0]['photos'], old['photos'])

    def test_gender_is_required_before_upload_and_report_not_inferred(self):
        with isolated_client() as client:
            session = client.post('/api/v1/selfit/sessions', json={'onboardingMode': 'new'}).json()['session']
            url = '/api/v1/selfit/sessions/' + session['sessionId']
            for endpoint in ('/photos/face', '/photos/body', '/report-jobs'):
                response = client.post(url + endpoint)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()['error']['code'], 'profile.gender_required')
            for value in (None, '', 'other', [], True):
                self.assertEqual(client.patch(url + '/gender', json={'gender': value}).status_code, 422)
            self.assertEqual(client.patch(url + '/gender', json={'gender': 'male'}).status_code, 200)
            # Once selected, the request passes the gender gate (missing file is now the error).
            self.assertEqual(client.post(url + '/photos/face').json()['error']['code'], 'photo.image_missing')

    def test_retest_inherits_only_explicit_gender_from_report_snapshot(self):
        with isolated_client() as client:
            old = photo_session()
            old['gender'] = 'male'
            data = make_data(old, onboarding._profile_snapshot(old))
            onboarding._write_store(data)
            self.assertEqual(onboarding._account_profile(data, USER['user_id'])['gender'], 'male')
            session = client.post('/api/v1/selfit/sessions', json={'onboardingMode': 'retest'}).json()['session']
            self.assertEqual(session['gender'], 'male')
            fresh = client.post('/api/v1/selfit/sessions', json={'onboardingMode': 'new'}).json()['session']
            self.assertIsNone(fresh['gender'])
            snapshot = onboarding._profile_snapshot(old)
            self.assertEqual(snapshot['gender'], 'male')
            self.assertEqual(snapshot['manualOverrides'], {})

    def test_gender_patch_honors_session_ownership(self):
        with isolated_client() as client:
            old = photo_session()
            old['user_id'] = 'another-user'
            data = onboarding._store_module.empty_store()
            data['sessions'].append(old)
            onboarding._write_store(data)
            self.assertIn(client.patch('/api/v1/selfit/sessions/' + old['session_id'] + '/gender', json={'gender': 'male'}).status_code, (403, 404))

    def test_report_job_persists_gender_and_template_identity(self):
        with isolated_client() as client, patch.object(onboarding._REPORT_EXECUTOR, 'submit'), \
                patch.object(selfit_report, '_personality_template_catalog', return_value=GenderReportTests().catalog()), \
                patch.object(selfit_report, 'resolve_image_references', side_effect=lambda value: value), \
                patch.object(selfit_report.selfit_persona, 'classify_persona', return_value={'primary_persona': 'MUTE'}):
            session = client.post('/api/v1/selfit/sessions', json={'onboardingMode': 'new'}).json()['session']
            url = '/api/v1/selfit/sessions/' + session['sessionId']
            client.patch(url + '/gender', json={'gender': 'male'})
            client.patch(url + '/preferences', json={'axes': {'shape': 40}})
            response = client.post(url + '/report-jobs')
            self.assertEqual(response.status_code, 202)
            onboarding._run_report_job(response.json()['job']['jobId'])
            stored = onboarding._load_store()['reports'][-1]
            self.assertEqual(stored['data']['gender'], 'male')
            self.assertEqual(stored['data']['templateId'], 'mute-male')
            self.assertEqual(stored['profile']['gender'], 'male')
            self.assertEqual(stored['profile']['manualOverrides'], {})


class GenderReportTests(unittest.TestCase):
    def catalog(self):
        base = {'gender': 'unisex', 'metadata': {'name': '静音时髦'}, 'hero': {'image': {'src': '/female.jpg'}},
                'recommendations': {'outfits': {'items': [{'id': 'f', 'image': {'src': '/female-outfit.jpg'}}]}}}
        male = copy.deepcopy(base)
        male.update(gender='male', hero={'image': {'src': '/male.jpg'}})
        male['recommendations']['outfits']['items'][0]['image']['src'] = '/male-outfit.jpg'
        return {'types': {'mute': base}, 'variants': {'mute-male': male}}

    def test_matching_gender_template_is_used_without_changing_persona(self):
        with patch.object(selfit_report, '_personality_template_catalog', return_value=self.catalog()), patch.object(selfit_report, 'resolve_image_references', side_effect=lambda value: value):
            male = selfit_report.default_personality_report('MUTE', 'male')
            female = selfit_report.default_personality_report('MUTE', 'female')
            self.assertEqual(male['typeId'], female['typeId'])
            self.assertEqual(male['templateId'], 'mute-male')
            self.assertEqual(male['heroImage']['src'], '/male.jpg')
            self.assertEqual(male['outfits'][0]['imageUrl'], '/male-outfit.jpg')
            self.assertEqual(female['outfits'][0]['imageUrl'], '/female-outfit.jpg')

    def test_missing_male_template_is_explicit_not_female_fallback(self):
        catalog = self.catalog()
        catalog['variants'] = {}
        with patch.object(selfit_report, '_personality_template_catalog', return_value=catalog), patch.object(selfit_report, 'resolve_image_references', side_effect=lambda value: value):
            report = selfit_report.default_personality_report('mute', 'male')
            self.assertEqual(report['gender'], 'male')
            self.assertEqual(report['recommendationStatus'], 'pending_gender_content')
            self.assertEqual(report['heroImage'], {})
            self.assertEqual(report['outfits'], [])
            self.assertEqual(report['makeup'], [])
            self.assertTrue(report['recommendationNotice'])

    def test_report_builder_passes_self_declared_gender(self):
        with patch.object(selfit_report, 'default_personality_report', return_value={}) as renderer:
            session = {'preferences': {'axes': {'shape': 40, 'energy': 60, 'trend': 40}}, 'gender': 'female'}
            selfit_report.default_report_builder(session)
            female_code = renderer.call_args.args[0]
            session['gender'] = 'male'
            selfit_report.default_report_builder(session)
            male_code = selfit_report.selfit_persona.classify_persona(
                selfit_report.selfit_persona.build_user_vector(session), 'male')['primary_persona']
            self.assertEqual(renderer.call_args.args, (male_code, 'male'))
            self.assertIn(male_code, selfit_report.selfit_persona.MALE_PERSONA_CODES)


if __name__ == '__main__':
    unittest.main()
