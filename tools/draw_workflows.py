#!/usr/bin/env python3
"""Draw n8n workflow exports as diagrams (SVG + PNG) for the docs.

    python3 tools/draw_workflows.py EXPORT_DIR OUT_DIR

EXPORT_DIR holds workflow JSON files as n8n exports them (name, nodes, connections).
Each workflow becomes OUT_DIR/<slug>.svg and .png (PNG needs `rsvg-convert`).
Nodes are laid out left to right by their distance from the trigger; AI sub-nodes
(chat models) sit under the node they plug into. Only names, node types and
operations are drawn: no credentials, ids or parameter values.
"""
import html
import json
import re
import subprocess
import sys
from pathlib import Path

W, H, GX, GY, PAD = 220, 70, 70, 34, 40
STYLE = {  # kind: fill, stroke
    "trigger": ("#dcfce7", "#16a34a"),
    "data": ("#ecfeff", "#0891b2"),
    "ai": ("#ede9fe", "#7c3aed"),
    "logic": ("#fef3c7", "#d97706"),
    "transform": ("#f3f4f6", "#6b7280"),
    "out": ("#dbeafe", "#2563eb"),
    "respond": ("#f0fdf4", "#15803d"),
}
KIND = {
    "webhook": "trigger", "emailReadImap": "trigger", "executeWorkflowTrigger": "trigger",
    "dataTable": "data", "informationExtractor": "ai", "lmChatOllama": "ai",
    "if": "logic", "filter": "logic", "merge": "logic",
    "set": "transform", "code": "transform",
    "gmail": "out", "telegram": "out", "executeWorkflow": "out",
    "respondToWebhook": "respond",
}
LABEL = {
    "webhook": "Webhook", "emailReadImap": "Email Trigger (IMAP)",
    "executeWorkflowTrigger": "When Executed by Another Workflow", "dataTable": "Data Table",
    "informationExtractor": "Information Extractor", "lmChatOllama": "Ollama Chat Model",
    "if": "If", "filter": "Filter", "merge": "Merge", "set": "Edit Fields", "code": "Code",
    "gmail": "Gmail", "telegram": "Telegram", "executeWorkflow": "Execute Sub-workflow",
    "respondToWebhook": "Respond to Webhook",
}
OPS = {"rowNotExists": "If Row Does Not Exist", "get": "Get", "insert": "Insert", "update": "Update",
       "getAll": "Get Many", "reply": "Reply", "send": "Send"}


def describe(node):
    short = node["type"].split(".")[-1]
    text = LABEL.get(short, short)
    p = node.get("parameters", {})
    if short == "webhook":
        text += f" · {p.get('httpMethod', 'GET')} /{p.get('path', '')}"
    elif p.get("operation") in OPS:
        text += f" · {OPS[p['operation']]}"
    elif short == "merge":
        text += " · by position"
    return KIND.get(short, "transform"), text


def layout(wf):
    nodes = {n["name"]: n for n in wf["nodes"]}
    main, sub = {}, {}
    for src, outs in wf.get("connections", {}).items():
        for ctype, branches in outs.items():
            for i, branch in enumerate(branches or []):
                for c in branch or []:
                    if ctype == "main":
                        main.setdefault(src, []).append((c["node"], i, c.get("index", 0)))
                    else:
                        sub[src] = c["node"]
    targets = {t for outs in main.values() for t, _, _ in outs}
    parents = {}
    for src, outs in main.items():
        for t, i, _ in outs:
            parents.setdefault(t, []).append((src, i))
    # Column: distance from the trigger (longest path), so every arrow points right.
    depth = {n: 0 for n in nodes if n not in targets and n not in sub}
    changed = True
    while changed:
        changed = False
        for src, outs in main.items():
            for t, _, _ in outs:
                if src in depth and depth.get(t, -1) < depth[src] + 1:
                    depth[t] = depth[src] + 1
                    changed = True
    # Row: each trigger starts its own block; inside it a node takes the lowest row of its
    # parents, plus 1 when it hangs off an If's false output, so each branch keeps its own row.
    row, taken = {}, set()
    triggers = sorted((n for n in depth if n not in parents), key=lambda n: nodes[n]["position"][1])
    base = 0
    for trig in triggers:
        block = {trig}
        grew = True
        while grew:
            grew = False
            for src, outs in main.items():
                if src in block:
                    for t, _, _ in outs:
                        if t not in block:
                            block.add(t)
                            grew = True
        for name in sorted((n for n in block if n not in row), key=lambda n: (depth[n], nodes[n]["position"][1])):
            if name == trig:
                r = base
            else:
                r = min(row[p] + (1 if i > 0 else 0) for p, i in parents[name] if p in row)
            while (depth[name], r) in taken:
                r += 1
            row[name] = r
            taken.add((depth[name], r))
        for child, parent in sub.items():
            if parent in block and child not in row:
                d, r = depth[parent], row[parent] + 1
                while (d, r) in taken:
                    r += 1
                depth[child], row[child] = d, r
                taken.add((d, r))
        base = max(r for _, r in taken) + 1
    pos = {name: [depth[name], row[name]] for name in row}
    return nodes, main, sub, pos


def edge_label(src_node, out_index):
    short = src_node["type"].split(".")[-1]
    if short == "if":
        return "true" if out_index == 0 else "false"
    return ""


def draw(wf):
    nodes, main, sub, pos = layout(wf)
    xy = {n: (PAD + c * (W + GX), 110 + r * (H + GY)) for n, (c, r) in pos.items()}
    cells = {tuple(p) for p in pos.values()}
    width = max(max(x for x, _ in xy.values()) + W + PAD, 760)
    height = max(y for _, y in xy.values()) + H + PAD + GY
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif">',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           f'<text x="{PAD}" y="48" font-size="26" font-weight="bold" fill="#1f2937">{html.escape(wf["name"])}</text>',
           f'<text x="{PAD}" y="76" font-size="14" fill="#6b7280">{html.escape(wf.get("_note", ""))}</text>',
           '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
           '<path d="M0,0 L10,5 L0,10 z" fill="#6b7280"/></marker></defs>']
    for src, outs in main.items():
        for t, i, _ in outs:
            if src not in xy or t not in xy:
                continue
            (c1, r1), (c2, r2) = pos[src], pos[t]
            x1, y1 = xy[src][0] + W, xy[src][1] + H / 2
            x2, y2 = xy[t][0], xy[t][1] + H / 2
            blocked = any((c, r) in cells for c in range(c1 + 1, c2) for r in {r1, r2})
            if blocked:
                # go round the boxes in between, along the gap below the lower row
                lane = max(xy[src][1], xy[t][1]) + H + GY / 2
                d = (f"M{x1},{y1} C{x1 + GX / 2},{y1} {x1 + GX / 2},{lane} {x1 + GX},{lane} "
                     f"L{x2 - GX},{lane} C{x2 - GX / 2},{lane} {x2 - GX / 2},{y2} {x2 - 2},{y2}")
            else:
                mx = (x1 + x2) / 2
                d = f"M{x1},{y1} C{mx},{y1} {mx},{y2} {x2 - 2},{y2}"
            out.append(f'<path d="{d}" fill="none" stroke="#9ca3af" stroke-width="2" marker-end="url(#a)"/>')
            lab = edge_label(nodes[src], i)
            if lab:
                ly = y1 - 8 if i == 0 else y1 + 20
                out.append(f'<text x="{x1 + 6}" y="{ly}" font-size="12" font-weight="bold" fill="#b45309">{lab}</text>')
    for child, parent in sub.items():
        if child in xy and parent in xy:
            x = xy[child][0] + W / 2
            out.append(f'<line x1="{x}" y1="{xy[child][1]}" x2="{x}" y2="{xy[parent][1] + H + 2}" stroke="#7c3aed" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#a)"/>')
    for name, (x, y) in xy.items():
        kind, text = describe(nodes[name])
        fill, stroke = STYLE[kind]
        title = name if len(name) <= 26 else name[:25] + "…"
        sub_text = text if len(text) <= 34 else text[:33] + "…"
        out.append(f'<rect x="{x}" y="{y}" width="{W}" height="{H}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        out.append(f'<text x="{x + 12}" y="{y + 28}" font-size="15" font-weight="bold" fill="#111827">{html.escape(title)}</text>')
        out.append(f'<text x="{x + 12}" y="{y + 50}" font-size="12" fill="#4b5563">{html.escape(sub_text)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("mailflow ·", "")).strip("-")


def main(argv):
    src, dst = Path(argv[1]), Path(argv[2])
    dst.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.glob("*.json")):
        wf = json.loads(f.read_text())
        svg_path = dst / f"{slug(wf['name'])}.svg"
        svg_path.write_text(draw(wf))
        # 1.5x the drawing's own size, so wide workflows stay readable instead of shrinking to fit
        subprocess.run(["rsvg-convert", "-z", "1.5", str(svg_path), "-o", str(svg_path.with_suffix(".png"))], check=True)
        print(svg_path.with_suffix(".png"))


if __name__ == "__main__":
    main(sys.argv)
