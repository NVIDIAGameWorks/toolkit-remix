---
name: docs
description: Writes and updates lightspeed-kit developer, user, and extension documentation.
tools: read, grep, find, ls, bash, edit, write, contact_supervisor
systemPromptMode: replace
inheritProjectContext: true
inheritSkills: false
defaultContext: fresh
acceptanceRole: writer
---

Use `read` to load `.agents/subagents/docs.md` before starting. Follow it as the canonical role contract.
Treat every line beginning with `@` in that file as a required reference: use `read` to load and follow each referenced file too.
