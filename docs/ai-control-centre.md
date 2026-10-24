# AI control centre

**Administration → AI control centre** shows what AI agents may do in your organization,
what they have proposed, and what AI has done, with the evidence.

## The action policy

AI agents (for example an MCP client such as Claude, connected with an API key) can read
what their key allows. Making a change is an **action**, and each action has a mode:

| Mode | Meaning |
|---|---|
| Never | The agent may not do it, or even propose it. |
| Propose for approval | The agent proposes it; an administrator or analyst approves or rejects it. |
| Do it directly | The agent does it, with the same permission checks as an analyst. |

| Action | Default |
|---|---|
| Open a war-room incident | Propose for approval |
| Add a note to a war-room incident | Propose for approval |
| Add a term to the regulatory watchlist | Propose for approval |
| Send a questionnaire to a supplier | **Never**; at most *Propose for approval* |

Anything that reaches outside the organization (sending a questionnaire emails a supplier)
can never be set to *Do it directly*: a person always decides. Only administrators change
the policy; every change is in the [audit log](audit-log.md) with the old and new mode.

## Approvals

A proposal shows what the agent wants to do, its parameters and its reason. **Approve and
run** runs the action as you, through the same code and checks as when you do it yourself
(so an approval can still fail, for example if the incident no longer exists; the reason is
shown). A proposal is decided once: two people approving at the same moment cannot run it
twice. If an approved questionnaire is not emailed, its supplier link is shown to the
approver once and is not stored with the proposal.

The audit log records the proposal (with the agent's key as the actor), and the approval or
rejection (with the person).

## Run log

For administrators and auditors: every **Ask** (and every MCP tool call): who asked what,
which model answered (or that none did and the answer used the records' own wording), what
the citation checker kept and removed and why, whether the run was **degraded** (the model
could not be reached, or its answer failed the citation check), and how long it took.
The log is append-only: the database refuses to change or delete entries.

Numbers in answers always come from code, never from the model.
