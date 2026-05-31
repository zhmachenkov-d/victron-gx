---
name: handoff
description: Compact the current conversation into a handoff document for another agent to pick up.
argument-hint: "What will the next session be used for?"
---

Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save it to the temporary directory of the user's OS, not the current workspace. In your final response, include the exact absolute path where the handoff was saved.

Use a filename that is easy to identify later, such as `cursor-handoff-<repo-or-topic>-<YYYYMMDD-HHMM>.md`.

## Required structure

The handoff must include these sections:

1. **Purpose / next-session focus** - what the next agent is expected to do, using any user-provided arguments to tailor this section.
2. **Current repo state** - repo path, branch if known, notable dirty files, and any important "do not touch" user changes.
3. **Work completed** - concise summary of decisions made and changes already applied.
4. **Important artifacts** - one-line summary plus path or URL for relevant PRDs, plans, ADRs, issues, commits, diffs, logs, or files.
5. **Commands and verification** - commands run and their results, including failures or skipped checks.
6. **Open questions / blockers** - anything unresolved, risky, or requiring user input.
7. **Suggested next steps** - ordered, actionable steps for the next agent.
8. **Suggested skills** - only skills available in the current session, with one sentence explaining when or why to invoke each.

Do not paste large content already captured in other artifacts. Include a one-line summary and reference the artifact by path or URL instead.

Redact sensitive information, including API keys, tokens, passwords, secrets, credentials, personal data, customer data, and sensitive log contents. Preserve useful repo-relative file paths and public issue/PR URLs when they are needed for continuity.

After saving the document, tell the user where it was saved and briefly summarize what it covers.

If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.
