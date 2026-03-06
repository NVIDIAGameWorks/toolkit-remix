---
name: unit-test-writer
description: "PROACTIVELY use this agent after feature code is written and unit tests are needed. Do NOT use for e2e or UI tests.\n\nExamples:\n- After writing a new function → dispatch unit-test-writer\n- \"I refactored the layer manager\" → dispatch unit-test-writer\n- \"Add tests for the price calculator\" → dispatch unit-test-writer"
model: opus
color: blue
memory: project
skills: kit-test
mcpServers: kit-dev-mcp
---

@.agents/subagents/unit-tests.md
