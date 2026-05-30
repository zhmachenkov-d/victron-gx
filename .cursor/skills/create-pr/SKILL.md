---
name: create-pr
description: Create pull requests with Conventional Commits-style titles and descriptions based on the repository pull request template. Use when the user asks to create, open, draft, prepare, or write a PR or pull request.
---

# Create PR

## Instructions

When creating or drafting a pull request:

1. Inspect the branch diff, commit history, and current working tree before writing the PR.
2. Use a Conventional Commits-style PR title:

   ```text
   <type>[optional scope]: <description>
   ```

3. Choose the PR title type from the actual change:
   - `feat`: new user-facing functionality
   - `fix`: bug fix
   - `docs`: documentation-only change
   - `refactor`: code change that is neither a feature nor a fix
   - `test`: adding or correcting tests
   - `chore`: project maintenance or tooling
   - `ci`: CI configuration
   - `build`: build or dependency changes

4. Fill the PR body using `.github/pull_request_template.md` when it exists. Preserve the template section order and headings.
5. Replace placeholder prompts with concrete details from the diff. Do not leave empty placeholders such as "What changed:" without an answer.
6. Mark checklist items that are supported by the change or by commands already run. Leave unchecked items that still require manual validation.
7. Mention test commands and results exactly enough for a reviewer to understand what was verified.
8. Keep the body concise and reviewer-oriented. Explain why the change exists, not every edited file.

## Default PR Body Shape

If the repository has no pull request template, use:

```markdown
## Summary

- [What changed]
- [Why it changed]

## Validation

- [Commands run, or "Not run" with reason]

## Risk / impact

[Reviewer-relevant risk, migration, or rollout notes]
```

## Examples

Title:

```text
chore(cursor): add commit quality gate
```

Body excerpt:

```markdown
## Summary

- What changed: Added a Cursor hook that runs Ruff formatting, Ruff linting, and pytest before `git commit`.
- Why it changed: Keeps Home Assistant integration changes aligned with project quality checks before they enter review.

## Home Assistant validation

- [x] `ruff format .`
- [x] `ruff check .`
- [x] `pytest`
- [ ] Loaded in Home Assistant (if integration behavior changed)
- [ ] Config flow tested (if setup flow changed)
```
