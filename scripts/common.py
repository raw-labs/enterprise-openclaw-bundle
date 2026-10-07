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
