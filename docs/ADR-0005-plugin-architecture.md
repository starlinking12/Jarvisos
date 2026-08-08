# ADR-0005: Explicitly Allowlisted Plugin Architecture

- **Status:** Accepted
- **Phase:** 5
- **Date:** 2026-08-08

## Context

JARVIS OS needs a controlled extension mechanism without creating a second
execution or authorization system. The existing `ToolRegistry` is already
the backend capability catalogue, while `ToolExecutor` and `SafetyGate` are
the central execution and authorization boundary.

Plugins therefore must extend the existing registry rather than introduce a
parallel tool runner.

## Decision

Phase 5 plugins use a small `jarvis.plugin.json` manifest containing:

- `id`
- `version`
- `name`
- `description`
- `entry_point` (`module:attribute`)
- `requested_permissions`

Manifest discovery is metadata-only and never imports plugin code.

Code loading requires an explicit plugin-id allowlist from
`JARVIS_PLUGINS_JSON`. A plugin is not enabled merely because its manifest is
present on disk.

An allowlisted entry point is a callable factory receiving the existing
`ToolRegistry`. The factory may register normal `ToolSpec` objects, but the
plugin manifest's requested permissions do **not** grant those permissions.
Every invocation continues through the existing:

`DomainAgent -> ToolExecutor -> SafetyGate -> ToolSpec.handler`

path.

## Security properties

1. Plugins are disabled by default.
2. Discovery does not execute code.
3. Only explicitly allowlisted plugin IDs may be imported.
4. Malformed manifests fail closed.
5. Duplicate plugin IDs fail closed.
6. Requested permissions are descriptive metadata, not authorization.
7. Plugins cannot bypass `ToolExecutor` by being registered.
8. Plugin initialization failures are surfaced as plugin load failures rather
   than silently ignored.

## Configuration

Example:

```json
{
  "directories": ["~/.jarvis/plugins"],
  "allowed_ids": ["example.plugin"]
}
```

Set this JSON through `JARVIS_PLUGINS_JSON`. If unset, no plugin directory is
discovered and no plugin code is imported.

## Non-goals

This ADR does not define remote plugin installation, package downloading,
sandboxing of arbitrary third-party Python, signature verification, or a new
permission model. Those require separate security design before being added.
