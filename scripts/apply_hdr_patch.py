"""Apply the prior patch only when all three target files match known bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, type=Path)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    repo = args.repo.resolve()
    manifest = json.loads((ROOT / "manifests/patch_manifest.json").read_text())
    if (repo / ".git").exists():
        commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        if commit != manifest["commit"]:
            raise ValueError("Repo commit is not the pinned version")
    else:
        raise ValueError("External repo must have Git provenance")
    actual = [digest(repo / f["path"]) for f in manifest["files"]]
    if actual == [f["after_sha256"] for f in manifest["files"]]:
        print(json.dumps({"state": "already_applied", "repo": str(repo)}))
        return
    if actual != [f["before_sha256"] for f in manifest["files"]]:
        raise ValueError("Target files contain unknown changes; refusing overwrite")
    patch = ROOT / "patches/replace_hdr_sampling.patch"
    if digest(patch) != manifest["patch_sha256"]:
        raise ValueError("Patch hash mismatch")
    subprocess.run(["git", "-C", str(repo), "apply", "--check", str(patch)], check=True)
    if args.apply:
        subprocess.run(["git", "-C", str(repo), "apply", str(patch)], check=True)
        if [digest(repo / f["path"]) for f in manifest["files"]] != [f["after_sha256"] for f in manifest["files"]]:
            raise RuntimeError("Post-apply hash mismatch")
    print(json.dumps({"state": "applied" if args.apply else "ready", "repo": str(repo)}))


if __name__ == "__main__":
    main()
