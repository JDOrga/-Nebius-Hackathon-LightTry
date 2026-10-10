"""Offline real locator/bridge checks using synthetic CLI snapshots."""
import base64
import copy
import importlib.util
import json
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
worker=load('transition_worker',ROOT/'cloud/host_capture_api.py')
bridge=load('transition_bridge',ROOT/'cloud/cli_bridge.py')
KEY='ssh-ed25519 '+base64.b64encode(struct.pack('>I',11)+b'ssh-ed25519'+struct.pack('>I',32)+bytes(range(32))).decode()
SETTINGS=dict(cli_path='NEVER_EXECUTED',profile='synthetic',project_id='project-synthetic',
              tenant_id='tenant-synthetic',devlab_id='devlab-synthetic')
DEV=dict(metadata=dict(id=SETTINGS['devlab_id'],parent_id=SETTINGS['project_id']),
    spec=dict(image='synthetic-image',workspace=dict(container_path='/home'),ssh_authorized_keys=[KEY]),
    status=dict(state='IMAGE_PULLING',instances=[dict(compute_instance_id='computeinstance-synthetic',
        state='IMAGE_PULLING',compute_instance_state='RUNNING',public_ip='192.0.2.10',private_ip='10.0.0.1')]))
VM=dict(metadata=dict(id='computeinstance-synthetic',parent_id='project-synthetic'),
    status=dict(state='RUNNING',network_interfaces=[dict(public_ip_address=dict(address='192.0.2.10'))]),
    spec=dict(cloud_init_user_data='#cloud-config\nusers:\n  - name: nebius\n    ssh_authorized_keys:\n      - '+KEY+'\n'))

class TransitionTests(unittest.TestCase):
    def run_locator(self,before,after,vm=None):
        replies=iter([before,after]); calls=[];audit=[]
        def cli(settings,args,structured=True):
            calls.append(args)
            if args[:2]==['config','get']:
                return SETTINGS['tenant_id'] if args[2]=='tenant-id' else SETTINGS['project_id']
            if args[:3]==['iam','v2','project']:
                return dict(metadata=dict(id=SETTINGS['project_id'],parent_id=SETTINGS['tenant_id']))
            if args[:2]==['ai','devlab']:return copy.deepcopy(next(replies))
            if args[:2]==['compute','instance']:return copy.deepcopy(vm or VM)
            raise AssertionError(args)
        with patch.object(worker,'cli',cli):
            try:return worker.locate(SETTINGS,bridge,KEY,audit),audit,calls,None
            except Exception as error:return None,audit,calls,error

    def test_status_transition_records_exact_diff_then_full_reread_can_succeed(self):
        after=copy.deepcopy(DEV);after['status']['state']='RUNNING';after['status']['instances'][0]['state']='RUNNING'
        result,audit,calls,error=self.run_locator(DEV,after)
        self.assertIsNone(result);self.assertEqual(error.label,'STARTUP_STATE_TRANSITION');self.assertTrue(error.retryable)
        self.assertEqual({d['field'] for d in audit[0]['differences']},{'state','instances[0].state'})
        self.assertEqual(audit[0]['before']['state'],'IMAGE_PULLING')
        self.assertEqual(audit[0]['after']['state'],'RUNNING')
        result,audit,calls,error=self.run_locator(after,after)
        self.assertIsNone(error);self.assertTrue(result['public_key_mapping_verified'])
        self.assertTrue(any(c[:3]==['iam','v2','project'] for c in calls))
        self.assertEqual(sum(c[:2]==['compute','instance'] for c in calls),1)

    def test_same_status_different_vm_or_ip_is_hard_failure(self):
        for field,value in [('compute_instance_id','computeinstance-other'),('public_ip','192.0.2.20'),('private_ip','10.0.0.2')]:
            with self.subTest(field=field):
                after=copy.deepcopy(DEV);after['status']['instances'][0][field]=value
                _,audit,_,error=self.run_locator(DEV,after)
                self.assertEqual(error.label,'VM_IDENTITY_CHANGED');self.assertFalse(error.retryable)
                self.assertIn('instances[0].'+field,{d['field'] for d in audit[0]['differences']})

    def test_status_change_never_masks_key_owner_image_or_vm_owner_mismatch(self):
        for field,value,label in [('key',[],'LOCAL_KEY_NOT_IN_DEVLAB'),
                                ('owner','project-other','DEVLAB_ID_OR_PROJECT_MISMATCH'),
                                ('image','changed-image','VM_IDENTITY_CHANGED')]:
            after=copy.deepcopy(DEV);after['status']['state']='RUNNING'
            if field=='key':after['spec']['ssh_authorized_keys']=value
            if field=='owner':after['metadata']['parent_id']=value
            if field=='image':after['spec']['image']=value
            _,audit,_,error=self.run_locator(DEV,after)
            self.assertEqual(error.label,label);self.assertFalse(error.retryable)
            self.assertTrue(audit[0]['differences'])
        vm=copy.deepcopy(VM);vm['metadata']['parent_id']='project-other'
        _,_,_,error=self.run_locator(DEV,DEV,vm)
        self.assertEqual(str(error),'VM_ID_OR_PROJECT_MISMATCH')

    def test_stopping_or_missing_instance_is_not_retryable_transition(self):
        for status in ('STOPPING','STOPPED'):
            after=copy.deepcopy(DEV);after['status']['state']=status
            _,_,_,error=self.run_locator(DEV,after)
            self.assertEqual(error.label,'DEVLAB_UNSAFE_STATE_CHANGE');self.assertFalse(error.retryable)
        after=copy.deepcopy(DEV);after['status']['instances']=[]
        _,_,_,error=self.run_locator(DEV,after)
        self.assertEqual(error.label,'VM_IDENTITY_CHANGED')

    def test_allowlisted_evidence_never_contains_keys_cloud_init_or_unrelated_fields(self):
        dev=copy.deepcopy(DEV);dev['spec']['token']='SECRET_TOKEN';dev['metadata']['note']='PRIVATE_NOTE'
        _,audit,_,error=self.run_locator(dev,dev)
        self.assertIsNone(error)
        encoded=json.dumps(audit)
        for forbidden in (KEY,'SECRET_TOKEN','PRIVATE_NOTE','cloud_init','ssh_authorized_keys'):
            self.assertNotIn(forbidden,encoded)

if __name__=='__main__':unittest.main()
