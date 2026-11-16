"""Inspect target prerequisites without writing to Kubernetes or PostgreSQL."""

import ipaddress
import json
import os
import subprocess

from integrity import digest, require


def kubernetes_reader(args):
    def read(*resource):
        return json.loads(subprocess.check_output(
            ["kubectl", "--kubeconfig", args.kubeconfig, "--context", args.context,
             "--request-timeout=15s", "get", *resource, "-o", "json"],
            stderr=subprocess.DEVNULL, timeout=20,
        ))

    return read


def postgres_version(service, minimum):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    for key in ("PGSERVICEFILE", "PGSYSCONFDIR", "PGPASSFILE", "PGSSLROOTCERT",
                "PGSSLCERT", "PGSSLKEY"):
        if key in os.environ:
            env[key] = os.environ[key]
    env.update(PGSERVICE=service, PGCONNECT_TIMEOUT="10")
    result = subprocess.check_output(
        ["psql", "-X", "-w", "-At", "-v", "ON_ERROR_STOP=1", "-c", "SHOW server_version_num"],
        env=env, stderr=subprocess.DEVNULL, text=True, timeout=20,
    ).strip()
    require(result.isascii() and result.isdigit() and int(result) >= 100000,
            "unexpected PostgreSQL version response")
    major = int(result) // 10000
    require(major >= minimum, f"PostgreSQL {major} is below the bundle baseline ({minimum})")
    return {"observedMajor": major, "minimumMajor": minimum}


def api_destinations(read, mode):
    namespace = ("--namespace", "default")
    if mode == "both":
        service = api_destinations(read, "service")
        endpoints = api_destinations(read, "endpoint")
        require(service and endpoints, "could not discover both Kubernetes API Service and backend destinations")
        return service | endpoints
    if mode == "service":
        spec = read("service", "kubernetes", *namespace)["spec"]
        ports = [p["port"] for p in spec["ports"]
                 if p.get("name") == "https" and p.get("protocol", "TCP") == "TCP"]
        return {(ip, port) for ip in spec.get("clusterIPs", [spec["clusterIP"]])
                for port in ports}

    slices = read("endpointslices.discovery.k8s.io", *namespace,
                  "-l", "kubernetes.io/service-name=kubernetes")["items"]
    if slices:
        return {(ip, p["port"]) for s in slices for p in s["ports"]
                if p.get("name") == "https" and p.get("protocol", "TCP") == "TCP"
                for endpoint in s["endpoints"] if endpoint.get("conditions", {}).get("ready") is not False
                for ip in endpoint["addresses"]}
    # Some servers expose the default API backends only through legacy Endpoints.
    subsets = read("endpoints", "kubernetes", *namespace).get("subsets", [])
    return {(a["ip"], p["port"]) for subset in subsets for a in subset.get("addresses", [])
            for p in subset.get("ports", [])
            if p.get("name") == "https" and p.get("protocol", "TCP") == "TCP"}


def api_policy(read, mode, cluster):
    targets = api_destinations(read, mode)
    require(targets, f"could not discover Kubernetes API {mode} destinations")
    cidrs = [ipaddress.ip_network(cidr, strict=False) for cidr in cluster["cidrs"]]
    missed = [f"{ip}:{port}" for ip, port in sorted(targets)
              if port != cluster["port"]
              or not any(ipaddress.ip_address(ip) in network for network in cidrs)]
    require(not missed, "chart cluster.cidrs/port does not cover observed "
            f"Kubernetes API {mode} destinations: {', '.join(missed)}")
    return {"destinationMode": mode, "destinationsMatched": len(targets)}


def ready_node(node):
    return (not node["spec"].get("unschedulable")
            and not any(taint["effect"] in {"NoSchedule", "NoExecute"}
                        for taint in node["spec"].get("taints", []))
            and any(c["type"] == "Ready" and c["status"] == "True"
                    for c in node["status"].get("conditions", [])))


def node_pools(read, values, runtime, architecture, released_architectures):
    arch = architecture.removeprefix("linux/")
    released = {item.removeprefix("linux/") for item in released_architectures}
    require(runtime["nodeSelector"].get("kubernetes.io/arch") == arch,
            "runtime node selector does not match selected architecture")
    nodes = [node["metadata"].get("labels", {}) for node in read("nodes")["items"]
             if ready_node(node)]
    matches = {}
    for role, selector in (
        ("controlPlane", values["controlPlane"].get("nodeSelector", {})),
        ("gateway", runtime["gatewayNodeSelector"]),
        ("runtime", runtime["nodeSelector"]),
    ):
        matches[role] = sum(
            all(labels.get(k) == v for k, v in selector.items())
            and labels.get("kubernetes.io/os") == "linux"
            and labels.get("kubernetes.io/arch") in ({arch} if role == "runtime" else released)
            for labels in nodes
        )
    missing = [role for role, count in matches.items() if not count]
    require(not missing, "no ready, schedulable matching Linux node for: "
            + ", ".join(missing))
    return matches


def storage_classes(read, runtime, bootstrap):
    required = {runtime["gatewayStorageClassName"]}
    if bootstrap:
        required.add(bootstrap)
    for name in sorted(required):
        try:
            read("storageclass", name)
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError(f"could not read selected StorageClass {name!r}") from error
    return {"namedClassesFound": sorted(required)}


def confinement(root, release, runtime, architecture):
    profile = runtime.get("codexSeccompProfile")
    if not profile:
        return {"selected": False, "installedOnNodesVerified": False}
    policy = release["seccomp"]["profiles"][architecture]
    require(digest((root / policy["path"]).read_bytes()) == policy["sha256"],
            "package seccomp digest does not match the released policy")
    node_path = "openclaw/codex-" + policy["sha256"] + ".json"
    return {
        "packagedSha256": policy["sha256"],
        "packagedNodePath": node_path,
        "selectedNodePath": profile,
        "matchesPackagedPolicy": profile == node_path,
        "installedOnNodesVerified": False,
    }


def inspect(args, root, release, values, installation, architecture):
    require(architecture in release["architectures"], "select a released architecture")
    require(not values.get("executionCluster", {}).get("enabled"),
            "this preflight supports only installations with a shared Kubernetes target")
    runtime = installation["drivers"]["compute"]["configuration"]["runtime"]
    require(installation["drivers"]["compute"]["id"] == "compute-kubernetes",
            "this preflight requires OCE Kubernetes Compute")
    require(runtime.get("gatewayNodeSelector"), "missing runtime Gateway node selector")
    read = kubernetes_reader(args)
    report = {"mode": "read-only", "workloadConnectivityVerified": False,
              "workloadConfinementVerified": False, "checks": {}}
    for name, check in (
        ("postgres", lambda: postgres_version(args.pg_service, release["postgresMinimumMajor"])),
        ("kubernetesApiPolicy", lambda: api_policy(read, args.api_policy_destination, values["cluster"])),
        ("nodePools", lambda: node_pools(read, values, runtime, architecture, release["architectures"])),
        ("storageClasses", lambda: storage_classes(read, runtime, args.bootstrap_storage_class)),
        ("seccomp", lambda: confinement(root, release, runtime, architecture)),
    ):
        try:
            report["checks"][name] = {"ok": True, **check()}
        except (OSError, subprocess.SubprocessError):
            report["checks"][name] = {
                "ok": False, "error": "inspection failed; check local tool, access and target settings",
            }
        except (ValueError, KeyError, TypeError) as error:
            report["checks"][name] = {"ok": False, "error": str(error)}
    report["ok"] = all(check["ok"] for check in report["checks"].values())
    return report
