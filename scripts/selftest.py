"""Discover offline regressions; never install packages or initialize the cloud."""
import argparse
import ast
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def dependency_issues():
    issues = []
    for module, package in (('numpy', 'numpy'), ('PIL', 'Pillow'), ('yaml', 'PyYAML')):
        try:
            importlib.import_module(module)
        except (ImportError, OSError):
            issues.append('Missing or unusable offline dependency: ' + package)
    if os.name != 'nt':
        issues.append('Full offline suite requires Windows PowerShell 5.1')
    else:
        shell = Path(os.environ.get('SystemRoot', '')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        if not shell.is_file():
            issues.append('Windows PowerShell 5.1 is unavailable')
        if not shutil.which('ssh-keygen.exe'):
            issues.append('OpenSSH ssh-keygen.exe is unavailable (synthetic key tests only)')
    return issues


def discover_commands(root=ROOT):
    commands = []
    for folder in ('prototype', 'tests', 'project/tests'):
        for path in sorted((root / folder).glob('test_*.py')):
            # Existing standalone integration scripts and new unittest modules
            # are both discovered without a filename registry.
            try:
                tree = ast.parse(path.read_text(encoding='utf-8-sig'))
                uses_unittest = any(
                    (isinstance(node, ast.Import) and any(a.name == 'unittest' for a in node.names))
                    or (isinstance(node, ast.ImportFrom) and node.module == 'unittest')
                    for node in ast.walk(tree))
            except SyntaxError:
                uses_unittest = False
            argv = (['-m', 'unittest', 'discover', '-s', folder, '-p', path.name, '-v']
                    if uses_unittest else [path.relative_to(root).as_posix()])
            commands.append((folder.replace('/', '-') + '-' + path.stem, argv))
    return commands


def output_text(value):
    return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')


def run_group(name, argv, directory, timeout, python_executable=None):
    before = time.monotonic()
    row = {'name': name, 'command': argv, 'python_executable': str(python_executable or sys.executable), 'exit_code': None, 'status': 'failed'}
    try:
        result = subprocess.run([str(python_executable or sys.executable), '-B', *argv], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=timeout)
        row.update(exit_code=result.returncode, status='passed' if result.returncode == 0 else 'failed')
        log = result.stdout + result.stderr
    except subprocess.TimeoutExpired as error:
        row.update(status='timeout', timeout_seconds=timeout)
        log = output_text(error.stdout) + output_text(error.stderr) + '\nSELFTEST_GROUP_TIMEOUT\n'
    except OSError as error:
        row.update(status='error', error_type=type(error).__name__)
        log = str(error)
    row['seconds'] = round(time.monotonic() - before, 3)
    path = directory / (name + '.log')
    path.write_text(log, encoding='utf-8')
    row['log'] = str(path)
    return row


def main():
    # Reuse path-only local configuration; never install dependencies or read keys.
    configured_product = None
    configured = ROOT / '.local/studio.json'
    if configured.is_file():
        sys.path.insert(0, str(ROOT))
        from start import local_options
        _, paths, _ = local_options([])
        configured_product = paths.get('python')
        offline = paths.get('offline_python')
        if __name__ == '__main__' and offline and Path(offline).resolve() != Path(sys.executable).resolve():
            if not Path(offline).is_file(): raise FileNotFoundError('CONFIGURED_OFFLINE_PYTHON_MISSING')
            os.execv(offline, [offline, '-X', 'utf8', '-B', str(Path(__file__).resolve()), *sys.argv[1:]])
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=ROOT / '.local/selftest.json')
    parser.add_argument('--product-python', type=Path, default=configured_product,
                        help='Existing CPU product-test runtime; no automatic installation.')
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    report = {'offline': True, 'cloud_calls': 0, 'passed': False, 'status': 'checking_dependencies',
              'groups': [], 'issues': dependency_issues(),
              'optional_gpu_and_external_upstream_checks': 'see explicit unittest skips'}

    def save():
        temporary = args.out.with_name(args.out.name + '.tmp')
        temporary.write_text(json.dumps(report, indent=2), encoding='utf-8')
        temporary.replace(args.out)

    save()
    if report['issues']:
        report.update(status='dependency_failure',
                      setup_hint='Install requirements/offline.txt in your chosen virtual environment; no automatic installation')
        save()
        print(json.dumps(report))
        return 1
    commands = discover_commands()
    report.update(status='running', discovered_groups=len(commands))
    save()
    for name, argv in commands:
        runtime = args.product_python if name.startswith('project-tests-') else None
        row = run_group(name, argv, args.out.parent, timeout=240, python_executable=runtime)
        report['groups'].append(row)
        save()
        print(json.dumps(row), flush=True)
    report['passed'] = bool(commands) and all(row['status'] == 'passed' for row in report['groups'])
    report['status'] = 'passed' if report['passed'] else 'failed'
    save()
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
