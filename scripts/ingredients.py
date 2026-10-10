"""Resolve checksum-pinned native plugin packages from GitHub's npm registry."""

import base64
import hashlib
import io
import json
import os
import re
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

from common import HASH, SHA, digest, require, safe_path

PLUGIN_ID = re.compile(r"[a-z][a-z0-9-]*")
VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?")


def plugin_selections(plugins, schema):
    require(isinstance(plugins, list) and plugins, "select native plugins")
    ids, bundled, packages = [], [], []
    for plugin in plugins:
        if isinstance(plugin, str):
            require(PLUGIN_ID.fullmatch(plugin), "invalid bundled plugin ID")
            bundled.append(plugin)
            identity = plugin
        else:
            require(schema in (3, 4, 5) and isinstance(plugin, dict), "unsupported plugin selection")
            require(
                set(plugin) == {"id", "package", "version", "sha256", "source"},
                "plugin package requires id, package, version, sha256 and source",
            )
            identity = plugin["id"]
            require(isinstance(identity, str) and PLUGIN_ID.fullmatch(identity), "invalid native plugin ID")
            require(
                isinstance(plugin["package"], str) and re.fullmatch(r"@raw-labs/[a-z][a-z0-9-]*", plugin["package"])
                and isinstance(plugin["version"], str) and VERSION.fullmatch(plugin["version"])
                and isinstance(plugin["sha256"], str) and HASH.fullmatch(plugin["sha256"]),
                "pin an exact RAW GitHub npm package and checksum",
            )
            source = plugin["source"]
            require(
                isinstance(source, dict) and set(source) == {"repository", "commit"}
                and isinstance(source["repository"], str) and re.fullmatch(r"https://github.com/raw-labs/[\w.-]+\.git", source["repository"])
                and isinstance(source["commit"], str) and SHA.fullmatch(source["commit"]),
                "plugin source requires an exact RAW repository commit",
            )
            packages.append(plugin)
        require(identity not in ids, "duplicate native plugin ID")
        ids.append(identity)
    return bundled, packages


class RegistryRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        destination = urllib.parse.urlsplit(url)
        require(destination.scheme == "https" and destination.netloc in ("npm.pkg.github.com", "pkg-npm.githubusercontent.com"), "registry redirect rejected")
        redirected = super().redirect_request(request, fp, code, message, headers, url)
        if destination.netloc != urllib.parse.urlsplit(request.full_url).netloc:
            redirected.remove_header("Authorization")
        return redirected


def download_package(plugin):
    token = os.environ.get("GH_TOKEN")
    require(token, "GH_TOKEN with private package read access is required")
    opener = urllib.request.build_opener(RegistryRedirect())

    def read(url):
        parsed = urllib.parse.urlsplit(url)
        require(parsed.scheme == "https" and parsed.netloc == "npm.pkg.github.com", "unexpected plugin registry")
        request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
        with opener.open(request, timeout=60) as response:
            data = response.read(32 * 1024 * 1024 + 1)
        require(len(data) <= 32 * 1024 * 1024, "plugin package exceeds size limit")
        return data

    metadata = json.loads(read("https://npm.pkg.github.com/" + urllib.parse.quote(plugin["package"], safe="@")))
    version = metadata["versions"][plugin["version"]]
    require(version["name"] == plugin["package"] and version["version"] == plugin["version"], "registry package identity mismatch")
    require(
        version["repository"]["url"].removeprefix("git+") == plugin["source"]["repository"],
        "registry package source mismatch",
    )
    if version.get("gitHead"):
        require(version["gitHead"] == plugin["source"]["commit"], "registry source commit mismatch")
    data = read(version["dist"]["tarball"])
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
    require(integrity == version["dist"]["integrity"], "registry plugin integrity mismatch")
    return data


def package_files(data, plugin):
    require(digest(data) == plugin["sha256"], "plugin package checksum mismatch")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        size = 0
        for member in archive.getmembers():
            require(member.isfile() or member.isdir(), "plugin archive links/devices rejected")
            require(member.name.startswith("package/"), "invalid plugin archive root")
            relative = member.name.removeprefix("package/")
            if not relative and member.isdir():
                continue
            safe_path(Path("/plugin"), relative)
            require(not re.search(r"(?:^|/)(?:node_modules|\.env|state|tests|src)(?:/|$)", relative), "private/build files in plugin package")
            if member.isfile():
                require(relative not in files, "duplicate plugin archive member")
                size += member.size
                require(size <= 64 * 1024 * 1024, "expanded plugin package exceeds size limit")
                files[relative] = archive.extractfile(member).read()
    metadata = json.loads(files["package.json"])
    manifest = json.loads(files["openclaw.plugin.json"])
    require(metadata["name"] == plugin["package"] and metadata["version"] == plugin["version"], "packed plugin identity mismatch")
    require(metadata["repository"]["url"].removeprefix("git+") == plugin["source"]["repository"], "packed plugin source mismatch")
    require(manifest["id"] == plugin["id"] and manifest["version"] == plugin["version"], "native plugin manifest mismatch")
    for path in [*metadata["openclaw"]["extensions"], *manifest.get("skills", [])]:
        relative = path.removeprefix("./")
        safe_path(Path("/plugin"), relative)
        require(relative in files or any(p.startswith(relative + "/") for p in files), "missing native plugin entry or skills")
    if manifest.get("controlUi"):
        require(manifest["controlUi"]["entry"] in files, "missing native plugin UI")
    require(all(p in files for p in ["LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"]), "plugin notices missing")
    return files


def resolve_plugins(packages, source, cache=None):
    resolved = []
    for plugin in packages:
        filename = plugin["package"].split("/")[-1] + "-" + plugin["version"] + ".tgz"
        cached = Path(cache) / filename if cache else None
        # Release assets may retain the scope in their filename.
        if cached and not cached.exists():
            cached = Path(cache) / ("raw-labs-" + filename)
        data = cached.read_bytes() if cached and cached.exists() else download_package(plugin)
        files = package_files(data, plugin)
        archives = source.parent / "dependencies"
        archives.mkdir(exist_ok=True)
        (archives / filename).write_bytes(data)
        directory = source / "deploy/bundle/plugins" / plugin["id"]
        for name, content in files.items():
            target = safe_path(directory, name)
            require(not target.exists(), "plugin would overwrite source")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        resolved.append({**plugin, "files": {name: digest(content) for name, content in sorted(files.items())}})
    return resolved
