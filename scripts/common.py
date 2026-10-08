"""Release invariants shared by build and customer artifact tools (stdlib only)."""

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
    if release.get("schemaVersion") == 2:
        return validate_stock(release)
    require(release["schemaVersion"] == 1, "unsupported release schema")
    require(
        bool(re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,79}", release["id"])),
        "invalid release identity",
    )
    require(
        release["kind"] in ("recorded-baseline", "candidate", "release"),
        "invalid release kind",
    )
    require(release["architecture"] == "linux/amd64", "only linux/amd64 is selected")
    for src in release["sources"].values():
        require(bool(SHA.fullmatch(src["commit"])), "source must pin a full commit")
        require(
            bool(HASH.fullmatch(src["archiveSha256"])),
            "source archive checksum required",
        )
        require(
            bool(
                re.fullmatch(
                    r"https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git",
                    src["repository"],
                )
            ),
            "invalid source repository",
        )
    oce = release["sources"]["oce"]["commit"]
    require(release["chart"]["sourceCommit"] == oce, "chart/source mismatch")
    require(release["chart"]["name"] == "openclaw-enterprise", "unexpected chart name")
    require(
        bool(
            re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][\w.-]+)?", release["chart"]["version"])
        ),
        "invalid chart version",
    )
    require(set(release["images"]) == set(ROLES), "exactly three image roles required")
    for role, image in release["images"].items():
        require(
            bool(IMAGE.fullmatch(image["reference"])),
            f"{role} must use immutable image digest",
        )
        require(image["oceCommit"] == oce, f"{role} image/source mismatch")
    runtime = release["images"]["runtime"]
    require(
        runtime["openclawCommit"] == release["sources"]["openclaw"]["commit"],
        "runtime/OpenClaw mismatch",
    )
    overlay = release["overlay"]
    require(
        overlay["id"] == "codex-" + overlay["codexVersion"], "overlay identity mismatch"
    )
    require(
        runtime["codexVersion"] == overlay["codexVersion"],
        "runtime/overlay version mismatch",
    )
    require(
        overlay["files"] and overlay["qualificationPatch"] in overlay["files"],
        "tracked qualification patch required",
    )
    require(
        bool(IMAGE.fullmatch(release["build"]["nodeBaseImage"]))
        and bool(IMAGE.fullmatch(release["build"]["nodeRuntimeBaseImage"])),
        "base images must be digest pinned",
    )
    require(bool(HASH.fullmatch(release["seccomp"]["sha256"])), "seccomp hash required")
    q = release["qualification"]
    require(
        q["status"] in ("unqualified", "pilot-recorded", "qualified"),
        "invalid qualification status",
    )
    require(
        isinstance(q["customerQualified"], bool),
        "customer qualification must be explicit",
    )
    if q["status"] == "pilot-recorded":
        require(
            release["kind"] == "recorded-baseline" and not q["customerQualified"],
            "pilot is not a customer release",
        )
        require(
            q["evidence"]["images"] == identities(release),
            "pilot evidence image mismatch",
        )
        require(
            q["evidence"]["oceCommit"] == oce
            and q["evidence"]["openclawCommit"] == runtime["openclawCommit"],
            "pilot evidence source mismatch",
        )
    if q["status"] == "unqualified":
        require(
            release["kind"] == "candidate" and not q["customerQualified"],
            "unqualified input must be a candidate",
        )
    if q["status"] == "qualified":
        require(
            release["kind"] == "release"
            and q.get("receipt")
            and HASH.fullmatch(q.get("receiptSha256", "")),
            "qualified release requires reviewed receipt",
        )
    return release


def read_release(path, root=None):
    path = Path(path)
    release = validate(load(path))
    if release["schemaVersion"] == 2:
        if root is not None:
            notice = release["build"]["noticeLayer"]
            require(
                digest(release_file(path, root, notice["fragment"]).read_bytes())
                == notice["sha256"],
                "notice layer integrity mismatch",
            )
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
        if release["qualification"]["status"] == "qualified":
            q = release["qualification"]
            review = safe_path(path.parent, q["receipt"])
            require(
                digest(review.read_bytes()) == q["receiptSha256"],
                "review receipt integrity mismatch",
            )
            validate_stock_review(release, load(review))
        return release
    if root is not None:
        verify_files(root, release["overlay"]["files"])
        verify_files(root, release["payloadFiles"])
        overlay = release["overlay"]
        package = load(safe_path(root, overlay["directory"] + "/package.json"))
        lock = load(safe_path(root, overlay["directory"] + "/package-lock.json"))
        version = overlay["codexVersion"]
        require(
            package["dependencies"]["@openai/codex"] == version,
            "overlay package/release version mismatch",
        )
        require(
            lock["packages"]["node_modules/@openai/codex"]["version"] == version,
            "overlay lock/release version mismatch",
        )
        require(
            lock["packages"]["node_modules/@openai/codex-linux-x64"]["version"]
            == version + "-linux-x64",
            "overlay binary/release version mismatch",
        )
        dockerfile = safe_path(root, overlay["directory"] + "/Dockerfile").read_text()
        require(
            release["sources"]["openclaw"]["commit"] in dockerfile
            and release["sources"]["openclaw"]["archiveSha256"] in dockerfile,
            "overlay/source selection mismatch",
        )
        require(
            "OPENAI_CODEX_VERSION=" + version in dockerfile,
            "overlay Dockerfile/release version mismatch",
        )
    if release["qualification"]["status"] == "qualified":
        q = release["qualification"]
        receipt = safe_path(path.parent, q["receipt"])
        require(
            digest(receipt.read_bytes()) == q["receiptSha256"],
            "qualification receipt integrity mismatch",
        )
        proof = load(receipt)
        require(
            proof["status"] == "passed" and proof["images"] == identities(release),
            "qualification receipt image mismatch",
        )
        require(
            proof["oceCommit"] == release["sources"]["oce"]["commit"]
            and proof["openclawCommit"] == release["sources"]["openclaw"]["commit"],
            "qualification receipt source mismatch",
        )
        require(
            proof["architecture"] == release["architecture"]
            and proof["codexVersion"] == release["overlay"]["codexVersion"],
            "qualification receipt runtime mismatch",
        )
        require(
            proof["seccompSha256"] == release["seccomp"]["sha256"]
            and proof["qualificationPatchSha256"]
            == release["overlay"]["files"][release["overlay"]["qualificationPatch"]],
            "qualification input mismatch",
        )
        require(
            proof["counts"]["tests"] > 0
            and proof["counts"]["pass"] == proof["counts"]["tests"]
            and all(proof["counts"][k] == 0 for k in ("fail", "skipped", "cancelled")),
            "qualification must pass without skips",
        )
    return release


def validate_stock(release):
    """New stock inputs cannot inherit pilot images or claim automatic promotion."""
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
            q["status"] == "qualified"
            and release["kind"] == "release"
            and q.get("receipt")
            and HASH.fullmatch(q.get("receiptSha256", "")),
            "stock promotion requires reviewed acceptance",
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


def validate_stock_review(release, review):
    require(
        review["status"] == "reviewed-native-artifacts"
        and isinstance(review.get("reviewedBy"), str)
        and review["reviewedBy"].strip()
        and review["releaseId"] == release["id"]
        and review["images"] == identities(release)
        and review["oceCommit"] == release["sources"]["oce"]["commit"]
        and review["openclawCommit"] == release["sources"]["openclaw"]["commit"]
        and review["codexVersion"] == release["runtime"]["codexVersion"]
        and review["nativeReceipts"] == release["qualification"]["nativeReceipts"]
        and review["confinementProfiles"] == release["seccomp"]["profiles"]
        and review["scope"]
        == "native shipping artifacts; provider access and customer installation acceptance remain separate",
        "review does not accept these exact native artifacts",
    )


def install_gate(release, allow_pilot):
    require(
        release["qualification"]["status"] != "unqualified",
        "candidate cannot be installed through bundle tooling",
    )
    require(
        release["qualification"]["status"] != "pilot-recorded" or allow_pilot,
        "pilot baseline requires --allow-pilot-baseline for evaluation",
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
