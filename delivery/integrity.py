"""File verification for the delivered package; Python standard library only."""

import hashlib
import json
import re
import stat
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
        require(isinstance(name, str) and name, "invalid inventory path")
        relative = Path(name)
        require(
            not relative.is_absolute()
            and ".." not in relative.parts
            and name == relative.as_posix()
            and name != ".",
            "invalid inventory path",
        )
        path = root / relative
        require(
            not any(p.is_symlink() for p in [path, *path.parents] if p != root),
            "inventory links rejected",
        )
        require(
            isinstance(expected, str)
            and re.fullmatch(r"[a-f0-9]{64}", expected) is not None,
            "invalid file hash",
        )
        require(
            path.is_file() and digest(path.read_bytes()) == expected,
            f"file integrity mismatch: {name}",
        )


def verify_package(root):
    """Check the entire extracted kit, with only the manifest exempt from hashing."""
    root = Path(root).resolve()
    manifest_name = "metadata/manifest.json"
    manifest = root / manifest_name
    require(
        not manifest.parent.is_symlink()
        and not manifest.is_symlink()
        and manifest.is_file(),
        "package manifest must be a regular file",
    )
    files = load(manifest)
    require(
        isinstance(files, dict) and manifest_name not in files,
        "invalid package manifest",
    )
    verify_files(root, files)
    expected = set(files) | {manifest_name}
    directories = {
        parent.as_posix()
        for name in expected
        for parent in Path(name).parents
        if parent != Path(".")
    }
    for path in root.rglob("*"):
        name = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        require(not stat.S_ISLNK(mode), f"package links rejected: {name}")
        if stat.S_ISDIR(mode):
            require(name in directories, f"unexpected package directory: {name}")
        else:
            require(stat.S_ISREG(mode), f"non-regular package file: {name}")
            require(name in expected, f"unexpected package file: {name}")


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
