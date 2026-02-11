# Example 2: New API Endpoint (Complex)

## Scenario
User asks to add a new API endpoint for exporting user data (GDPR compliance).

## Conversation

**User:**
```
Add a new API endpoint for GDPR data export - users should be able to download all their data
```

**Assistant:**

Let me plan this implementation.

*After planning:*

**Plan:**
1. Create data export service (`services/exportService.ts`)
   - Query all user tables (users, posts, comments, likes, sessions)
   - Aggregate data into single JSON structure
   - Handle large datasets with pagination
   - Implement streaming for memory efficiency

2. Add API endpoint (`routes/api/export.ts`)
   - POST /api/export/request - Initiate export job
   - GET /api/export/status/:jobId - Check export status
   - GET /api/export/download/:jobId - Download file
   - Authentication middleware required
   - Rate limiting (1 export per day per user)

3. Background job processing
   - Queue export jobs (Redis)
   - Process asynchronously
   - Store results in S3 or filesystem
   - Send email notification when complete

4. Database additions
   - Create export_jobs table (status tracking)
   - Add indexes for performance
   - Migration scripts

5. Security considerations
   - Verify user owns the data being exported
   - Sanitize sensitive fields (passwords, tokens)
   - Implement secure temporary download links
   - Auto-expire downloads after 48 hours

6. Testing
   - Unit tests for export service
   - Integration tests for API endpoints
   - Security tests (unauthorized access)
   - Performance tests (large datasets)

**Estimated:**
- ~500 lines of code
- 8+ files (service, routes, models, migrations, tests, queue)
- Multiple packages (API, services, database, queue)
- Complex business logic and security requirements

---

## Triage (Over-Engineer No More)

**Checking complexity...**

Trivial Implementation Indicators:
- [ ] Just adding constants/data ❌ (new services and logic)
- [ ] No new functions or types ❌ (creating multiple new functions)
- [ ] No business logic or algorithms ❌ (data aggregation, streaming, security)
- [ ] Just updating data structures + tests ❌ (database changes, API endpoints)
- [ ] < 100 lines of code ❌ (~500 lines)
- [ ] < 3 files ❌ (8+ files)
- [ ] Same package/module ❌ (API, services, DB, queue)

**0/7 indicators = COMPLEX**

---

## Decision Announcement

```
Plan complete. Checking execution complexity...

Changes required:
- New export service with data aggregation logic
- 3 new API endpoints with auth/rate limiting
- Background job processing with queue
- Database migration for export_jobs table
- Security implementation (auth, sanitization, expiry)
- Comprehensive test suite

This is complex implementation requiring:
- New business logic and algorithms
- Multi-file coordination across packages
- Database migrations and API changes
- Security-critical code

I'll use subagent-driven development for:
- Fresh context per task
- Thorough review cycles
- Quality verification
- Security review

Proceeding with subagent-driven development.
```

---

## Execution

**Using heavyweight process:**

1. **Task 1: Database migration** (Subagent)
   - Create export_jobs table
   - Add indexes
   - Review schema design

2. **Task 2: Export service** (Subagent)
   - Implement data aggregation
   - Add streaming for memory efficiency
   - Review data sanitization

3. **Task 3: Queue integration** (Subagent)
   - Set up Redis job queue
   - Implement job processing
   - Review error handling

4. **Task 4: API endpoints** (Subagent)
   - Create routes
   - Add middleware (auth, rate limiting)
   - Review security implementation

5. **Task 5: Testing** (Subagent)
   - Unit tests for service
   - Integration tests for API
   - Security tests
   - Review test coverage

6. **Task 6: Security review** (Subagent)
   - Review authentication
   - Review authorization
   - Review data sanitization
   - Review GDPR compliance

---

## Why Heavyweight Process is Justified

**Fresh Context Benefits:**
- Each subagent focuses on one concern (DB, API, security)
- Dedicated security review catches vulnerabilities
- Test subagent ensures comprehensive coverage

**Review Cycle Benefits:**
- Code review catches authorization bugs
- Security review identifies data leakage risks
- Integration review ensures components work together

**Quality Benefits:**
- Better error handling (each subagent considers edge cases)
- Better test coverage (dedicated test implementation)
- Better security (dedicated security review)

---

## Result

**Time:** 2-3 hours (with review cycles)
**Files changed:** 12
**Lines added:** 487
**Quality:** High (thorough reviews, good test coverage)
**Credits used:** 18 subagents

**What heavyweight process provided:**
- Fresh context for complex tasks
- Dedicated security review (caught 3 issues)
- Comprehensive test coverage (95%)
- Multiple review checkpoints
- Proper error handling throughout

---

## Key Insight

**When implementation involves:**
- New business logic
- Multiple packages/systems
- Security requirements
- Database changes
- API endpoints

**→ Use heavyweight process. The review cycles and fresh context justify the overhead.**
