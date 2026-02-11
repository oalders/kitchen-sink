# Example 4: Anti-Patterns to Avoid

## ❌ Anti-Pattern 1: Over-Engineering Trivial Changes

### Scenario
User asks to add 3 new color constants.

**BAD Response:**
```
I'll create a comprehensive plan and use subagent-driven development
to ensure quality.

Task 1: Implement color constants (Subagent)
Task 2: Review color constants (Subagent)
Task 3: Test color constants (Subagent)
Task 4: Documentation review (Subagent)
Task 5: Final integration review (Subagent)

Launching 5 subagents...
```

**WHY BAD:** Adding 3 constants doesn't need 5 subagents and 2 hours.

**GOOD Response:**
```
Checking execution complexity...

Changes needed:
- Add 3 color constants to colors.ts
- Update test assertions

This is trivial (adding constants to a file).
Implementing directly.

[5 minutes later: Done]
```

**IMPACT:** Saved 2 hours and 32x credits for identical result.

---

## ❌ Anti-Pattern 2: Skipping Triage Entirely

### Scenario
After writing a plan, immediately launching heavyweight execution.

**BAD Response:**
```
Plan complete. Now I'll use subagent-driven development...

[Launches 20 subagents for what turns out to be 4 lines of code]
```

**WHY BAD:** Didn't check if the plan was trivial or complex!

**GOOD Response:**
```
Plan complete. Checking execution complexity...

[Runs triage]
This is trivial - just updating 2 data arrays.
Implementing directly.
```

**IMPACT:** Avoided 20 unnecessary subagents and hours of overhead.

---

## ❌ Anti-Pattern 3: Ignoring User Signals

### Scenario
User says "just add..." or "trivial change..."

**BAD Response:**
```
User: "Just add a new status code to the enum"
Assistant: I'll create a detailed plan and use subagent-driven development...
[2 hours later: Done]
```

**WHY BAD:** User literally said "just add" - that's a signal!

**GOOD Response:**
```
User: "Just add a new status code to the enum"
Assistant: That's trivial - adding one constant.
[2 minutes later: Done]
```

**USER SIGNALS TO WATCH FOR:**
- "just add..."
- "simple change..."
- "quick fix..."
- "trivial..."
- "only need to..."

---

## ❌ Anti-Pattern 4: Under-Engineering Complex Changes

### Scenario
User asks for authentication system.

**BAD Response:**
```
This is just adding some login code. I'll implement directly.

[2 hours later: Security vulnerabilities, missing tests, poor architecture]
```

**WHY BAD:** Complex implementations need review cycles!

**GOOD Response:**
```
This involves security-critical code with multiple components.
Using subagent-driven development for:
- Proper security review
- Comprehensive testing
- Fresh context per task
```

**IMPACT:** Heavyweight process catches 3 security issues that direct implementation missed.

---

## ❌ Anti-Pattern 5: All-or-Nothing Thinking

### Scenario
Assuming every task is either "trivial" or "needs 50 subagents"

**BAD Mindset:**
```
Either:
- Direct implementation (10 minutes)
OR
- Full subagent-driven development (3 hours, 50 subagents)

No middle ground.
```

**GOOD Mindset:**
```
Options:
- Trivial: Direct implementation (10 min)
- Simple but needs review: 2-3 focused subagents (30 min)
- Complex: Full subagent-driven development (2-3 hours)

Match process to complexity.
```

---

## ✅ Best Practices Summary

### DO:
1. **Always run triage** after planning
2. **Check complexity indicators** (constants? < 100 lines? < 3 files?)
3. **Announce your decision** with clear reasoning
4. **Listen to user signals** ("just add..." = trivial)
5. **Match process to complexity** (don't over/under-engineer)

### DON'T:
1. **Launch subagents without checking** complexity first
2. **Ignore user language** ("just add" means trivial!)
3. **Over-engineer simple changes** (constants don't need 20 subagents)
4. **Under-engineer complex changes** (security code needs review)
5. **Think in all-or-nothing terms** (there are gradations)

---

## Quick Decision Tree

```
After planning...
  |
  v
Check indicators:
- [ ] Adding constants/data?
- [ ] < 100 lines?
- [ ] < 3 files?
- [ ] No business logic?
- [ ] Same module?
  |
  v
3+ checked? --> TRIVIAL --> Direct implementation
  |
  v
0-2 checked? --> COMPLEX --> Heavyweight process
```

---

## Real Cost Comparison

### Trivial Task: Add 5 constants

**Direct Implementation:**
- Time: 5-10 minutes
- Credits: 1 agent
- Quality: Perfect
- User experience: Fast, efficient

**Over-Engineered:**
- Time: 2-3 hours
- Credits: 30+ agents
- Quality: Perfect (same!)
- User experience: "Why is this taking so long?"

**Verdict:** Over-engineering wastes time and credits for ZERO quality improvement.

### Complex Task: New authentication system

**Direct Implementation:**
- Time: 2 hours
- Credits: 1 agent
- Quality: Poor (missed security issues)
- User experience: Fast but buggy

**Heavyweight Process:**
- Time: 3 hours
- Credits: 15 agents
- Quality: Excellent (security reviewed)
- User experience: "Glad you were thorough"

**Verdict:** Under-engineering sacrifices quality for minimal time savings.

---

## Key Insight

**The goal is NOT to always use heavyweight processes.**
**The goal is NOT to always use direct implementation.**

**The goal is to MATCH the process to the complexity.**

- Trivial changes → Direct (save time/credits)
- Complex changes → Heavyweight (ensure quality)
- Simple with review needs → Middle ground (2-3 focused subagents)
