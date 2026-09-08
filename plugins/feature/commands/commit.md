---
description: Creates a git commit whose message summarizes the changes, in the language of the repo's history
---

Create a git commit with a message describing what the changes were about.

Steps:
1. Run in parallel:
   - `git status` (without `-uall`)
   - `git diff` (staged and unstaged)
   - `git log --oneline -10` for the style of previous commits
2. Analyze the changes and propose a concise commit message (1 line, ideally under 72
   characters). Focus on the "why" / "what changes", not a file listing. **Write it in the
   language the repo's existing commits use**, and match their tone and style (capitalization,
   trailing period, imperative vs. noun phrase — copy whatever the history does). If the
   history is empty or mixed, use English.
3. In parallel:
   - `git add` the specific relevant files (never `-A`, never `.`)
   - `git commit -m "<message>"` via HEREDOC, WITHOUT a Co-Authored-By line and WITHOUT any
     mention of Claude
4. Then `git status` to verify.

Rules:
- NEVER commit files that look like secrets (`.env`, credentials, etc.)
- NEVER use `--no-verify` or `--amend` unless the user explicitly asks
- NEVER push
- No emoji, no Co-Authored-By line
