# Qualify an existing cohost upgrade

Use the shared sudostack cold checkpoint through the pinned Edge action. Keep
existing units/drop-ins, data, identities, model routes and the Moss database.
The installed Moss/cohost pair is an actual product runtime, not a disposable
Agent fixture. A source or placement receipt does not prove an upgrade.

The common [runtime preparation and authority design](https://github.com/sudoprivacy/sudostack/blob/main/docs/design/cohost-deploy-and-domain-join.md#runtime-preparation)
defines the package/bootstrap path and the distinction between device deploy,
managed Session control and Agent collaboration. Edge supplies the device
profile and invokes the pinned Stack actions. The current DGX browser profile
keeps local Moss and its cohost; its existing execution is the acceptance
target. A cohost binary already contains Nexus and scode, while standalone CLI
local execution already has an in-process Kernel.

Initial SSH delivery and a future enrolled-device request use the same local
deploy entry. Host permissions currently come from the SSH OS account; a
machine-enforced bounded deploy delegation and the unified package/bootstrap
entry remain pending. Their product design is shared in Stack, rather than
being implemented as another Edge authentication or download protocol.

The controlled DGX upgrade has now run through the pinned shared selection
action on the existing three-service product. Both Nexus services and official
Moss 0.1.78 passed authenticated readiness. The stable controller instance,
32-session startup inventory, original Agent/owner/durable SID/repository and
the old 18-message projection were preserved. Three real local-Qwen turns,
including a dependent reply and reattach/recall, passed with original model and
content-policy configuration unchanged. The actual Moss product retains its
execution. Cross-domain join and seven-party delivery have not been qualified.

For another device, use the same source-owned steps with a private device
profile, rather than copying this device's credentials or identity:

1. Inspect actual service executables, entries, environments and every drop-in;
   pin their hashes and all durable/native configuration roots. Obtain the
   product's actual controller instance and existing session binding through
   the Moss producer checkers. Prepare only a missing stable instance setting;
   do not replace it with a random ID.
2. Stage immutable architecture/source/digest-verified cohost and Moss artifacts.
   Qualify their real migrations and original-session recovery on cold copies
   with the product's complete model cache, loopback dependency and installed
   post-start recovery action. The sandbox owns all copied executions/cleanup.
3. Run `prepare-product-selection.py` as described below. Review its native
   systemd validation and exact shared selection plan; preparation activates
   nothing.
4. Apply that plan through the exact-pinned `stack-action.py selection apply`.
   Preserve the private cold checkpoint, configuration backups and receipt.
   The shared action owns the maintenance transaction and actual process pins.
5. Run native Node-mTLS readiness and the producer's same-owner existing-session
   checks against the actual product. An explicit model-journey acceptance uses
   that original session and its existing REST/WebSocket/model route. It adds
   real messages to that session; ordinary readiness must not silently submit
   model turns. Keep private payload logs on the device and export bounded
   hashes, counts and native identity bindings in the deployment receipt.
6. Record domain join as pending until the native identity, scoped authority,
   local content-gated forwarding and actual receive/commit checks pass. CA
   registration or a visible directory does not complete that step.

The following earlier failures and their corrections are retained as recovery
evidence; the old restart/storage-only checks are not substitutes for the later
real deployment and model journey.

The 2026-10-24 DGX maintenance preserved 32 sessions, 77 attempts and 547 events.
The original execution cohost restarted on its original bytes. Moss initially
refused startup twice because its previous heartbeat was still live while
`MOSS_INSTANCE_ID` was unset; the existing restart policy later recovered it and
`/readyz` returned 200. Preserve that negative evidence. A subsequent deploy
must persist the actual controller's instance identity using the native Moss
configuration contract and verify application readiness, rather than treating
MainPID existence as successful restoration or bypassing the peer guard.

Run the producer's offline checks on another copy of the checkpoint first.
The selected f6cb2593 cohost's `doctor` read all four legacy Raft zones without
alarms. This checks storage health; it does not boot a daemon, recover native
session history or prove a model call.

`tests/cohost-checkpoint-boot.py` is the next bounded compatibility check. Its
profile pins the candidate/probe, a host network namespace id, and exact
original-path to cold-copy mount bindings. It refuses ordinary host execution
before starting a candidate. A reviewed, one-shot OS sandbox must provide a
different network namespace, read-only host filesystem, writable private copy
and those bind mounts. Run as the original unprivileged device user with no
capabilities. Public/native protocol sources and installed gRPC dependencies
are supplied by the pinned device profile, not generated as another runtime.

The read-only Node-mTLS probe compares the actual process directory's Agent,
owner, zone and state bindings against a baseline from the restored old cohost.
The v0.8.3 directory is an in-memory DashMap: its 24 terminated entries vanished
on the original-version restart, while the 32 durable Moss sessions remained.
An initial checker incorrectly expected those 24 records to persist and failed
before isolation. Preserve that failed baseline and source correction. An empty
process baseline can qualify boot/control readiness; it cannot prove durable
Agent identity or native history recovery.
It starts no Agent or model request. Logs and clone credentials stay private
on the device. No existing service, deployment or global entry is changed by
this isolated boot check. A platform denial of isolation must be resolved via
the supported operator approval path; do not run the duplicate identity on the
ordinary network to obtain a green result.

Passing this check still leaves native history/owner recovery, real Moss
session resume, local model/content-gate behavior, controlled activation and
cross-domain join/AuthN/AuthZ to qualify. Preserve pre/post-admission Unknown
semantics and actual reader guarantees in subsequent A2A tests.

For the complete product check, `tests/product-checkpoint-boot.py` reuses the
same OS boundary verifier. A private device profile binds cold copies of both
Nexus stores/identities, controller credentials and Moss home at their original
paths. It starts the pinned primary Nexus, execution cohost and producer Moss
entry in order, with each original environment kept in a private file. Both
Nexus instances must pass the native mTLS probe; Moss must become HTTP-ready
under the preserved configured instance ID. Existing session/attempt/event
counts must remain. Children stop in reverse order with bounded cleanup and
any forced cleanup is retained. The process test starts no Agent and does not
claim native history resume, a model call or a domain join from HTTP readiness.

An explicit `mossProductProbe` additionally selects the producer's pinned
existing-session recovery program and the recorded original session ID. The
startup count assertions run first, unchanged. Only then may the same-owner
session be resumed through Moss, its native binding verified, and its live
Nexus owner/Agent identity observed. There must still be the original logical
session count and exactly one new execution attempt. The ordinary native
directory probe remains strict about zero live Agents; only the explicit
`--live-agent` mode accepts that one preserved identity. No model turn is
submitted, and recovered-context correctness with the real model remains a
separate gate. The enclosing sandbox still owns all child cleanup.
Before stopping the product services it uses the same producer program's
explicit `--terminate-existing` action for that same owned copied session.
This ends the recovered execution through Moss; it does not delete history or
resume a second session. Native cleanup failure remains a failed case, and
the outer service manager must also observe an empty process group. Normal
exit of only the direct children is insufficient for a clean-close claim.
`mossProductProbe.liveModelJourney: true` explicitly opts into the producer's
three-turn real-model journey on that same copied existing session. It uses
the shared deployed REST/WebSocket protocol: arithmetic, a dependent reply,
then reattach and recall. Original provider/model settings remain unchanged.
Each model turn retains the existing live journey's 180-second deadline and
each WebSocket hello 30 seconds. This distinct full journey has an explicit
1080-second parent probe budget; the resume-only budget remains 240 seconds.

If the existing provider uses a real host loopback model endpoint, an explicit
`loopbackDependency` supplies the pinned Stack `qualification_endpoint.py`,
its private host-side Unix socket and that exact port. The fixture starts only
the namespace-side transport before the product, then closes it after all
product children. The operator must start and close the corresponding host
transport. Provider URLs, discovery responses, authentication and model policy
remain the product's original values; no model catalog is synthesized. This
grants access only to the selected host loopback service, not the production
Nexus listeners or a general network route.

A raw executable launch does not replay a systemd unit's recovery transaction.
If the real product has `ExecStartPost` model-route recovery, its private
qualification profile must supply that exact pinned Node entry as `postStart`.
It runs with the original service environment after authenticated startup and
before Moss starts, retaining the installed recovery action's 180-second bound.
Bind its backend cache to a private cold copy too. Omitting this action can
leave `.prompt` writes without a live model backend even though process and
REST readiness succeeded. Keep that failure as evidence; do not substitute a
direct provider request to bypass the native mount or its content policy.

For a controlled existing-product upgrade, `scripts/prepare-product-selection.py
PRIVATE_PROFILE NEW_PRIVATE_DIRECTORY` inspects the actual user-service
executables, arguments, main units and every drop-in through the pinned Stack
boundary. Its versioned profile contains `exclusiveConfigurationOwner: true`,
the complete `checkpoint` plan and exactly one `versions` entry per service:
`unit`, source commit `source`, candidate `binary` and `sha256`, optional
`entry: {before, path, sha256}`, and optional `workingDirectory`. The original
application entry and native units/drop-ins must already be checkpoint pins.

The preparer preserves unit bytes outside the selected executable, application
entry and working directory. It refuses ExecStart overrides in drop-ins or
commands requiring runtime expansion, verifies the new units with native
`systemd-analyze`, and emits private prepared units plus a shared selection
plan. Preparation changes no service or existing configuration. Apply that
exact plan with `scripts/stack-action.py selection apply --plan PLAN --output
NEW_EVIDENCE` under the same exclusive owner. Stack owns stopping, checkpoint,
file selection, reload and process verification; Edge then checks native
readiness and the original-session model journey. Existing model-route and
content-policy drop-ins remain in place. A failure after selection keeps
services stopped for native recovery rather than auto-restoring an old DB.

After selection, the same thin entry invokes shared existing-product
qualification: `scripts/stack-action.py product inspect --plan PRIVATE_PLAN
--output NEW_PRIVATE_EVIDENCE`, followed by the explicit `product apply` at
the product's natural quiet point. The new pinned Moss producer's
`--inspect-existing` mode first authenticates and reads exactly the original
session without resuming it. Stack compares that original owner/history,
then calls the producer's three-turn model and reattach journey and checks the
recorded native Agent/SID/repository binding. It checks the actual Moss process
and unchanged private configuration before and after. The producer and Node
runtime are source/digest pinned; no package installation runs on the DGX.

Keep the native producer/configuration paths, original session metadata and
current history hash in the private versioned qualification plan documented in
Stack's `docs/deployment/agent-host.md`. Evidence must be new. Submission is
recorded before model execution; an uncertain model result is never retried.
The original Moss execution remains owned by the product, with no service stop
or global-entry change as cleanup. This is authenticated product qualification;
the receipt still reports `domainJoinAccepted:false` until native joining and
actual cross-domain delivery have independently passed.

`scripts/nexus/probe-checkpoint.cjs PROFILE --existing-agent` records the same
native owner/Agent binding even if its execution has ended. It reports the
actual state and `executionActive` separately. This is the pre-resume
observation, never proof of a live receiver. The existing `--live-agent` mode
continues to refuse a terminated execution and remains the post-resume check.
Historical terminated execution records may remain for that same owner/Agent.
The live check requires exactly one active execution and refuses another owner
or Agent even in historical records; two active executions also refuse. The
cold-copy no-live/count/hash baseline is separate and remains strict.
