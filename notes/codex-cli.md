Run Codex non-interactively

Usage: codex exec [OPTIONS] [PROMPT]
       codex exec [OPTIONS] <COMMAND> [ARGS]

Commands:
  resume  Resume a previous session by id or pick the most recent with --last
  review  Run a code review against the current repository
  help    Print this message or the help of the given subcommand(s)

Arguments:
  [PROMPT]
          Initial instructions for the agent. If not provided as an argument (or if `-` is used),
          instructions are read from stdin. If stdin is piped and a prompt is also provided, stdin
          is appended as a `<stdin>` block

Options:
  -c, --config <key=value>
          Override a configuration value that would otherwise be loaded from `~/.codex/config.toml`.
          Use a dotted path (`foo.bar.baz`) to override nested values. The `value` portion is parsed

## Engine status (probed 2026-08-03)
- codex exec: WORKING + authenticated (CODEX_OK, non-interactive confirmed; use --skip-git-repo-check in worktrees).
- claude -p: BLOCKED — "Failed to authenticate: OAuth session expired". Human must re-auth (claude setup-token recommended for headless).
- NOTE: .claude hooks (protect/gate) only apply to claude workers, NOT codex — codex workers rely on worktree isolation + driver review before merge.
