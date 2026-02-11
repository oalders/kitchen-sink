# Example 3: Simple Bug Fix (Trivial)

## Scenario
Email validation regex doesn't accept plus signs in email addresses (`user+tag@example.com`).

## Conversation

**User:**
```
Fix bug #456 - email validation rejects valid emails with plus signs
```

**Assistant:**

Let me check the issue and plan the fix.

*Reads issue:*
```
Bug: Email validation fails for user+tag@example.com
Expected: Should accept plus signs (RFC 5322 compliant)
Current: Regex rejects any email with +
```

*After planning:*

**Plan:**
1. Update email regex in `utils/validation.ts`
   - Change: `/^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/`
   - To: `/^[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/`
   - (Add `+` to allowed characters)

2. Update error message to be more specific
   - Change: "Invalid email format"
   - To: "Invalid email format (letters, numbers, ., _, +, - allowed)"

3. Add test case for plus sign emails
   - Test: `user+tag@example.com` should validate
   - Test: `test+filter@domain.co.uk` should validate

**Estimated:**
- ~10 lines of code changed
- 2 files (validation.ts, validation.test.ts)
- Same module (utils)
- Simple regex update

---

## Triage (Over-Engineer No More)

**Checking complexity...**

Trivial Implementation Indicators:
- [x] No new functions/constants (just modifying regex)
- [x] Minimal logic change (add one character to pattern)
- [x] Isolated to validation module
- [x] < 100 lines of code (~10 lines)
- [x] < 3 files (2 files)
- [x] Same package/module
- [x] Simple bug fix with clear solution

**6/7 indicators = TRIVIAL**

---

## Decision Announcement

```
Plan complete. Checking execution complexity...

Changes required:
- Update email regex pattern (add + to allowed chars)
- Update error message for clarity
- Add test cases for plus sign emails

This is trivial implementation (simple regex fix + test update).

I'll implement directly rather than using subagent-driven development.
This will:
- Save time (5 min vs 30 min)
- Use fewer credits (1 agent vs 9)
- Produce the same quality result

Proceeding with direct implementation.
```

---

## Implementation

**File 1: utils/validation.ts**
```typescript
export function isValidEmail(email: string): boolean {
  // Updated regex to allow plus signs (RFC 5322 compliant)
  const emailRegex = /^[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  return emailRegex.test(email);
}

export const EMAIL_ERROR =
  "Invalid email format (letters, numbers, ., _, +, - allowed)";
```

**File 2: utils/validation.test.ts**
```typescript
describe('isValidEmail', () => {
  // ... existing tests ...

  it('should accept plus signs in email', () => {
    expect(isValidEmail('user+tag@example.com')).toBe(true);
    expect(isValidEmail('test+filter@domain.co.uk')).toBe(true);
  });

  it('should still reject invalid formats', () => {
    expect(isValidEmail('user@')).toBe(false);
    expect(isValidEmail('user space@example.com')).toBe(false);
  });
});
```

---

## Verification

```bash
npm test -- validation.test.ts
```

Output: ✓ All tests passing

---

## Result

**Time:** 5 minutes
**Files changed:** 2
**Lines changed:** 8 (1 regex + 1 error message + 6 test lines)
**Quality:** Perfect
**Credits used:** 1 agent

**What we avoided:**
- 3 implementation subagents (validation, tests, review)
- 3 review subagents
- 25 minutes of overhead

---

## Key Insight

**Simple bug fixes with clear solutions are trivial:**
- One-line regex fix
- Isolated to single module
- Clear test cases

**No need for heavyweight process when the fix is obvious and contained.**

---

## Contrast: When Bug Fix is NOT Trivial

**Example:** "Fix race condition in session management"
- [ ] Not simple logic change (race conditions are complex)
- [ ] Requires deep analysis
- [ ] May affect multiple modules
- [ ] Security-critical

**→ Use heavyweight process** (needs thorough analysis and review)
