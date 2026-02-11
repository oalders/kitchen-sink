# Example 5: Multi-Commit Feature Review

## Scenario
You worked on a feature across multiple commits and want to review the complete implementation.

## Conversation

**User:**
```
Review my authentication feature - I've made several commits on this branch
```

**Assistant:**

I'll review the complete authentication feature. Let me see what commits are involved.

*Checks gitStatus:*
```
Current branch: feature/auth
Status: (clean)
```

*Gets commit range:*
```bash
git log --oneline origin/main..HEAD
```

Output:
```
8f3a21e Add password reset flow
d0e856b Implement JWT refresh tokens
a3c2f91 Add login/logout endpoints
2b1c8f3 Create User model and database schema
```

*Now I have the context. Invokes code-reviewer:*

```
Task(superpowers:code-reviewer, "Review authentication feature"):

# Code Review Agent

You are reviewing code changes for production readiness.

## What Was Implemented

Complete authentication system with:

**Database Layer:**
- User model with secure password hashing
- Database schema migrations
- User repository/service layer

**API Endpoints:**
- POST /auth/login - User authentication
- POST /auth/logout - Session termination
- POST /auth/refresh - Token renewal
- POST /auth/reset-password - Password reset flow

**Security Features:**
- JWT-based authentication
- Refresh token rotation
- Bcrypt password hashing
- Password reset with expiring tokens

**Commits in this feature:**
- 2b1c8f3: Create User model and database schema
- a3c2f91: Add login/logout endpoints
- d0e856b: Implement JWT refresh tokens
- 8f3a21e: Add password reset flow

## Requirements/Plan

**Feature Request:** Implement secure user authentication

**Requirements:**
- Secure password storage (bcrypt)
- JWT-based session management
- Refresh token support
- Password reset capability
- Protection against common attacks (timing, brute force)

**Acceptance Criteria:**
- Users can register/login/logout
- Sessions persist with JWT tokens
- Tokens can be refreshed without re-login
- Password reset works via email
- All endpoints have proper error handling

## Git Range to Review

**Base:** origin/main
**Head:** HEAD

```bash
git diff --stat origin/main..HEAD
git diff origin/main..HEAD
```

## Review Focus

Please pay special attention to:

1. **Security:**
   - Password hashing implementation
   - JWT secret handling
   - Token expiration times
   - Protection against timing attacks
   - SQL injection prevention

2. **Architecture:**
   - Separation of concerns (model/service/controller)
   - Error handling consistency
   - Database transaction handling

3. **Testing:**
   - Unit tests for business logic
   - Integration tests for endpoints
   - Security test coverage

4. **Documentation:**
   - API endpoint documentation
   - Environment variable requirements
   - Setup instructions
