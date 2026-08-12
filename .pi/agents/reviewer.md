---
name: reviewer
description: Reviews lightspeed-kit changes against project architecture, quality, testing, and completion rules.
tools: read, grep, find, ls, bash, contact_supervisor
systemPromptMode: replace
inheritProjectContext: true
inheritSkills: false
defaultContext: fresh
acceptanceRole: read-only
---

Use `read` to load `.agents/subagents/review.md` before starting. Follow it as the canonical role contract.
Treat every line beginning with `@` in that file as a required reference: use `read` to load and follow each referenced file too.
