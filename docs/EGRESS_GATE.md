# Content egress checks and ecosystem integration

This is the SudoEdge deployment reference for detection points, policy and
acceptance, checked on 2026-10-13. The first diagram in
[Sudo Cloud architecture](https://s.shareone.vip/s/sudo-cloud-plan) is the
deployment direction. Shared component selection and policy configuration are
owned by [sudostack's DLP composition](https://github.com/sudoprivacy/sudostack/blob/95415b0493de52abb6a7bb8dfc7880aee96ebd7f/security/egress-gate/COMPOSITION.md).
The tables below distinguish a supported mechanism from an accepted deployment.

## Who detects, decides and sends

1. A write reaches the sending node's Nexus kernel. A native hook service named
   `egress_gate` claims only configured model and cross-domain transcript paths.
2. Its classifier combines native identifier/credential rules with the optional
   loopback Presidio analyzer. The analyzer applies the deployment's literal
   business policy after upstream recognition.
3. `EgressContentHook::on_pre` applies the policy in that same invocation:
   `Pass`, `Replace(redacted bytes)`, or an error that aborts the write.
4. The model driver sends the stored, permitted prompt after the pre-write step.
   A refused write does not reach that send step.

The refusal is enforced by Nexus, including when the classifier returns an
error. Presidio does not enforce the model call, and Router authorization does
not decide which text is sensitive. The gate and permission provider are
different checks: permission decides whether the caller may write a path;
the content hook decides which bytes may be written there.

## Entry points and boundaries

| Entry point | How it is selected | What is checked | Acceptance as of 2026-10-13 |
|---|---|---|---|
| Outbound model request | `.prompt` beneath a mount in `NEXUS_EGRESS_GATE_MODEL_MOUNTS`, such as `/cloud-model` | Request bytes before the model driver sends them | Actual cohost, mTLS, new-api and real SudoRouter model-write acceptance passed; production browser cloud selection and permanent credentials remain pending |
| Cross-domain agent message | Conversation `transcript` beneath `NEXUS_EGRESS_GATE_A2A_MOUNTS` | Envelope through the sending node's kernel; redaction preserves authenticated authorship fields | Native kernel/stream tests exist; real box-to-cloud agent acceptance remains pending |
| File, batch, stream or pipe write on a claimed plane | `sys_write`, `write_batch`, `stream_write_nowait`, `pipe_write_nowait` use the common mutating-write seam | The same hook and replacement/error outcome | Native kernel integration tests; this does not make every ordinary file an outbound plane |
| Node-local GPU request | `/model` deliberately omitted from outbound model mounts | No outbound content rewriting | Raw local input and visible local model replies passed |
| Local managed-session turns | Local session transcript omitted from outbound A2A mounts | No outbound content rewriting | Native local-session regression; local browser/session checks in [SETUP.md](SETUP.md) |
| Ordinary workspace file or exported artifact | No general artifact/export plane is installed by this gate | No automatic artifact classification | Export, binary/OCR and archives remain pending |
| Direct provider HTTP, shell networking, direct remote-broker writes | Does not pass through the configured sending-node plane | No content gate on that route | Requires the route's own controls; it cannot be counted as gated acceptance |

Empty writes, paths outside the configured planes, and kernel-internal
`/__sys__/` paths pass this content hook. The kernel may still apply other
checks. Compiling the gate does not configure a plane: empty mount lists mean
no traffic is inspected, with a startup warning.

## Detection catalogue

These detectors classify the same claimed write. Under `redact`, actionable
findings become markers such as `[REDACTED:PRC-ID]` or `[REDACTED:PROTECTED_TERM]`.
Native rules scan the request bytes, including structured values. Contextual
recognition and literal business policy receive decoded prose values.

| Detector | Categories or selection | Handling and limits |
|---|---|---|
| Nexus `DeterministicRules` | PRC identity card, mainland mobile, payment card, unified social credit identifier | Checksum/format, carrier-segment and whole-token rules; structured matching does not prove that a value is confidential business information |
| Nexus `CredentialRules` | PEM private keys; recognized OpenAI-compatible, Anthropic, GitHub, AWS, Aliyun, Tencent and Slack credential formats; JWTs; bearer tokens; password/secret/token assignments; URL passwords | Protect matched bytes. Prefix/length and assignment rules have bounded coverage; placeholders and ordinary words have exclusions |
| Loopback Presidio + spaCy | Configured entity types; the box requests `PERSON,LOCATION,ORGANIZATION` | Recognize prose at the configured score threshold; general Chinese recognition has not met admission quality |
| Explicit `protected_terms` | Known customer/contact/contract aliases and internal source/design terms | Case-sensitive literals, including repeated/overlapping matches; configure aliases and case variants explicitly |
| Explicit `protected_markers` | An agreed marker classifies the submitted prose as a protected record | Protect all analyzed prose in that write; this can deliberately redact more than one field |
| `public_organizations` | An exact organization span declared public | Suppress only that `ORGANIZATION` finding; an explicit protection takes precedence |

The contextual prose keys are `body`, `content`, `text`, `system`,
`instructions`, `prompt`, `input`, and `arguments`, plus a bare JSON string.
Model IDs, roles, routing keys and values under other structured keys are not
all sent to contextual recognition. Escaped Unicode prose is decoded before
analysis and findings are mapped back to the original bytes. Unlabelled client
lists, arbitrary structured tool values, obfuscation and business meaning are
not fully covered by this selection.

The shared business analyzer rejects caller allow-lists, ad-hoc recognizers and
unsupported request fields. Entity selection or a high NER threshold cannot
remove the configured literal/marked protection. The policy file is loaded at
worker startup; `/policy` reports its version and hash without tenant values.
Changes require analyzer recreation and another real-write acceptance, not an
existing DLP settings WebUI. See the shared composition for the exact schema.

## Policy and failure matrix

| Condition on a claimed write | `redact` (box default) | `deny` | `observe` | Owner |
|---|---|---|---|---|
| No actionable finding | Allow | Allow | Allow | Nexus hook |
| Sensitive content can be safely rewritten | Redact and allow | Reject | Allow and record the finding | Nexus hook and redaction implementation |
| Analyzer unreachable, deadline exceeded, non-200 response, malformed findings or invalid spans | Reject | Reject | Allow; record classifier failure | Presidio provider reports the error; Nexus hook applies the policy |
| Redaction would split UTF-8, apply an out-of-range span, or rewrite a certain finding on JSON structure | Reject | Reject because a finding exists | Allow because redaction is not attempted | Nexus redaction implementation and hook |
| Probable NER finding only on JSON keys/syntax | Discard the structure finding; preserve valid JSON | Reject if the classification still has an actionable finding | Allow | Nexus policy and redaction implementation |
| Gate built, but invalid policy/mount, requested model driver or analyzer provider absent, or non-loopback analyzer URL | Abort daemon service installation | Same | Same | Nexus boot configuration/provider validation |
| Invalid or missing business policy file | Analyzer worker startup fails; subsequent claimed writes requiring it fail closed | Same | Classifier failure is allowed by this policy | Shared analyzer startup validation, then Nexus hook |

`observe` is a diagnostic option that allows sensitive content and classifier
failures. It cannot establish a confidentiality guarantee. The deployment
default is `redact`, with `on_classifier_error: Deny`; a single failed write
does not switch the whole appliance into `deny` mode.

Redaction changes supported JSON values while preserving syntax; a complete
number can become a quoted marker. Overlapping edits merge. Match audit lines
record caller, path, kinds and counts without repeating the matched value.
This is content-hook audit coverage, not a claim about every application's logs.

## How the runtime forms share the mechanism

| Form | Intended assembly | Required integration and current status |
|---|---|---|
| SudoEdge browser | Local WebUI → local Moss → ManagedAgentService in nexusd-cohost → in-process scode → Nexus mount → local new-api | Local route is deployed. The external route has passed isolated real-wire acceptance; install the permanent gated mount and encrypted credential, then accept browser selection and restart recovery |
| Sudo Cloud | Cloud Moss → nexusd-cluster control plane → user's nexusd-cohost → tenant model mount → SudoRouter | Put the hook and loopback analyzer in the daemon whose kernel receives that tenant's model writes. Configure tenant policy and outbound mounts there; the central broker alone does not inspect a user's pod-local prompt |
| Sudo Private | Customer-managed service form using the same shared assembly | The customer chooses which model and A2A mounts cross its approved boundary. An endpoint outside one process is not automatically outside the customer's trust boundary |
| Standalone scode CLI | Independent CLI process using a model mount on a local gate-bearing Nexus daemon | CLI transport accepts `nexus:///mount` when its filesystem reaches Nexus. Unlike cohost, standalone direct-HTTP configuration is permitted by code; a gate-bearing daemon, filesystem wiring, credential confinement and real CLI acceptance are still required |

Cohost requires mounted model transport and refuses a direct provider URL.
Its profile imports nexusd-cluster's service set and replaces the managed-agent
spawn provider; it keeps the egress service. The independent CLI need not be
migrated into cohost to share the gate. Its deployment must actually route
through the same sending-node kernel, with direct cloud credentials and other
network routes controlled by the deployment.

For the edge, local and external new-api groups use separate tokens. Keep the
local `/model` token local-only, including when the local GPU fails; hold the
external token only in a model mount listed as outbound. Group separation is
Router/deployment enforcement, not a content-hook decision. Cross-domain A2A
must first use the sending node's configured transcript plane; sending straight
to the cloud broker does not establish local DLP coverage.

Implementation ownership remains:

- **nexus-vfs:** service/hook, native rules, provider interface and redaction.
- **sudocode:** CLI/cohost runtime, mounted model transport and its caller errors.
- **sudostack:** common image, policy schema/extensions, composition and evaluation.
- **sudoedge:** device installation, plane selection, Router/network wiring and evidence.
- **Moss/Sudowork:** policy selection/error presentation in user workflows, when implemented.

## Evidence and next acceptance

The checked runtime is sudocode `592c7cb8e839` with Nexus v0.8.3. Its successful
[ARM64 build](https://github.com/sudoprivacy/sudocode/actions/runs/37949464744/job/113884295954)
uses `daemon,driver-ai,egress-gate-presidio`. Running process bytes matched the
released artifact; the journal records `deterministic-prc+credentials+presidio`
and `on_finding: Redact, on_classifier_error: Deny` on `/cloud-model`.

Earlier native identifier/mobile/card captures passed 40 assertions. On
2026-10-13 the verifier rechecked those retained artifacts; model calls were
not repeated. The newer runtime's isolated real-cloud acceptance uses actual
cohost/mTLS → new-api → production SudoRouter `gpt-4.1-mini`, with a node-local
GPUStack/Qwen control. It covers native API-key detection and both agreed
business policy families: redact emits 8 requests, deny emits only the 2 clean
requests, analyzer outage emits none. The local control preserves raw input.
See [the runbook](SETUP.md) for immutable sources, hashes and evidence paths.

Next accept the product paths separately: permanent edge cloud mount/credential
and browser errors; standalone CLI through a gate-bearing daemon; managed cloud
cohost; encrypted credential cold-start restore; actual sender-side A2A; and
artifact export. Held-out business annotations and Chinese recognition quality
remain a separate admission gate. A model-write acceptance does not establish
all of those paths.

## Exact implementation references

- [Native service and environment parsing](https://github.com/nexi-lab/nexus-vfs/blob/v0.8.3/rust/egress_gate/src/lib.rs)
- [Hook decisions and claimed planes](https://github.com/nexi-lab/nexus-vfs/blob/v0.8.3/rust/egress_gate/src/hook.rs)
- [Redaction and malformed-span handling](https://github.com/nexi-lab/nexus-vfs/blob/v0.8.3/rust/egress_gate/src/enforce.rs)
- [Native identifier rules](https://github.com/nexi-lab/nexus-vfs/blob/v0.8.3/rust/egress_gate/src/rules.rs)
- [Native credential rules](https://github.com/nexi-lab/nexus-vfs/blob/v0.8.3/rust/egress_gate/src/credentials.rs)
- [Loopback provider, Unicode mapping and prose selection](https://github.com/nexi-lab/nexus-vfs/blob/v0.8.3/rust/egress_gate/src/presidio.rs)
- [Cohost service composition](https://github.com/sudoprivacy/sudocode/blob/592c7cb8e839de589c0b779af594e2a5976c295f/rust/crates/nexusd-cohost/src/main.rs)
- [Runtime mounted-model requirement](https://github.com/sudoprivacy/sudocode/blob/592c7cb8e839de589c0b779af594e2a5976c295f/rust/crates/api/src/client.rs)
- [Shared business policy and analyzer](https://github.com/sudoprivacy/sudostack/tree/95415b0493de52abb6a7bb8dfc7880aee96ebd7f/security/egress-gate/presidio)

This Markdown file is the source for any ShareOne mirror; keep its remote URL
bound to a reviewed Git version and do not maintain a second editable copy.
