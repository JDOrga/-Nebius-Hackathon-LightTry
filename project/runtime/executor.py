"""No lifecycle: original strict guard/inverse rules plus exact environment scope."""
from pathlib import Path
import subprocess
import sys

from inference.executor import GuardedCosmosExecutor
from inference.driver import authorization,ROOT
from inference.jobs import read,atomic
from inference.images import digest
from inference.reuse import identity,key,validate


class SchemeExecutor(GuardedCosmosExecutor):
    supports_lighting_parameters=True
    def run_config(self):
        return {**super().run_config(),'lightingAdapterVersion':'single-scheme-hdr-adapter-v1'}
    def prepare_request(self,folder,request):
        config=read(self.config_path)
        if [p.get('carrierEnvironmentId',p.get('environmentId')) for p in request['presets']]!=config.get('required_environment_ids',['sunny']):
            raise ValueError('AUTHORIZED_SCHEME_ENVIRONMENT_REQUIRED')
        if config.get('required_language_operation_id'):
            p=request['preset']
            if (p.get('languageProposal',{}).get('operationId')!=config['required_language_operation_id'] or
                p['scheme']['parameters']!=config['required_parameters'] or
                request['original']['sha256']!=config['operator_scope']['approvedInputOriginalSha256']):
                raise ValueError('EXACT_ACCEPTED_LANGUAGE_SCHEME_AND_INPUT_REQUIRED')
        p=request['preset']
        if p.get('derivedHdrSha256'):
            from light_console import EnvironmentLibrary,sha
            library=EnvironmentLibrary(folder.parent.parent/'environments-v2',[])
            data=library.derived(p['parameters'])
            if sha(data)!=p['derivedHdrSha256']:raise ValueError('DERIVED_HDR_IDENTITY_MISMATCH')
            target=folder/'inputs/lighting.hdr'
            if target.exists() and target.read_bytes()!=data:raise ValueError('DERIVED_HDR_COLLISION')
            target.write_bytes(data)
        requirement=config.get('required_inverse_reuse')
        if requirement is not None:
            value=identity(request,(folder/'inputs/photo.png').read_bytes(),
                read(ROOT/'manifests/weights_manifest.json'),read(ROOT/'manifests/patch_manifest.json'))
            record=validate(ROOT/'.local/state/inverse-cache'/key(value),value)
            if requirement!={'key':key(value),'source':record['source']}:
                raise ValueError('STRICT_REQUIRED_INVERSE_REUSE_MISMATCH_NO_COLD_FALLBACK')
            request['requiredInverseReuse']=requirement
    def submit(self,folder,request):
        run,_,settings,_,_=authorization(self.config_path)
        atomic(folder/'runtime-binding.json',{'guardRunId':run.name,'resourceId':settings['devlab_id'],
            'launchSha256':digest((run/'launch.json').read_bytes())})
        with (folder/'driver.log').open('xb') as log:
            child=subprocess.Popen([sys.executable,'-X','utf8','-B',str(Path(__file__).with_name('driver.py')),
                '--config',str(self.config_path),'--job',str(folder)],stdin=subprocess.DEVNULL,stdout=log,
                stderr=subprocess.STDOUT,shell=False)
        self.children.append(child)
