#!/usr/bin/env python3
"""Exercise the extracted package on an owned, disposable k3d cluster."""

import argparse
import importlib.util
import io
import json
import os
import platform
import secrets
import shlex
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "delivery"))
from integrity import digest, helm_values, load, require, save  # noqa: E402

# Infrastructure pins from the selected OCE CI fixtures; these are test prerequisites.
K3S = "docker.io/rancher/k3s:v1.35.9-k3s1@sha256:ec9868c6a38d4e8c1869832fb5fd1eb8473c39794a0b44d2b952e7ba911951bc"
POSTGRES = "docker.io/library/postgres:18.6@sha256:86c951e05bf56c93d95d397747fb8820ac76cc3bedb78f43abd83eedbe3666ae"
ROUTING = (
    (
        "https://github.com/envoyproxy/gateway/releases/download/v1.6.7/install.yaml",
        "9a250c698d78b92c670d9d2bd6bd54615f1dee41ddd520ece9704edf63088df8",
    ),
    (
        "https://github.com/cert-manager/cert-manager/releases/download/v1.18.4/cert-manager.yaml",
        "aff085b4f0126f67372e3a02cb18feb70eed37dbd4de01973a159e6c13482f83",
    ),
)


def exercise(args):
    archive = Path(args.archive).resolve()
    layout = Path(args.controller).resolve()
    require((layout / "index.json").is_file(), "controller OCI layout is missing")
    cluster = "bundle-install-" + secrets.token_hex(6)
    arch = {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}[platform.machine()]
    log_path = Path(args.logs).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    os.umask(0o077)
    steps = []
    with (
        tempfile.TemporaryDirectory(prefix=cluster + "-") as temporary,
        log_path.open("wb") as logs,
    ):
        work = Path(temporary)

        def run(
            command,
            *,
            cwd=None,
            input=None,
            env=None,
            timeout=600,
            log_output=True,
            diagnostics=False,
        ):
            result = subprocess.run(
                [str(a) for a in command],
                cwd=cwd,
                input=input,
                env=env,
                capture_output=True,
                timeout=timeout,
            )
            if log_output:
                logs.write(result.stdout + result.stderr)
                logs.flush()
            if result.returncode and diagnostics:
                print(result.stderr.decode(errors="replace"), file=sys.stderr)
            require(
                result.returncode == 0,
                f"command failed ({result.returncode}): {shlex.join(str(a) for a in command)}; private log: {log_path}",
            )
            return result.stdout

        with tarfile.open(archive) as tar:
            require(
                all(
                    m.isfile()
                    and not Path(m.name).is_absolute()
                    and ".." not in Path(m.name).parts
                    for m in tar.getmembers()
                ),
                "invalid package member",
            )
            tar.extractall(work, filter="data")
        artifact = next(p for p in work.iterdir() if p.is_dir())
        release = load(artifact / "metadata/release.json")
        require(
            release["qualification"]["status"] == "native-verified",
            "native artifact checks required",
        )
        run([artifact / "bin/prepare", "verify"])
        candidate = artifact
        candidate_release = release
        candidate_controller = release["images"]["controller"]["reference"]

        def image_archive(directory, reference, name):
            index = load(directory / "index.json")
            require(len(index["manifests"]) == 1
                    and index["manifests"][0]["digest"] == reference.split("@")[1],
                    "installation test/controller index mismatch")
            index["manifests"][0]["annotations"] = {"org.opencontainers.image.ref.name": reference}
            target = work / name
            with tarfile.open(target, "w") as tar:
                for path in sorted(directory.rglob("*")):
                    if path.is_file() and path.name != "index.json":
                        tar.add(path, arcname=str(path.relative_to(directory)))
                data = json.dumps(index).encode()
                info = tarfile.TarInfo("index.json")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            return target

        image_archives = [image_archive(layout, candidate_controller, "candidate-controller.tar")]
        baseline = candidate_release.get("upgradeBaseline") if args.baseline else None
        require(not args.baseline or baseline, "unexpected installation upgrade baseline")
        if baseline:
            baseline_archive = Path(args.baseline)
            require(digest(baseline_archive.read_bytes()) == baseline["artifactSha256"], "baseline archive changed")
            old_root = work / "baseline"
            old_root.mkdir()
            with tarfile.open(baseline_archive) as tar:
                require(all(m.isfile() and m.name.startswith(baseline["releaseId"] + "/")
                            and ".." not in Path(m.name).parts for m in tar.getmembers()), "invalid baseline archive")
                tar.extractall(old_root, filter="data")
            artifact = old_root / baseline["releaseId"]
            run([artifact / "bin/prepare", "verify"])
            release = load(artifact / "metadata/release.json")
            require(release["id"] == baseline["releaseId"] and release["images"] == baseline["images"],
                    "baseline release identity changed")
            image_archives.append(image_archive(Path(args.baseline_controller),
                                  release["images"]["controller"]["reference"], "baseline-controller.tar"))
        controller = release["images"]["controller"]["reference"]
        kubeconfig = work / "kubeconfig"
        context = "k3d-" + cluster
        try:
            run(
                [
                    "k3d",
                    "cluster",
                    "create",
                    cluster,
                    "--image",
                    K3S,
                    "--agents",
                    "1",
                    "--k3s-arg",
                    "--disable=traefik@server:*",
                    "--k3s-arg",
                    "--disable=servicelb@server:*",
                    "--kubeconfig-update-default=false",
                    "--kubeconfig-switch-context=false",
                ]
            )
            kubeconfig.write_bytes(
                run(["k3d", "kubeconfig", "get", cluster], log_output=False)
            )
            kube = ["kubectl", "--kubeconfig", kubeconfig, "--context", context]

            def kubectl(*arguments, input=None, log_output=True):
                return run([*kube, *arguments], input=input, log_output=log_output)

            def apply(obj):
                kubectl("apply", "-f", "-", input=json.dumps(obj).encode())

            def resource(kind, name, namespace="openclaw-system"):
                return json.loads(
                    kubectl("-n", namespace, "get", kind, name, "-o", "json")
                )

            nodes = json.loads(kubectl("get", "nodes", "-o", "json"))["items"]
            for node in nodes:
                name = node["metadata"]["name"]
                role = "control" if "server" in name else "agents"
                kubectl("label", "node", name, "oce-role=" + role)
                for imported in image_archives:
                    run(["docker", "cp", imported, name + ":/tmp/controller.tar"])
                    run(
                    [
                        "docker",
                        "exec",
                        name,
                        "ctr",
                        "--address",
                        "/run/k3s/containerd/containerd.sock",
                        "-n",
                        "k8s.io",
                        "images",
                        "import",
                        "--all-platforms",
                        "--no-unpack",
                        "/tmp/controller.tar",
                    ],
                        diagnostics=True,
                    )
                actual = json.loads(
                    run(
                        [
                            "docker",
                            "exec",
                            name,
                            "crictl",
                            "--runtime-endpoint",
                            "unix:///run/k3s/containerd/containerd.sock",
                            "inspecti",
                            controller,
                        ],
                        diagnostics=True,
                    )
                )
                require(
                    controller in actual["status"]["repoDigests"],
                    "node image digest mismatch",
                )
            for number, (url, checksum) in enumerate(ROUTING):
                with urllib.request.urlopen(url, timeout=120) as response:
                    data = response.read()
                require(digest(data) == checksum, "routing prerequisite hash mismatch")
                path = work / f"routing-{number}.yaml"
                path.write_bytes(data)
                kubectl("apply", "--server-side", "-f", path)
            for ns, name in (
                ("envoy-gateway-system", "envoy-gateway"),
                ("cert-manager", "cert-manager"),
                ("cert-manager", "cert-manager-webhook"),
            ):
                kubectl(
                    "-n",
                    ns,
                    "rollout",
                    "status",
                    "deployment/" + name,
                    "--timeout=300s",
                )
            apply(
                {
                    "apiVersion": "gateway.networking.k8s.io/v1",
                    "kind": "GatewayClass",
                    "metadata": {"name": "eg"},
                    "spec": {
                        "controllerName": "gateway.envoyproxy.io/gatewayclass-controller"
                    },
                }
            )
            kubectl("create", "namespace", "openclaw-system")
            database_host = "postgres.openclaw-system.svc.cluster.local"
            run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=" + database_host,
                    "-addext",
                    "subjectAltName=DNS:" + database_host,
                    "-keyout",
                    work / "server.key",
                    "-out",
                    work / "server.crt",
                ]
            )
            app_password, migration_password = (
                secrets.token_hex(24),
                secrets.token_hex(24),
            )

            def secret(name, values, namespace="openclaw-system"):
                apply(
                    {
                        "apiVersion": "v1",
                        "kind": "Secret",
                        "metadata": {"name": name, "namespace": namespace},
                        "stringData": values,
                    }
                )

            secret(
                "postgres-tls",
                {
                    "server.key": (work / "server.key").read_text(),
                    "server.crt": (work / "server.crt").read_text(),
                },
            )
            sql = (
                f"CREATE ROLE occ_migrator LOGIN PASSWORD '{migration_password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;\n"
                f"CREATE ROLE occ_app LOGIN PASSWORD '{app_password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;\n"
                "GRANT CREATE ON DATABASE openclaw_enterprise TO occ_migrator;\n"
                "CREATE SCHEMA occ AUTHORIZATION occ_migrator;\nCREATE SCHEMA drizzle AUTHORIZATION occ_migrator;\n"
                "REVOKE CREATE ON SCHEMA public FROM PUBLIC;\n"
            )
            secret(
                "postgres-init", {"init.sql": sql, "password": secrets.token_hex(24)}
            )
            apply(
                {
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {
                        "name": "postgres",
                        "namespace": "openclaw-system",
                        "labels": {"app": "postgres"},
                    },
                    "spec": {
                        "nodeSelector": {"oce-role": "control"},
                        "containers": [
                            {
                                "name": "postgres",
                                "image": POSTGRES,
                                "command": [
                                    "bash",
                                    "-ec",
                                    "cp /tls/server.* /tmp/; chown 999:999 /tmp/server.*; chmod 600 /tmp/server.key; exec docker-entrypoint.sh postgres -c ssl=on -c ssl_cert_file=/tmp/server.crt -c ssl_key_file=/tmp/server.key",
                                ],
                                "env": [
                                    {
                                        "name": "POSTGRES_DB",
                                        "value": "openclaw_enterprise",
                                    },
                                    {
                                        "name": "POSTGRES_PASSWORD",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "name": "postgres-init",
                                                "key": "password",
                                            }
                                        },
                                    },
                                ],
                                "volumeMounts": [
                                    {
                                        "name": "tls",
                                        "mountPath": "/tls",
                                        "readOnly": True,
                                    },
                                    {
                                        "name": "init",
                                        "mountPath": "/docker-entrypoint-initdb.d",
                                        "readOnly": True,
                                    },
                                ],
                                "readinessProbe": {
                                    "exec": {
                                        "command": [
                                            "pg_isready",
                                            "-h",
                                            "127.0.0.1",
                                            "-U",
                                            "postgres",
                                            "-d",
                                            "openclaw_enterprise",
                                        ]
                                    },
                                    "periodSeconds": 2,
                                },
                            }
                        ],
                        "volumes": [
                            {"name": "tls", "secret": {"secretName": "postgres-tls"}},
                            {
                                "name": "init",
                                "secret": {
                                    "secretName": "postgres-init",
                                    "items": [{"key": "init.sql", "path": "init.sql"}],
                                },
                            },
                        ],
                    },
                }
            )
            apply(
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "postgres", "namespace": "openclaw-system"},
                    "spec": {
                        "selector": {"app": "postgres"},
                        "ports": [{"port": 5432}],
                    },
                }
            )
            kubectl(
                "-n",
                "openclaw-system",
                "wait",
                "--for=condition=Ready",
                "pod/postgres",
                "--timeout=180s",
            )
            endpoint = resource("endpoints", "kubernetes", "default")["subsets"][0]
            site = load(artifact / "examples/installations/site.json")
            cp = site["controlPlane"]
            cp["databaseCidrs"] = [
                resource("pod", "postgres")["status"]["podIP"] + "/32"
            ]
            cp["clusterCidrs"] = [
                address["ip"] + "/32" for address in endpoint["addresses"]
            ]
            cp["databaseCa"] = {
                "secretName": "occ-database-ca",
                "key": "ca.pem",
                "mountPath": "/etc/openclaw/database-ca",
            }
            cp["pluginStatusProxySourceCidrs"] = [
                node["status"]["addresses"][0]["address"] + "/32" for node in nodes
            ]
            site["runtime"]["gatewayStorageClassName"] = "local-path"
            path = work / "site.json"
            save(path, site)
            rendered = work / "rendered"
            if release["distribution"]["published"]:
                run(
                    [
                        artifact / "bin/prepare",
                        "render",
                        "--input",
                        path,
                        "--profile",
                        "codex",
                        "--architecture",
                        "linux/" + arch,
                        "--output",
                        rendered,
                    ]
                )
            else:
                spec = importlib.util.spec_from_file_location(
                    "package_prepare", artifact / "lib/prepare.py"
                )
                prepare = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(prepare)
                prepare.render(
                    argparse.Namespace(
                        input=path,
                        profile="codex",
                        architecture="linux/" + arch,
                        output=rendered,
                        mirrors=None,
                    ),
                    release,
                    admit=False,
                )
            run(
                [
                    artifact / "bin/prepare",
                    "check",
                    "--directory",
                    rendered,
                ]
            )
            steps.append("extracted package verification and release-bound rendering")
            values = helm_values(rendered / "values.yaml")
            # k3d exposes its API endpoint on 6443; cluster.port is an upstream chart option.
            # The Installation bytes and their paired checksum remain unchanged.
            values["cluster"]["port"] = endpoint["ports"][0]["port"]
            save(rendered / "values.yaml", values)
            run(
                [
                    artifact / "bin/prepare",
                    "check",
                    "--directory",
                    rendered,
                ]
            )
            upstream = artifact / "oce"
            claim = helm_values(
                upstream / "deploy/examples/production/bootstrap-pvc.yaml"
            )
            claim["metadata"]["namespace"] = cp["namespace"]
            claim["metadata"]["name"] = cp["bootstrapPasswordClaimName"]
            claim["spec"]["storageClassName"] = "local-path"
            apply(claim)
            chart_values = helm_values(
                upstream / "deploy/helm/openclaw-enterprise/values.yaml"
            )
            installation_settings = (
                chart_values["installation"] | values["installation"]
            )
            secret(
                installation_settings["secretName"],
                {
                    installation_settings["key"]: (
                        rendered / "installation.yaml"
                    ).read_text()
                },
            )
            ca_path = "/etc/openclaw/database-ca/ca.pem"
            suffix = f"@{database_host}:5432/openclaw_enterprise?sslmode=verify-full&sslrootcert={ca_path}"
            secret(
                "occ-database",
                {
                    "application-url": "postgresql://occ_app:" + app_password + suffix,
                    "migration-url": "postgresql://occ_migrator:"
                    + migration_password
                    + suffix,
                },
            )
            secret("occ-database-ca", {"ca.pem": (work / "server.crt").read_text()})
            secret("occ-auth", {"secret": secrets.token_hex(32)})
            secret(cp["gatewayApiKeySecretName"], {"occ": secrets.token_hex(32)})
            run(
                [
                    "bash",
                    "scripts/prepare-bootstrap-volume",
                    "--kubeconfig",
                    kubeconfig,
                    "--context",
                    context,
                    "--namespace",
                    cp["namespace"],
                    "--claim",
                    cp["bootstrapPasswordClaimName"],
                    "--image",
                    controller,
                    "--node-selector",
                    "oce-role=control",
                ],
                cwd=upstream,
            )
            steps.append("upstream bootstrap volume preparation")
            run(
                [
                    "helm",
                    "upgrade",
                    "--install",
                    cp["releaseName"],
                    "deploy/helm/openclaw-enterprise",
                    "--kubeconfig",
                    kubeconfig,
                    "--kube-context",
                    context,
                    "--namespace",
                    cp["namespace"],
                    "-f",
                    rendered / "values.yaml",
                    "--wait",
                    "--timeout",
                    "10m",
                ],
                cwd=upstream,
                timeout=660,
                diagnostics=True,
            )
            steps.append(
                "packaged chart migration, bootstrap, API and worker readiness"
            )
            # Test storage access belongs to the fixture, not the delivered product.
            reader = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": "bootstrap-reader", "namespace": cp["namespace"]},
                "spec": {
                    "nodeSelector": {"oce-role": "control"},
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
                            "image": controller,
                            "command": ["node", "-e", "setInterval(()=>{},1000)"],
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "readOnlyRootFilesystem": True,
                                "capabilities": {"drop": ["ALL"]},
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
                                "claimName": cp["bootstrapPasswordClaimName"],
                                "readOnly": True,
                            },
                        }
                    ],
                },
            }
            apply(reader)
            kubectl(
                "-n",
                cp["namespace"],
                "wait",
                "--for=condition=Ready",
                "pod/bootstrap-reader",
                "--timeout=120s",
            )
            key = kubectl(
                "-n",
                cp["namespace"],
                "exec",
                "bootstrap-reader",
                "--",
                "cat",
                "/bootstrap/initial-admin-service-key.json",
                log_output=False,
            )
            key_path = work / "service-key.json"
            key_path.write_bytes(key)
            # The production API binds its Pod IP. Use an explicitly allowed client
            # for the test connection; the relay is fixture-only and carries no key.
            client = cp["apiClients"][0]
            kubectl("create", "namespace", client["namespace"])
            api_ca = work / "api.crt"
            run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                 "-days", "1", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
                 "-keyout", work / "api.key", "-out", api_ca])
            secret("api-client-tls", {"server.crt": api_ca.read_text(), "server.key": (work / "api.key").read_text()},
                   namespace=client["namespace"])
            api_origin = "https://127.0.0.1:18080"
            api_tls = ssl.create_default_context(cafile=api_ca)
            api_port = (chart_values["api"] | values.get("api", {}))["port"]
            apply(
                {
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {
                        "name": "api-client",
                        "namespace": client["namespace"],
                        "labels": client["podLabels"],
                    },
                    "spec": {
                        "nodeSelector": cp["nodeSelector"],
                        "restartPolicy": "Never",
                        "automountServiceAccountToken": False,
                        "securityContext": reader["spec"]["securityContext"],
                        "containers": [
                            {
                                "name": "client",
                                "image": controller,
                                "securityContext": reader["spec"]["containers"][0][
                                    "securityContext"
                                ],
                                "command": [
                                    "node",
                                    "-e",
                                    """
const net = require('node:net'), tls = require('node:tls'), fs = require('node:fs');
tls.createServer({cert:fs.readFileSync('/tls/server.crt'),key:fs.readFileSync('/tls/server.key')}, client => {
  const upstream = net.connect(Number(process.env.API_PORT), process.env.API_HOST);
  client.pipe(upstream).pipe(client);
  client.on('error', () => upstream.destroy());
  upstream.on('error', () => client.destroy());
}).listen(8080, '0.0.0.0');
""",
                                ],
                                "env": [
                                    {
                                        "name": "API_HOST",
                                        "value": f"openclaw-enterprise-api.{cp['namespace']}.svc.cluster.local",
                                    },
                                    {"name": "API_PORT", "value": str(api_port)},
                                ],
                                "volumeMounts": [{"name": "tls", "mountPath": "/tls", "readOnly": True}],
                                "readinessProbe": {
                                    "tcpSocket": {"port": 8080},
                                    "periodSeconds": 1,
                                },
                            }
                        ],
                        "volumes": [{"name": "tls", "secret": {"secretName": "api-client-tls", "defaultMode": 0o440}}],
                    },
                }
            )
            kubectl(
                "-n",
                client["namespace"],
                "wait",
                "--for=condition=Ready",
                "pod/api-client",
                "--timeout=120s",
            )
            forward = subprocess.Popen(
                [
                    str(x)
                    for x in [
                        *kube,
                        "-n",
                        client["namespace"],
                        "port-forward",
                        "pod/api-client",
                        "18080:8080",
                    ]
                ],
                stdout=logs,
                stderr=logs,
            )
            try:
                deadline = time.monotonic() + 30
                while True:
                    try:
                        with urllib.request.urlopen(
                            api_origin + "/healthz", timeout=2, context=api_tls
                        ) as response:
                            require(response.status == 200, "API health failed")
                        break
                    except OSError:
                        require(
                            forward.poll() is None and time.monotonic() < deadline,
                            "API port forward failed",
                        )
                        time.sleep(1)
                response = json.loads(
                    run(
                        [
                            artifact / "bin/occ",
                            "--url",
                            api_origin,
                            "--ca-bundle",
                            api_ca,
                            "--service-key-file",
                            key_path,
                            "installation",
                            "get",
                            "--output",
                            "json",
                        ]
                    )
                )
                require(
                    response["id"] == json.loads(key)["meta"]["installationId"],
                    "authenticated Installation identity mismatch",
                )
                steps.append("packaged occ authenticated Installation request")
                if release.get("presets"):
                    def occ(*args):
                        return json.loads(run([
                            artifact / "bin/occ", "--url", api_origin, "--ca-bundle", api_ca,
                            "--service-key-file", key_path, "--output", "json", *args,
                        ]))

                    namespace = occ("namespace", "create", "Bundle preset check")
                    namespace_id = namespace["id"]
                    # Follow OCE's production-agents procedure: its worker can
                    # create the Namespace but needs tenant-local RoleBindings.
                    deadline = time.monotonic() + 60
                    while True:
                        tenants = json.loads(kubectl("get", "namespaces", "-l", f"openclaw.dev/namespace={namespace_id}", "-o", "json"))["items"]
                        if tenants:
                            require(len(tenants) == 1, "test Namespace backing resource is ambiguous")
                            tenant = tenants[0]["metadata"]["name"]
                            break
                        require(time.monotonic() < deadline, "test backing Namespace was not created")
                        time.sleep(1)
                    for name, role, account in (
                        ("worker", "worker", "worker"),
                        ("api-secrets", "api", "api"),
                        ("api-configuration", "configuration", "api"),
                    ):
                        apply({
                            "apiVersion": "rbac.authorization.k8s.io/v1", "kind": "RoleBinding",
                            "metadata": {"name": "openclaw-enterprise-" + name, "namespace": tenant},
                            "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": cp["releaseName"] + "-openclaw-tenant-" + role},
                            "subjects": [{"kind": "ServiceAccount", "name": "openclaw-enterprise-" + account, "namespace": cp["namespace"]}],
                        })
                    steps.append("documented tenant-local RoleBindings on the owned test Namespace")
                    deadline = time.monotonic() + 180
                    while occ("namespace", "get", namespace_id)["status"] != "ready":
                        require(time.monotonic() < deadline, "preset test Namespace did not become ready")
                        time.sleep(1)

                    def seeded():
                        result = occ("--namespace", namespace_id, "preset", "list")
                        items = result if isinstance(result, list) else result["items"]
                        return {
                            p["name"]: occ("--namespace", namespace_id, "preset", "get", p["id"])
                            for p in items
                        }

                    before = seeded()
                    if release.get("includeDefaultPresets") is False:
                        require(set(before) == {p["name"] for p in release["presets"]}, "unexpected seeded preset choices")
                    for selected in release["presets"]:
                        expected = load(artifact / "oce" / selected["path"].removeprefix("/app/"))
                        require(selected["name"] in before and before[selected["name"]]["template"] == expected["template"], "selected RAW preset was not automatically seeded")
                    steps.append("selected RAW presets automatically seeded with exact templates")
                    if release.get("includeDefaultPresets") is False:
                        edited = before[release["presets"][0]["name"]]
                        edited["template"]["variables"]["name"]["description"] = "Retained installation edit"
                        request = urllib.request.Request(
                            f"{api_origin}/namespaces/{namespace_id}/presets/{edited['id']}",
                            method="PATCH", data=json.dumps({"template": edited["template"]}).encode(),
                            headers={"content-type": "application/json", "x-api-key": json.loads(key)["data"]["key"]},
                        )
                        with urllib.request.urlopen(request, timeout=30, context=api_tls) as response:
                            updated = json.load(response)["data"]
                        require(updated["template"] == edited["template"], "native Preset update did not retain the edited template")
                    if baseline:
                        installation_id = json.loads(key)["meta"]["installationId"]
                        kubectl("-n", cp["namespace"], "annotate", "secret", installation_settings["secretName"],
                                "openclaw.dev/installation-id=" + installation_id)
                        live = json.loads(run(["helm", "get", "values", cp["releaseName"],
                                              "--kubeconfig", kubeconfig, "--kube-context", context,
                                              "--namespace", cp["namespace"], "--output", "json"]))
                        save(rendered / "values.yaml", live)
                        run(["bash", candidate / "oce/scripts/upgrade-production-images",
                             "--kubeconfig", kubeconfig, "--context", context,
                             "--namespace", cp["namespace"], "--release", cp["releaseName"],
                             "--values", rendered / "values.yaml", "--installation", rendered / "installation.yaml",
                             "--controller-image", candidate_controller,
                             "--source-revision", candidate_release["sources"]["oce"]["commit"],
                             "--evidence-dir", work / "upgrade-evidence", "--occ", candidate / "bin/occ",
                             "--timeout-seconds", "600"], cwd=candidate / "oce", timeout=900,
                            env=dict(os.environ, OCC_URL=api_origin, OCC_SERVICE_KEY_FILE=str(key_path), OCC_CA_BUNDLE=str(api_ca)),
                            diagnostics=True)
                        artifact = candidate
                        require(occ("installation", "get")["id"] == installation_id, "upgrade replaced the Installation")
                        require(occ("namespace", "get", namespace_id)["status"] == "ready", "upgrade lost the Namespace")
                        require(resource("deployment", "openclaw-enterprise-api")["spec"]["template"]["spec"]["containers"][0]["image"]
                                == candidate_controller, "upgrade did not select the candidate controller")
                        steps.append("selected previous bundle upgraded through packaged OCE helper and database migrations")
                    kubectl("-n", cp["namespace"], "rollout", "restart", "deployment/openclaw-enterprise-api")
                    kubectl("-n", cp["namespace"], "rollout", "status", "deployment/openclaw-enterprise-api", "--timeout=180s")
                    after = seeded()
                    for selected in release["presets"]:
                        require(after[selected["name"]]["id"] == before[selected["name"]]["id"], "controller restart duplicated or replaced an existing preset")
                        require(after[selected["name"]]["template"] == before[selected["name"]]["template"], "controller restart replaced an installed preset template")
                    steps.append("controller restart preserves existing preset identities and edits")
            finally:
                forward.terminate()
                forward.wait(timeout=15)
        except Exception:
            if kubeconfig.exists():
                diagnostic = subprocess.run(
                    [
                        "kubectl",
                        "--kubeconfig",
                        str(kubeconfig),
                        "--context",
                        context,
                        "get",
                        "pods",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ],
                    capture_output=True,
                    timeout=30,
                )
                if diagnostic.returncode == 0:
                    for pod in json.loads(diagnostic.stdout)["items"]:
                        status = pod.get("status", {})
                        print(
                            json.dumps(
                                {
                                    "pod": pod["metadata"]["name"],
                                    "namespace": pod["metadata"]["namespace"],
                                    "phase": status.get("phase"),
                                    "containers": [
                                        {
                                            "name": c["name"],
                                            "ready": c.get("ready"),
                                            "reason": next(
                                                (
                                                    v.get("reason")
                                                    for v in c.get("state", {}).values()
                                                ),
                                                None,
                                            ),
                                        }
                                        for c in status.get("initContainerStatuses", [])
                                        + status.get("containerStatuses", [])
                                    ],
                                }
                            ),
                            file=sys.stderr,
                        )
            raise
        finally:
            run(["k3d", "cluster", "delete", cluster])
            clusters = json.loads(run(["k3d", "cluster", "list", "-o", "json"]))
            require(
                not any(c["name"] == cluster for c in clusters),
                "owned cluster cleanup incomplete",
            )
    save(
        args.output,
        {
            "status": "passed-package-installation",
            "artifactSha256": digest(archive.read_bytes()),
            "releaseId": candidate_release["id"],
            "controller": candidate_controller,
            "architecture": "linux/" + arch,
            "referenceEnvironment": "disposable k3d with PostgreSQL TLS, restricted database roles, cert-manager and Envoy Gateway",
            "checks": steps,
            "cleanup": "completed",
            "customerQualified": False,
            "scope": "package installation and bootstrap; no provider, ingress, Agent turn or customer acceptance",
            **({"upgrade": {"status": "passed-retained-installation-upgrade",
                 "fromReleaseId": baseline["releaseId"], "artifactSha256": baseline["artifactSha256"],
                 "scope": "retained Installation, Namespace, preset identities and edits; database migration and controller upgrade; no running Agent rollout"}} if baseline else {}),
        },
    )
    print(
        "Extracted package installation and authenticated occ check passed; owned cluster removed"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--controller", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--logs", required=True)
    parser.add_argument("--baseline")
    parser.add_argument("--baseline-controller")
    try:
        exercise(parser.parse_args())
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        sys.exit(f"package installation check: {error}")
