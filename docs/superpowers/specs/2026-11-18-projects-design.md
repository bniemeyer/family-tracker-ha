# HouseKeeper — Projects

## Intent
A **Projects** tab (after Seasonal) for household projects, organized as
**Project → Heading → Task → Subtask** (headings group tasks; subtasks are the deepest level).

## Goals
- Create/rename/reorder/delete at every level; check off tasks and subtasks.
- Progress at every level (heading n/m, task subtasks n/m, project bar). Checking the last subtask checks its task;
  unchecking a subtask unchecks its task.
- Project status: Planning · Active · On hold · Done. Done projects collapse into "Completed".
- Task fields (owner chose all four):
  - **Due date** (also an optional project target date). Overdue / due-soon tasks of non-Done projects feed the
    Overview list, the HA sensors (`sensor.family_tracker_overdue` / `due_soon`, section "Projects"), reminders,
    calendar feed and voice answers.
  - **Assigned to** — one person from a **People** list edited in Settings (doc `meta/people`; not hard-coded,
    the repo is public). Projects page gets a "Mine / Everyone" person filter.
  - **Cost** — estimated and actual per task; project shows budget (sum of estimates, or an explicit project
    budget) vs. spent (sum of actuals).
  - **Notes & link** — free-text notes plus one URL, shown as a 🛒/↗ button like the parts list.
- Subtasks: text + done only (keep the deepest level light).

- **Supplies & tools** (added by owner): per-project list `materials:[{id,name,kind:'Supply'|'Tool',qty,unit,taskId,
  status:'need'|'have',estCost,actCost,url,notes,partId}]`.
  - Optional link to an existing Parts inventory item (`partId`): shows on-hand qty; auto "have" when on hand ≥ qty.
  - Costs roll into project budget/spent with task costs.
  - Task rows show a 🧰 count of linked materials.
  - "What to buy" view across active projects (grouped by project, 🛒 Buy buttons); voice "what do I need to buy
    [for <project>]" includes project needs; existing "what do we need to buy" adds them.
  - Marking an item have/bought records actual cost; optional "add leftovers to inventory".

## Non-goals
- No dependencies/Gantt, no recurring project tasks (Home tasks cover recurrence), no photos per task (v1).

## Approaches
1. **One document per project with nested arrays (chosen).** `projects/<id>` = {name, status, targetDate,
   budget, notes, headings:[{id,title,tasks:[{id,text,done,doneAt,due,assignee,estCost,actCost,notes,url,
   subtasks:[{id,text,done}]}]}]}. Matches how Seasonal stores items; atomic saves; simple backup/import.
2. Separate collections per level (projects/headings/tasks/subtasks). Rejected: many writes per edit and more
   listeners for no benefit at household scale.
3. Reuse Seasonal checklists with nesting. Rejected: different lifecycle (seasonal reset vs one-off projects).

## UI
- Projects list: cards with status badge, progress bar, next due task, budget/spent, assignee chips.
- Project page: header (name, status select, target date, budget, notes), collapsible headings, task rows with
  checkbox, due badge, assignee chip, cost, link button; inline "+ task", "+ subtask", "+ heading";
  tap a task to open its editor (all fields); ↑/↓ reorder; delete with confirm.
- Settings → People panel to add/remove names.

## Shipping
Version 1.5.0; tag + GitHub release; update add-on in HA. Voice automation learns "what projects are active",
"what's left on <project>". Assist/automations keep using existing sensor IDs.

## Left to the builder
Exact layout/spacing, keyboard handling for inline adds.
