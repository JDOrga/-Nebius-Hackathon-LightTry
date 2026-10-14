"""Recipe-aware facade over the original durable, strictly verified TaskStore."""
import copy
from pathlib import Path

from inference.jobs import TaskStore, JobError, read, ID, atomic
from inference.images import digest
from lighting import normalize_scheme, identity, CLOSED


class SchemeStore(TaskStore):
    def __init__(self, root, presets, executor=None, timeout=1080, retention=86400,
                 *, lighting_capabilities=CLOSED, approved_language_operation=None, **kwargs):
        self.environments = {p['id']: copy.deepcopy(p) for p in presets}
        from light_console import EnvironmentLibrary
        self.environment_library=EnvironmentLibrary(Path(root).parent/'environments-v2',presets)
        self.environments.update(self.environment_library.environments)
        self.lighting_capabilities = copy.deepcopy(lighting_capabilities)
        self.approved_language_operation=approved_language_operation
        super().__init__(root, presets, executor, timeout, retention, **kwargs)
        # Restore submitted snapshots, not browser assertions or renamed presets.
        for folder in self.root.iterdir():
            if ID.fullmatch(folder.name) and not folder.is_symlink() and (folder / 'request.json').is_file():
                request = read(folder / 'request.json')
                for preset in request.get('presets', [request['preset']]):
                    if 'scheme' in preset:
                        self._restore_preset(preset)

    def _restore_preset(self, preset):
        env = self.environments.get(preset.get('carrierEnvironmentId',preset.get('environmentId')))
        if not env or any(preset.get(k) != env[k] for k in ('hdr', 'sha256', 'index')):
            raise ValueError('STORED_SCHEME_ENVIRONMENT_MISMATCH')
        scheme = preset['scheme']
        # Historical snapshots may be viewed even after an evidence policy closes
        # a level. This does NOT admit that level into new submissions.
        pair = [scheme['parameters']['offsetDeg'], scheme['parameters']['strength']]
        historic = {'revision': preset['capabilityRevision'],
                    'approvedVariants': {env['id']: [pair]}}
        normalized = normalize_scheme(scheme, self.environments, historic)
        binding={'planId':normalized['planId'],'version':normalized['version'],'recipeKey':normalized['recipeKey']}
        if 'languageProposal' in preset:binding['languageProposalId']=preset['languageProposal']['operationId']
        expected = identity(binding)
        if preset['id'] != expected or preset['recipeKey'] != normalized['recipeKey']:
            raise ValueError('STORED_SCHEME_IDENTITY_MISMATCH')
        self.presets[preset['id']] = copy.deepcopy(preset)

    def submit(self, data, metadata, mime, *, reserved_task_id=None):
        if 'lightingScheme' not in metadata:
            return super().submit(data, metadata, mime, reserved_task_id=reserved_task_id)  # old three-preset requests unchanged
        with self.mutex:
            try:
                scheme = normalize_scheme(metadata['lightingScheme'], self.environments,
                                          self.lighting_capabilities)
                if scheme['inputId'] != metadata.get('inputId'):
                    raise ValueError('SCHEME_INPUT_MISMATCH')
                if self.executor and not getattr(self.executor, 'supports_lighting_parameters', False):
                    if scheme['parameters'].get('schemaVersion')==2 or (scheme['parameters']['offsetDeg'], scheme['parameters']['strength']) != (0, 1):
                        raise ValueError('EXECUTOR_HAS_NO_PARAMETER_ADAPTER')
                is_v2=scheme['parameters'].get('schemaVersion')==2
                selected=self.environments.get(scheme['parameters']['environmentId'])
                env=selected if selected and selected.get('source',{}).get('kind')!='local-import' else self.environments['sunny']
                derived=self.environment_library.derived(scheme['parameters']) if is_v2 else None
                raw = copy.deepcopy(metadata['lightingScheme'])
                if is_v2:raw['parameters']=copy.deepcopy(scheme['parameters'])
                origin=None
                if 'languageProposalId' in metadata:
                    if self.approved_language_operation is None:raise ValueError('LANGUAGE_PROVENANCE_NOT_CONFIGURED')
                    try:origin=self.approved_language_operation(metadata['languageProposalId'],scheme['inputId'],raw['parameters'])
                    except Exception as error:raise ValueError('LANGUAGE_PROVENANCE_REJECTED') from error
                binding={'planId':scheme['planId'],'version':scheme['version'],'recipeKey':scheme['recipeKey']}
                if origin:binding['languageProposalId']=origin['operationId']
                preset = {**copy.deepcopy(env),
                    'id': identity(binding),
                    'name': scheme['name'], 'environmentId': env['id'], 'scheme': raw,
                    'recipeKey': scheme['recipeKey'], 'parameters': scheme['parameters'],
                    'capabilityRevision': scheme['parameters'].get('capabilityRevision','parameterized-engineering-v2')}
                if is_v2:
                    preset['carrierEnvironmentId']=env['id']
                    preset['sourceEnvironment']=selected
                    preset['environmentId']=scheme['parameters']['environmentId']
                    if derived is not None:
                        preset['derivedHdrSha256']=digest(derived)

                if origin:preset['languageProposal']=origin
                self.presets[preset['id']] = preset
                value = {k: v for k, v in metadata.items() if k != 'lightingScheme'}
                value.update(presetId=preset['id'], presetIds=[preset['id']])
            except (ValueError, KeyError, TypeError):
                raise JobError('INVALID_LIGHTING_SCHEME', '方案版本、输入关联或参数范围无效；未执行。', 422)
            return super().submit(data, value, mime, reserved_task_id=reserved_task_id)

    def capabilities(self):
        return {**super().capabilities(), 'maxSchemesPerSubmit': 1,
                'lightingParameters': bool(self.executor and getattr(self.executor, 'supports_lighting_parameters', False)),
                'schemeSchemaVersion': 1}

    def public(self, task):
        value = super().public(task)
        value['originalInput']={k:task['original'][k] for k in ('sha256','mime')}
        if 'scheme' in task['preset']:
            value['lightingScheme'] = copy.deepcopy(task['preset']['scheme'])
            value['recipeKey'] = task['preset']['recipeKey']
        if 'transferRecovery' in task:value['transferRecovery']=copy.deepcopy(task['transferRecovery'])
        return value

    def recover_transferred_result(self,task_id,recovery_run_id):
        """Explicit recovery of a completed transfer failure, never a timed-out model.

        Original deadline/events remain in immutable backups. No model is started,
        no inverse/source/hash check is weakened and no deadline is extended.
        """
        with self.mutex:
            if type(recovery_run_id) is not str or not ID.fullmatch(recovery_run_id):raise JobError('RECOVERY_INVALID','恢复身份无效。',422)
            folder=self.directory(task_id);task=read(folder/'task.json');event=read(folder/'execution.json')
            if (task['status']!='failed' or task.get('executionUncertain') or task.get('error',{}).get('code')!='EXECUTION_FAILED' or
                event.get('stage')!='transferring' or event.get('executionStopped') is not True):
                raise JobError('RECOVERY_NOT_ALLOWED','仅恢复已结束且仅取回失败的任务；超时/未知执行不反转。',409)
            root=Path(__file__).resolve().parents[1];run=root/'cloud-runs'/recovery_run_id
            release=read(run/'independent-stopped-release.json');beat=read(run/'heartbeat.json');binding=read(folder/'runtime-binding.json')
            proof=read(folder/'result-recovery.json');receipt=read(folder/'receipt.json');remote=proof['remoteExecution']
            if (release.get('independent_api') is not True or release.get('id')!=binding['resourceId'] or release.get('state')!='STOPPED' or
                release.get('instances')!=[] or beat.get('stopped_verified') is not True or beat.get('sleep_held') is not False or
                proof.get('recoveryGuardRunId')!=recovery_run_id or proof.get('sourceRunId')!=binding['guardRunId'] or
                (remote.get('taskId'),remote.get('nonce'),remote.get('status'),remote.get('executionStopped'))!=(task_id,task['nonce'],'succeeded',True) or
                receipt['finishedAt']>task['deadline'] or remote['observedAt']>task['deadline']):
                raise JobError('RECOVERY_PROOF_INVALID','当前独立停机、原完成窗口或实际生成归属证明不符。',422)
            result=self._check_result(folder,task,receipt)
            for name in ('task.json','execution.json'):
                target=folder/('transfer-failure-original-'+name);data=(folder/name).read_bytes()
                if target.exists() and target.read_bytes()!=data:raise JobError('RECOVERY_HISTORY_CHANGED','原失败记录变化；不覆盖。',409)
                if not target.exists():target.write_bytes(data)
            now=self.clock();recovery={'sourceRunId':binding['guardRunId'],'recoveryGuardRunId':recovery_run_id,
                'generationFinishedAt':receipt['finishedAt'],'recoveredAt':now,'originalDeadline':task['deadline'],
                'modelRerun':False,'receiptSha256':digest((folder/'receipt.json').read_bytes())}
            result['transferRecovery']=recovery
            task.update(status='succeeded',result=result,error=None,executionUncertain=False,expiresAt=now+self.retention,updatedAt=now,transferRecovery=recovery)
            task['presetResults'][task['preset']['id']].update(status='succeeded',result=result,error=None)
            atomic(folder/'task.json',task)
            atomic(folder/'execution.json',{'taskId':task_id,'nonce':task['nonce'],'status':'succeeded','stage':'validating','executionStopped':True,'observedAt':now,'transferRecovery':recovery})
            return self.public(task)

    def _check_result(self, folder, task, receipt):
        if 'scheme' in task['preset']:
            p = task['preset'];proof = receipt.get('lighting', {})
            if (proof.get('recipeKey') != p['recipeKey'] or proof.get('parameters') != p['parameters'] or
                    proof.get('adapterVersion') != task['runConfig'].get('lightingAdapterVersion')):
                raise ValueError('RESULT_LIGHTING_IDENTITY_MISMATCH')
            if proof.get('derivedHdrSha256')!=p.get('derivedHdrSha256'):raise ValueError('RESULT_DERIVED_HDR_MISMATCH')
            from light_console import preprocessing_parameters
            expected = preprocessing_parameters(p['parameters'])
            condition = proof.get('actualCondition', {})
            metadata = condition.get('metadata', {})
            if (condition.get('parameters') != expected or metadata.get('envmap_rot') != expected['envRot'] or
                    metadata.get('envmap_strength') != expected['strength'] or metadata.get('envmap_flip') is not True or
                    metadata.get('rotate_envlight') is not False):
                raise ValueError('RESULT_ACTUAL_HDR_PARAMETERS_MISMATCH')
            model = proof.get('actualModelCondition', {})
            if any(model.get(k, {}).get('shape') != [1,3,1,704,1280] for k in ('env_ldr','env_log','env_nrm')):
                raise ValueError('RESULT_ACTUAL_MODEL_CONDITION_MISSING')
        result = super()._check_result(folder, task, receipt)
        if 'scheme' in task['preset']:
            result['recipeKey'] = task['preset']['recipeKey']
            result['parameters'] = copy.deepcopy(task['preset']['parameters'])
            result['submittedPlan'] = {'planId':task['preset']['scheme']['planId'],
                                       'version':task['preset']['scheme']['version']}
            result['parameterValidation'] = 'actual helper parameters and model-entry tensors checked; not a physical-control guarantee'
            if 'languageProposal' in task['preset']:result['languageProposal']=copy.deepcopy(task['preset']['languageProposal'])
        return result
