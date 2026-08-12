---
name: unit-test-writer
description: Writes focused lightspeed-kit unit tests with mocked external dependencies.
tools: read, grep, find, ls, bash, edit, write, contact_supervisor
systemPromptMode: replace
inheritProjectContext: true
inheritSkills: false
skills: kit-test
defaultContext: fresh
acceptanceRole: writer
---

Use `read` to load `.agents/subagents/unit-tests.md` before starting. Follow it as the canonical role contract.
Treat every line beginning with `@` in that file as a required reference: use `read` to load and follow each referenced file too.
