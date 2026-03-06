---
name: reviewer
description: "PROACTIVELY use this agent for code review — diffs, MRs, completed features, pre-submission checks.\n\nExamples:\n- After implementing a feature → dispatch reviewer\n- \"Review the layer manager changes\" → dispatch reviewer\n- \"Check if this MR is ready\" → dispatch reviewer"
model: opus
color: red
memory: project
tools: Read, Glob, Grep
---

@.agents/subagents/review.md
