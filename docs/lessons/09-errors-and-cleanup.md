# Lesson 9: Errors and cleanup

## Goal

Two small side jobs. `MailFlow · Errors` sends any MailFlow failure to your Telegram.
`MailFlow · Cleanup` deletes rows older than 90 days every night, so the table never fills up.
Design: [SYSTEM-DESIGN.md §4 and §8](../SYSTEM-DESIGN.md#8-operations).

```
Error Trigger → Telegram
Schedule Trigger (02:00) → Delete old rows
```

## What you need

- All MailFlow workflows built so far.
- Credential `RI Email` and your chat ID (copy it from `Format alert` in `Work email · Telegram`,
  as in lesson 2).
- Decision D7 (how long to keep emails; default 90 days).

## Steps

### A. MailFlow · Errors

1. **Create Workflow** `MailFlow · Errors`, tag `mailflow`.
2. Add **Error Trigger**. It runs whenever a workflow that names this one as its error workflow fails.
3. Add **Telegram** → **Send Message**, credential `RI Email`, your chat ID, **Text**:

   ```
   MailFlow error
   Workflow: {{ $json.workflow.name }}
   Node: {{ $json.execution.lastNodeExecuted }}
   Error: {{ $json.execution.error.message }}
   Open: {{ $json.execution.url }}
   ```

   These are n8n's standard error fields. To confirm them: the Error Trigger's output panel shows
   example data after you **Execute step**; drag from there if a name differs.
4. **Save**. An error workflow does not need to be active.
5. Set it as the error workflow everywhere. In **each** MailFlow workflow (Process email, every
   collector, Inbox page, Email page, Cleanup, and `Work email · Telegram` too) open **Settings**
   → **Error workflow** → `MailFlow · Errors` → **Save**.

### B. MailFlow · Cleanup

6. **Create Workflow** `MailFlow · Cleanup`, tag `mailflow`.
7. Add **Schedule Trigger**: every **Day**, at hour **2**, minute **0** (02:00 server time).
8. Add a **Data Table** node `Delete old rows`: **Operation** **Delete**, table `MailFlow emails`,
   condition `received_at` **Less Than** `{{ $now.minus({days: 90}).toISO() }}`.
   (Change `90` if you chose another number in D7.)
9. If the node offers a **Dry Run** option, turn it **on** for the first run. A dry run shows
   which rows *would* be deleted without deleting them. If your version has no Dry Run, run the
   same condition first with a **Get** operation to see the rows, then switch to Delete.
10. Click **Execute workflow**. Check the output lists only rows older than 90 days (on a new
    table: none at all).
11. Turn **Dry Run** off, **Settings** → **Error workflow** `MailFlow · Errors`, **Save**, **Active**.

## Check it works

1. **Errors**: editor test runs do not fire the error workflow, so make a real, harmless failure.
   Create a throwaway workflow `MailFlow · error test`: **Schedule Trigger** (every minute) →
   **Code** node containing `throw new Error('MailFlow test error');`. Set its **Error workflow**
   to `MailFlow · Errors`, save, activate, wait one minute. A Telegram message
   "MailFlow error … MailFlow test error" arrives with a link to the failed run. Then deactivate
   and delete the throwaway workflow.
2. **Cleanup**: the dry run in step 10 listed only old rows. The next morning, **Executions**
   shows no failed Cleanup run.

## If something goes wrong

| Problem | What to do |
|---|---|
| No error message on Telegram | The failing workflow's **Error workflow** setting is not `MailFlow · Errors`, or the chat ID is wrong. Error workflows fire only for **active** (production) runs, not editor tests. |
| Error text shows `undefined` | A field name differs; drag it from the Error Trigger's output. |
| Cleanup deleted nothing | Expected while all mail is younger than 90 days. |
| Cleanup would delete new rows | Check the operator is **Less Than**, not Greater Than. |

## What you learned

- One error workflow can watch every workflow; each one points to it in its settings.
- A Schedule Trigger runs jobs on a timer without anyone clicking.
- Try destructive steps with a dry run (or a Get) first.
