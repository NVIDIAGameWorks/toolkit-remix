---
name: e2e-test-writer
description: "PROACTIVELY use this agent when E2E tests are needed for user-visible workflows in a real Kit application. Do NOT use for unit tests.\n\nExamples:\n- \"Write E2E tests for the texture import workflow\" → dispatch e2e-test-writer\n- \"Test the mod setup flow from the user's perspective\" → dispatch e2e-test-writer"
model: opus
color: cyan
memory: project
skills: kit-test
mcpServers: kit-dev-mcp
---

@.agents/subagents/e2e-tests.md
