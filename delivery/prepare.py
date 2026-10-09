#!/usr/bin/env python3
"""Verify a bundle or prepare release-bound inputs for OCE and Helm."""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from integrity import (
    IMAGE,
    ROLES,
    digest,
    helm_values,
    load,
    require,
    save,
    verify_files,
)

ROOT = Path(__file__).resolve().parents[1]


def artifact():
    verify_files(ROOT, load(ROOT / "manifest.json"))
    return load(ROOT / "release.json")


def selected_images(release, mapping):
    refs = {role: release["images"][role]["reference"] for role in ROLES}
    require(
        all(IMAGE.fullmatch(ref or "") for ref in refs.values()),
        "release has no complete shipping image selection",
    )
    if mapping:
        mirrors = load(mapping)
        require(
            set(mirrors) == set(ROLES), "mirror map must contain exactly three roles"
        )
        for role, ref in mirrors.items():
            require(
                IMAGE.fullmatch(ref) and ref.split("@")[1] == refs[role].split("@")[1],
                f"{role} mirror digest mismatch",
            )
        refs = mirrors
    return refs


def render(args, release, admit=True):
    require(
        not admit or release["qualification"]["status"] == "native-verified",
        "candidate cannot be installed through bundle tooling",
    )
    require(
        not admit or release["distribution"].get("published") is True,
        "unpublished verification artifact cannot be installed",
    )
    out = Path(args.output).resolve()
    require(not out.exists(), "render output exists; use a new directory")
    site = load(args.input)
    refs = selected_images(release, args.mirrors)
    cp, runtime = site["controlPlane"], site["runtime"]
    architecture = args.architecture
    require(
        architecture in release["architectures"], "select a released --architecture"
    )
    selector = runtime.setdefault("nodeSelector", {})
    arch = architecture.split("/")[1]
    require(
        selector.get("kubernetes.io/arch", arch) == arch,
        "runtime node selector architecture mismatch",
    )
    selector["kubernetes.io/arch"] = arch
    for obj, key, role in (
        (cp, "controllerImage", "controller"),
        (runtime, "image", "runtime"),
    ):
        require(
            key not in obj or obj[key] == refs[role],
            f"{role} installation/release mismatch",
        )
        obj[key] = refs[role]
    repository = site.get("repository", {})
    if repository.get("enabled"):
        require(
            "image" not in repository
            or repository["image"] == refs["repositoryCredentials"],
            "repository installation/release mismatch",
        )
        repository["image"] = refs["repositoryCredentials"]
    if args.profile == "codex":
        site.setdefault("codex", {}).setdefault("modelDiscoveryCidrs", [])
        policy = release["seccomp"]["profiles"][architecture]
        expected = "openclaw/codex-" + policy["sha256"] + ".json"
        require(
            "codexSeccompProfile" not in runtime
            or runtime["codexSeccompProfile"] == expected,
            "seccomp/release mismatch",
        )
        runtime["codexSeccompProfile"] = expected
    out.mkdir(parents=True, mode=0o700)
    with tempfile.TemporaryDirectory() as temporary:
        effective = Path(temporary) / "input.json"
        save(effective, site)
        subprocess.run(
            [
                "node",
                ROOT / "upstream/scripts/render-installation-profile.mjs",
                "--profile",
                args.profile,
                "--profile-file",
                ROOT / release["profiles"][args.profile],
                "--input",
                effective,
                "--out-dir",
                out,
            ],
            check=True,
            stdout=subprocess.PIPE,
        )
    save(
        out / "selection.json",
        {
            "releaseId": release["id"],
            "images": refs,
            "profile": args.profile,
            "architecture": architecture,
            "namespace": cp["namespace"],
            "releaseName": cp["releaseName"],
        },
    )
    check(argparse.Namespace(directory=out), release)
    print(
        f"Prepared {out}. Review preflight.json and rendered.yaml; follow INSTALL.md."
    )


def check(args, release):
    out = Path(args.directory).resolve()
    selection = load(out / "selection.json")
    require(selection["releaseId"] == release["id"], "rendered release mismatch")
    require(set(selection["images"]) == set(ROLES), "rendered image roles mismatch")
    refs = selected_images(release, None)
    for role, ref in selection["images"].items():
        require(
            IMAGE.fullmatch(ref) and ref.split("@")[1] == refs[role].split("@")[1],
            "rendered digest mismatch",
        )
    values = helm_values(out / "values.yaml")
    installation = (out / "installation.yaml").read_bytes()
    config = helm_values(out / "installation.yaml")
    compute = config["drivers"]["compute"]["configuration"]
    require(
        values["images"]["controller"] == selection["images"]["controller"],
        "rendered controller mismatch",
    )
    require(
        all(
            compute["images"][role] == selection["images"]["runtime"]
            for role in ("gateway", "agent")
        ),
        "rendered runtime mismatch",
    )
    require(
        compute["images"]["requireImmutableDigest"] is True,
        "immutable runtime selection required",
    )
    architecture = selection["architecture"]
    require(architecture in release["architectures"], "rendered architecture mismatch")
    require(
        compute["runtime"]["nodeSelector"]["kubernetes.io/arch"]
        == architecture.split("/")[1],
        "rendered architecture selector mismatch",
    )
    profile = selection["profile"]
    require(profile in release["profiles"], "rendered profile mismatch")
    require(
        config["drivers"]["plugin"]
        == load(ROOT / release["profiles"][profile])["installation"]["drivers"][
            "plugin"
        ],
        "rendered profile selection mismatch",
    )
    if profile == "codex":
        expected = (
            "openclaw/codex-"
            + release["seccomp"]["profiles"][architecture]["sha256"]
            + ".json"
        )
        require(
            compute["runtime"]["codexSeccompProfile"] == expected,
            "rendered confinement mismatch",
        )
    if values.get("repositoryCredentials", {}).get("enabled"):
        require(
            values["repositoryCredentials"]["image"]
            == selection["images"]["repositoryCredentials"],
            "rendered repository service mismatch",
        )
    require(
        values["controlPlane"]["installationChecksum"] == digest(installation),
        "installation/Helm checksum mismatch",
    )
    require(load(out / "preflight.json")["ok"], "upstream profile preflight failed")
    chart = ROOT / release["chart"]["artifact"]
    subprocess.run(
        ["helm", "lint", chart, "-f", out / "values.yaml"],
        check=True,
        stdout=subprocess.PIPE,
    )
    rendered = subprocess.check_output(
        [
            "helm",
            "template",
            selection["releaseName"],
            str(chart),
            "--namespace",
            selection["namespace"],
            "-f",
            str(out / "values.yaml"),
        ]
    )
    (out / "rendered.yaml").write_bytes(rendered)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify")
    render_parser = commands.add_parser("render")
    render_parser.add_argument("--input", required=True)
    render_parser.add_argument(
        "--profile", choices=("openclaw", "codex"), required=True
    )
    render_parser.add_argument(
        "--architecture", choices=("linux/amd64", "linux/arm64"), required=True
    )
    render_parser.add_argument("--output", required=True)
    render_parser.add_argument("--mirrors")
    commands.add_parser("check").add_argument("--directory", required=True)
    args = parser.parse_args()
    release = artifact()
    if args.command == "verify":
        print(
            f"Verified {release['id']}; artifact status: {release['qualification']['status']}"
        )
    else:
        {"render": render, "check": check}[args.command](args, release)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f"prepare: {error}")
