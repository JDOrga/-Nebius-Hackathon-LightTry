"""Private single-workspace persistence. No browser credentials or model execution."""
from contextlib import contextmanager
import json
import os
import re
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from inference.images import decode, digest, MAX_BYTES, InputError
from inference.jobs import ID, JobError
from lighting import normalize_scheme, canonical

WIRE = ('schemaVersion', 'planId', 'version', 'name', 'parameters', 'inputId', 'parentVersion')
EXTRAS = ('recipeKey', 'provenance', 'importedResultSha256')


class Workspace:
    def __init__(self, root, environments, capabilities):
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError('ABSOLUTE_DATA_ROOT_REQUIRED')
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError('DATA_ROOT_SYMLINK_FORBIDDEN')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = self.root.resolve()
        self.environments, self.capabilities = environments, capabilities
        self.lock = threading.RLock()
        for name in ('photos', 'tasks', 'environments-v2', 'inverse-cache', 'logs', 'tmp'):
            if (self.root / name).is_symlink():
                raise ValueError('PERSISTENT_PATH_SYMLINK_FORBIDDEN')
            (self.root / name).mkdir(exist_ok=True, mode=0o700)
        if (self.root / 'workspace.sqlite3').is_symlink():
            raise ValueError('DATABASE_SYMLINK_FORBIDDEN')
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS photos (
                    id TEXT PRIMARY KEY, sha TEXT NOT NULL, mime TEXT NOT NULL,
                    name TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS schemes (
                    plan_id TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL,
                    saved_at REAL NOT NULL, PRIMARY KEY(plan_id, version));
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / 'workspace.sqlite3', timeout=10)
        (self.root / 'workspace.sqlite3').chmod(0o600)
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_photo(self, input_id, name, payload, mime):
        if not isinstance(input_id, str) or not ID.fullmatch(input_id):
            raise JobError('INPUT_ID_REQUIRED', '照片身份无效。', 422)
        if not isinstance(name, str) or not 1 <= len(name) <= 200 or any(ord(c) < 32 for c in name):
            raise JobError('PHOTO_NAME_INVALID', '照片名称无效。', 422)
        if mime not in ('image/png', 'image/jpeg', 'image/webp') or not 0 < len(payload) <= MAX_BYTES:
            raise JobError('INVALID_IMAGE', '照片格式或大小无效。', 422)
        try:
            rgb, _, meta = decode(payload, mime)
        except InputError as error:
            raise JobError('INVALID_IMAGE', str(error), 422) from error
        sha = meta['sha256']
        with self.lock, self.connect() as db:
            old = db.execute('SELECT sha FROM photos WHERE id=?', (input_id,)).fetchone()
            if old and old[0] != sha:
                raise JobError('PHOTO_ID_CONFLICT', '照片身份已绑定其他字节，不覆盖。', 409)
            target = self.root / 'photos' / sha
            if target.is_symlink():
                raise JobError('UNSAFE_PHOTO_PATH', '照片路径无效。', 422)
            if target.exists():
                if digest(target.read_bytes()) != sha:
                    raise JobError('PHOTO_CHANGED', '照片字节校验失败。', 409)
            else:
                tmp = target.with_name(sha + '.' + uuid.uuid4().hex + '.tmp')
                try:
                    with tmp.open('xb') as stream:
                        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
                    os.replace(tmp, target)
                finally:
                    tmp.unlink(missing_ok=True)
            db.execute('INSERT OR IGNORE INTO photos VALUES (?,?,?,?,?,?)',
                       (input_id, sha, mime, name, *rgb.size))
        return self.photo(input_id)[0]

    def photo(self, input_id):
        if not isinstance(input_id, str) or not ID.fullmatch(input_id):
            raise JobError('PHOTO_NOT_FOUND', '照片不存在。', 404)
        with self.connect() as db:
            row = db.execute('SELECT id,sha,mime,name,width,height FROM photos WHERE id=?', (input_id,)).fetchone()
        if row is None:
            raise JobError('PHOTO_NOT_FOUND', '照片不存在。', 404)
        pid, sha, mime, name, width, height = row
        path = self.root / 'photos' / sha
        if path.is_symlink() or not path.is_file():
            raise JobError('PHOTO_CHANGED', '照片文件缺失。', 409)
        payload = path.read_bytes()
        if digest(payload) != sha:
            raise JobError('PHOTO_CHANGED', '照片字节校验失败。', 409)
        return {'id': pid, 'name': name, 'width': width, 'height': height,
                'originalSha': sha, 'url': '/api/photos/' + pid,
                'originalUrl': '/api/photos/' + pid, 'needsFile': True}, payload, mime

    def library(self):
        with self.connect() as db:
            schemes = [json.loads(r[0]) for r in db.execute('SELECT body FROM schemes ORDER BY saved_at,plan_id,version')]
            ids = [r[0] for r in db.execute('SELECT id FROM photos')]
        return {'schemaVersion': 1, 'schemes': schemes, 'photos': [self.photo(i)[0] for i in ids]}

    def save_library(self, value):
        if not isinstance(value, dict) or set(value) != {'schemaVersion', 'schemes'} or value['schemaVersion'] != 1:
            raise JobError('LIBRARY_INVALID', '需要 v1 方案库 JSON。', 422)
        if not isinstance(value['schemes'], list) or len(value['schemes']) > 200:
            raise JobError('LIBRARY_LIMIT', '方案库最多 200 个版本。', 422)
        bodies = []
        try:
            for scheme in value['schemes']:
                if not isinstance(scheme, dict) or set(scheme) - set(WIRE + EXTRAS):
                    raise ValueError('SCHEME_FIELDS_INVALID')
                normalize_scheme({k: scheme[k] for k in WIRE}, self.environments, self.capabilities)
                for field in ('recipeKey', 'importedResultSha256'):
                    if field in scheme and (type(scheme[field]) is not str or not re.fullmatch('[a-f0-9]{64}', scheme[field])):
                        raise ValueError('PROVENANCE_HASH_INVALID')
                if 'provenance' in scheme:
                    provenance = scheme['provenance']
                    if (type(provenance) is not dict or set(provenance) - {'taskId','caseId','cohort'} or
                            any(type(v) is not str or not 1 <= len(v) <= 80 or
                                not re.fullmatch('[a-zA-Z0-9_-]+', v) for v in provenance.values())):
                        raise ValueError('PROVENANCE_FIELDS_INVALID')
                bodies.append((scheme['planId'], scheme['version'], canonical(scheme)))
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            raise JobError('LIBRARY_INVALID', '方案字段、关联、版本或环境无效；未保存。', 422) from error
        with self.lock, self.connect() as db:
            for pid, ver, body in bodies:
                previous = db.execute('SELECT body FROM schemes WHERE plan_id=? AND version=?', (pid, ver)).fetchone()
                if previous and previous[0] != body:
                    raise JobError('VERSION_CONFLICT', '同一方案版本内容冲突；请创建新版本，不覆盖。', 409)
                db.execute('INSERT OR IGNORE INTO schemes VALUES (?,?,?,?)', (pid, ver, body, time.time()))
            if db.execute('SELECT count(*) FROM schemes').fetchone()[0] > 200:
                raise JobError('LIBRARY_LIMIT', '服务方案库已到 200 个版本上限。', 422)
        return self.library()
