# Code Review Flow Examples

Sample invocations showing different ways to use the code-review-flow skill.

## Examples Overview

### [01-simple-feature.md](01-simple-feature.md)
**Use Case:** Quick review of a simple feature

**Demonstrates:**
- Using commit SHAs from recent command output
- Minimal context gathering
- Simple feature description

**When to use:** Small, self-contained features (< 5 files changed)

---

### [02-github-issue-fix.md](02-github-issue-fix.md)
**Use Case:** Reviewing a bug fix linked to a GitHub issue

**Demonstrates:**
- Getting issue context with `gh issue view`
- Using branch names to infer issue numbers
- Structured requirement documentation from issue

**When to use:** Fixes on `fix-*` branches with associated issues

---

### [03-explicit-commit-range.md](03-explicit-commit-range.md)
**Use Case:** User provides specific SHAs or symbolic references

**Demonstrates:**
- Using provided SHAs directly (no fetching needed)
- Symbolic references (`HEAD~3`, `origin/main`)
- Getting commit context with `git log`

**When to use:** User specifies exact commits to review

---

### [04-anti-patterns.md](04-anti-patterns.md)
**Use Case:** What NOT to do

**Demonstrates:**
- ❌ Compound commands that trigger permission prompts
- ❌ Unnecessary git commands when context exists
- ❌ Missing implementation context
- ❌ Too broad review ranges
- ❌ Ignoring gitStatus information
- ✅ Best practices for each scenario

**When to use:** Reference guide to avoid common mistakes

---

### [05-multi-commit-feature.md](05-multi-commit-feature.md)
**Use Case:** Large feature spanning multiple commits

**Demonstrates:**
- Reviewing complete feature branches
- Using `git log origin/main..HEAD` for commit range
- Comprehensive feature documentation
- Security-focused review requests

**When to use:** Feature branches with 4+ commits, complex implementations

---

## Quick Reference

### Getting Git SHAs (Priority Order)

1. **Symbolic references** (best)
   - `HEAD`, `origin/main`, `HEAD~1`
   - No commands needed!

2. **Context** (fast)
   - Check gitStatus
   - Recent git command output
   - Conversation history

3. **Git log** (simple)
   ```bash
   git log --oneline -5
   ```

4. **Git rev-parse** (last resort)
   ```bash
   git rev-parse origin/main
   git rev-parse HEAD
   ```

### Template Checklist

Every review should include:

- [ ] **What Was Implemented** - Clear description
- [ ] **Requirements/Plan** - Why it was built
- [ ] **Base SHA** - Starting point
- [ ] **Head SHA** - Ending point
- [ ] **Review Focus** (optional) - Specific concerns
- [ ] **After review** - Check for PR and post findings as inline review comments if exists

### Common Patterns

**After implementing a feature:**
```
User: "Review the authentication feature"
→ Use Example 5 pattern (multi-commit)
```

**After fixing a bug:**
```
User: "Review my fix"
→ Use Example 1 or 2 pattern (simple/issue)
```

**User provides SHAs:**
```
User: "Review abc123..def456"
→ Use Example 3 pattern (explicit range)
```

**Before doing anything:**
```
→ Read Example 4 (anti-patterns) to avoid mistakes
```

## Integration with Other Commands

This skill integrates well with:

- **`/request-review`** - Command wrapper for code review
- **`/fix-gh-issue`** - Auto-reviews after implementing fixes
- **`superpowers:requesting-code-review`** - The underlying skill
- **`superpowers:receiving-code-review`** - Handling review feedback

## Posting Review to PR

**After review completes, check if PR exists:**

```bash
# Check for PR on current branch
gh pr list --head $(git branch --show-current) --json number,url
```

**If PR exists**, post findings as inline diff-line comments batched into a single review (the
canonical protocol lives in [../SKILL.md](../SKILL.md#inline-review-protocol)):
```bash
# Resolve the head SHA (never assume local HEAD matches the PR head)
HEAD_SHA=$(gh pr view <pr-number> --json headRefOid -q .headRefOid)

# Private temp dir; auto-cleaned. Never a fixed /tmp path.
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/review.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

# Write each finding body with a SINGLE-QUOTED heredoc (<<'BODY') so backticks / $(...) / $var
# in attacker-controlled diff text are written literally and never executed. Finding text must
# never transit a double-quoted shell word.
cat > "$WORKDIR/b1.md" <<'BODY'
**[Important]** No handling for invalid distance formats.
BODY

# Build review.json with jq — only the SHA is an --arg; bodies come in raw via --rawfile. Each
# file:line finding is an inline anchored comment; un-anchorable findings + the overall
# assessment go in the summary body.
jq -n --arg commit "$HEAD_SHA" \
  --arg body "Automated review — inline findings below." \
  --rawfile b1 "$WORKDIR/b1.md" \
  '{commit_id: $commit, event: "COMMENT", body: $body,
    comments: [ {path: "src/utils/tags.ts", line: 23, side: "RIGHT", body: $b1} ]}' \
  > "$WORKDIR/review.json"

# POST once so the author gets a single notification
gh api repos/{owner}/{repo}/pulls/<pr-number>/reviews --method POST --input "$WORKDIR/review.json"
```

`code-review-flow` always uses `event: "COMMENT"` and **never self-approves** — solo-developer
workflows don't allow it. A finding that can't be tied to a changed diff line goes into the
summary `body` instead, so nothing is dropped.

**Benefits:**
- ✅ Each finding anchors to the exact diff line instead of a wall of text
- ✅ Other reviewers can see the AI review right in the diff
- ✅ Review is preserved with the PR history
- ✅ One review POST = one notification, not N

**If no PR exists:**
- Display review in conversation
- User can create PR later
- Review is still available in chat history

## Tips

1. **Always provide context** - Even if minimal, explain what was built
2. **Keep reviews focused** - One feature/fix per review
3. **Use symbolic refs** - Avoid unnecessary SHA resolution
4. **Check gitStatus first** - Information is already there
5. **Document requirements** - Link to issues, plans, or describe inline
6. **Post to PR if exists** - Keeps review discussion centralized
