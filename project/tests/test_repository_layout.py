"""Offline structure/configuration regression; no provider or lifecycle calls."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'project'))
spec = importlib.util.spec_from_file_location('local_studio_launch', ROOT/'start.py')
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)

class RepositoryLayoutTests(unittest.TestCase):
    def test_single_frontend_no_next_product(self):
        self.assertTrue((ROOT/'project/web/index.html').is_file())
        self.assertTrue((ROOT/'project/studio.py').is_file())
        self.assertFalse((ROOT/'project/next/server.py').exists())
        self.assertFalse((ROOT/'project/server.py').exists())

    def test_launcher_has_no_dated_machine_fallback(self):
        text=(ROOT/'start.py').read_text(encoding='utf-8')
        self.assertNotIn('202610',text)
        self.assertNotIn('cpu-venv',text)

    def test_configuration_paths_relative_to_repository_not_cwd(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'paths.json'
            p.write_text(json.dumps({'assets_dir':'relative assets','tasks_dir':'relative tasks','accepted_packages':[]}))
            _,cfg,args=launch.local_options(['--local-config',str(p),'--port','8801'])
            self.assertEqual(cfg['assets_dir'],str((ROOT/'relative assets').resolve()))
            self.assertEqual(args,['--port','8801'])

    def test_config_cannot_enable_paid_services_or_embed_keys(self):
        for field in ('inference_config','language_key_file','budget','api_key'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as t:
                p=Path(t)/'config.json';p.write_text(json.dumps({field:'OFFLINE_SYNTHETIC'}))
                with self.assertRaisesRegex(ValueError,'PATH_FIELDS_ONLY'):
                    launch.local_options(['--local-config',str(p)])

    def test_explicit_missing_configuration_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'EXPLICIT_LOCAL_CONFIG_MISSING'):
                launch.local_options(['--local-config',str(Path(t)/'missing.json')])

    def test_config_types_are_checked_before_launch(self):
        for cfg in ({'tasks_dir':False},{'accepted_packages':'not-a-list'},{'accepted_packages':[False]}):
            with tempfile.TemporaryDirectory() as t:
                p=Path(t)/'config.json';p.write_text(json.dumps(cfg))
                with self.assertRaises(ValueError):launch.local_options(['--local-config',str(p)])

    def test_historical_packet_layout_is_read_only(self):
        from runtime.layout import packet_runtime_file
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);old=root/'project/next/runtime/environments.json';old.parent.mkdir(parents=True)
            original=b'[{"id":"OFFLINE_SYNTHETIC"}]';old.write_bytes(original)
            self.assertEqual(packet_runtime_file(root,'environments.json'),old)
            self.assertEqual(old.read_bytes(),original)
            new=root/'project/runtime/environments.json';new.parent.mkdir(parents=True);new.write_bytes(b'[]')
            self.assertEqual(packet_runtime_file(root,'environments.json'),new)
            with self.assertRaises(ValueError):packet_runtime_file(root,'../../next/runtime/environments.json')

    def test_parameter_driver_delegates_shared_validation(self):
        from runtime import driver
        from inference import driver as shared
        self.assertIs(driver.authorization,shared.authorization)
        with patch.object(shared,'build_bundle',return_value='OBSERVED') as call:
            self.assertEqual(driver.build_bundle('job','run',{'OFFLINE':True}),'OBSERVED')
            self.assertTrue(call.call_args.kwargs['include_derived_hdr'])
            self.assertIn('project/runtime/layout.py',call.call_args.kwargs['bundle_files'])
        with patch.object(shared,'extract_result',return_value={}) as call:
            driver.extract_result('archive','target',require_gbuffers=True)
            self.assertEqual(call.call_args.kwargs,{'require_gbuffers':True,'extra_audit':('parameter-proof.json',)})

    def test_test_discovery_includes_product_with_portable_group_names(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        import selftest
        groups=selftest.discover_commands(ROOT)
        self.assertTrue(any(g[0]=='project-tests-test_repository_layout' for g in groups))
        self.assertTrue(all('/' not in g[0] and '\\' not in g[0] for g in groups))

    def test_runner_uses_explicit_existing_interpreter(self):
        import subprocess
        sys.path.insert(0,str(ROOT/'scripts'))
        import selftest
        with tempfile.TemporaryDirectory() as t, patch.object(selftest.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'OFFLINE','')) as call:
            row=selftest.run_group('product',['-m','unittest'],Path(t),timeout=10,python_executable='SYNTHETIC_CPU_PYTHON')
            self.assertEqual(call.call_args.args[0][0],'SYNTHETIC_CPU_PYTHON')
            self.assertEqual(row['python_executable'],'SYNTHETIC_CPU_PYTHON')
            self.assertEqual(row['exit_code'],0)

    def test_cache_reuses_configured_original_without_copying(self):
        from inference.driver import cache_directory
        with tempfile.TemporaryDirectory() as t, patch.dict('os.environ',{},clear=True):
            root=Path(t);config=root/'.local/studio.json';config.parent.mkdir()
            config.write_text(json.dumps({'inverse_cache_dir':'project/.inverse-cache'}))
            self.assertEqual(cache_directory(root),(root/'project/.inverse-cache').resolve())
            self.assertFalse((root/'project/.inverse-cache').exists())
            self.assertFalse((root/'.local/state').exists())
            config.write_text(json.dumps({'inverse_cache_dir':'../outside'}))
            with self.assertRaisesRegex(ValueError,'OUTSIDE_WORKSPACE'):cache_directory(root)

    def test_cache_environment_override_remains_workspace_bounded(self):
        from inference.driver import cache_directory
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            with patch.dict('os.environ',{'LIGHTTRY_INVERSE_CACHE':str(root/'explicit-cache')}):
                self.assertEqual(cache_directory(root),(root/'explicit-cache').resolve())
            with patch.dict('os.environ',{'LIGHTTRY_INVERSE_CACHE':str(root.parent/'outside-cache')}):
                with self.assertRaisesRegex(ValueError,'OUTSIDE_WORKSPACE'):cache_directory(root)

if __name__=='__main__':unittest.main()
