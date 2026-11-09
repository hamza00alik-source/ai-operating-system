# MCP discovered tool catalogue

The Owner Console's **Test connection** action performs an owner-triggered, read-only
MCP initialize and `tools/list` handshake. It now persists the returned tool names,
descriptions, JSON input schemas, discovery timestamps, and SHA-256 schema fingerprints.

## Safety properties

- No tool is invoked during discovery.
- Only enabled, registered servers can have a catalogue persisted.
- Tool names must be unique and bounded; the catalogue is capped at 100 tools.
- Input schemas are limited to 64 KiB and checked as JSON Schema Draft 2020-12.
- External `$ref` and `$dynamicRef` references are rejected to prevent remote schema
  retrieval during validation.
- Schema replacement is atomic per server and recorded in the immutable audit log.
- Agent proposals must match the department allowlist and validate against the
  currently stored schema for an enabled server.
- The schema fingerprint is included in the proposal fingerprint so later execution
  can detect schema drift.
- MCP execution remains disabled. Owner approval records a decision only.

## Refreshing a catalogue

An owner must explicitly use **Test connection** after registering and enabling an MCP
server. A successful response reports the catalogue count and schema fingerprints.
If a server's tools change, run discovery again; old catalogue entries are replaced
atomically. Proposals without a current discovered schema are rejected.
