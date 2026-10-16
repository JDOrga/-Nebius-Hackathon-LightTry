"""Local development binding cannot activate paid/cloud operations."""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_cpu_api import LocalCPUAPI


class LocalCPUTests(unittest.TestCase):
    def setUp(self):
        self.output=[]
        self.h=SimpleNamespace(task_store=SimpleNamespace(executor=None,capabilities=lambda:{'enabled':False}),
            recipe_language=None,csrf_token='SYNTHETIC_CSRF',headers={'X-LightTry-Token':'SYNTHETIC_CSRF'},
            valid_host=lambda:True,valid_origin=lambda:True,
            json_response=lambda value,status=200:self.output.append((status,value)),
            job_error=lambda error:self.output.append((error.http,error.code)))

    def test_construction_and_status_never_construct_real_provider(self):
        with patch('nebius_provider.NebiusProvider.__init__',side_effect=AssertionError('NO PROVIDER CONSTRUCTION')):
            api=LocalCPUAPI();self.assertTrue(api.get(self.h,'/api/gpu/entry-status'))
        code,value=self.output[-1]
        self.assertEqual(code,200);self.assertFalse(value['configured']);self.assertFalse(value['canStart'])
        self.assertEqual(value['state'],'UNKNOWN');self.assertTrue(value['adaptersLoaded'])

    def test_health_capabilities_and_controls(self):
        api=LocalCPUAPI();api.get(self.h,'/api/health')
        self.assertFalse(self.output[-1][1]['paidServices'])
        api.get(self.h,'/api/inference/capabilities');self.assertEqual(self.output[-1][1]['csrfToken'],'SYNTHETIC_CSRF')
        for route in api.controls:
            api.get(self.h,route);self.assertEqual(self.output[-1][0],405)
            api.post(self.h,route);self.assertEqual(self.output[-1][0],503)

    def test_local_control_requires_csrf_and_origin_even_when_disabled(self):
        api=LocalCPUAPI();self.h.headers={};api.post(self.h,'/api/gpu/entry-start')
        self.assertEqual(self.output[-1][0],403)
        self.h.headers={'X-LightTry-Token':'SYNTHETIC_CSRF'};self.h.valid_origin=lambda:False
        api.post(self.h,'/api/gpu/stop');self.assertEqual(self.output[-1][0],403)

    def test_unrelated_routes_not_intercepted(self):
        api=LocalCPUAPI();self.assertFalse(api.get(self.h,'/api/catalog'));self.assertFalse(api.post(self.h,'/api/tasks'))


if __name__=='__main__':unittest.main()
