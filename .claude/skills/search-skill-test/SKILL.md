---
name: search-skill-test
description: >
  Evaluate this project's skill-search quality by probing it with a fleet of
  fresh agents — one realistic task per catalog category — and report which
  skill each one actually landed on. Use when asked to test, evaluate,
  benchmark or sanity-check skill-search or the catalog, to check whether a
  catalog fix worked, or to find out why search returns poor matches. Not for
  running skill-search normally, and not for rebuilding the catalog.
---

# search-skill-test

A manual, agent-driven test of `skill-search`. Unlike the pytest suite in
`tests/`, this one has no assertions — it measures whether a *fresh agent*,
given a realistic task and nothing else, lands on the right skill.

It tests two things unit tests cannot:

1. **Routing** — does the index text steer an agent to the right category?
2. **Contents** — once there, is the right skill actually in the shard?

Most failures are #2. Routing has held at 10/10 across every run so far.

## 0. Ask before running

This spawns ten agents at once — enough that the wrong shape of run is worth
avoiding. Ask first with `AskUserQuestion`, leading with the recommended option:

| Question | Options | Default |
| --- | --- | --- |
| **Which model?** | Opus / Haiku / both | Opus — see *Choosing a model* |
| **How many probes?** | one per category (10) / a named subset / a single category | one per category |
| **What output?** | table alone / table plus a written analysis | table alone |

You always write the tasks yourself — never ask the user to supply them. Step 2
is where the test's rigour lives, and handing it over invites tasks phrased in
catalog vocabulary, which tests string matching rather than routing.

Of the questions above, **model** is the one that changes the run materially
rather than just its presentation: it decides whether you get a QA signal at
all. Haiku routes fine but rarely reports friction, so a Haiku-only run can look
like a clean pass over a catalog with real defects.

Skip the questions only when the user has already specified the run.

## 1. Read the categories

```
cat .claude/skill-atlas/catalog/_index.md
```

One agent per category. Skip `uncategorized` — it is a fall-through, not a
destination, and gets tested implicitly when a probe fails to find its answer
elsewhere.

## 2. Write one realistic task per category

The task is the whole experiment. Rules that matter:

- **Phrase it as a user would**, not as the category does. If the task echoes
  the index wording, you are testing string matching, not routing.
- **Never name a skill, plugin, or tool.** The agent must arrive on its own.
- **Avoid platform giveaways** unless the platform is the point. Saying
  "Shopify" hands the agent the answer; saying "our storefront" tests whether
  the catalog can cope.
- **Vary the phrasing between runs.** Reusing tasks re-tests a known result.

## 3. Launch the agents

All in one message so they run concurrently. Each gets this prompt:

```
READ-ONLY EXPERIMENT. Rules: Do NOT create, edit, or delete any file. Do NOT
run state-changing git commands. Do NOT actually do the task. Only run the
skill search and report.

Working directory: <repo root>

STEP 1: Use the Skill tool to invoke `skill-atlas:skill-search` with the task
below, and follow its instructions.

TASK: "<the task>"

STEP 2: Report exactly this:
1. CATEGORY PICKED: the category from catalog/_index.md, plus one line on why.
2. SHARD READ: which catalog/<category>.md file(s) you read.
3. TOP MATCHES: for each — id, tier ([enabled]/[searchable]), path.
4. SKILL I WOULD INVOKE: the one skill you'd actually use, and how.
5. VERDICT: good fit? yes / partial / no, one sentence why.
6. FRICTION: anything confusing or wrong about the search. Be blunt.

End by confirming you changed zero files.
```

The read-only framing is load-bearing. Agents that actually perform the task
burn time and can leave changes behind; the search result is the only output
that matters.

## 4. Verify the claims

Agents misreport. Check anything surprising against the catalog yourself before
writing it up — in one run a probe attributed `writing-plans` to the wrong
plugin, which would have read as a catalog defect if taken at face value.

Confirm the tree is clean when finished:

```
git status --porcelain
```

## Choosing a model

Both tiers route correctly. They differ sharply as *instruments*:

| | Routing | Usefulness as QA |
| --- | --- | --- |
| Opus | 10/10 | Flags real defects on nearly every probe |
| Haiku | 10/10 | Answers "FRICTION: None" ~8/10 times |

**Prefer Opus.** Haiku confirms the search works but rarely says why it doesn't.
Run Haiku only to check that a fix holds across model tiers.

## Reading the results

A probe that returns a plausible skill has **not** necessarily passed. Check:

- **Did it stay in budget?** `skill-search` allows the index plus at most two
  shards. A probe reading three has found something the catalog handles badly,
  even if it eventually got the right answer.
- **Was the answer right, or lucky?** A category whose members are all locked to
  one platform will answer confidently for every platform. Ask whether the same
  task on a different stack would still work.
- **Did a better skill exist that the catalog couldn't offer?** Compare against
  the session's actually-enabled skills. Silent shadowing is the worst failure
  mode: the agent is satisfied, and the better skill is unreachable.
- **Did several probes flag the same thing?** Independent agents converging on
  one complaint is a strong signal.

## Final output to show the user

**The table is the output.** One row per probe, and it always comes first:

```
| Task | Category | Skill picked | Fit |
```

Then the headline number (`N/10 hit`), then the defects. For each defect give:
what happens, why it happens (traced to the source, not guessed), why it
matters, and what shape the fix takes. Rank by whether the defect produces
*wrong answers* or merely *missing ones* — wrong is worse, because the agent
never knows to look further.

Close with confirmation that nothing was modified.

That much is always required. If the user asked for a **written analysis** at
step 0, add it after the defects — patterns across probes, how this run compares
to previous ones, what the results imply about the catalog's shape. It is an
addition to the table, never a replacement for it, and never a place to relocate
a defect: a reader who stops after the table must still have seen everything
that is wrong.

Keep it short either way. The table plus three or four real defects beats a full
transcript dump — the individual reports are evidence, not the deliverable.
