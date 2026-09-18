## Version 1.2.2

- Show the running application version in the dashboard.
- Add Get update for stable GitHub releases with verified installer downloads.
- Preserve saved logins, reports, private display-name mappings and scheduling during updates.
- Support encrypted, repository-scoped access to private GitHub releases.
- Prevent updates during active report collection and retain the previous version for rollback.
- Include the Windows startup fix for false port-conflict errors.
- Allow retry after an interrupted update and include current installation instructions.
- Reuse an existing Git sign-in as invicto-labs for private release access, without copying the publishing credential into application storage. Other PCs can use a repository-scoped read-only token.
