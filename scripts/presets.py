"""Admission policy for curated templates, not installation-owned Configuration."""

import re

from common import require

HOST = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


def reviewed_preset(preset):
    values = preset["template"]["configuration"]["values"]
    require(
        values.get("browser", {}).get("enabled") is False
        and values["browser"].get("noSandbox", False) is False,
        "curated presets must disable browser access",
    )
    require(
        values["gateway"]["controlUi"]
        .get("experimental", {})
        .get("customPlugins", False)
        is False,
        "experimental plugin UI requires installation-owner opt-in",
    )
    entries = values["plugins"]["entries"]
    require(
        all(
            entries.get(name, {}).get("enabled", False) is False
            for name in ("browser", "slack", "msteams")
        ),
        "optional browser and channel plugins require installation-owner opt-in",
    )
    tools = values["tools"]
    require(
        tools["elevated"]["enabled"] is False
        and "browser" not in tools.get("alsoAllow", []),
        "curated presets must not grant browser or elevated tools",
    )
    if preset["template"]["agent"]["executionMode"] != "dedicated":
        return
    app = entries["codex"]["config"]["appServer"]
    require(
        app.get("approvalPolicy") == "on-request"
        and app.get("approvalsReviewer") == "user"
        and app.get("sandbox") == "workspace-write",
        "curated Coding requires human approval and workspace confinement",
    )
    proxy = app.get("networkProxy", {})
    require(
        proxy.get("enabled") is True
        and proxy.get("mode") == "limited"
        and proxy.get("baseProfile") == "workspace",
        "curated Coding requires the limited workspace network proxy",
    )
    domains = proxy.get("domains")
    require(
        isinstance(domains, dict)
        and domains
        and all(
            isinstance(host, str)
            and len(host) <= 253
            and HOST.fullmatch(host)
            and permission == "allow"
            for host, permission in domains.items()
        ),
        "curated Coding requires exact named network hosts",
    )
    require(
        proxy.get("unixSockets") == {}
        and all(
            proxy.get(name) is False
            for name in (
                "enableSocks5",
                "enableSocks5Udp",
                "allowUpstreamProxy",
                "allowLocalBinding",
                "dangerouslyAllowNonLoopbackProxy",
                "dangerouslyAllowAllUnixSockets",
            )
        ),
        "curated Coding network escape options must remain disabled",
    )
    require(
        tools["web"]["fetch"]["enabled"] is False
        and tools["web"]["search"]["openaiCodex"]["mode"] == "cached",
        "curated Coding requires cached search without direct web fetch",
    )
