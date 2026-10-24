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

Acceptance must prove raw local-GPU input, redacted cloud input, refused
analyzer failure, on/off changes without a cohost restart and recovery after
Moss/cohost/box restart. A2A and artifact export need their own configured
mounts and real acceptance; the empty list does not imply coverage.
