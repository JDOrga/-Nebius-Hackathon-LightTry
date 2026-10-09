"""Reuse a documented historical check without rereading checkpoint contents.

This is an explicit speed/integrity tradeoff, NOT a checksum cache hit. The old
run did not record stat identities, so same-size edits/bitrot cannot be detected.
No network, download, model import, or cloud operation.

Extracted unchanged from the validated four-material fastpath reuse algorithm.
Runtime does not read that historical directory. References are explicitly
supplied through private local configuration and copied into the current bundle.
"""
import hashlib
import json
from pathlib import Path
import time


def validate_reference(current_manifest, historical_manifest, receipt, reference):
    current = json.loads(Path(current_manifest).read_bytes())['files']
    prior_bytes = Path(historical_manifest).read_bytes()
    prior = json.loads(prior_bytes)['files']
    reference = json.loads(Path(reference).read_bytes())
    keys = ('path', 'size', 'sha256', 'git_blob', 'md5')
    identities = lambda entries: [{key: entry.get(key) for key in keys} for entry in entries]
    if identities(current) != identities(prior):
        raise ValueError('HISTORICAL_AND_CURRENT_MODEL_IDENTITIES_DIFFER')
    if hashlib.sha256(prior_bytes).hexdigest() != reference['weights_manifest_sha256'] or hashlib.sha256(Path(receipt).read_bytes()).hexdigest() != reference['receipt_sha256']:
        raise ValueError('HISTORICAL_REFERENCE_HASH_MISMATCH')
    historical = json.loads(Path(receipt).read_bytes())['files']
    if [entry['path'] for entry in historical] != [entry['path'] for entry in prior] or not all(entry.get('verified') is True for entry in historical):
        raise ValueError('HISTORICAL_CONTENT_CHECK_REQUIRED')


def reuse_existing(directory, manifest_path, receipt_path, reference_path, deadline=None):
    start = time.perf_counter()
    start_ns = time.time_ns()
    manifest_bytes = Path(manifest_path).read_bytes()
    receipt_bytes = Path(receipt_path).read_bytes()
    manifest = json.loads(manifest_bytes)
    receipt = json.loads(receipt_bytes)
    reference = json.loads(Path(reference_path).read_text(encoding="utf-8"))
    if hashlib.sha256(manifest_bytes).hexdigest() != reference["weights_manifest_sha256"]:
        raise ValueError("WEIGHT_MANIFEST_DIFFERS_FROM_HISTORICAL_REFERENCE")
    if hashlib.sha256(receipt_bytes).hexdigest() != reference["receipt_sha256"]:
        raise ValueError("HISTORICAL_WEIGHT_RECEIPT_CHANGED")
    entries = manifest["files"]
    expected = [e["path"] for e in entries]
    historical = receipt["files"]
    if (len(set(expected)) != len(expected) or
            [e["path"] for e in historical] != expected or
            any(e.get("verified") is not True for e in historical)):
        raise ValueError("HISTORICAL_WEIGHT_CHECK_INCOMPLETE_OR_DIFFERENT")
    directory = Path(directory).resolve()
    records = []
    for entry in entries:
        if deadline is not None and time.time() >= deadline:
            raise TimeoutError("Fixed work deadline reached")
        rel = Path(entry["path"])
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("INVALID_CHECKPOINT_RELATIVE_PATH")
        path = directory / rel
        if not path.resolve().is_relative_to(directory) or not path.is_file():
            raise ValueError("EXISTING_WEIGHT_MISSING_OR_OUTSIDE_DIRECTORY: " + entry["path"])
        stat = path.stat()
        if stat.st_size != entry["size"]:
            raise ValueError("EXISTING_WEIGHT_SIZE_CHANGED: " + entry["path"])
        records.append({"path": entry["path"], "expected_bytes": entry["size"],
                        "present_bytes": stat.st_size, "mtime_ns_observed_now": stat.st_mtime_ns,
                        "prior_content_verified": True, "content_verified_this_run": False})
    return {"mode": "reuse_historical_without_content_scan", "start_epoch_ns": start_ns,
            "end_epoch_ns": time.time_ns(), "seconds": time.perf_counter() - start,
            "files": records, "all_present_expected_size": True,
            "all_verified": False, "content_verified_this_run": False,
            "checkpoint_content_bytes_read": 0, "new_downloads": False,
            "historical_run_id": reference["historical_run_id"],
            "historical_receipt_sha256": reference["receipt_sha256"],
            "limitation": "Historical content verification only. No historical stat identities: "
                          "current same-size corruption/replacement is not detected."}
