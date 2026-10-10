"""Focused offline PS5.1 transition evidence, identity lock and deadline tests."""
import json
import unittest
import test_host_capture as fixture

class CaptureTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=fixture.RESULTS;root.mkdir()
        (root/'scanner.cs').write_text(fixture.SCANNER,encoding='ascii')
        build=root/'build.ps1'
        build.write_text('Add-Type -Path $args[0] -OutputAssembly $args[1] -OutputType ConsoleApplication\n',encoding='ascii')
        result=fixture.ps(build,[root/'scanner.cs',root/'synthetic-keyscan.exe'])
        if result.returncode:raise AssertionError(result.stderr)

    def test_transition_evidence_persisted_and_original_timing_unchanged(self):
        run,config=fixture.fixture('recover',api=['success','success','transition','success'])
        timing=(run/'timing.json').read_bytes()
        code,events,error,_=fixture.execute(run,config)
        self.assertEqual(code,0,error)
        reads=[e['details']['validation_reads'] for e in events if e.get('event')=='end' and
               'validation_reads' in e.get('details',{})]
        self.assertEqual(reads[0][0]['differences'][0],{'field':'state','before':'IMAGE_PULLING','after':'RUNNING'})
        self.assertEqual((run/'timing.json').read_bytes(),timing)
        self.assertFalse((run/'complete.json').exists())
        self.assertFalse((run/'host-trust.json').exists())
        self.assertEqual(len((config.parent/'arguments.txt').read_text().splitlines()),2)

    def test_transition_locks_vm_before_success_and_refuses_different_vm(self):
        run,config=fixture.fixture('identity-lock',api=['transition','changed'])
        code,_,error,_=fixture.execute(run,config)
        self.assertEqual(code,1)
        self.assertEqual(error['category'],'VM_IDENTITY_CHANGED')
        self.assertTrue((run/'complete.json').exists())
        self.assertFalse((run/'host-candidate.json').exists())
        self.assertFalse((config.parent/'arguments.txt').exists())

    def test_repeated_transitions_exhaust_original_read_limit_without_reanchoring(self):
        run,config=fixture.fixture('read-limit',api=['transition'])
        value=json.loads(config.read_text())
        value['simulation_policy']={'ready_seconds':15,'capture_seconds':20,'ready_poll_ms':1,'ready_max_reads':3}
        fixture.write(config,value)
        timing=(run/'timing.json').read_bytes()
        code,events,error,_=fixture.execute(run,config)
        self.assertEqual(code,1)
        self.assertEqual(error['category'],'READY_WAIT_READ_LIMIT')
        self.assertEqual((run/'timing.json').read_bytes(),timing)
        self.assertTrue(json.loads((run/'complete.json').read_text())['stop_required'])
        self.assertEqual(int((config.parent/'api-index.txt').read_text()),3)

if __name__=='__main__':unittest.main()
