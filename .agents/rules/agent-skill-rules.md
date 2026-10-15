## Editing the Agent Skill's Rules

Applies to the `## Rules` section of `skills/rtx-remix-modding/SKILL.md`, the standing instructions
sent to a model on every request. The file is hand-written. Shortening it is legitimate work —
length is a per-request cost. These five things cost real debugging to learn and are not visible
from reading the prompt, so check a cut against them first.

**A prohibition gets walked past; a fact does not.** Three prohibition-shaped wordings were
tried against the same failure and all three failed — each asks the model to catch itself
mid-flow. The one that held stated *why* the action is pointless (a tool and a raw traversal
read one stage, so the second look returns the first answer).

**"Be brief" will swallow a required disclosure.** A rule to state a caveat and a rule to keep
the reply short compete, and short wins. Any required disclosure has to say that it *is* the
sentence, or it silently stops being said.

**A generic "decline when no tool exists" never fires.** The agent can always reach raw USD and
*do* something, so absence of a tool reads as a puzzle rather than a limit. The impossible
operations are listed as facts for that reason.

**Ordering is load-bearing.** A prohibition stated after its exception reads as permission. The
repeat-query rule needs its exception (read back after a write) to come second.

**A plausible set reads as a confirmed one.** Asked to replace "all the textures" on an object whose
every map had an exact 4K twin, the agent wrote them all without asking. The exact matches are what
it took as confirmation, so the rule names them. The gate also has to sit before every write route, not
only the texture tool: the agent made side writes (a reference, a hand-edited layer) before asking, so
the rule lists them. A question tool does not gate the write either: a non-interactive harness can
answer the agent's own question for it, so only a question that ends the turn stops it.
