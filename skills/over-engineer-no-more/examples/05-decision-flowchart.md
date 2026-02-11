# Example 5: Decision Flowchart

## Visual Decision Tree

```
┌─────────────────────────────────┐
│  Implementation Plan Complete   │
└───────────────┬─────────────────┘
                │
                v
┌─────────────────────────────────┐
│   RUN TRIAGE (Check Indicators) │
└───────────────┬─────────────────┘
                │
                v
┌─────────────────────────────────────────────────────────┐
│ Count TRUE indicators:                                  │
│                                                          │
│ [ ] Just adding constants/enums/data?                   │
│ [ ] No new functions or types?                          │
│ [ ] No new business logic/algorithms?                   │
│ [ ] Just updating data structures + tests?              │
│ [ ] < 100 lines of code?                                │
│ [ ] < 3 files changed?                                  │
│ [ ] Same package/module?                                │
└───┬─────────────────────────────┬──────────────────────┘
    │                             │
    v                             v
┌───────────┐                ┌───────────┐
│  5-7 ✓    │                │  0-2 ✓    │
│           │                │           │
│  TRIVIAL  │                │  COMPLEX  │
└─────┬─────┘                └─────┬─────┘
      │                            │
      v                            v
┌──────────────────────┐    ┌──────────────────────────┐
│ DIRECT               │    │ HEAVYWEIGHT              │
│ IMPLEMENTATION       │    │ PROCESS                  │
│                      │    │                          │
│ 1. Make changes      │    │ 1. Subagent-driven dev   │
│ 2. Run tests         │    │ 2. Review cycles         │
│ 3. Commit            │    │ 3. Quality verification  │
│ 4. Done              │    │ 4. Security review       │
│                      │    │                          │
│ Time: 5-15 min       │    │ Time: 1-3 hours          │
│ Credits: 1 agent     │    │ Credits: 10-30 agents    │
└──────────────────────┘    └──────────────────────────┘
                                    │
                                    v
                            ┌───────────────┐
                            │   3-4 ✓       │
                            │               │
                            │   MIDDLE      │
                            │   GROUND      │
                            └───────┬───────┘
                                    │
                                    v
                            ┌──────────────────────────┐
                            │ FOCUSED SUBAGENTS        │
                            │                          │
                            │ 1. 2-3 implementation    │
                            │    subagents             │
                            │ 2. Quick review cycle    │
                            │ 3. Done                  │
                            │                          │
                            │ Time: 30-60 min          │
                            │ Credits: 3-5 agents      │
                            └──────────────────────────┘
```

---

## Examples by Category

### 🟢 TRIVIAL (Direct Implementation)

**Indicators: 5-7 ✓**

```
✓ Adding constants
✓ No new functions
✓ No business logic
✓ Data structure updates
✓ < 100 lines
✓ < 3 files
✓ Same module
```

**Examples:**
- Add 5 color constants
- Add items to enum
- Update test assertions
- Fix typo in error message
- Add field to struct/type
- Rename variables (simple)

**Process:** Make changes → Test → Commit → Done (5-15 min)

---

### 🔴 COMPLEX (Heavyweight Process)

**Indicators: 0-2 ✓**

```
✗ New functions/systems
✗ Complex business logic
✗ Multiple packages
✗ > 300 lines
✗ 6+ files
✗ Security/performance
```

**Examples:**
- New API endpoints
- Authentication system
- Database migrations
- Payment processing
- Multi-step algorithms
- Cross-cutting refactors

**Process:** Subagent-driven dev → Review cycles → Done (1-3 hours)

---

### 🟡 MIDDLE GROUND (Focused Subagents)

**Indicators: 3-4 ✓**

```
~ Some new logic
~ Moderate complexity
~ 3-5 files
~ 100-300 lines
~ Needs review but not complex
```

**Examples:**
- Simple bug fix with tests
- Add validation logic
- Simple API route (CRUD only)
- Configuration restructure
- Test framework updates

**Process:** 2-3 focused subagents → Quick review → Done (30-60 min)

---

## Decision Examples

### Example A: "Add 10 status codes"

```
Check indicators:
✓ Just adding constants
✓ No new functions
✓ No business logic
✓ Data structure updates
✓ ~40 lines
✓ 2 files
✓ Same module

Score: 7/7 → TRIVIAL
Decision: Direct implementation
Time: 8 minutes
```

### Example B: "Implement password reset flow"

```
Check indicators:
✗ New functions (sendEmail, generateToken, validateToken)
✗ Business logic (token expiry, validation)
✗ Multiple packages (email, auth, DB)
✗ ~400 lines
✗ 8 files
✗ Security-critical

Score: 0/7 → COMPLEX
Decision: Heavyweight process
Time: 2 hours
```

### Example C: "Fix email validation regex"

```
Check indicators:
~ One function change
✓ Simple logic fix
✓ Same module
✓ ~15 lines
✓ 2 files (code + test)
✗ Some logic involved

Score: 4/7 → MIDDLE GROUND
Decision: 2 subagents (implementation + review)
Time: 25 minutes
```

---

## User Signal Detection

### Signals for TRIVIAL:
- "just add..."
- "simple change..."
- "quick fix..."
- "only need to..."
- "trivial..."
- "add X to the list"

### Signals for COMPLEX:
- "new feature..."
- "implement authentication..."
- "refactor the..."
- "database migration..."
- "security fix..."
- "performance optimization..."

### Ambiguous (Check Indicators):
- "fix the bug..."
- "update the..."
- "add a..."
- "change the..."

---

## Time/Credit Decision Matrix

```
                        TIME CRITICAL?
                    YES             NO
                    │               │
QUALITY       HIGH  │  COMPLEX      │  COMPLEX
CRITICAL?           │  (Fast lanes) │  (Full review)
                    │               │
              LOW   │  TRIVIAL      │  MIDDLE
                    │  (Fast impl)  │  (Focused)
```

**Key:**
- **High quality + time critical** → Use parallelized subagents
- **High quality + not time critical** → Full review cycles
- **Low complexity + time critical** → Direct implementation
- **Low complexity + not urgent** → Focused subagents for learning

---

## Common Mistakes to Avoid

### ❌ Mistake 1: "We wrote a plan, so we need subagents"
**Reality:** Plans can describe trivial work. Check indicators!

### ❌ Mistake 2: "It's only 3 files, must be trivial"
**Reality:** 3 files of complex logic > 10 files of constants.

### ❌ Mistake 3: "User wants it fast, skip review"
**Reality:** Trivial = fast. Complex = needs review for quality.

### ❌ Mistake 4: "Always err on heavyweight side"
**Reality:** Over-engineering frustrates users and wastes resources.

### ❌ Mistake 5: "Always optimize for speed"
**Reality:** Under-engineering complex work causes bugs and rework.

---

## Success Criteria

**You're triaging correctly when:**

1. ✅ Trivial tasks finish in < 15 minutes
2. ✅ Complex tasks get thorough review
3. ✅ Users don't complain about slow progress on simple changes
4. ✅ Users appreciate thoroughness on complex changes
5. ✅ You rarely launch 20+ subagents for data changes
6. ✅ You never skip review on security/business logic
7. ✅ Credits used match complexity appropriately

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────┐
│ TRIAGE CHEAT SHEET                              │
├─────────────────────────────────────────────────┤
│                                                 │
│ TRIVIAL (Direct):                               │
│   • Constants, enums, data                      │
│   • < 100 lines, < 3 files                      │
│   • No business logic                           │
│   • Time: 5-15 min, Credits: 1                  │
│                                                 │
│ MIDDLE (2-3 Subagents):                         │
│   • Simple bug fixes with tests                 │
│   • 100-300 lines, 3-5 files                    │
│   • Some logic, needs review                    │
│   • Time: 30-60 min, Credits: 3-5               │
│                                                 │
│ COMPLEX (Heavyweight):                          │
│   • New features, APIs, auth                    │
│   • > 300 lines, 6+ files                       │
│   • Security, performance critical              │
│   • Time: 1-3 hours, Credits: 10-30             │
│                                                 │
└─────────────────────────────────────────────────┘
```
