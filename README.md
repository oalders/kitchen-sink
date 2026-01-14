# kitchen-sink

A collection of useful Claude Code skills and commands for software development workflows.

## Installation

Add to your Claude Code plugins:

```bash
claude plugins add oalders/kitchen-sink
```

## Contents

### Skills

| Skill | Description |
|-------|-------------|
| **fix-issue** | Workflow for fixing GitHub issues on `fix-NNN` branches - extracts issue number, assesses complexity, guides through resolution |
| **execution-complexity-triage** | Evaluate implementation complexity after planning to avoid over-engineering trivial changes |
| **fixing-linter-issues** | Systematic batch approach to fixing linter issues (25 per iteration) while maintaining code quality |

### Commands

| Command | Description |
|---------|-------------|
| **/git-rebase** | Rebase current branch onto origin/main |
| **/break-into-issues** | Break down features into small GitHub issues with tracking |
| **/address-review** | Check last code review and address feedback systematically |

## Skills Overview

### fix-issue

Automates the workflow for fixing GitHub issues:
1. Extracts issue number from branch name (`fix-978` -> `978`)
2. Fetches issue details with `gh`
3. Assesses complexity (trivial vs non-trivial)
4. Suggests brainstorming for complex issues
5. Guides through verification and PR creation

### execution-complexity-triage

Prevents over-engineering by evaluating whether a task needs heavyweight processes:
- Checks indicators: adding constants? < 100 lines? < 3 files?
- Announces decision with reasoning
- Routes to direct implementation or subagent workflow

### fixing-linter-issues

Batch approach to linter cleanup:
- Fix 25 issues per iteration
- Prioritize quick wins (formatting, constants)
- Use suppression directives when fixes would degrade code
- Always include justification comments

## License

MIT
