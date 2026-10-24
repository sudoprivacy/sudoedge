# Qualify an existing cohost upgrade

Use the shared sudostack cold checkpoint through the pinned Edge action. Keep
existing units/drop-ins, data, identities, model routes and the Moss database.
The installed Moss/cohost pair is an actual product runtime, not a disposable
Agent fixture. A source or placement receipt does not prove an upgrade.

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

The read-only Node-mTLS probe compares the actual persisted managed Agent,
owner, zone and state bindings against a baseline from the restored old cohost.
It starts no Agent or model request. Logs and clone credentials stay private
on the device. No existing service, deployment or global entry is changed by
this isolated boot check. A platform denial of isolation must be resolved via
the supported operator approval path; do not run the duplicate identity on the
ordinary network to obtain a green result.

Passing this check still leaves native history/owner recovery, real Moss
session resume, local model/content-gate behavior, controlled activation and
cross-domain join/AuthN/AuthZ to qualify. Preserve pre/post-admission Unknown
semantics and actual reader guarantees in subsequent A2A tests.
