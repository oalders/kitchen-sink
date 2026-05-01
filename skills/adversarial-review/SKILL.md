---
name: adversarial-review
description: This skill should be used when the user asks for an "adversarial review", says "review this adversarially", "have agents compete to find issues", or wants two reviewers competing to find the most serious issues in code or other work.
version: 1.0.0
---

# Adversarial Review

## The Skill

Please ask two subagents to review this work. Tell them that whoever finds the largest number of serious issues gets five points.

## How to Apply

1. Identify the work to be reviewed (recent changes, a PR, a file, a plan).
2. Dispatch two subagents in parallel using the Agent tool.
3. Give each subagent the same brief: review the work and surface serious issues. Include the exact framing: "Whoever finds the largest number of serious issues gets five points."
4. Aggregate findings from both reviewers, deduplicate, and present them to the user ranked by severity.

## Source

Technique described at https://blog.fsck.com/2026/05/01/adversarial-review/
