#!/usr/bin/env python3
"""Customer artifact CLI: verify, render and generate scoped supplemental resources."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from common import (
    IMAGE,
    ROLES,
    digest,
    helm_values,
    identities,
    install_gate,
    load,
    read_release,
    require,
    run,
    save,
    verify_files,
)

ROOT = Path(__file__).resolve().parents[1]


def artifact():
    verify_files(ROOT, load(ROOT / "manifest.json"))
    return read_release(ROOT / "release.json")


def selected_images(release, mapping):
    refs = identities(release)
    if mapping:
        mirrors = load(mapping)
        require(
            set(mirrors) == set(ROLES), "mirror map must contain exactly three roles"
        )
        for role, ref in mirrors.items():
            require(
                IMAGE.fullmatch(ref) is not None
                and ref.split("@")[1] == refs[role].split("@")[1],
                f"{role} mirror digest mismatch",
            )
        refs = mirrors
    return refs


def render(args, release):
    install_gate(release, args.allow_pilot_baseline)
    out = Path(args.output).resolve()
    require(not out.exists(), "render output exists; use a new directory")
    input = load(args.input)
    refs = selected_images(release, args.mirrors)
    cp = input["controlPlane"]
    rt = input["runtime"]
    for obj, key, role in [
        (cp, "controllerImage", "controller"),
        (rt, "image", "runtime"),
    ]:
        require(
            key not in obj or obj[key] == refs[role],
            f"{role} installation/release mismatch",
        )
        obj[key] = refs[role]
    repo = input.get("repository", {})
    if repo.get("enabled"):
        require(
            "image" not in repo or repo["image"] == refs["repositoryCredentials"],
            "repository image/release mismatch",
        )
        repo["image"] = refs["repositoryCredentials"]
    require(
        not any(key in cp for key in ("github", "google", "oidc")),
        "external login requires a separately qualified release/profile",
    )
    require(
        not input.get("codex", {}).get("managedServiceAccounts"),
        "managed issuance is outside baseline qualification",
    )
    require(
        not input.get("presets", {}).get("files"),
        "artifact does not mount additional controller preset files; import templates through OCE API",
    )
    if args.profile == "codex":
        input.setdefault("codex", {}).setdefault("modelDiscoveryCidrs", [])
        expected = "openclaw/codex-" + release["seccomp"]["sha256"] + ".json"
        require(
            "codexSeccompProfile" not in rt or rt["codexSeccompProfile"] == expected,
            "seccomp/release mismatch",
        )
        rt["codexSeccompProfile"] = expected
    out.mkdir(parents=True, mode=0o700)
    with tempfile.TemporaryDirectory() as tmp:
        effective = Path(tmp) / "input.json"
        save(effective, input)
        run(
            [
                "node",
                ROOT / "upstream/scripts/render-installation-profile.mjs",
                "--profile",
                args.profile,
                "--input",
                effective,
                "--out-dir",
                out,
            ],
            stdout=subprocess.PIPE,
        )
    # Curated catalog override changes these hosted-profile advisories explicitly.
    if args.profile == "codex":
        preflight = load(out / "preflight.json")
        preflight["warnings"] = [
            w for w in preflight["warnings"] if "codex_pat" not in w
        ]
        preflight["prerequisites"] = [
            w for w in preflight["prerequisites"] if "Hosted discovery" not in w
        ]
        preflight["prerequisites"].append(
            "Curated catalog selected; supply and grant each Agent its own model credentials. Bundle templates use API-key Secrets; other credential modes require separate qualification."
        )
        save(out / "preflight.json", preflight)
    # Never render Secrets or alter the chart. Bootstrap PVC is installation-specific.
    pvc = {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {
            "name": cp["bootstrapPasswordClaimName"],
            "namespace": cp["namespace"],
        },
        "spec": {
            "accessModes": ["ReadWriteOnce"],
            "storageClassName": rt["gatewayStorageClassName"],
            "resources": {"requests": {"storage": "1Gi"}},
        },
    }
    save(out / "bootstrap-pvc.json", pvc)
    # ALB's source IP peers are not admitted by the chart's Pod-selector policy.
    supplemental = []
    proxy = cp.get("trustedProxy", {})
    if proxy.get("preset") == "aws":
        supplemental.append(
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": {
                    "name": "bundle-alb-api-ingress",
                    "namespace": cp["namespace"],
                },
                "spec": {
                    "podSelector": {
                        "matchLabels": {
                            "app.kubernetes.io/name": "openclaw-enterprise",
                            "app.kubernetes.io/instance": cp["releaseName"],
                            "app.kubernetes.io/component": "api",
                        }
                    },
                    "policyTypes": ["Ingress"],
                    "ingress": [
                        {
                            "from": [
                                {"ipBlock": {"cidr": cidr}} for cidr in proxy["cidrs"]
                            ],
                            "ports": [{"protocol": "TCP", "port": 8080}],
                        }
                    ],
                },
            }
        )
    save(
        out / "supplemental.json",
        {"apiVersion": "v1", "kind": "List", "items": supplemental},
    )
    save(
        out / "selection.json",
        {
            "releaseId": release["id"],
            "images": refs,
            "profile": args.profile,
            "namespace": cp["namespace"],
            "releaseName": cp["releaseName"],
            "inputSha256": digest(Path(args.input).read_bytes()),
            "controllerNodeSelector": cp["nodeSelector"],
            "bootstrapClaim": cp["bootstrapPasswordClaimName"],
        },
    )
    check(argparse.Namespace(directory=out), release)
    print(
        f"Prepared {out}; inspect preflight.json and rendered.yaml. No cluster changes."
    )


def check(args, release):
    out = Path(args.directory)
    selection = load(out / "selection.json")
    require(selection["releaseId"] == release["id"], "rendered release mismatch")
    for role, ref in selection["images"].items():
        require(
            IMAGE.fullmatch(ref)
            and ref.split("@")[1] == identities(release)[role].split("@")[1],
            "rendered digest mismatch",
        )
    values = helm_values(out / "values.yaml")
    installation = (out / "installation.yaml").read_text()
    config = helm_values(out / "installation.yaml")
    require(
        values["images"]["controller"] == selection["images"]["controller"],
        "rendered controller mismatch",
    )
    require(
        all(
            config["drivers"]["compute"]["configuration"]["images"][role]
            == selection["images"]["runtime"]
            for role in ("gateway", "agent")
        ),
        "rendered runtime mismatch",
    )
    require(
        config["drivers"]["compute"]["configuration"]["images"][
            "requireImmutableDigest"
        ]
        is True,
        "immutable runtime selection required",
    )
    if values.get("repositoryCredentials", {}).get("enabled"):
        require(
            values["repositoryCredentials"]["image"]
            == selection["images"]["repositoryCredentials"],
            "rendered repository service mismatch",
        )
    require(
        values["controlPlane"]["installationChecksum"] == digest(installation.encode()),
        "installation/Helm checksum mismatch",
    )
    require(load(out / "preflight.json")["ok"], "upstream profile preflight failed")
    chart = ROOT / release["chart"]["artifact"]
    run(["helm", "lint", chart, "-f", out / "values.yaml"], stdout=subprocess.PIPE)
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
    print(f"Validated installation, paired checksum and chart rendering: {out}")


def tenant_resources(args, release):
    require(
        re.fullmatch(r"ns_[a-f0-9-]{36}", args.tenant_id),
        "explicit OCE Namespace ID required",
    )
    kube = ["kubectl", "--kubeconfig", args.kubeconfig, "--context", args.context]
    namespaces = json.loads(
        subprocess.check_output(kube + ["get", "namespaces", "-o", "json"])
    )["items"]
    targets = []
    for item in namespaces:
        labels = item["metadata"].get("labels", {})
        if labels.get("openclaw.dev/gateway-namespace") == args.tenant_id:
            targets.append((item["metadata"]["name"], True))
        elif labels.get("openclaw.dev/namespace") == args.tenant_id:
            targets.append((item["metadata"]["name"], False))
    require(
        1 <= len(targets) <= 2,
        "expected one or two exact labeled tenant namespaces; retry after worker provisioning",
    )
    resources = []
    for namespace, gateway in targets:
        roles = [
            ("worker", "tenant-worker", "worker"),
            ("api-secrets", "tenant-api", "api"),
            ("api-configuration", "tenant-configuration", "api")
            if gateway
            else ("api-observer", "gateway-observer", "api"),
        ]
        for name, role, service in roles:
            resources.append(
                {
                    "apiVersion": "rbac.authorization.k8s.io/v1",
                    "kind": "RoleBinding",
                    "metadata": {
                        "name": "openclaw-enterprise-" + name,
                        "namespace": namespace,
                    },
                    "roleRef": {
                        "apiGroup": "rbac.authorization.k8s.io",
                        "kind": "ClusterRole",
                        "name": args.release_name + "-openclaw-" + role,
                    },
                    "subjects": [
                        {
                            "kind": "ServiceAccount",
                            "name": "openclaw-enterprise-" + service,
                            "namespace": args.namespace,
                        }
                    ],
                }
            )
        if args.public_egress:
            require(
                args.agent_id and re.fullmatch(r"agt_[a-f0-9-]{36}", args.agent_id),
                "public egress requires one explicit Agent ID",
            )
            resources.append(
                {
                    "apiVersion": "networking.k8s.io/v1",
                    "kind": "NetworkPolicy",
                    "metadata": {
                        "name": "bundle-public-egress-" + args.agent_id[4:12],
                        "namespace": namespace,
                    },
                    "spec": {
                        "podSelector": {
                            "matchLabels": {
                                "app.kubernetes.io/managed-by": "openclaw-enterprise",
                                "openclaw.dev/network-profile": "broad-egress-v1",
                                "openclaw.dev/agent": args.agent_id,
                            },
                            "matchExpressions": [
                                {
                                    "key": "openclaw.dev/workload-role",
                                    "operator": "In",
                                    "values": ["gateway", "agent"],
                                }
                            ],
                        },
                        "policyTypes": ["Egress"],
                        "egress": [
                            {
                                "to": [
                                    {
                                        "ipBlock": {
                                            "cidr": "0.0.0.0/0",
                                            "except": [
                                                "0.0.0.0/8",
                                                "10.0.0.0/8",
                                                "100.64.0.0/10",
                                                "127.0.0.0/8",
                                                "169.254.0.0/16",
                                                "172.16.0.0/12",
                                                "192.0.0.0/24",
                                                "192.0.2.0/24",
                                                "192.168.0.0/16",
                                                "198.18.0.0/15",
                                                "198.51.100.0/24",
                                                "203.0.113.0/24",
                                                "224.0.0.0/4",
                                                "240.0.0.0/4",
                                            ],
                                        }
                                    }
                                ],
                                "ports": [{"protocol": "TCP"}],
                            }
                        ],
                    },
                }
            )
    path = Path(args.output)
    require(not path.exists(), "supplemental output exists")
    save(path, {"apiVersion": "v1", "kind": "List", "items": resources})
    print(
        f"Scoped resources: {path}; review, then apply explicitly. Repeat for gateway namespace once created."
    )


def bootstrap_read(args, release):
    selection = load(Path(args.directory) / "selection.json")
    secure = Path(args.output)
    require(not secure.exists(), "credential output directory exists")
    secure.mkdir(mode=0o700, parents=True)
    kube = [
        "kubectl",
        "--kubeconfig",
        args.kubeconfig,
        "--context",
        args.context,
        "-n",
        selection["namespace"],
    ]
    pod = "oce-bootstrap-reader"
    definition = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": pod},
        "spec": {
            "nodeSelector": selection["controllerNodeSelector"],
            "restartPolicy": "Never",
            "automountServiceAccountToken": False,
            "securityContext": {
                "runAsUser": 1000,
                "runAsGroup": 1000,
                "fsGroup": 1000,
                "runAsNonRoot": True,
                "seccompProfile": {"type": "RuntimeDefault"},
            },
            "containers": [
                {
                    "name": "reader",
                    "image": selection["images"]["controller"],
                    "command": ["node", "-e", "setInterval(()=>{},1000)"],
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": True,
                        "capabilities": {"drop": ["ALL"]},
                    },
                    "resources": {
                        "requests": {"cpu": "10m", "memory": "64Mi"},
                        "limits": {"cpu": "100m", "memory": "128Mi"},
                    },
                    "volumeMounts": [
                        {
                            "name": "bootstrap",
                            "mountPath": "/bootstrap",
                            "readOnly": True,
                        }
                    ],
                }
            ],
            "volumes": [
                {
                    "name": "bootstrap",
                    "persistentVolumeClaim": {
                        "claimName": selection["bootstrapClaim"],
                        "readOnly": True,
                    },
                }
            ],
        },
    }
    run(kube + ["create", "-f", "-"], input=json.dumps(definition), text=True)
    try:
        run(kube + ["wait", "--for=condition=Ready", "pod/" + pod, "--timeout=60s"])
        for name in ["initial-admin-password", "initial-admin-service-key.json"]:
            contents = subprocess.check_output(
                kube + ["exec", pod, "--", "cat", "/bootstrap/" + name]
            )
            fd = os.open(secure / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(contents)
        print(
            f"Bootstrap credentials saved privately under {secure}; no values printed"
        )
    finally:
        run(kube + ["delete", "pod", pod, "--wait=false"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify")
    p = sub.add_parser("render")
    p.add_argument("--input", required=True)
    p.add_argument("--profile", choices=["openclaw", "codex"], required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--mirrors")
    p.add_argument("--allow-pilot-baseline", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("--directory", required=True)
    p = sub.add_parser("tenant-resources")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--namespace", required=True)
    p.add_argument("--release-name", required=True)
    p.add_argument("--kubeconfig", required=True)
    p.add_argument("--context", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--public-egress", action="store_true")
    p.add_argument("--agent-id")
    p = sub.add_parser("bootstrap-read")
    p.add_argument("--directory", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--kubeconfig", required=True)
    p.add_argument("--context", required=True)
    args = parser.parse_args()
    release = artifact()
    if args.command == "verify":
        print(
            f"{release['id']}: artifact contents verified ({release['qualification']['status']})"
        )
    else:
        globals()[args.command.replace("-", "_")](args, release)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f"install: {error}", file=sys.stderr)
        sys.exit(1)
