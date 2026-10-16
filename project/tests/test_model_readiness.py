import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from model_readiness import ready


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.session={'sessionId':'a'*32,'resourceId':'RESOURCE_FIXTURE','hostIdentity':{'vmId':'FIXTURE_VM'}}
        self.health={**self.session,'modelState':'ready','simulation':False,'modelLoaded':True,'executionMode':'resident'}

    def test_real_resident(self):self.assertTrue(ready(self.health,self.session))
    def test_cold_wrong_host_and_wrong_session_are_not_ready(self):
        for field,value in [('modelLoaded',False),('modelLoaded',None),('executionMode','per-job'),
                            ('simulation',True),('modelState','loading'),('hostIdentity',{'vmId':'OTHER'}),
                            ('sessionId','b'*32),('resourceId','OTHER')]:
            with self.subTest(field=field,value=value):
                health=copy.deepcopy(self.health);health[field]=value
                self.assertFalse(ready(health,self.session))

    def test_simulation_is_explicit_and_still_binds_identity(self):
        h={k:self.health[k] for k in ['sessionId','resourceId','modelState']}
        self.assertFalse(ready(h,self.session));self.assertTrue(ready(h,self.session,simulation=True))
        h['sessionId']='b'*32;self.assertFalse(ready(h,self.session,simulation=True))

if __name__=='__main__':unittest.main()
