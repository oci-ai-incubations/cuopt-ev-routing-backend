---
name: github
description: Orchestrate PR workflow — open, check, monitor CI, and request review via gh CLI.
user-invocable: true
allowed-tools: Bash, Read, Grep, AskUserQuestion, TaskCreate, TaskUpdate, TaskList, TaskGet
argument-hint: [open-pr|check-pr|monitor-ci|request-review|setup]
---

# GitHub PR Workflow

Orchestrate the PR-based development workflow using the `gh` CLI.

## Arguments

- `$0` (optional) — Sub-command to run. Defaults to `check-pr` if omitted.

| Sub-command | Purpose |
|---|---|
| `setup` | Check gh install + auth, guide user through login |
| `open-pr` | Push branch, create PR targeting main |
| `check-pr` | Show PR status: CI jobs, reviews, merge readiness |
| `monitor-ci` | Watch CI run, auto-fix failures where possible, re-push |
| `request-review` | Add reviewer and trigger the `review_requested` CI event |

## Preflight

Every sub-command starts with:

```bash
gh auth status
```

If this fails, redirect the user to `/github setup` and stop.

Also verify the working directory is inside the `cuopt-ev-routing-backend` repo:

```bash
git rev-parse --show-toplevel
```

## Sub-commands

### `setup`

1. Check `gh` is installed: `gh --version`.
2. Check auth: `gh auth status`.
3. If not authenticated, tell the user to run `gh auth login` interactively
   (Claude cannot do interactive OAuth).
4. Verify the remote is accessible: `gh repo view --json name,owner`.
5. Report success with gh version, authenticated user, and repo name.

### `open-pr`

1. Run preflight.
2. Confirm the current branch is NOT `main`. If on main, ask the user for a
   branch name and create it:
   ```bash
   git checkout -b <branch-name>
   ```
3. Check for uncommitted changes with `git status`. If there are changes, ask
   whether to commit them first.
4. Push the branch:
   ```bash
   git push -u origin HEAD
   ```
5. Create the PR:
   ```bash
   gh pr create --title "<title>" --body "<body>" --assignee dkennetzoracle
   ```
   - Ask the user for a PR title and description, or offer to generate one
     from the commit log.
   - Always assign `dkennetzoracle`.
6. Report the PR URL.

### `check-pr` (default)

1. Run preflight.
2. Find the PR for the current branch:
   ```bash
   gh pr view --json number,title,state,reviews,statusCheckRollup,mergeable,headRefName
   ```
3. If no PR exists, tell the user to run `/github open-pr`.
4. Display a status table:
   - **CI Jobs**: name, status, conclusion for each check.
   - **Reviews**: reviewer, state (approved/changes_requested/pending).
   - **Mergeable**: yes/no/conflicting.
   - **Overall**: ready to merge, needs fixes, or waiting on review.
5. If CI has not triggered yet (no checks), say so explicitly.

### `monitor-ci`

1. Run preflight.
2. Find the latest workflow run for the current branch:
   ```bash
   gh run list --branch "$(git branch --show-current)" --limit 1 \
     --json databaseId,status,conclusion
   ```
3. If a run is in progress, watch it:
   ```bash
   gh run watch <run-id>
   ```
4. If the run **succeeded**, report success and suggest `/github check-pr` or
   `/github request-review`.
5. If the run **failed**:
   a. Get failed job logs:
      ```bash
      gh run view <run-id> --log-failed
      ```
   b. Categorize failures by job:
      - **security-scan**: Ruff bandit issues or pip-audit vulnerabilities.
      - **lint**: Ruff lint/format errors.
      - **test**: pytest failures or coverage below 80%.
      - **build-and-push**: Docker build errors or OCIR auth failures.
   c. For **code failures** (lint, test, security): fix the code, commit,
      and push:
      ```bash
      git add <files>
      git commit -m "fix: resolve CI failures in <job>"
      git push
      ```
      Then re-run this sub-command to monitor the new run.
   d. For **auth/secrets failures** (build-and-push OCIR login, missing
      GitHub secrets): **always escalate to the user**. Claude cannot fix
      GitHub Actions secrets or OCI tenancy issues. Explain which secret is
      missing and how to add it.
   e. Use TaskCreate/TaskUpdate to track multi-step fix attempts.

### `request-review`

1. Run preflight.
2. Verify a PR exists for the current branch.
3. Check CI status — warn the user if CI is not passing.
4. Add the reviewer:
   ```bash
   gh pr edit --add-reviewer dkennetzoracle
   ```
5. Report that review has been requested. This triggers the `review_requested`
   CI event.

## Error Handling

- **Network errors**: Retry once, then escalate to user.
- **Auth failures**: Always escalate — Claude cannot fix credentials.
- **Merge conflicts**: Tell the user to resolve manually, offer to help after
  resolution.
- **Rate limits**: Wait and retry with backoff, inform the user.

## Notes

- The `monitor-ci` loop is the core autonomous feature — it watches,
  diagnoses, fixes code-level failures, and re-pushes.
- Never force-push. Always create new commits for fixes.
- The `build-and-push` CI job requires OCI secrets configured in GitHub —
  these cannot be fixed by code changes.
