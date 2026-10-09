"""File verification for the delivered package; Python standard library only."""

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROLES = ("controller", "runtime", "repositoryCredentials")
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


def verify_files(root, files):
    root = Path(root).resolve()
    require(isinstance(files, dict) and files, "missing file inventory")
    for name, expected in files.items():
        relative = Path(name)
        require(
            not relative.is_absolute() and ".." not in relative.parts,
            "invalid inventory path",
        )
        path = root / relative
        require(
            not any(p.is_symlink() for p in [path, *path.parents] if p != root),
            "inventory links rejected",
        )
        require(
            re.fullmatch(r"[a-f0-9]{64}", expected) is not None, "invalid file hash"
        )
        require(
            path.is_file() and digest(path.read_bytes()) == expected,
            f"file integrity mismatch: {name}",
        )


def helm_values(path):
    """Read YAML through the required Helm runtime without another dependency."""
    with tempfile.TemporaryDirectory() as temporary:
        chart = Path(temporary)
        (chart / "templates").mkdir()
        (chart / "Chart.yaml").write_text(
            "apiVersion: v2\nname: bundle-value-inspection\nversion: 0.1.0\n"
        )
        (chart / "templates/values.yaml").write_text("{{ .Values | toJson }}\n")
        output = subprocess.check_output(
            ["helm", "template", "inspect", str(chart), "-f", str(path)], text=True
        )
    return json.loads(
        "\n".join(
            line
            for line in output.splitlines()
            if line != "---" and not line.startswith("#")
        )
    )
