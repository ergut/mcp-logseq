# Logseq Task Operating System (for Personal + Work + Attention Regulation)

This is a practical methodology designed for this MCP Logseq server.
It uses Logseq tasks, properties, namespaces, journals, and queries so an AI agent can help you plan, execute, and review consistently.

## 1) Data model (simple, structured, queryable)

Use **one task format** everywhere:

```markdown
- TODO Write API proposal
  type:: work
  project:: [[projects/work/client-alpha]]
  area:: [[areas/career]]
  energy:: medium
  attention_cost:: high
  estimate_min:: 45
  due:: <2026-02-26 Thu>
  emotion_before:: anxious
  emotion_after:: relieved
  focus_score:: 2
  outcome_score:: 4
```

### Required properties
- `type`: `work` | `personal`
- `project`: page link to a project (or `[[projects/personal/life-admin]]`)
- `attention_cost`: `low` | `medium` | `high`

### Recommended properties
- `energy`: `low` | `medium` | `high`
- `estimate_min`: planned effort in minutes
- `due`: Logseq date
- `emotion_before`: short feeling label before starting
- `emotion_after`: short feeling label after finishing
- `focus_score`: 1-5 self-rating of attention quality
- `outcome_score`: 1-5 self-rating of completion quality

## 2) Page structure

- `projects/work/<name>` and `projects/personal/<name>` for project pages
- `areas/<area-name>` for long-lived responsibilities
- Journal pages for daily capture and execution

Each project page should contain:
- `status:: active | paused | done`
- `review_cadence:: weekly`
- `success_metric:: <plain text>`
- A section for next actions (task blocks with `project:: [[this page]]`)

## 3) Task lifecycle

Use markers consistently:
- `TODO` = not started
- `DOING` = currently in progress (keep WIP low)
- `DONE` = completed

Suggested flow:
1. Capture quickly in journal or inbox page.
2. Clarify into a concrete next action (`verb + object`).
3. Attach project + attention/emotion properties.
4. Execute in short focus blocks (15-50 minutes).
5. On completion, set `emotion_after`, `focus_score`, `outcome_score`, then mark `DONE`.

## 4) Daily workflow (attention-friendly)

### Morning (5-10 min)
- Pick top 1-3 tasks from active projects.
- Balance by attention cost: 1 high + 1 medium + optional low.
- Pre-log `emotion_before` to improve self-awareness.

### During day
- Keep only one `DOING` task at a time.
- If stuck >10 min, split task into a smaller subtask.
- If dysregulated, switch to one pre-selected low attention task.

### Evening (5 min)
- Mark outcomes and emotional shift (`emotion_before` -> `emotion_after`).
- Add one sentence: "What helped focus today?"

## 5) Weekly review (performance + regulation)

Track these metrics by querying tasks from last 7 days:
- Completion rate = `DONE / (TODO+DOING+DONE created this week)`
- Focus average = mean(`focus_score`)
- Outcome average = mean(`outcome_score`)
- Emotion shift trend = frequent transitions (e.g., anxious -> relieved)
- Attention fit = how often high `attention_cost` tasks were completed when energy was high

Then decide:
- Which project needs scope reduction?
- Which task types cause repeated low focus?
- What schedule changes improve completion for high attention tasks?

## 6) MCP usage pattern

Use the MCP tools in this order:
1. `query` for task selection and weekly analytics.
2. `find_pages_by_property` to list active projects (`status:: active`).
3. `update_page` to append daily plan/review blocks.
4. `insert_nested_block` to break large tasks into smaller children.

## 7) Example queries to run via MCP `query`

### Active tasks for a project
```clojure
(and (task todo) (page [[projects/work/client-alpha]]))
```

### High-attention tasks not done
```clojure
(and (task todo) (property attention_cost high))
```

### Completed tasks with low focus
```clojure
(and (task done) (property focus_score 1))
```

### Personal tasks due soon
```clojure
(and (task todo) (property type personal))
```

> Adjust query syntax to your Logseq version if needed.

## 8) Why this works for attention regulation

- **Externalizes state**: emotion and focus become visible data, not vague memory.
- **Reduces overwhelm**: strict `DOING` limit and smaller subtasks.
- **Improves planning accuracy**: compare `estimate_min` vs outcomes over time.
- **Builds feedback loops**: daily + weekly review converts experience into better task design.
