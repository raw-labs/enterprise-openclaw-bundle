#!/usr/bin/env python3
"""Verify a bundle or prepare release-bound inputs for OCE and Helm."""

import argparse
import json
import re
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
    verify_package,
)
from preflight import inspect

ROOT = Path(__file__).resolve().parents[1]


CHANNELS = "gatewayRouting.channels"
COMPUTE = "drivers.compute.configuration."
HELM_OVERRIDES = {
    "cluster.port": lambda v: type(v) is int and 1 <= v <= 65535,
    CHANNELS + ".enabled": lambda v: type(v) is bool,
    CHANNELS + ".hostname": lambda v: isinstance(v, str) and bool(v),
    CHANNELS + ".tlsSecretName": lambda v: isinstance(v, str) and bool(v),
    CHANNELS + ".listenerPort": lambda v: type(v) is int and 1 <= v <= 65535,
    CHANNELS + ".ingressPeers": lambda v: isinstance(v, list),
}
INSTALLATION_OVERRIDES = {
    COMPUTE + "resources.namespace.quota.pods": lambda v: matches(v, r"[1-9][0-9]*"),
    COMPUTE + "runtime.nativeOpenClawSessionCapacity":
        lambda v: type(v) is int and 1 <= v <= 1024,
    COMPUTE + CHANNELS + ".hostname":
        lambda v: matches(v, r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+"),
    "repository.configuration.sessionDurationSeconds":
        lambda v: type(v) is int and 1 <= v <= (2**53 - 1) // 1000,
}


def matches(value, pattern):
    return isinstance(value, str) and re.fullmatch(pattern, value)


def apply_overrides(target, patch, allowed, prefix=""):
    require(isinstance(patch, dict), "overrides must be an object")
    for key, value in patch.items():
        require(isinstance(key, str) and "." not in key, "override keys must be nested")
        path = prefix + key
        if path in allowed:
            validator = allowed[path]
            require(validator(value), f"invalid site override: {path}")
            target[key] = value
        else:
            require(isinstance(value, dict) and value
                    and any(p.startswith(path + ".") for p in allowed),
                    f"unsupported site override: {path}")
            if path == "repository":
                require(key in target, "repository override requires an enabled repository broker")
            child = target.setdefault(key, {})
            require(isinstance(child, dict), f"cannot override non-object: {path}")
            apply_overrides(child, value, allowed, path + ".")


def apply_site_overrides(args, out):
    helm = getattr(args, "helm_overrides", None)
    installation = getattr(args, "installation_overrides", None)
    if not (helm or installation):
        return
    values_path, installation_path = out / "values.yaml", out / "installation.yaml"
    values = helm_values(values_path)
    if helm:
        apply_overrides(values, helm_values(helm), HELM_OVERRIDES)
    if installation:
        config = helm_values(installation_path)
        apply_overrides(config, helm_values(installation), INSTALLATION_OVERRIDES)
        save(installation_path, config)
    values["controlPlane"]["installationChecksum"] = digest(installation_path.read_bytes())
    save(values_path, values)


def artifact():
    verify_package(ROOT)
    return load(ROOT / "metadata/release.json")


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
    # The bundle's selected templates are controller image ingredients.
    # Reuse OCE's file seeding; installers do not import a second copy.
    selected_presets = [p["path"] for p in release.get("presets", [])]
    if selected_presets or "includeDefaultPresets" in release:
        presets = site.setdefault("presets", {})
        if "includeDefaultPresets" in release:
            selected = release["includeDefaultPresets"]
            require(presets.get("includeDefaults", selected) == selected,
                    "presets.includeDefaults is selected by the bundle definition")
            presets["includeDefaults"] = selected
        existing = presets.get("files", [])
        require(isinstance(existing, list) and all(isinstance(p, str) for p in existing), "presets.files must contain paths")
        presets["files"] = list(dict.fromkeys([*selected_presets, *existing]))
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
                ROOT / "oce/scripts/render-installation-profile.mjs",
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
    apply_site_overrides(args, out)
    save(
        out / "selection.json",
        {
            "releaseId": release["id"],
            "images": refs,
            "profile": args.profile,
            "architecture": architecture,
            "namespace": cp["namespace"],
            "releaseName": cp["releaseName"],
            "valuesSha256": digest((out / "values.yaml").read_bytes()),
            "installationSha256": digest((out / "installation.yaml").read_bytes()),
        },
    )
    check(argparse.Namespace(directory=out), release)
    print(
        f"Prepared {out}. Review preflight.json and rendered.yaml; follow INSTALL.md."
    )


def check(args, release, *, write_rendered=True):
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
    values_path = out / "values.yaml"
    installation = (out / "installation.yaml").read_bytes()
    require(selection.get("valuesSha256") == digest(values_path.read_bytes()),
            "prepared Helm values changed; render again")
    require(selection.get("installationSha256") == digest(installation),
            "prepared Installation changed; render again")
    values = helm_values(values_path)
    config = helm_values(out / "installation.yaml")
    presets = config.get("presets", {})
    require(all(p["path"] in presets.get("files", []) for p in release.get("presets", [])),
            "rendered preset selection mismatch")
    if "includeDefaultPresets" in release:
        require(presets.get("includeDefaults") is release["includeDefaultPresets"],
                "rendered preset default selection mismatch")
    compute = config["drivers"]["compute"]["configuration"]
    helm_channels = values.get("gatewayRouting", {}).get("channels", {})
    installation_channels = compute.get("gatewayRouting", {}).get("channels", {})
    require(
        (helm_channels.get("hostname") if helm_channels.get("enabled") is True else None)
        == installation_channels.get("hostname")
        and (not helm_channels.get("enabled") or bool(installation_channels.get("hostname"))),
        "enabled Helm channel listener and Installation callback hostname must match",
    )
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
    if write_rendered:
        (out / "rendered.yaml").write_bytes(rendered)
    return values, config, architecture


def preflight(args, release):
    if args.directory:
        require(not args.live_installation and not args.architecture,
                "use the rendered directory or the live pair, not both")
        require(args.bootstrap_storage_class, "select the bootstrap PVC storage class")
        values, installation, architecture = check(args, release, write_rendered=False)
        if "port" not in values["cluster"]:
            chart = ROOT / release["chart"]["artifact"]
            values["cluster"]["port"] = helm_values(chart / "values.yaml")["cluster"]["port"]
    else:
        require(args.live_installation and args.architecture,
                "--live-values requires --live-installation and --architecture")
        values = helm_values(args.live_values)
        installation = helm_values(args.live_installation)
        architecture = args.architecture
    report = inspect(args, ROOT, release, values, installation, architecture)
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        sys.exit(1)


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
    render_parser.add_argument("--helm-overrides")
    render_parser.add_argument("--installation-overrides")
    commands.add_parser("check").add_argument("--directory", required=True)
    preflight_parser = commands.add_parser("preflight")
    baseline = preflight_parser.add_mutually_exclusive_group(required=True)
    baseline.add_argument("--directory")
    baseline.add_argument("--live-values", help="Computed Helm values from the existing installation")
    preflight_parser.add_argument("--live-installation")
    preflight_parser.add_argument("--architecture", choices=("linux/amd64", "linux/arm64"))
    preflight_parser.add_argument("--kubeconfig", required=True)
    preflight_parser.add_argument("--context", required=True)
    preflight_parser.add_argument("--pg-service", required=True)
    preflight_parser.add_argument("--api-policy-destination", choices=("service", "endpoint", "both"), required=True)
    preflight_parser.add_argument("--bootstrap-storage-class")
    args = parser.parse_args()
    release = artifact()
    if args.command == "verify":
        print(
            f"Verified {release['id']}; artifact status: {release['qualification']['status']}"
        )
    else:
        {"render": render, "check": check, "preflight": preflight}[args.command](args, release)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f"prepare: {error}")
