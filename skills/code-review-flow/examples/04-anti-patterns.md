# Example 4: Anti-Patterns to Avoid

## ❌ Anti-Pattern 1: Compound Commands

**DON'T:**
```bash
# This triggers permission prompts!
BASE_SHA=$(git rev-parse origin/main) && HEAD_SHA=$(git rev-parse HEAD) && echo "$BASE_SHA..$HEAD_SHA"
```

**WHY:** Compound commands with variable assignments require shell execution permissions.

**DO INSTEAD:**
```bash
# Run as separate commands
git rev-parse origin/main
```
Then in a separate call:
```bash
git rev-parse HEAD
```

Or better yet, use symbolic references directly:
- **Base:** `origin/main`
- **Head:** `HEAD`

---

## ❌ Anti-Pattern 2: Unnecessary Bash Calls

**DON'T:**
```
User: "Review my last commit"

Assistant runs:
git rev-parse HEAD~1
git rev-parse HEAD
```

**WHY:** For simple cases, you can use symbolic references directly!

**DO INSTEAD:**
```
Task(superpowers:code-reviewer, "Review last commit"):
  Base: HEAD~1
  Head: HEAD
```

Git accepts symbolic references - no need to resolve them to SHAs.

---

## ❌ Anti-Pattern 3: Missing Context

**DON'T:**
```
Task(superpowers:code-reviewer):
  Base: abc123
  Head: def456
```

**WHY:** Code reviewer has no idea what was implemented or why!

**DO INSTEAD:**
```
Task(superpowers:code-reviewer, "Review login feature"):

  ## What Was Implemented
  Added JWT-based authentication with refresh tokens

  ## Requirements
  Issue #543 - Secure login with session management

  Base: abc123
  Head: def456
```

Always provide context about what was built and why.

---

## ❌ Anti-Pattern 4: Too Broad Review Range

**DON'T:**
```
User: "Review my work this week"
Assistant reviews 127 commits from Monday to Friday
```

**WHY:** Too many changes to review meaningfully. Code reviewer will be overwhelmed.

**DO INSTEAD:**
Break into smaller reviews:
- Review per feature/fix
- Review per day
- Review per PR

```
User: "Review today's login feature work"
Assistant: Reviews 3 focused commits
```

---

## ❌ Anti-Pattern 5: Ignoring gitStatus

**DON'T:**
```
Assistant: Let me run git status to see what's changed
```

**WHY:** gitStatus is already in the system prompt! It's provided at conversation start.

**DO INSTEAD:**
```
Assistant: I can see from gitStatus:
  Current branch: fix-1234
  Recent commits show: d0e856b
```

Check the system prompt first before running redundant commands.

---

## ✅ Best Practices Summary

1. **Use symbolic references** (`HEAD`, `origin/main`) instead of resolving to SHAs
2. **Check context first** - gitStatus, recent command output, conversation history
3. **Provide clear context** - explain what was built and why
4. **Keep reviews focused** - one feature/fix at a time
5. **Avoid compound commands** - run git commands separately
6. **Read before running** - check gitStatus before `git status`, etc.

---

## Quick Reference: Getting SHAs

**Priority Order:**
1. **Use symbolic references** - `HEAD`, `origin/main`, `HEAD~1`
2. **Check context** - gitStatus, recent git output
3. **Run simple git log** - `git log --oneline -5`
4. **Last resort** - `git rev-parse` (separate commands)

**Never:**
- Compound commands with `&&`
- Variable assignments `SHA=$(...)`
- Unnecessary command substitution
