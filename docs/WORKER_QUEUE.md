## Bounded worker queue (added after initial core)

The independent worker queue provides durable SQLite-backed enqueue/claim/complete/fail operations, atomic lease acquisition, stale-token rejection, expired-lease recovery, and a configurable retry ceiling with a dead-letter state. Payload size, retry count, and lease duration are bounded.

This is queue infrastructure, not yet an autonomous worker process. It deliberately does not execute models, shell commands, browser actions, external integrations, or protected business actions. A separate runner must later connect queue claims to the model gateway and role executor, persist execution-attempt/artifact records, enforce budget policy, and keep owner approvals around protected actions.
