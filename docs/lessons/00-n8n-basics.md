# Lesson 0: n8n basics (20-minute warm-up)

## Goal

Get comfortable with the n8n editor on the company server before building MailFlow. You will
make a throwaway workflow, run it, read its output, write one expression, pin data, and delete it.

## What you need

- A computer on the company tailnet (Tailscale switched on).
- Your n8n login.
- 20 minutes.

## Steps

1. Open **http://ai:5678** in your browser and log in.
2. Click **Create Workflow** (top left, or the **+** button). An empty canvas opens.
3. Click the workflow name at the top and rename it to `Practice · delete me`.
4. Click **Add first step** and choose **Trigger manually**. This adds **Manual Trigger**
   ("When clicking 'Execute workflow'"). It starts the workflow only when you click a button.
5. Click the **+** on the right of the trigger. Search for **Edit Fields (Set)** and add it.
6. In **Edit Fields**, keep **Mode: Manual Mapping**. Click **Add Field** three times and fill in:

   | Name | Type | Value |
   |---|---|---|
   | `from_address` | String | `sipho@example.com` |
   | `subject` | String | `Charged twice for November` |
   | `priority` | String | `P1` |

7. Close the node and click **Execute workflow** at the bottom of the canvas.
8. Double-click **Edit Fields** again. The right side is the **output panel**. Try the three views:
   **Table**, **JSON** and **Schema**. They show the same item in different ways.
9. Click the **+** after **Edit Fields** and add a second **Edit Fields (Set)** node. Its left
   side is the **input panel**: it shows the three fields from the first node. In every later
   lesson you will drag fields from here.
10. Add a field `alert_copy`, type String, and **drag** `subject` from the input panel into its
    value box. n8n writes `{{ $json.subject }}` for you. `$json` means "the item coming into
    this node". Dragging is the safest way to get field names right.
11. Now write an **expression** by hand. Add a field `alert`, type String, and type:

    ```
    {{ $json.priority === 'P1' ? 'Answer today: ' + $json.subject : 'Can wait' }}
    ```

    The grey preview under the box shows the result before you run anything.
    Click **Execute workflow** again and look at the second node's output.
12. **Pin data**: open the first **Edit Fields** node, and in the output panel click the **pin**
    icon. The output turns purple-ish and stays fixed. Change a value in the node and run again:
    the pinned output does not change. Click the pin again to unpin.
13. Delete the practice workflow: go back to **Overview**, open the **⋯** menu on
    `Practice · delete me`, choose **Delete** (in newer versions **Archive** first, then
    **Delete**).

## Check it works

- You saw the item in Table, JSON and Schema views.
- The second Edit Fields output shows `alert_copy` = `Charged twice for November`.
- `Practice · delete me` is no longer in the workflow list.

## If something goes wrong

| Problem | What to do |
|---|---|
| http://ai:5678 does not open | Check Tailscale is connected on your computer. |
| An expression shows `undefined` | The field is not in the input. Drag it from the input panel instead of typing it. |
| The value box shows text instead of a result | It is in **Fixed** mode. Switch it to **Expression** (the toggle above the box) or start with `{{`. |
| "No input data" in a node | Run the nodes before it first (**Execute previous nodes** or **Execute workflow**). |

## What you learned

- A workflow is a trigger plus nodes; each node gets items in and gives items out.
- Expressions in `{{ }}` read data; dragging from the input panel writes them for you.
- Pinned data freezes a node's output so you can test the rest without fetching again.
