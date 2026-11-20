Updates OpenClaw Enterprise and OpenClaw (2026.11.4). Connections stays at 0.3.1.

Before upgrading, review Agent access and sign-in. OCE removes the old per-person Agent runtime role assignments and the `auth.github` Helm settings. Sites using those features should plan their replacement access or OIDC configuration before switching images.

If your Helm values set `agentNativeAdmin.sharedCookieDomain`, keep the live values as the baseline and omit that key from a copy passed as `--candidate-values`. OCE derives the cookie scope from the Console URL and Agent domain.
