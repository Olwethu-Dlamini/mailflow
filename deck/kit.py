"""Slide helpers shared by build_client.py and build_technical.py.

Same look as the MailFlow page: white, flat, one blue accent, soft tints for labels.
Needs python-pptx; PDFs come from LibreOffice (see build.sh).
"""

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
IMAGES = HERE.parent / "docs" / "images"

TEXT = RGBColor(0x11, 0x18, 0x27)
TEXT2 = RGBColor(0x37, 0x41, 0x51)
MUTED = RGBColor(0x6B, 0x72, 0x80)
FAINT = RGBColor(0x9C, 0xA3, 0xAF)
LINE = RGBColor(0xE5, 0xE7, 0xEB)
HOVER = RGBColor(0xF6, 0xF7, 0xF9)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BLUE, BLUE_SOFT = RGBColor(0x25, 0x63, 0xEB), RGBColor(0xEF, 0xF4, 0xFF)
RED, RED_SOFT = RGBColor(0xB4, 0x23, 0x18), RGBColor(0xFE, 0xF1, 0xF0)
AMBER, AMBER_SOFT = RGBColor(0xB5, 0x47, 0x08), RGBColor(0xFF, 0xF6, 0xE5)
GREEN, GREEN_SOFT = RGBColor(0x06, 0x76, 0x47), RGBColor(0xEC, 0xFD, 0xF3)
VIOLET, VIOLET_SOFT = RGBColor(0x59, 0x25, 0xDC), RGBColor(0xF4, 0xF3, 0xFF)
SKY, SKY_SOFT = RGBColor(0x02, 0x6A, 0xA2), RGBColor(0xF0, 0xF9, 0xFF)

FONT = "Noto Sans"
W, H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.75)
CONTENT_W = W - 2 * MARGIN
TOP = Inches(1.85)  # where content starts under a slide title


class Deck:
    def __init__(self, footer: str):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = W, H
        self.blank = self.prs.slide_layouts[6]
        self.footer = footer

    @property
    def count(self) -> int:
        return len(self.prs.slides._sldIdLst)

    def title_slide(self, kicker: str, title: str, subtitle: str, notes: str, footnote: str = ""):
        s = self.prs.slides.add_slide(self.blank)
        mark(s, MARGIN, Inches(1.2), Inches(0.62))
        text(s, MARGIN + Inches(0.8), Inches(1.2), Inches(6), Inches(0.62), "MailFlow", 26, TEXT, True,
             anchor=MSO_ANCHOR.MIDDLE)
        text(s, MARGIN, Inches(2.65), CONTENT_W, Inches(0.4), kicker.upper(), 14, BLUE, True)
        text(s, MARGIN, Inches(3.1), Inches(11), Inches(1.6), title, 40, TEXT, True)
        text(s, MARGIN, Inches(4.75), Inches(10.5), Inches(1.0), subtitle, 20, MUTED)
        if footnote:
            rule(s, MARGIN, Inches(6.55), CONTENT_W)
            text(s, MARGIN, Inches(6.7), CONTENT_W, Inches(0.4), footnote, 12, FAINT)
        s.notes_slide.notes_text_frame.text = notes
        return s

    def slide(self, section: str, title: str, notes: str, subtitle: str = ""):
        s = self.prs.slides.add_slide(self.blank)
        text(s, MARGIN, Inches(0.5), Inches(9), Inches(0.35), section.upper(), 12, BLUE, True)
        text(s, MARGIN, Inches(0.8), CONTENT_W, Inches(0.75), title, 30, TEXT, True)
        if subtitle:
            text(s, MARGIN, Inches(1.38), CONTENT_W, Inches(0.4), subtitle, 15, MUTED)
        mark(s, MARGIN, Inches(7.0), Inches(0.24))
        text(s, MARGIN + Inches(0.32), Inches(6.98), Inches(6), Inches(0.3), self.footer, 10, FAINT,
             anchor=MSO_ANCHOR.MIDDLE)
        text(s, W - MARGIN - Inches(1), Inches(6.98), Inches(1), Inches(0.3), str(self.count), 10, FAINT,
             align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
        s.notes_slide.notes_text_frame.text = notes
        return s

    def save(self, path: Path):
        self.prs.save(path)
        print(f"Wrote {path.name} ({self.count} slides)")


def _style(run, size, color, bold):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold


def shape(s, x, y, w, h, fill=None, line=None, kind=MSO_SHAPE.RECTANGLE, radius=None):
    sh = s.shapes.add_shape(kind, x, y, w, h)
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(0.75)
    sh.shadow.inherit = False
    if radius is not None and kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        sh.adjustments[0] = radius
    return sh


def text(s, x, y, w, h, lines, size=16, color=TEXT, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, spacing=0):
    tb = s.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, line in enumerate([lines] if isinstance(lines, str) else lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(spacing)
        if isinstance(line, tuple):  # (bold lead, rest)
            _style(_run(p, line[0]), size, color, True)
            _style(_run(p, line[1]), size, color, bold)
        else:
            _style(_run(p, line), size, color, bold)
    return tb


def _run(p, value):
    r = p.add_run()
    r.text = value
    return r


def bullets(s, x, y, w, h, items, size=17, color=TEXT2, dot=BLUE, spacing=10):
    """items: strings or (bold lead, rest) tuples."""
    tb = s.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(spacing)
        _style(_run(p, "●  "), size - 7, dot, False)
        if isinstance(item, tuple):
            _style(_run(p, item[0]), size, TEXT, True)
            _style(_run(p, item[1]), size, color, False)
        else:
            _style(_run(p, item), size, color, False)
    return tb


def rule(s, x, y, w, color=LINE):
    return shape(s, x, y, w, Pt(1), fill=color)


def mark(s, x, y, size):
    """The blue M square from the page."""
    sq = shape(s, x, y, size, size, fill=BLUE, kind=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.22)
    tf = sq.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    _style(_run(p, "M"), max(8, int(size / 12700 * 0.55)), WHITE, True)
    return sq


def pill(s, x, y, label, fg=TEXT2, bg=HOVER, size=12, w=None):
    w = w or Inches(0.13 * len(label) * size / 12 + 0.35)
    sh = shape(s, x, y, w, Inches(0.32 * size / 12), fill=bg, kind=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
    tf = sh.text_frame
    tf.margin_left = tf.margin_right = Inches(0.08)
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    _style(_run(p, label), size, fg, True)
    return w


def card(s, x, y, w, h, head, body, accent=BLUE, tint=None, head_size=17, body_size=14, number=None):
    """A white card with a thin border; optional coloured number circle or tinted fill."""
    shape(s, x, y, w, h, fill=tint or WHITE, line=LINE, kind=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
    pad = Inches(0.25)
    ty = y + pad
    if number is not None:
        c = shape(s, x + pad, ty, Inches(0.46), Inches(0.46), fill=accent, kind=MSO_SHAPE.OVAL)
        tf = c.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        _style(_run(tf.paragraphs[0], str(number)), 15, WHITE, True)
        ty += Inches(0.62)
    # Rough line count for the heading: about 0.55 em per character in Noto Sans bold.
    chars_per_line = max(1, int((w - 2 * pad) / 12700 / (head_size * 0.58)))
    head_lines = -(-len(head) // chars_per_line)
    head_h = Pt(head_size * 1.3 * head_lines)
    text(s, x + pad, ty, w - 2 * pad, head_h, head, head_size, accent if tint else TEXT, True)
    body_y = ty + head_h + Inches(0.12)
    text(s, x + pad, body_y, w - 2 * pad, h - (body_y - y) - pad, body, body_size, TEXT2)


def picture(s, path, x=None, y=TOP, max_w=CONTENT_W, max_h=Inches(4.9), border=True):
    path = Path(path) if Path(path).is_absolute() else IMAGES / path
    with Image.open(path) as im:
        ratio = im.width / im.height
    w = max_w
    h = int(w / ratio)
    if h > max_h:
        h = max_h
        w = int(h * ratio)
    x = int((W - w) / 2) if x is None else x
    pic = s.shapes.add_picture(str(path), x, y, w, h)
    if border:
        pic.line.color.rgb = LINE
        pic.line.width = Pt(0.75)
    return pic


def table(s, x, y, col_w, rows, size=13, row_h=Inches(0.42), head_fill=HOVER, first_bold=True):
    shp = s.shapes.add_table(len(rows), len(rows[0]), x, y, sum(col_w), row_h * len(rows))
    t = shp.table
    for i, cw in enumerate(col_w):
        t.columns[i].width = cw
    for r, row in enumerate(rows):
        t.rows[r].height = row_h
        for c, val in enumerate(row):
            cell = t.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = head_fill if r == 0 else WHITE
            cell.margin_left = cell.margin_right = Inches(0.12)
            cell.margin_top = cell.margin_bottom = Inches(0.05)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            _style(_run(p, val), size if r else size - 1, MUTED if r == 0 else TEXT,
                   r == 0 or (first_bold and c == 0))
    tbl = shp._element.graphic.graphicData.tbl
    tbl.tblPr.set("bandRow", "0")
    tbl.tblPr.set("firstRow", "0")
    return shp


def arrow(s, x1, y1, x2, y2, color=BLUE, width=1.75):
    from pptx.enum.shapes import MSO_CONNECTOR
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x1, y1, x2, y2)
    c.line.color.rgb = color
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    tail = ln.makeelement("{http://schemas.openxmlformats.org/drawingml/2006/main}tailEnd", {"type": "triangle"})
    ln.append(tail)
    return c


def flow(s, y, steps, h=Inches(2.6), accent=BLUE, gap=Inches(0.35), body_size=13):
    """A row of numbered cards joined by arrows. steps: [(head, body)]."""
    n = len(steps)
    w = int((CONTENT_W - gap * (n - 1)) / n)
    for i, (head, body) in enumerate(steps):
        x = MARGIN + i * (w + gap)
        card(s, x, y, w, h, head, body, accent=accent, number=i + 1, head_size=15, body_size=body_size)
        if i < n - 1:
            arrow(s, x + w + Inches(0.05), y + h // 2, x + w + gap - Inches(0.05), y + h // 2, color=FAINT, width=1.25)
