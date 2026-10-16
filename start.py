"""Single local launch; configuration contains paths only, paid services stay opt-in."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
FIELDS = {'python', 'offline_python', 'assets_dir', 'tasks_dir', 'evidence_config', 'accepted_packages', 'inverse_cache_dir','local_cpu_config'}

def local_options(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--local-config', type=Path, default=ROOT/'.local/studio.json')
    parser.add_argument('--paths', action='store_true')
    options, remaining = parser.parse_known_args(argv)
    if not options.local_config.is_file() and any(a == '--local-config' or a.startswith('--local-config=') for a in argv):
        raise ValueError('EXPLICIT_LOCAL_CONFIG_MISSING')
    cfg = json.loads(options.local_config.read_text(encoding='utf-8-sig')) if options.local_config.is_file() else {}
    if not isinstance(cfg, dict) or set(cfg) - FIELDS:
        raise ValueError('LOCAL_CONFIG_PATH_FIELDS_ONLY')
    for name, value in cfg.items():
        if name == 'accepted_packages':
            if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
                raise ValueError('LOCAL_CONFIG_PATH_LIST_REQUIRED')
        elif not isinstance(value, str) or not value:
            raise ValueError('LOCAL_CONFIG_PATH_STRING_REQUIRED')
    def path(value):
        p = Path(value)
        return str((p if p.is_absolute() else ROOT/p).resolve())
    effective = {'assets_dir': path(cfg.get('assets_dir', 'project/demo-assets')),
                 'tasks_dir': path(cfg.get('tasks_dir', '.local/state/tasks')),
                 'inverse_cache_dir': path(cfg.get('inverse_cache_dir', '.local/state/inverse-cache')),
                 'accepted_packages': [path(p) for p in cfg.get('accepted_packages', [])]}
    for name in ('python', 'offline_python', 'evidence_config','local_cpu_config'):
        if name in cfg: effective[name] = path(cfg[name])
    return options, effective, remaining

def main():
    if '--model-phase' in sys.argv[1:]:
        sys.path.insert(0,str(ROOT/'project'))
        from resident_model import main as serve_phase
        return serve_phase(sys.argv[1:])
    if any(a in sys.argv[1:] for a in ('--worker','--guard','--deadman')):
        sys.path.insert(0, str(ROOT/'project'))
        from guard_runtime import main as serve_runtime
        return serve_runtime(sys.argv[1:])
    # Service mode is explicit and never reads machine-local Windows configuration.
    if '--service' in sys.argv[1:]:
        sys.path.insert(0, str(ROOT/'project'))
        from service import main as serve_service
        return serve_service([a for a in sys.argv[1:] if a != '--service'])
    options, cfg, remaining = local_options(sys.argv[1:])
    if options.paths:
        print(json.dumps({'paths':cfg, 'paid_defaults':False}, ensure_ascii=False, indent=2))
        return
    runtime = cfg.get('python')
    if runtime and Path(sys.executable).resolve() != Path(runtime):
        if not Path(runtime).is_file(): raise FileNotFoundError('CONFIGURED_PYTHON_MISSING')
        os.execv(runtime, [runtime, '-X', 'utf8', '-B', str(Path(__file__).resolve()), *sys.argv[1:]])
    os.environ['LIGHTTRY_INVERSE_CACHE'] = cfg['inverse_cache_dir']
    sys.path.insert(0, str(ROOT/'project'))
    if cfg.get('local_cpu_config'):
        if remaining:raise ValueError('AUTHENTICATED_LOCAL_PROFILE_OWNS_LISTEN_AND_RUNTIME_OPTIONS')
        from local_cpu import main as serve_local_cpu
        return serve_local_cpu(cfg)
    from studio import main as serve
    args = ['--assets-dir', cfg['assets_dir'], '--tasks-dir', cfg['tasks_dir']]
    if cfg.get('evidence_config'): args += ['--evidence-config', cfg['evidence_config']]
    for package in cfg['accepted_packages']: args += ['--accepted-package', package]
    sys.argv = [sys.argv[0], *args, *remaining]
    serve()

if __name__ == '__main__': main()
