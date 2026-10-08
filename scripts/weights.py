"""Anonymous, bounded-memory, restartable downloads from pinned official URLs.

Default command is plan. Download requires an externally confirmed model license
and an absolute UTC deadline. No credentials, login, HF cache, or model imports.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CHUNK = 8 * 1024 * 1024


def parse_utc(value):
    # DateTimeOffset 'o' has seven fractional digits. Python 3.10 accepts 3/6.
    # Truncate sub-microsecond precision conservatively; wire JSON stays exact.
    normalized = re.sub(r'\.(\d+)(?=Z|[+-]\d\d:\d\d|$)',
                        lambda m: '.' + m.group(1)[:6].ljust(6, '0'), value)
    deadline = dt.datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if deadline.utcoffset() != dt.timedelta(0):
        raise ValueError("deadline must explicitly be UTC")
    return deadline


def parse_deadline(value):
    deadline = parse_utc(value)
    return deadline.timestamp()


def check_time(deadline):
    if deadline is not None and time.time() >= deadline:
        raise TimeoutError("Fixed execution deadline reached; partials retained")


def verify(path, entry, deadline=None):
    if not path.is_file() or path.stat().st_size != entry["size"]:
        return False
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    blob = hashlib.sha1(b"blob " + str(entry["size"]).encode() + b"\0")
    with path.open("rb") as source:
        while True:
            check_time(deadline)
            block = source.read(CHUNK)
            if not block:
                break
            sha.update(block)
            md5.update(block)
            blob.update(block)
    expected = [(entry.get("sha256"), sha.hexdigest()),
                (entry.get("git_blob"), blob.hexdigest()),
                (entry.get("md5"), md5.hexdigest())]
    return any(want for want, _ in expected) and all(not want or want == got for want, got in expected)


def transfer(path, entry, deadline, opener=urllib.request.urlopen):
    """Resume one partial; refuse ignored/wrong Range responses without truncating."""
    part = path.with_name(path.name + ".part")
    offset = part.stat().st_size if part.exists() else 0
    if offset > entry["size"]:
        raise ValueError("Oversized partial; retain for inspection: " + str(part))
    if offset == entry["size"]:
        if not verify(part, entry, deadline):
            raise ValueError("Complete partial checksum mismatch; retained: " + str(part))
        part.rename(path)
        return
    check_time(deadline)
    headers = {"User-Agent": "Nebius-Cosmos-preparation/1.0", "Accept-Encoding": "identity"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(entry["url"], headers=headers)
    timeout = max(0.1, min(30, deadline - time.time()))
    with opener(request, timeout=timeout) as response:
        if offset:
            content_range = response.headers.get("Content-Range", "")
            if response.status != 206 or not content_range.startswith(f"bytes {offset}-") or not content_range.endswith(f'/{entry["size"]}'):
                raise ValueError("Server did not honor exact resume Range; partial retained")
        elif response.status != 200:
            raise ValueError("Initial response must be HTTP 200")
        with part.open("ab" if part.exists() else "xb") as target:
            while offset < entry["size"]:
                check_time(deadline)
                block = response.read(min(CHUNK, entry["size"] - offset))
                if not block:
                    raise OSError("Truncated response; partial retained for resume")
                target.write(block)
                offset += len(block)
            target.flush()
            os.fsync(target.fileno())
    if not verify(part, entry, deadline):
        raise ValueError("Downloaded file checksum mismatch; partial retained")
    part.rename(path)


def plan(directory, manifest):
    probe = directory
    while not probe.exists():
        probe = probe.parent
    remaining = 0
    files = []
    for entry in manifest["files"]:
        path = directory / entry["path"]
        part = path.with_name(path.name + ".part")
        saved = path.stat().st_size if path.exists() else (part.stat().st_size if part.exists() else 0)
        remaining += max(0, entry["size"] - saved)
        files.append({"path": entry["path"], "expected_bytes": entry["size"], "present_bytes": saved})
    free = shutil.disk_usage(probe).free
    # Upstream recommends >=70 GB; use 70 GiB and reserve 10 GiB beyond missing files.
    required = max(70 * 1024**3 if remaining else 10 * 1024**3, remaining + 10 * 1024**3)
    return {"checkpoint_dir": str(directory), "total_bytes": manifest["total_bytes"],
            "remaining_bytes": remaining, "free_bytes": free, "required_free_bytes": required,
            "space_ok": free >= required, "files": files, "content_verified": False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["plan", "verify", "download"], nargs="?", default="plan")
    p.add_argument("--checkpoint-dir", type=Path, default=ROOT / "checkpoints")
    p.add_argument("--manifest", type=Path, default=ROOT / "manifests/weights_manifest.json")
    p.add_argument("--deadline-utc")
    p.add_argument("--license-ack", choices=["nvidia-open-model-license"])
    args = p.parse_args()
    manifest = json.loads(args.manifest.read_text())
    directory = args.checkpoint_dir.resolve()
    deadline = parse_deadline(args.deadline_utc) if args.deadline_utc else None
    if args.action == "plan":
        print(json.dumps(plan(directory, manifest), indent=2))
        return 0
    if args.action == "verify":
        checks = [{"path": entry["path"], "valid": verify(directory / entry["path"], entry, deadline)}
                  for entry in manifest["files"]]
        print(json.dumps({"files": checks, "all_verified": all(f["valid"] for f in checks)}, indent=2))
        return 0 if all(f["valid"] for f in checks) else 1
    if not args.license_ack or deadline is None:
        p.error("download requires confirmed --license-ack and --deadline-utc")
    check_time(deadline)
    state = plan(directory, manifest)
    if not state["space_ok"]:
        raise OSError("Insufficient free disk space: " + json.dumps(state))
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".cosmos-download-lock"
    lock.mkdir()  # No concurrent download; never remove another process's lock.
    (lock / "owner.json").write_text(json.dumps({"pid": os.getpid(), "deadline_utc": args.deadline_utc}))
    try:
        for entry in manifest["files"]:
            path = directory / entry["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                if not verify(path, entry, deadline):
                    raise ValueError("Existing final file is invalid; refusing overwrite: " + str(path))
                print(json.dumps({"path": entry["path"], "state": "verified_existing"}), flush=True)
                continue
            for attempt in range(3):
                try:
                    transfer(path, entry, deadline)
                    break
                except urllib.error.HTTPError as exc:
                    # Auth/gating errors require human attention, never login automatically.
                    if exc.code in (401, 403) or attempt == 2:
                        raise RuntimeError(f"HTTP {exc.code} for {entry['path']}; no authentication attempted") from None
                except (OSError, urllib.error.URLError):
                    check_time(deadline)
                    if attempt == 2:
                        raise RuntimeError("Download interrupted: " + entry["path"]) from None
            print(json.dumps({"path": entry["path"], "state": "downloaded_and_verified", "bytes": entry["size"]}), flush=True)
    finally:
        (lock / "owner.json").unlink()
        lock.rmdir()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
