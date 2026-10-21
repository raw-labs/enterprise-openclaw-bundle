"""Synthetic validator inputs. These records never qualify or ship an artifact."""


def candidate():
    sha, checksum = "1" * 40, "2" * 64
    roles = ("controller", "runtime", "repositoryCredentials")
    return {
        "schemaVersion": 2,
        "definitionSchemaVersion": 5,
        "id": "v0.0.0-alpha.1",
        "kind": "candidate",
        "architectures": ["linux/amd64", "linux/arm64"],
        "definitionSha256": checksum,
        "plugins": ["codex"],
        "pluginPackages": [],
        "presets": [],
        "includeDefaultPresets": False,
        "sources": {
            name: {
                "repository": f"https://github.com/fixtures/{name}.git",
                "commit": sha,
                "archiveSha256": checksum,
                "files": "source-files.json",
                "filesSha256": checksum,
            }
            for name in ("oce", "openclaw")
        },
        "chart": {"name": "openclaw-enterprise", "sourceCommit": sha},
        "runtime": {
            "selection": "upstream-stock",
            "overlay": None,
            "codexVersion": "0.0.0",
            "inventoryHelperSha256": checksum,
        },
        "build": {
            "noticeLayerSha256": checksum,
            "nodeBaseImage": "fixture.invalid/build@sha256:" + checksum,
            "nodeRuntimeBaseImage": "fixture.invalid/runtime@sha256:" + checksum,
            "controller": {"dockerfile": "Dockerfile", "target": "runtime"},
            "runtime": {"dockerfile": "deploy/runtime/Dockerfile", "target": "runtime"},
            "repositoryCredentials": {
                "dockerfile": "deploy/runtime/Dockerfile",
                "target": "repository-credentials-service",
            },
        },
        "rendererDependencies": {
            name: {"version": "0.0.0", "archiveSha256": checksum}
            for name in ("tldts", "tldts-core")
        },
        "images": {
            role: {
                "reference": None,
                "platforms": {},
                "oceCommit": sha,
                **(
                    {"openclawCommit": sha, "codexVersion": "0.0.0"}
                    if role == "runtime"
                    else {}
                ),
            }
            for role in roles
        },
        "payloadFiles": {},
        "seccomp": {"profiles": {}},
        "distribution": {
            "registry": "ghcr.io",
            "visibility": "private",
            "namespace": "raw-labs/enterprise-openclaw-bundle",
            "published": False,
        },
        "qualification": {"status": "unqualified", "customerQualified": False},
    }
