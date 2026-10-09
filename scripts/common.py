"""Factory release invariants; this module is not delivered to installers."""

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROLES = ("controller", "runtime", "repositoryCredentials")
SHA = re.compile(r"^[a-f0-9]{40}$")
HASH = re.compile(r"^[a-f0-9]{64}$")
IMAGE = re.compile(r"^[a-zA-Z0-9][^@\s]+@sha256:[a-f0-9]{64}$")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def safe_path(root, relative):
    require(
        isinstance(relative, str) and relative and not Path(relative).is_absolute(),
        "path must be relative",
    )
    path = (Path(root) / relative).resolve()
    require(path.is_relative_to(Path(root).resolve()), "path escapes input root")
    return path


def release_file(selection, root, relative):
    """Prefer the release's pinned snapshot to mutable repository defaults."""
    path = safe_path(Path(selection).parent, relative)
    return path if path.exists() else safe_path(root, relative)


def verify_files(root, files):
    require(isinstance(files, dict) and files, "missing file integrity map")
    for name, expected in files.items():
        require(bool(HASH.fullmatch(expected)), "invalid file hash")
        path = safe_path(root, name)
        require(
            path.is_file() and digest(path.read_bytes()) == expected,
            f"file integrity mismatch: {name}",
        )


def identities(release):
    return {r: release["images"][r]["reference"] for r in ROLES}


def validate(release):
    require(release.get("schemaVersion") == 2, "unsupported release schema")
    return validate_stock(release)


def read_release(path, root=None):
    path = Path(path)
    release = validate(load(path))
    if release["schemaVersion"] == 2:
        if root is not None:
            for name, expected in release["payloadFiles"].items():
                source = release_file(path, root, name)
                require(
                    digest(source.read_bytes()) == expected, f"payload mismatch: {name}"
                )
        for arch, receipt in release["qualification"].get("nativeReceipts", {}).items():
            proof_path = safe_path(path.parent, receipt["path"])
            require(
                digest(proof_path.read_bytes()) == receipt["sha256"],
                "native receipt integrity mismatch",
            )
            proof = load(proof_path)
            require(
                proof["status"] == "passed-native-export-checks"
                and proof["native"] is True
                and proof["cleanup"] == "completed"
                and proof["releaseId"] == release["id"]
                and proof["platform"] == "linux/" + arch
                and proof["oceCommit"] == release["sources"]["oce"]["commit"]
                and proof["openclawCommit"] == release["sources"]["openclaw"]["commit"]
                and proof["codexVersion"] == release["runtime"]["codexVersion"]
                and proof["images"]
                == {
                    r: release["images"][r]["platforms"]["linux/" + arch] for r in ROLES
                },
                "native receipt identity mismatch",
            )
            require(
                release["seccomp"]["profiles"]["linux/" + arch]["sha256"]
                == proof["confinement"]["seccompSha256"],
                "native receipt confinement mismatch",
            )
            require(set(proof["lanes"]) == set(ROLES), "all native test lanes required")
            for counts in proof["lanes"].values():
                require(
                    counts["tests"] > 0
                    and counts["tests"] == counts["pass"]
                    and all(counts[k] == 0 for k in ("fail", "skipped", "cancelled")),
                    "native receipt failed or skipped tests",
                )
        if release["qualification"]["status"] == "native-verified":
            workflows = []
            for ref in release["qualification"]["nativeReceipts"].values():
                proof = load(safe_path(path.parent, ref["path"]))
                require(
                    proof.get("definitionSha256") == release["definitionSha256"]
                    and proof["workflow"]["GITHUB_REPOSITORY"]
                    == "raw-labs/enterprise-openclaw-bundle",
                    "native receipt definition/repository mismatch",
                )
                workflows.append(
                    {
                        k: v
                        for k, v in proof["workflow"].items()
                        if k != "GITHUB_RUN_ATTEMPT"
                    }
                )
            require(
                workflows[0] == workflows[1], "native receipts belong to different runs"
            )
        return release


def validate_stock(release):
    """Validate resolved ingredients and native artifact admission."""
    require(
        re.fullmatch(r"v\d+\.\d+\.\d+-(alpha|beta|rc)\.[1-9]\d*", release["id"]),
        "stock candidate requires a numbered SemVer prerelease",
    )
    require(release["kind"] in ("candidate", "release"), "invalid stock release kind")
    require(
        release["architectures"] == ["linux/amd64", "linux/arm64"],
        "both native architectures are required",
    )
    for src in release["sources"].values():
        require(SHA.fullmatch(src["commit"]), "source must pin a full commit")
        require(
            HASH.fullmatch(src["archiveSha256"]), "source archive checksum required"
        )
        require(
            re.fullmatch(r"https://github.com/[\w.-]+/[\w.-]+\.git", src["repository"]),
            "invalid source repository",
        )
    oce = release["sources"]["oce"]["commit"]
    require(release["chart"]["sourceCommit"] == oce, "chart/source mismatch")
    require(release["chart"]["name"] == "openclaw-enterprise", "unexpected chart")
    runtime = release["runtime"]
    require(
        runtime["selection"] == "upstream-stock" and runtime["overlay"] is None,
        "stock source does not accept a hidden overlay",
    )
    require(
        re.fullmatch(r"\d+\.\d+\.\d+", runtime["codexVersion"]), "invalid Codex version"
    )
    require(HASH.fullmatch(runtime["inventoryHelperSha256"]), "helper hash required")
    require(
        HASH.fullmatch(release["build"]["noticeLayerSha256"]),
        "license build hash required",
    )
    for image in ("nodeBaseImage", "nodeRuntimeBaseImage"):
        require(IMAGE.fullmatch(release["build"][image]), "base image digest required")
    for role, expected in {
        "controller": {"dockerfile": "Dockerfile", "target": "runtime"},
        "runtime": {"dockerfile": "deploy/runtime/Dockerfile", "target": "runtime"},
        "repositoryCredentials": {
            "dockerfile": "deploy/runtime/Dockerfile",
            "target": "repository-credentials-service",
        },
    }.items():
        require(release["build"][role] == expected, "unexpected stock build recipe")
    require(
        set(release["rendererDependencies"]) == {"tldts", "tldts-core"},
        "unexpected renderer dependency set",
    )
    for dependency in release["rendererDependencies"].values():
        require(
            re.fullmatch(r"\d+\.\d+\.\d+", dependency["version"])
            and HASH.fullmatch(dependency["archiveSha256"]),
            "invalid renderer dependency pin",
        )
    require(set(release["images"]) == set(ROLES), "exactly three image roles required")
    for role, image in release["images"].items():
        require(image["oceCommit"] == oce, f"{role} image/source mismatch")
        if image["reference"] is None:
            require(not image["platforms"], "unbuilt role cannot carry platform images")
        else:
            require(
                IMAGE.fullmatch(image["reference"]), "immutable index digest required"
            )
            require(
                set(image["platforms"]) == set(release["architectures"]),
                "platform set mismatch",
            )
            for platform in image["platforms"].values():
                require(
                    re.fullmatch(r"sha256:[a-f0-9]{64}", platform["digest"]),
                    "platform digest required",
                )
                require(
                    re.fullmatch(r"sha256:[a-f0-9]{64}", platform["configDigest"]),
                    "config digest required",
                )
    require(
        release["images"]["runtime"]["openclawCommit"]
        == release["sources"]["openclaw"]["commit"]
        and release["images"]["runtime"]["codexVersion"] == runtime["codexVersion"],
        "runtime/source metadata mismatch",
    )
    q = release["qualification"]
    require(
        q["customerQualified"] is False,
        "generic artifact cannot qualify a customer installation",
    )
    if q["status"] == "unqualified":
        require(
            release["kind"] == "candidate",
            "unqualified artifacts must remain candidates",
        )
    else:
        require(
            q["status"] == "native-verified" and release["kind"] == "release",
            "release requires native artifact verification",
        )
        require(
            HASH.fullmatch(release.get("definitionSha256", "")),
            "native release must bind its bundle definition",
        )
        require(
            all(image["reference"] for image in release["images"].values()),
            "review requires all shipping image digests",
        )
        require(
            set(q.get("nativeReceipts", {})) == {"amd64", "arm64"},
            "review requires both native receipts",
        )
        require(
            set(release["seccomp"]["profiles"]) == set(release["architectures"]),
            "review requires both confinement artifacts",
        )
        for profile in release["seccomp"]["profiles"].values():
            require(
                release["payloadFiles"].get(profile["path"]) == profile["sha256"],
                "reviewed policy inventory mismatch",
            )
    require(
        release["distribution"]["registry"] == "ghcr.io"
        and release["distribution"]["visibility"] == "private"
        and release["distribution"]["namespace"]
        == "raw-labs/enterprise-openclaw-bundle",
        "unexpected distribution destination",
    )
    return release


def install_gate(release):
    require(
        release["distribution"].get("published", True),
        "unpublished verification artifact cannot be installed",
    )
    require(
        release["qualification"]["status"] != "unqualified",
        "candidate cannot be installed through bundle tooling",
    )


def helm_values(path):
    """Parse YAML using the operator's required Helm runtime, avoiding another dependency."""
    with tempfile.TemporaryDirectory() as tmp:
        chart = Path(tmp)
        (chart / "templates").mkdir()
        (chart / "Chart.yaml").write_text(
            "apiVersion: v2\nname: bundle-value-inspection\nversion: 0.1.0\n"
        )
        (chart / "templates/values.yaml").write_text("{{ .Values | toJson }}\n")
        text = subprocess.check_output(
            ["helm", "template", "inspect", str(chart), "-f", str(path)], text=True
        )
    return json.loads(
        "\n".join(
            line
            for line in text.splitlines()
            if line != "---" and not line.startswith("#")
        )
    )
