# Example 1: Adding Constants (Trivial)

## Scenario
User asks to add new country codes to support additional regions.

## Conversation

**User:**
```
Add support for 5 new countries: Finland, Norway, Sweden, Denmark, Iceland
```

**Assistant:**

Let me plan this implementation.

*After planning:*

**Plan:**
1. Add 5 new country code constants to `constants/countries.ts`
2. Add 5 entries to country lookup map in `data/countryData.ts`
3. Add 5 new flag emoji mappings in `utils/flags.ts`
4. Update test assertions in `__tests__/countries.test.ts`

**Estimated:**
- ~40 lines of code (5 constants × 8 files/places)
- 3 files affected
- No new functions or logic
- Just data structure updates

---

## Triage (Over-Engineer No More)

**Checking complexity...**

Trivial Implementation Indicators:
- [x] Just adding constants/data
- [x] No new functions or types
- [x] No business logic or algorithms
- [x] Just updating data structures + tests
- [x] < 100 lines of code (~40 lines)
- [x] < 3 files (3 files)
- [x] Same package/module

**7/7 indicators = TRIVIAL**

---

## Decision Announcement

```
Plan complete. Checking execution complexity...

Changes required:
- Add 5 country constants (FI, NO, SE, DK, IS)
- Add 5 country lookup entries
- Add 5 flag emoji mappings
- Update test assertions

This is trivial implementation (adding items to constants/data structures).

I'll implement directly rather than using subagent-driven development.
This will:
- Save time (10 min vs 2 hours)
- Use fewer credits (1 agent vs 33)
- Produce the same quality result

Proceeding with direct implementation.
```

---

## Implementation

**File 1: constants/countries.ts**
```typescript
export const COUNTRY_CODES = {
  // ... existing codes ...
  FI: 'FI',
  NO: 'NO',
  SE: 'SE',
  DK: 'DK',
  IS: 'IS',
} as const;
```

**File 2: data/countryData.ts**
```typescript
export const COUNTRY_DATA = {
  // ... existing data ...
  FI: { name: 'Finland', region: 'Europe' },
  NO: { name: 'Norway', region: 'Europe' },
  SE: { name: 'Sweden', region: 'Europe' },
  DK: { name: 'Denmark', region: 'Europe' },
  IS: { name: 'Iceland', region: 'Europe' },
};
```

**File 3: utils/flags.ts**
```typescript
export const FLAG_EMOJI = {
  // ... existing flags ...
  FI: '🇫🇮',
  NO: '🇳🇴',
  SE: '🇸🇪',
  DK: '🇩🇰',
  IS: '🇮🇸',
};
```

**File 4: __tests__/countries.test.ts**
```typescript
describe('Nordic countries', () => {
  it('should have all Nordic countries', () => {
    expect(COUNTRY_CODES).toHaveProperty('FI');
    expect(COUNTRY_CODES).toHaveProperty('NO');
    expect(COUNTRY_CODES).toHaveProperty('SE');
    expect(COUNTRY_CODES).toHaveProperty('DK');
    expect(COUNTRY_CODES).toHaveProperty('IS');
  });
});
```

---

## Verification

```bash
npm test -- countries.test.ts
```

Output: ✓ All tests passing

---

## Result

**Time:** 8 minutes
**Files changed:** 3
**Lines added:** 38
**Quality:** Perfect (same as heavyweight process would produce)
**Credits used:** 1 agent

**What we avoided:**
- 11 implementation subagents
- 11 spec review subagents
- 11 code review subagents
- 2 hours of processing time
- 32x credit cost

---

## Key Insight

**When the implementation is just "add items to data structures," go direct.** Heavyweight processes are for complex logic, not data updates.
