---
name: wiki
description: "Generates or updates the project's technical wiki in docs/wiki/ following the LLM-wiki pattern — discovers the stack itself, assumes nothing"
---

This is the `/feature:wiki` command of this plugin. Codex migrates only short Claude Code commands to
skills on its own, and this one is too long, so the skill points at it instead of copying it.

Read `../../../commands/wiki.md` (relative to this file) in full and follow it as the command. The
user's text after the skill mention is the command's argument.
