# Trusted artifact publication

`Publisher(database, private_store).publish(lease_id=..., worker_session_id=...,
workspace_id=..., fencing_token=..., path=..., artifact=bytes, expected_digest=...)`
receives bounded bytes, never a worker-chosen source file. It validates current
ACTIVE unexpired lease, task revision/state/repository, session, workspace, fence,
lease claims and task scope while holding BEGIN IMMEDIATE on the controller DB.

Objects are content-addressed SHA-256 files created exclusively with O_NOFOLLOW,
fsynced before receipt insertion. Existing objects are checked for type, hard links
and exact content. Receipts are only valid after their DB commit; crash before
commit can leave an unreferenced object for later trusted garbage collection.
There is no cross-filesystem/DB atomicity claim. Retry validates lease freshness
again, including for already present objects. The caller is the trusted publisher,
not a model-selected arbitrary context or tool.

The object store and ancestors must be controlled by the host, never mounted in
worker containers or shared with untrusted writers. File mode is defense in depth,
not tamper-proof storage against the owner/root. This module records immutable
byte artifacts; it does not integrate them into Git, accept a task or execute an
external effect. General publication grants and outbox effects remain pending.
Linux/POSIX directory descriptors are required. Demo includes a lease-backed
publication and releases its lease after the bounded worker operation returns.
