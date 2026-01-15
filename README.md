# kitchen-sink

*Everything but the kitchen sink*

![Mog & the kitchen sink adventure](kitchen-sink.jpg)

A grab bag of skills to automate the boring parts out of your hair and into your robot.

## Requirements

**GitHub CLI:** Several skills and commands use [`gh`](https://cli.github.com/) to interact with GitHub issues and pull requests. Install it and authenticate with `gh auth login`.

**Superpowers plugin:** Most skills and commands rely on [obra/superpowers](https://github.com/obra/superpowers) for workflows like brainstorming, verification, and subagent-driven development. Install it first:

```bash
claude plugin marketplace add obra/superpowers
```

## Installation

Add from the Claude Code plugin marketplace:

```bash
claude plugin marketplace add oalders/kitchen-sink &&
  claude plugin install kitchen-sink
```

## Contents

### Commands

| Command | Description |
|---------|-------------|
| **/fix-gh-issue** | Point your robot at a GitHub issue and let it start beeping and booping |
| **/fix-linter-warnings** | Linter busywork in bite-sized chunks—your robot's idea of a good time, not yours |
| **/git-rebase** | Rebase without the cruel and unusual punishment of solving your own merge conflicts |
| **/break-into-gh-issues** | Maybe split big issues into smaller ones—so you get a code review and not an intervention |
| **/address-gh-review** | A robot that does the urgent repairs now and books appointments for the rest |

### Skills

| Skill | Description |
|-------|-------------|
| **over-engineer-no-more** | Prevents your robot from building a spaceship when you asked for a bicycle |

## Commands Overview

### /fix-gh-issue

Automates the workflow for fixing GitHub issues:
1. Gets issue number from argument or branch name (`fix-978` -> `978`)
2. Fetches issue details with `gh`
3. Assesses complexity (trivial vs non-trivial)
4. Suggests brainstorming for complex issues
5. Guides through verification and PR creation

### /fix-linter-warnings

Batch approach to linter cleanup:
- Fix 25 issues per iteration
- Prioritize quick wins (formatting, constants)
- Use suppression directives when fixes would degrade code
- Always include justification comments

### /git-rebase

Rebases the current branch onto origin/main:
- Fetches latest changes and pulls with `--rebase`
- Reads and resolves merge conflicts
- Uses `--force-with-lease` for safe pushing (never `--force`)

### /break-into-gh-issues

Breaks down work into manageable GitHub issues:
- Single issue for <= 400 lines of changes
- Multi-issue with umbrella tracking for larger work
- Creates labels if they don't exist
- Links sub-issues back to umbrella with progress checklist

### /address-gh-review

Addresses PR code review feedback:
- Fetches comments from the current branch's PR
- Evaluates each suggestion critically (doesn't blindly implement)
- Fixes immediate issues with atomic commits
- Creates GitHub issues for deferred items
- Runs tests and pushes when done

## Skills Overview

### over-engineer-no-more

Prevents over-engineering by evaluating whether a task needs heavyweight processes:
- Checks indicators: adding constants? < 100 lines? < 3 files?
- Announces decision with reasoning
- Routes to direct implementation or subagent workflow

## License

MIT

## Image Credit

"[Mog & the kitchen sink adventure #01](https://www.flickr.com/photos/87285907@N00/3009300486)" by [ju5ti](https://www.flickr.com/photos/87285907@N00) is licensed under [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/?ref=openverse).
