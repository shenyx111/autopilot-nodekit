# MCP security notes

MCP servers can be useful, but they increase the tool attack surface.

Recommended rules:

1. Add only servers that directly help the current project.
2. Prefer official or first-party servers.
3. Scope filesystem access to the workspace.
4. Prefer read-only mode for GitHub/Git until mutation is needed.
5. Run local MCP servers in containers or another sandbox when possible.
6. Require human approval for destructive tools, credentials, external publishing, package installation, and writes outside the workspace.
7. Log every tool invocation to an append-only event stream where possible.
8. Never use MCP memory as the only source of truth for task state; keep NodeKit SQLite and raw evidence.

Suggested first MCP additions:

- Context7 for current library documentation.
- GitHub MCP in read-only mode for issue/PR/repo context.
- Filesystem/Git only with tight workspace scoping.
