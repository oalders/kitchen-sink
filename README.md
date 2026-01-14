# kitchen-sink

![Mog & the kitchen sink adventure](kitchen-sink.jpg)

A collection of useful Claude Code skills and commands for software development workflows.

## Installation

Add from the Claude Code plugin marketplace:

```bash
claude plugin marketplace add oalders/kitchen-sink
```

## Requirements

Most skills and commands in this plugin rely on [obra/superpowers](https://github.com/obra/superpowers) for workflows like brainstorming, verification, and subagent-driven development. Install it first:

```bash
claude plugin marketplace add obra/superpowers
```

## Contents

### Skills

| Skill | Description |
|-------|-------------|
| **fix-gh-issue** | Workflow for fixing GitHub issues - extracts issue number, assesses complexity, guides through resolution |
| **execution-complexity-triage** | Evaluate implementation complexity after planning to avoid over-engineering trivial changes |
| **fix-linter-warnings** | Systematic batch approach to fixing linter warnings (25 per iteration) while maintaining code quality |

### Commands

| Command | Description |
|---------|-------------|
| **/git-rebase** | Rebase current branch onto origin/main |
| **/break-into-gh-issues** | Break down features into small GitHub issues with tracking |
| **/address-gh-review** | Check last GitHub PR review and address feedback systematically |

## Skills Overview

### fix-gh-issue

Automates the workflow for fixing GitHub issues:
1. Gets issue number from argument or branch name (`fix-978` -> `978`)
2. Fetches issue details with `gh`
3. Assesses complexity (trivial vs non-trivial)
4. Suggests brainstorming for complex issues
5. Guides through verification and PR creation

### execution-complexity-triage

Prevents over-engineering by evaluating whether a task needs heavyweight processes:
- Checks indicators: adding constants? < 100 lines? < 3 files?
- Announces decision with reasoning
- Routes to direct implementation or subagent workflow

### fix-linter-warnings

Batch approach to linter cleanup:
- Fix 25 issues per iteration
- Prioritize quick wins (formatting, constants)
- Use suppression directives when fixes would degrade code
- Always include justification comments

## License

MIT

## Image Credit

"[Mog & the kitchen sink adventure #01](https://www.flickr.com/photos/87285907@N00/3009300486)" by [ju5ti](https://www.flickr.com/photos/87285907@N00) is licensed under [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/?ref=openverse).
