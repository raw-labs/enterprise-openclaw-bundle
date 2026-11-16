#!/usr/bin/env python3
"""Fetch or verify a locked GitHub release before running any bundled code."""

import argparse
import hashlib
import json
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_lock(path):
    lock = json.loads(path.read_text())
    require(isinstance(lock, dict), "bundle lock must be a JSON object")
    for field, pattern in {
        "repository": r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*",
        "tag": r"v\d+\.\d+\.\d+(?:-[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*)?",
        "commit": r"[a-f0-9]{40}",
        "sha256": r"[a-f0-9]{64}",
    }.items():
        require(isinstance(lock.get(field), str) and re.fullmatch(pattern, lock[field]),
                f"invalid lock field: {field}")
    require(lock.get("archive") == "bundle.tar.gz", "invalid archive asset name")
    return lock


def github(path):
    return json.loads(subprocess.check_output(["gh", "api", "--hostname", "github.com", path]))


def remote_asset(lock):
    repo, tag = lock["repository"], lock["tag"]
    release = github(f"repos/{repo}/releases/tags/{tag}")
    require(release["tag_name"] == tag and release["draft"] is False,
            "expected a published release with the locked tag")
    ref = github(f"repos/{repo}/git/ref/tags/{tag}")["object"]
    for _ in range(8):
        if ref["type"] != "tag":
            break
        require(re.fullmatch(r"[a-f0-9]{40}", ref["sha"]), "invalid Git tag object")
        ref = github(f"repos/{repo}/git/tags/{ref['sha']}")["object"]
    require(ref["type"] == "commit" and ref["sha"] == lock["commit"],
            "published tag does not resolve to the locked commit")
    assets = [a for a in release["assets"] if a["name"] == lock["archive"]]
    require(len(assets) == 1 and assets[0].get("digest") == f"sha256:{lock['sha256']}",
            "published archive digest does not match lock")
    asset_id = assets[0]["id"]
    require(type(asset_id) is int and asset_id > 0, "invalid release asset ID")
    return f"repos/{repo}/releases/assets/{asset_id}"


def inventory(tar, tag):
    entries = {}
    for member in tar.getmembers():
        path = PurePosixPath(member.name)
        require(path.parts and path.parts[0] == tag and ".." not in path.parts
                and member.name == path.as_posix() and "\\" not in member.name
                and (member.isfile() or member.isdir()), "unsafe archive entry")
        require(path not in entries, "duplicate archive entry")
        entries[path] = member
    files = {p for p, m in entries.items() if m.isfile()}
    directories = {parent for path in entries for parent in path.parents if parent.parts}
    directories.update(p for p, m in entries.items() if m.isdir())
    require(not files & directories and PurePosixPath(tag) in directories,
            "invalid archive directory layout")
    require({PurePosixPath(tag, p) for p in (
        "bin/prepare", "metadata/release.json", "metadata/manifest.json",
    )} <= files, "archive is missing bundle tooling or metadata")
    return entries, files, directories


def inspect(entry, lock, *, extract=False):
    archive = entry / lock["archive"]
    require(entry.is_dir() and not entry.is_symlink(), "invalid cache entry")
    require(archive.is_file() and not archive.is_symlink(), "cached archive is missing or linked")
    with archive.open("rb") as stream:
        require(hashlib.file_digest(stream, "sha256").hexdigest() == lock["sha256"],
                "archive checksum mismatch")
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:gz") as tar:
            entries, files, directories = inventory(tar, lock["tag"])
            if extract:
                tar.extractall(entry, filter="data")
            for name in sorted(directories, key=lambda p: len(p.parts)):
                require(stat.S_ISDIR((entry / name).lstat().st_mode),
                        f"expected a real bundle directory: {name}")
            root = entry / lock["tag"]
            require({p.relative_to(entry).as_posix() for p in (root, *root.rglob("*"))}
                    == {p.as_posix() for p in files | directories},
                    "cached bundle has missing or unexpected entries")
            for name in sorted(files):
                path = entry / name
                mode = path.lstat().st_mode
                member = entries[name]
                require(stat.S_ISREG(mode) and mode & 0o7111 == member.mode & 0o111,
                        f"cached bundle file type or executable mode differs: {name}")
                with path.open("rb") as actual, tar.extractfile(member) as expected:
                    require(hashlib.file_digest(actual, "sha256").digest()
                            == hashlib.file_digest(expected, "sha256").digest(),
                            f"cached bundle differs from archive: {name}")
    release = json.loads((root / "metadata/release.json").read_text())
    require(release["id"] == lock["tag"], "archive release ID does not match the lock")
    return root


def fetch(args):
    lock = read_lock(args.lock)
    cache = args.cache.absolute()
    entry = cache / lock["tag"]
    require(not cache.is_symlink(), "cache directory must not be a symbolic link")
    if cache.exists():
        require(cache.is_dir() and not cache.stat().st_mode & 0o022,
                "cache directory must not be writable by other users")
    if args.command == "verify":
        return inspect(entry, lock)
    asset = remote_asset(lock) if args.archive is None else None
    if entry.exists() or entry.is_symlink():
        if args.archive is not None:
            with args.archive.open("rb") as stream:
                require(hashlib.file_digest(stream, "sha256").hexdigest() == lock["sha256"],
                        "supplied archive checksum mismatch")
        return inspect(entry, lock)
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temporary:
        stage = Path(temporary) / "entry"
        stage.mkdir(mode=0o700)
        archive = stage / lock["archive"]
        if asset:
            with archive.open("xb") as output:
                subprocess.run(
                    ["gh", "api", "--hostname", "github.com", "-H",
                     "Accept: application/octet-stream", asset],
                    stdout=output, check=True,
                )
        else:
            shutil.copyfile(args.archive, archive)
        inspect(stage, lock, extract=True)
        if entry.exists() or entry.is_symlink():
            return inspect(entry, lock)
        stage.rename(entry)
    return entry / lock["tag"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fetch", "verify"))
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--archive", type=Path, help="Use a local archive; verify by locked hash, offline")
    args = parser.parse_args()
    if args.command == "verify" and args.archive:
        parser.error("--archive is only accepted by fetch")
    try:
        print(fetch(args))
    except (ValueError, KeyError, TypeError, OSError, tarfile.TarError, subprocess.CalledProcessError) as error:
        sys.exit(f"fetch: {error}")


if __name__ == "__main__":
    main()
