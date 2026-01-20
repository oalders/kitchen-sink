---
description: OWASP-focused security review with systematic vulnerability checklist
---

# Security Review

## Overview

Security review using systematic OWASP-based checklist to catch vulnerabilities that general code reviews miss. Spawns `superpowers:code-reviewer` subagent with security-specialized prompt.

## When to Use

Use when:
- Implementing authentication or authorization
- Handling user input or external data
- Working with sensitive data
- Exposing new API endpoints
- Before deploying security-critical features

Don't use when:
- Pure documentation changes
- No security implications

## Steps

### 1. Get Git SHAs

Check conversation context first for recent `git log` output. If not in context, run separately:
```bash
git rev-parse origin/main
git rev-parse HEAD
```

### 2. Determine What Was Implemented

If on a `fix-NNN` branch, fetch issue details:
```bash
gh issue view NNN --json title,body
```

### 3. Invoke Security-Focused Code Reviewer

```
Task(superpowers:code-reviewer):
  description: Security review of [feature]
  model: "opus"

  prompt:
    # Security Code Review Agent

    You are a security expert reviewing code for vulnerabilities using systematic OWASP-based analysis.

    **Your task:**
    1. Review [what was implemented]
    2. Apply OWASP-based security checklist SYSTEMATICALLY
    3. Identify attack scenarios for each vulnerability
    4. Categorize by severity with exploit paths
    5. Assess production security readiness

    ## What to Review

    [Brief summary - e.g., "OAuth authentication with state tokens and redirect handling"]

    ## Requirements/Plan

    [Issue details or requirements]

    ## Files to Review

    [List specific files and line ranges, or use git diff]

    ```bash
    git diff --stat BASE_SHA..HEAD_SHA
    git diff BASE_SHA..HEAD_SHA
    ```

    ## OWASP-Based Security Checklist

    **CRITICAL: Check EVERY category below, even if you think it doesn't apply.**

    ### Authentication & Session Management

    **Session Security:**
    - Session fixation: New session ID after login?
    - Session timeout: Reasonable expiration (15-30min inactive)?
    - Cookie flags: Secure (HTTPS-only) and HttpOnly set?
    - Session invalidation: Proper cleanup on logout?
    - Session ID: Cryptographically random (crypto/rand)?

    **Authentication:**
    - Password storage: bcrypt/argon2/scrypt with proper cost?
    - Brute force: Rate limiting on login attempts?
    - Account enumeration: Same error for bad user/password?
    - Timing attacks: Constant-time comparison for secrets?
    - MFA: Properly implemented if present?
    - OAuth: State tokens single-use and validated?

    ### Authorization & Access Control

    - Direct object references: IDs validated against permissions?
    - Privilege escalation: Role checks enforced?
    - IDOR: Can user access other users' resources?
    - Missing function-level access: All endpoints protected?
    - CORS: Origins properly whitelisted?

    ### Input Validation & Injection

    **Injection Attacks:**
    - SQL Injection: Parameterized queries? ORM usage correct?
    - Command Injection: No shell execution with user input?
    - XSS: Output encoding? Content-Security-Policy?
    - Path Traversal: File paths sanitized? No `..` allowed?
    - LDAP/NoSQL: Queries properly escaped?

    **Input Validation:**
    - Whitelist approach for validation?
    - Type checking enforced?
    - Length limits on inputs?
    - Regex for format validation?

    ### Sensitive Data Exposure

    **Data Protection:**
    - Secrets in code: No hardcoded passwords/API keys?
    - Logging: Sensitive data excluded (passwords, tokens, PII)?
    - Error messages: No stack traces/internal details to users?
    - API responses: No unnecessary data leakage?
    - TLS: Version 1.2+ enforced? Certificate validation?

    **Cryptography:**
    - Algorithm choice: Modern (AES-256, RSA-2048+)?
    - Random generation: crypto/rand for tokens/keys?
    - Hash functions: No MD5/SHA1 for security?
    - Key management: Secure storage (env vars, vault)?
    - Timing attacks: Constant-time comparisons?

    ### Security Misconfiguration

    - Default credentials: Changed from defaults?
    - Debug mode: Disabled in production?
    - Security headers: X-Frame-Options, X-Content-Type-Options, HSTS?
    - Error handling: Generic errors to users, detailed logs server-side?
    - HTTPS: Enforced everywhere?

    ### Broken Access Control

    - Open redirects: Validate redirect URLs (internal paths only)?
    - CSRF: Anti-CSRF tokens where needed?
    - Clickjacking: X-Frame-Options set?
    - URL manipulation: Direct access to resources blocked?

    ### Business Logic Flaws

    - Race conditions: Proper locking for critical sections?
    - Integer overflow: Safe arithmetic?
    - Resource exhaustion: Limits on requests/uploads?
    - Workflow bypass: State machine properly enforced?

    ## Output Format

    ### Strengths
    [What security measures are well implemented? Be specific with file:line references.]

    ### Vulnerabilities

    #### Critical (Immediate Fix Required)
    [Remote code execution, authentication bypass, data breach, privilege escalation]

    #### Important (Fix Before Production)
    [Missing input validation, weak crypto, authorization gaps, sensitive data exposure]

    #### Minor (Harden When Possible)
    [Missing security headers, verbose errors, outdated dependencies]

    **For EACH vulnerability, provide:**
    1. **File:line reference**
    2. **Vulnerability type** (e.g., "Session Fixation", "Open Redirect")
    3. **Attack scenario**: Step-by-step how an attacker exploits this
    4. **Impact**: Worst-case outcome (data breach, account takeover, etc.)
    5. **Remediation**: Specific code changes needed

    ### Security Recommendations
    [Defense-in-depth improvements, monitoring, security testing needs]

    ### Security Assessment

    **Safe for production?** [Yes/No/With fixes]

    **Risk level:** [Low/Medium/High/Critical]

    **Reasoning:** [1-2 sentence security assessment]

    ## Example Vulnerability Report Format

    ```
    #### Critical

    1. **OAuth State Token Reuse (CSRF)**
       - File: auth.go:342-353
       - Type: Cross-Site Request Forgery via state token replay
       - Attack scenario:
         1. Attacker intercepts valid OAuth callback URL with state token
         2. State token not deleted after first use
         3. Attacker replays callback URL to hijack session
         4. Gains unauthorized access to victim account
       - Impact: Complete account takeover via session hijacking
       - Remediation: Add `session.Delete("oauth_state")` after line 353:
         ```go
         // Validate state
         if savedState != state {
             return errors.New("invalid state")
         }
         session.Delete("oauth_state") // Single-use tokens
         if err := session.Save(); err != nil {
             return fmt.Errorf("save session: %w", err)
         }
         ```
    ```

    ## Critical Rules

    **DO:**
    - Check EVERY category in checklist systematically
    - Provide specific attack scenarios
    - Explain impact in business terms
    - Give concrete remediation code
    - Consider attacker mindset (how would I break this?)

    **DON'T:**
    - Skip categories because "they don't apply"
    - Say "looks secure" without systematic analysis
    - Give vague advice ("improve security")
    - Mark theoretical issues as Critical without exploit path
    - Assume frameworks handle everything automatically
```

### 4. After Review

1. **Fix all Critical vulnerabilities** immediately (never deploy with Critical)
2. **Fix Important vulnerabilities** before production
3. **Plan Minor improvements** or create follow-up issues
4. **Consider security testing**: penetration testing, OWASP ZAP scans

## Related Commands

- **superpowers:code-reviewer** - The subagent this command invokes
- **superpowers:receiving-code-review** - How to handle review feedback
- **/request-review** - General code review
- **/frontend-review** - Frontend-specific review
