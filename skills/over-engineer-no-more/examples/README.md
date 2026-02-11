# Over-Engineer No More Examples

Sample scenarios showing how to triage implementation complexity and match execution process to task complexity.

## Core Principle

**Match execution process to implementation complexity.**

Don't launch 33 subagents to add items to arrays. Don't skip review cycles for complex security code.

---

## Examples Overview

### [01-trivial-constants.md](01-trivial-constants.md) 🟢
**Scenario:** Add 5 new country codes to the system

**Demonstrates:**
- Identifying trivial changes (adding constants/data)
- Running triage indicators (7/7 = trivial)
- Direct implementation workflow
- Time/credit savings (8 min vs 2 hours, 1 agent vs 33)

**Indicators:** ✓ Constants, ✓ No logic, ✓ < 100 lines, ✓ < 3 files, ✓ Same module

**Decision:** TRIVIAL → Direct implementation

**When to use:** Adding constants, enums, data structures, simple test updates

---

### [02-complex-feature.md](02-complex-feature.md) 🔴
**Scenario:** Implement GDPR data export API endpoint

**Demonstrates:**
- Identifying complex changes (new features, business logic, security)
- Running triage indicators (0/7 = complex)
- Heavyweight process workflow (subagent-driven development)
- Quality benefits (security review catches issues)

**Indicators:** ✗ New logic, ✗ Multiple packages, ✗ > 300 lines, ✗ Security-critical

**Decision:** COMPLEX → Heavyweight process

**When to use:** New features, APIs, authentication, database migrations, security

---

### [03-simple-bug-fix.md](03-simple-bug-fix.md) 🟢
**Scenario:** Fix email validation regex (doesn't accept plus signs)

**Demonstrates:**
- Bug fixes can be trivial (simple fixes)
- One-line regex change with test
- When direct implementation is appropriate for bugs

**Indicators:** ✓ Simple change, ✓ Isolated, ✓ < 20 lines, ✓ 2 files

**Decision:** TRIVIAL → Direct implementation

**Contrast:** Race condition bugs would be COMPLEX (needs analysis/review)

**When to use:** Simple validation fixes, typos, obvious bugs

---

### [04-anti-patterns.md](04-anti-patterns.md) ❌
**Scenario:** What NOT to do

**Demonstrates:**
- ❌ Over-engineering trivial changes (5 subagents for 3 constants)
- ❌ Skipping triage entirely (blindly launching heavyweight process)
- ❌ Ignoring user signals ("just add..." = trivial)
- ❌ Under-engineering complex changes (security without review)
- ❌ All-or-nothing thinking (gradations exist)
- ✅ Best practices for each scenario

**When to use:** Reference guide to avoid common mistakes

---

### [05-decision-flowchart.md](05-decision-flowchart.md) 📊
**Scenario:** Visual decision tree and quick reference

**Demonstrates:**
- Complete decision flowchart
- Examples categorized by complexity (trivial/middle/complex)
- User signal detection ("just add..." vs "implement auth...")
- Time/credit decision matrix
- Quick reference cheat sheet

**When to use:** Quick lookup for triaging any implementation

---

## Triage Process

### Step 1: Check Indicators

After planning, count TRUE indicators:

- [ ] Just adding constants/enums/data?
- [ ] No new functions or types?
- [ ] No new business logic/algorithms?
- [ ] Just updating data structures + tests?
- [ ] < 100 lines of code?
- [ ] < 3 files changed?
- [ ] Same package/module?

### Step 2: Score & Decide

- **5-7 ✓** = TRIVIAL → Direct implementation
- **3-4 ✓** = MIDDLE → 2-3 focused subagents
- **0-2 ✓** = COMPLEX → Heavyweight process

### Step 3: Announce Decision

```
Plan complete. Checking execution complexity...

Changes required:
- [List specific changes]

This is [TRIVIAL/COMPLEX] because:
- [Reasoning based on indicators]

I'll [implement directly / use subagent-driven development] for:
- [Benefits of chosen approach]

Proceeding with [chosen process].
```

---

## Quick Decision Guide

### Always TRIVIAL:
- Adding constants, enums, items to arrays/lists
- Updating test assertions to match code
- Fixing typos in strings/comments
- Adding fields to types/structs
- Simple variable renames

### Always COMPLEX:
- New API endpoints
- Authentication/authorization logic
- Database migrations
- Security-critical code
- Performance optimizations
- Cross-cutting refactors

### Context-Dependent:
- Bug fixes (validation fix = trivial, race condition = complex)
- Test additions (mirror existing = trivial, new framework = complex)
- Config changes (add env var = trivial, restructure system = complex)

---

## User Signals

### Signals for TRIVIAL:
- "just add..."
- "simple change..."
- "quick fix..."
- "only need to..."
- "trivial..."

### Signals for COMPLEX:
- "new feature..."
- "implement authentication..."
- "refactor the entire..."
- "database migration..."
- "security fix..."

---

## Cost Comparison

### Trivial Task (Add 5 constants)

| Metric | Direct | Over-Engineered |
|--------|--------|-----------------|
| **Time** | 5-10 min | 2-3 hours |
| **Credits** | 1 agent | 30+ agents |
| **Quality** | Perfect | Perfect (same!) |
| **User Experience** | Fast | "Why so slow?" |

**Verdict:** Over-engineering wastes resources for zero quality gain.

### Complex Task (Auth system)

| Metric | Direct | Heavyweight |
|--------|--------|-------------|
| **Time** | 2 hours | 3 hours |
| **Credits** | 1 agent | 15 agents |
| **Quality** | Poor (bugs) | Excellent |
| **User Experience** | Fast but buggy | Thorough |

**Verdict:** Under-engineering sacrifices quality for minimal time savings.

---

## Integration with superpowers Plugin

**After `superpowers:writing-plans`:**
```
Plan written
  ↓
Run over-engineer-no-more (triage)
  ↓
If TRIVIAL → Direct implementation
If COMPLEX → superpowers:subagent-driven-development
```

**After `superpowers:brainstorming`:**
```
Brainstorming complete
  ↓
If implementation clear → Run over-engineer-no-more
  ↓
If TRIVIAL → Direct implementation
If COMPLEX → superpowers:writing-plans → triage → execution
```

---

## Success Metrics

You're using this skill correctly when:

1. ✅ Trivial implementations finish in < 15 minutes
2. ✅ You rarely launch 30+ subagents for data structure changes
3. ✅ User doesn't complain about slow progress on simple changes
4. ✅ Complex implementations get thorough review
5. ✅ Security-critical code always gets review
6. ✅ Credits usage matches complexity appropriately

---

## Common Mistakes

1. **"We wrote a plan, so we need subagents"**
   - Plans can describe trivial work. Always check indicators!

2. **"It's only 3 files, must be trivial"**
   - 3 files of complex logic > 10 files of constants.

3. **"User wants it fast, skip review"**
   - Trivial = naturally fast. Complex = needs review for quality.

4. **"Always err on heavyweight side"**
   - Over-engineering frustrates users and wastes resources.

5. **"Always optimize for speed"**
   - Under-engineering complex work causes bugs and rework.

---

## Tips

1. **Always run triage** after planning, before execution
2. **Check all 7 indicators** systematically
3. **Announce your decision** with clear reasoning
4. **Listen to user language** ("just add" = trivial)
5. **Match process to complexity** (the core principle)
6. **Use middle ground when appropriate** (3-4 indicators)
7. **Never skip review on security/business logic**

---

## Related Skills

- **superpowers:writing-plans** - Creates implementation plan (use before this)
- **superpowers:subagent-driven-development** - Heavyweight execution (use after triage if complex)
- **superpowers:brainstorming** - Explores requirements (use before planning)
- **superpowers:requesting-code-review** - Reviews code quality (use after implementation)
