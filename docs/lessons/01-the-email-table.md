# Lesson 1: The email table

## Goal

Create the n8n data table `MailFlow emails`. Every sorted email becomes one row in it. The pages
in lessons 5 and 6 read from it. Design: [SYSTEM-DESIGN.md §4](../SYSTEM-DESIGN.md#4-data-the-mailflow-emails-table).

## What you need

- Lesson 0 done.
- The column list below (copied from the design).

## Steps

1. In n8n, go to **Overview** → **Data tables** → **Create Data table**.
2. Choose **From scratch**. Name it exactly `MailFlow emails` (capital M, capital F, one space).
3. Add these 14 columns, **in this order**, with these names and types. Names are lower case with
   underscores; type them carefully, because lesson 2 maps fields to columns by name.

   | # | Column | Type | Filled by |
   |---|---|---|---|
   | 1 | `message_id` | string | collector |
   | 2 | `mailbox` | string | collector |
   | 3 | `source` | string | collector |
   | 4 | `from_name` | string | collector |
   | 5 | `from_address` | string | collector |
   | 6 | `subject` | string | collector |
   | 7 | `received_at` | **date** | collector |
   | 8 | `body` | string | collector (max 4,000 characters) |
   | 9 | `category` | string | rules or AI |
   | 10 | `sentiment` | string | rules or AI |
   | 11 | `urgency` | string | rules or AI |
   | 12 | `summary` | string | rules or AI |
   | 13 | `sorted_by` | string | `rule` or `ai` |
   | 14 | `status` | string | `new` on insert, `done` from the page |

   n8n also adds its own `id`, `createdAt` and `updatedAt` columns. Leave them.
4. Add **one test row by hand** (the **+** / add row button in the table view):

   | Column | Value |
   |---|---|
   | `message_id` | `<test-1@mail.example.com>` |
   | `mailbox` | `test@` |
   | `source` | `imap` |
   | `from_name` | `Test Sender` |
   | `from_address` | `test@example.com` |
   | `subject` | `Hello table` |
   | `received_at` | today's date |
   | `body` | `Just a test.` |
   | `category` | `Other` |
   | `sentiment` | `Neutral` |
   | `urgency` | `Low` |
   | `summary` | `A test row.` |
   | `sorted_by` | `rule` |
   | `status` | `new` |

5. Look at the row. Check every value landed in the right column.
6. Delete the test row (select it, then delete).

## Check it works

- **Data tables** lists `MailFlow emails`.
- It has exactly the 14 columns above (plus n8n's own), `received_at` is a date, the rest strings.
- The table is empty again after you deleted the test row.

## If something goes wrong

| Problem | What to do |
|---|---|
| A column name has a typo | Rename the column now (or delete and re-add it). A typo breaks lesson 2's automatic mapping. |
| `received_at` was made as string | Delete that column and add it again as **date**. The pages sort and the cleanup deletes by this date. |
| No **Data tables** tab | Your n8n user may lack permission, or the n8n version is older. Ask your helper. |

## What you learned

- A data table is a simple spreadsheet-like store that lives inside n8n.
- Column names matter: later nodes match fields to columns by exact name.
- `received_at` is a real date, so you can sort and filter by time.
