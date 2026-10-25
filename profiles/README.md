# Edge egress deployment

This profile protects the external `/cloud-model` mount in **redact** mode.
The local GPU `/model` mount is excluded. Keep their Router credentials and
provider groups separate so a failed local model cannot fall back to a cloud
account with the original prompt.

The analyzer runs on the box at `http://127.0.0.1:59080`; its shared image and
business-policy handling come from
[sudostack](https://github.com/sudoprivacy/sudostack/tree/main/security/egress-gate).
The profile contains no customer values. Configure protected terms, public
company exceptions and whole-record markers in Moss after deployment.

Install `egress-policy.json` as `/etc/sudo/egress-policy.json` and merge
`moss-egress.json` into the current local Moss configuration. For a host cohost,
also set `egressGate.localPolicyFile` to the controller-owned policy file and
`egressGate.localOrganizationId` to the box's actual Moss organization ID.
Both values are required together. The cohost reads that file through
`NEXUS_EGRESS_GATE_CONFIG`; the agent must have read access only.
For Kubernetes owner runtimes, the shared SDK projects the file read-only.

The bootstrap policy seeds fresh Moss storage. Use its **Data egress
protection** page or authenticated settings API for subsequent changes.
The page distinguishes saved and applied revisions. This profile requires a
runtime with the native live-policy service; it does not upgrade a running
binary by itself.

## Local and cloud model selection

Once a compatible Moss and both native model routes are installed, merge
`cohost-model-routing.json` into the current Moss configuration. Build the
native `sudocode.json` and backend configuration through sudostack's shared
`buildCohostModelConfiguration`; use the actual Moss provider IDs as alias
prefixes. For example:

| Moss selection / native alias | Native mount | Router account |
|---|---|---|
| `box-gpu:qwen3-30b` | `/model` | local group only |
| `box-cloud:qwen3-30b` | `/cloud-model` | external group only |

Both aliases may map to the same upstream model ID. Moss retains the provider
prefix when starting the native execution and changing models within that
provider. The engine sends the raw model ID upstream using that route's
credential. A provider switch requires a new session. Qualify an undeclared
alias too: it must refuse without selecting either account.

The routing fragment depends on Moss's provider-qualified cohost support; it
does not create mounts, replace running services or refresh Router credentials.
Use the pinned shared deployment selection and existing-session qualification
in [COHOST_UPGRADE.md](../docs/COHOST_UPGRADE.md). Keep the existing owner, Agent,
history, model-route recovery and private cold checkpoint. Deploy the policy
through a parent directory mounted read-only for the agent; mode 0600 under
the same host user does not provide that isolation.

The candidate [shared provider-route acceptance](https://github.com/sudoprivacy/sudostack/pull/96)
checks local and external accounts against a real native cohost with a synthetic
model upstream. Actual DGX policy activation, real GPU/cloud requests and
restart recovery remain deployment acceptance; the profile is not evidence
that those services already enforce the policy.

Acceptance must prove raw local-GPU input, redacted cloud input, refused
analyzer failure, on/off changes without a cohost restart and recovery after
Moss/cohost/box restart. A2A and artifact export need their own configured
mounts and real acceptance; the empty list does not imply coverage.
