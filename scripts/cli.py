#!/usr/bin/env python3
"""Build unchanged OCC binaries from the resolved source; record exact outputs."""

import argparse
import json
import os
import platform
import subprocess
from pathlib import Path

from bundle import verify_source
from common import digest, load, read_release, require, run, save

PLATFORMS = [
    (os_name, arch) for os_name in ("darwin", "linux") for arch in ("amd64", "arm64")
]
GO_VERSION = "go1.27.1"


def build(args):
    selection = Path(args.selection).resolve()
    release = read_release(selection)
    source = Path(args.source).resolve()
    verify_source(release, selection, source)
    # Resolve an auto-selected toolchain once, then prohibit further toolchain switching.
    go = (
        Path(subprocess.check_output(["go", "env", "GOROOT"], text=True).strip())
        / "bin/go"
    )
    require(
        subprocess.check_output([go, "env", "GOVERSION"], text=True).strip()
        == GO_VERSION,
        "use the pinned Go toolchain",
    )
    out = Path(args.output).resolve()
    require(not out.exists(), "CLI output exists")
    out.mkdir(parents=True)
    version = "v" + load(source / "package.json")["version"]
    env = dict(os.environ, CGO_ENABLED="0", GOTOOLCHAIN="local")
    result = subprocess.check_output(
        [go, "test", "-count=1", "-json", "./cmd/occ", "./internal/occcli"],
        cwd=source,
        env=env,
        text=True,
    )
    events = [json.loads(line) for line in result.splitlines()]
    counts = {
        action: sum(e["Action"] == action and "Test" in e for e in events)
        for action in ("pass", "fail", "skip")
    }
    require(
        counts["pass"] > 0 and counts["fail"] == counts["skip"] == 0,
        "CLI tests must pass without skips",
    )
    records = {}
    for os_name, arch in PLATFORMS:
        name = f"occ-{os_name}-{arch}"
        binary = out / name
        run(
            [
                go,
                "build",
                "-trimpath",
                "-buildvcs=false",
                "-ldflags",
                f"-s -w -X github.com/openclaw/openclaw-enterprise/internal/occcli.Version={version}",
                "-o",
                binary,
                "./cmd/occ",
            ],
            cwd=source,
            env=dict(env, GOOS=os_name, GOARCH=arch),
        )
        binary.chmod(0o755)
        info = subprocess.check_output([go, "version", "-m", binary], text=True)
        require(
            f"GOOS={os_name}" in info
            and f"GOARCH={arch}" in info
            and "CGO_ENABLED=0" in info,
            "CLI platform metadata mismatch",
        )
        records[name] = {
            "sha256": digest(binary.read_bytes()),
            "os": os_name,
            "architecture": arch,
        }
    metadata = {
        "oceCommit": release["sources"]["oce"]["commit"],
        "sourceInventorySha256": release["sources"]["oce"]["filesSha256"],
        "version": version,
        "goVersion": GO_VERSION,
        "tests": counts,
        "binaries": records,
    }
    save(out / "cli.json", metadata)
    check(out)
    verify_source(release, selection, source)


def check(directory):
    directory = Path(directory)
    meta = load(directory / "cli.json")
    require(
        set(meta["binaries"]) == {f"occ-{o}-{a}" for o, a in PLATFORMS},
        "all four CLI platforms required",
    )
    for name, info in meta["binaries"].items():
        require(
            digest((directory / name).read_bytes()) == info["sha256"],
            "CLI integrity mismatch",
        )
    native_os = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system())
    native_arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}.get(
        platform.machine()
    )
    require(native_os and native_arch, "unsupported operator platform")
    binary = directory / f"occ-{native_os}-{native_arch}"
    require(
        subprocess.check_output([binary, "--version"], text=True).strip()
        == "occ " + meta["version"],
        "CLI version mismatch",
    )
    require(
        "Manage OpenClaw Control Plane"
        in subprocess.check_output([binary, "--help"], text=True),
        "CLI help contract changed",
    )
    print(
        f"Verified unchanged OCC CLI on {native_os}/{native_arch}; other platform binaries hash-checked"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("build")
    for field in ("selection", "source", "output"):
        p.add_argument("--" + field, required=True)
    p = commands.add_parser("check")
    p.add_argument("--directory", required=True)
    options = parser.parse_args()
    if options.command == "build":
        build(options)
    else:
        check(options.directory)
