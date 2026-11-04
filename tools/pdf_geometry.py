"""Extract the drawn geometry of a single-page matplotlib PDF, without rendering.

The paper's figures are matplotlib PDFs. Comparing their text (labels, counts)
cannot see a point, cell or bar that moved while every label stayed the same, and
comparing rasterised pixels mixes data changes with font, hinting and renderer
differences between platforms and matplotlib versions. This module reads the vector
content directly, using only the standard library:

* objects are located through the file's own xref table, so binary image streams
  are sliced by their declared /Length instead of by searching for delimiters;
* the page content stream is tokenised and interpreted with the PDF graphics-state
  rules that affect position (q/Q, cm) and colour (g/G, rg/RG, k/K, sc/scn);
* every painted path (stroke and/or fill) is recorded with its colours and the
  transformed coordinates of all its points; every Form XObject placement (scatter
  markers) is recorded at its transformed origin with a digest of the form's own
  drawing; every Image XObject is recorded with its placement and a digest of its
  decoded samples (the heatmap cells);
* text (BT ... ET) is deliberately not recorded: glyph positions legitimately vary
  with the font and matplotlib version, and the text itself is compared separately.

Coordinates are expressed relative to a reference frame -- the largest clipping
rectangle on the page (the axes area), or, when a figure has no clipped axes, the
bounding box of all recorded geometry -- so that a pure translation or scaling of
the whole plotting area (from a different label width in a tight layout) does not
count as a change, while any movement of an element *within* the frame does.

Only the PDF features that matplotlib's PDF backend emits are supported; anything
else raises GeometryError rather than being silently skipped.
"""
from __future__ import annotations

import hashlib
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path


class GeometryError(ValueError):
    pass


# ----------------------------------------------------------------- objects ---
def _objects(data: bytes) -> dict[int, tuple[bytes, bytes | None]]:
    """Map object number -> (dictionary bytes, decoded stream or None) via the xref."""
    m = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", data)
    if not m:
        raise GeometryError("no startxref trailer")
    pos = int(m.group(1))
    if data[pos:pos + 4] != b"xref":
        raise GeometryError("cross-reference streams are not supported")
    offsets: dict[int, int] = {}
    lines = data[pos:].split(b"\n")
    i = 1
    while i < len(lines):
        head = lines[i].strip().split()
        if len(head) != 2 or not all(t.isdigit() for t in head):
            break
        first, count = int(head[0]), int(head[1])
        for k in range(count):
            entry = lines[i + 1 + k].strip().split()
            if len(entry) == 3 and entry[2] == b"n":
                offsets[first + k] = int(entry[0])
        i += 1 + count

    def header(num: int) -> tuple[int, bytes]:
        off = offsets[num]
        hm = re.compile(rb"\s*%d\s+0\s+obj\s*" % num).match(data, off)
        if not hm:
            raise GeometryError(f"object {num} not at its xref offset")
        return hm.end(), data

    def read_dict(start: int) -> tuple[bytes, int]:
        if data[start:start + 2] != b"<<":
            return b"", start
        depth, j = 0, start
        while j < len(data):
            if data[j:j + 2] == b"<<":
                depth += 1
                j += 2
            elif data[j:j + 2] == b">>":
                depth -= 1
                j += 2
                if depth == 0:
                    return data[start:j], j
            elif data[j:j + 1] == b"(":  # skip literal strings
                level, j = 1, j + 1
                while level and j < len(data):
                    c = data[j:j + 1]
                    if c == b"\\":
                        j += 2
                        continue
                    level += {b"(": 1, b")": -1}.get(c, 0)
                    j += 1
            else:
                j += 1
        raise GeometryError("unterminated dictionary")

    def integer(num: int) -> int:
        start, _ = header(num)
        im = re.compile(rb"(\d+)\s*endobj").match(data, start)
        if not im:
            raise GeometryError(f"object {num} is not an integer")
        return int(im.group(1))

    objs: dict[int, tuple[bytes, bytes | None]] = {}
    for num in offsets:
        start, _ = header(num)
        d, after = read_dict(start)
        sm = re.compile(rb"\s*stream\r?\n").match(data, after)
        if not d or not sm:
            objs[num] = (d or data[start:data.index(b"endobj", start)], None)
            continue
        lm = re.search(rb"/Length\s+(\d+)(\s+0\s+R)?", d)
        if not lm:
            raise GeometryError(f"stream {num} has no /Length")
        length = integer(int(lm.group(1))) if lm.group(2) else int(lm.group(1))
        raw = data[sm.end():sm.end() + length]
        if b"/FlateDecode" in d:
            raw = zlib.decompress(raw)
        elif b"/Filter" in d:
            raise GeometryError(f"stream {num} uses an unsupported filter")
        objs[num] = (d, raw)
    return objs


# ------------------------------------------------------------ tokenisation ---
_DELIM = b"()<>[]{}/%"
_WS = b" \t\r\n\x0c\x00"


def _tokens(stream: bytes):
    i, n = 0, len(stream)
    while i < n:
        c = stream[i:i + 1]
        if c in (b" ", b"\t", b"\r", b"\n", b"\x0c", b"\x00"):
            i += 1
        elif c == b"%":
            while i < n and stream[i:i + 1] not in (b"\r", b"\n"):
                i += 1
        elif c == b"(":
            level, j = 1, i + 1
            while level and j < n:
                ch = stream[j:j + 1]
                if ch == b"\\":
                    j += 2
                    continue
                level += {b"(": 1, b")": -1}.get(ch, 0)
                j += 1
            yield ("str", stream[i:j])
            i = j
        elif c == b"<" and stream[i:i + 2] != b"<<":
            j = stream.index(b">", i)
            yield ("str", stream[i:j + 1])
            i = j + 1
        elif stream[i:i + 2] in (b"<<", b">>"):
            yield ("delim", stream[i:i + 2])
            i += 2
        elif c in (b"[", b"]"):
            yield ("delim", c)
            i += 1
        elif c == b"/":
            j = i + 1
            while j < n and stream[j:j + 1] not in _WS and stream[j:j + 1] not in _DELIM:
                j += 1
            yield ("name", stream[i + 1:j].decode("latin-1"))
            i = j
        else:
            j = i
            while j < n and stream[j:j + 1] not in _WS and stream[j:j + 1] not in _DELIM:
                j += 1
            word = stream[i:j]
            try:
                yield ("num", float(word))
            except ValueError:
                yield ("op", word.decode("latin-1"))
            i = j


# ------------------------------------------------------------------ images ---
def _literal(raw: bytes) -> bytes:
    """Decode a PDF literal string body (without the outer parentheses)."""
    out, i = bytearray(), 0
    esc = {b"n": 10, b"r": 13, b"t": 9, b"b": 8, b"f": 12, b"(": 40, b")": 41, b"\\": 92}
    while i < len(raw):
        c = raw[i:i + 1]
        if c != b"\\":
            out += c
            i += 1
            continue
        nxt = raw[i + 1:i + 2]
        if nxt in esc:
            out.append(esc[nxt])
            i += 2
        elif nxt.isdigit():
            j = i + 1
            while j < len(raw) and j < i + 4 and raw[j:j + 1] in b"01234567":
                j += 1
            out.append(int(raw[i + 1:j], 8) & 0xFF)
            i = j
        elif nxt in (b"\r", b"\n"):
            i += 2 + (raw[i + 1:i + 3] == b"\r\n")
        else:
            out += nxt
            i += 2
    return bytes(out)


def _unpredict(raw: bytes, row_bytes: int, bpp: int) -> bytes:
    """Undo PNG row filters (PDF /Predictor >= 10)."""
    out, prev, i = bytearray(), bytearray(row_bytes), 0
    while i < len(raw):
        ftype, row = raw[i], bytearray(raw[i + 1:i + 1 + row_bytes])
        i += 1 + row_bytes
        for x in range(len(row)):
            a = row[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if ftype == 1:
                row[x] = (row[x] + a) & 0xFF
            elif ftype == 2:
                row[x] = (row[x] + b) & 0xFF
            elif ftype == 3:
                row[x] = (row[x] + (a + b) // 2) & 0xFF
            elif ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[x] = (row[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
            elif ftype != 0:
                raise GeometryError(f"unknown PNG filter {ftype}")
        out += row
        prev = row
    return bytes(out)


def _decode_image(d: bytes, body: bytes) -> tuple[int, int, list[tuple[int, ...]]]:
    """Return (width, height, row-major RGB or grey samples) for a matplotlib image."""
    width = int(re.search(rb"/Width\s+(\d+)", d).group(1))
    height = int(re.search(rb"/Height\s+(\d+)", d).group(1))
    bpc = int(re.search(rb"/BitsPerComponent\s+(\d+)", d).group(1))
    palette = None
    im = re.search(rb"/ColorSpace\s*\[\s*/Indexed\s*/DeviceRGB\s+(\d+)\s*", d)
    if im:
        start = im.end()
        if d[start:start + 1] == b"(":
            level, j = 1, start + 1
            while level:
                ch = d[j:j + 1]
                if ch == b"\\":
                    j += 2
                    continue
                level += {b"(": 1, b")": -1}.get(ch, 0)
                j += 1
            table = _literal(d[start + 1:j - 1])
        else:
            hexm = re.match(rb"<([0-9A-Fa-f\s]*)>", d[start:])
            table = bytes.fromhex(hexm.group(1).decode())
        palette = [tuple(table[k:k + 3]) for k in range(0, len(table), 3)]
        colors = 1
    elif re.search(rb"/ColorSpace\s*/DeviceRGB", d):
        colors = 3
    elif re.search(rb"/ColorSpace\s*/DeviceGray", d):
        colors = 1
    else:
        raise GeometryError("unsupported image colour space")
    row_bytes = (width * colors * bpc + 7) // 8
    if re.search(rb"/Predictor\s+1\d", d):
        body = _unpredict(body, row_bytes, max(1, colors * bpc // 8))
    samples: list[tuple[int, ...]] = []
    for r in range(height):
        row = body[r * row_bytes:(r + 1) * row_bytes]
        bits = "".join(f"{byte:08b}" for byte in row)
        for x in range(width):
            vals = tuple(int(bits[(x * colors + k) * bpc:(x * colors + k + 1) * bpc], 2)
                         for k in range(colors))
            samples.append(palette[vals[0]] if palette is not None else vals)
    return width, height, samples


VALUE_TOLERANCE = 8  # per channel, 0-255: one resampling step of a smooth colour bar


def image_mismatch(a: tuple[int, int, list], b: tuple[int, int, list],
                   value_tol: int = VALUE_TOLERANCE) -> float:
    """Share of sample points, on a common grid of relative positions, whose colours differ.

    Each image is sampled at the centres of the smaller image's pixel grid, mapped to
    the nearest source pixel, and a sample differs when any channel differs by more
    than ``value_tol``. Resampling the same data to a size one pixel different only
    shifts samples next to cell boundaries, and moves a smooth gradient (the colour
    bar) by about one grey step; a change of the data changes whole cells by far more.
    """
    (wa, ha, pa), (wb, hb, pb) = a, b
    w, h = min(wa, wb), min(ha, hb)
    differ = 0
    for j in range(h):
        v = (j + 0.5) / h
        ra, rb = min(int(v * ha), ha - 1), min(int(v * hb), hb - 1)
        for i in range(w):
            u = (i + 0.5) / w
            ca = pa[ra * wa + min(int(u * wa), wa - 1)]
            cb = pb[rb * wb + min(int(u * wb), wb - 1)]
            if max(abs(x - y) for x, y in zip(ca, cb)) > value_tol:
                differ += 1
    return differ / (w * h)


# ---------------------------------------------------------------- geometry ---
Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mul(m: Matrix, n: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D,
            e * A + f * C + E, e * B + f * D + F)


def _apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


@dataclass
class Element:
    kind: str                      # "path", "form" or "image"
    style: tuple                   # paint operator and colours, or a content digest
    points: list[tuple[float, float]] = field(default_factory=list)
    pixels: tuple[int, int, list] | None = None


@dataclass
class PageGeometry:
    elements: list[Element]
    frame: tuple[float, float, float, float]   # x0, y0, width, height
    frame_source: str

    def normalised(self) -> list[tuple[str, tuple, list[tuple[float, float]]]]:
        x0, y0, w, h = self.frame
        return [(e.kind, e.style, [((x - x0) / w, (y - y0) / h) for x, y in e.points])
                for e in self.elements]
    dropped_background: int = 0


_PAINT = {"S": (False, True), "s": (False, True), "f": (True, False), "F": (True, False),
          "f*": (True, False), "B": (True, True), "B*": (True, True), "b": (True, True),
          "b*": (True, True)}


def extract(pdf: Path) -> PageGeometry:
    data = Path(pdf).read_bytes()
    objs = _objects(data)
    pages = [num for num, (d, _) in objs.items() if re.search(rb"/Type\s*/Page\b", d)]
    if len(pages) != 1:
        raise GeometryError(f"expected one page, found {len(pages)}")
    page_dict = objs[pages[0]][0]
    cm_ = re.search(rb"/Contents\s+(\d+)\s+0\s+R", page_dict)
    if not cm_:
        raise GeometryError("page has no single content stream")
    content = objs[int(cm_.group(1))][1] or b""
    xobjects: dict[str, int] = {}
    res = objs[int(re.search(rb"/Resources\s+(\d+)\s+0\s+R", page_dict).group(1))][0] \
        if re.search(rb"/Resources\s+(\d+)\s+0\s+R", page_dict) else page_dict
    xm = re.search(rb"/XObject\s+(\d+)\s+0\s+R", res)
    if xm:
        for name, ref in re.findall(rb"/([^\s/<>\[\]()]+)\s+(\d+)\s+0\s+R", objs[int(xm.group(1))][0]):
            xobjects[name.decode("latin-1")] = int(ref)

    elements: list[Element] = []
    clips: list[tuple[float, float, float, float]] = []
    ctm, stack = IDENTITY, []
    fill, stroke = ("g", 0.0), ("G", 0.0)
    path: list[tuple[float, float]] = []
    pending_rect: list[tuple[float, float, float, float]] = []
    operands: list = []
    in_text = False
    for kind, value in _tokens(content):
        if kind != "op":
            operands.append(value)
            continue
        op = value
        if op == "BT":
            in_text = True
        elif op == "ET":
            in_text = False
        elif in_text:
            pass  # text is compared separately; only cm inside q/Q matters below
        elif op == "q":
            stack.append((ctm, fill, stroke))
        elif op == "Q":
            ctm, fill, stroke = stack.pop()
        elif op == "cm":
            ctm = _mul(tuple(float(v) for v in operands[-6:]), ctm)  # type: ignore[arg-type]
        elif op in ("g", "rg", "k", "sc", "scn"):
            fill = (op, *[round(float(v), 4) for v in operands if isinstance(v, float)])
        elif op in ("G", "RG", "K", "SC", "SCN"):
            stroke = (op, *[round(float(v), 4) for v in operands if isinstance(v, float)])
        elif op == "m" or op == "l":
            path.append(_apply(ctm, operands[-2], operands[-1]))
        elif op == "c":
            v = operands[-6:]
            path.extend(_apply(ctm, v[k], v[k + 1]) for k in (0, 2, 4))
        elif op in ("v", "y"):
            v = operands[-4:]
            path.extend(_apply(ctm, v[k], v[k + 1]) for k in (0, 2))
        elif op == "re":
            x, y, w, h = (float(t) for t in operands[-4:])
            corners = [_apply(ctm, x, y), _apply(ctm, x + w, y),
                       _apply(ctm, x + w, y + h), _apply(ctm, x, y + h)]
            path.extend(corners)
            xs, ys = [p[0] for p in corners], [p[1] for p in corners]
            pending_rect.append((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
        elif op == "h":
            pass
        elif op in ("W", "W*"):
            if len(pending_rect) == 1:
                clips.append(pending_rect[0])
        elif op in _PAINT:
            filled, stroked = _PAINT[op]
            style = (op, fill if filled else None, stroke if stroked else None)
            elements.append(Element("path", style, path))
            path, pending_rect = [], []
        elif op == "n":
            path, pending_rect = [], []
        elif op == "Do":
            name = operands[-1]
            ref = xobjects.get(name)
            if ref is None:
                raise GeometryError(f"unknown XObject {name}")
            d, body = objs[ref]
            digest = hashlib.sha256(body or b"").hexdigest()[:16]
            if b"/Subtype /Form" in d or b"/Subtype/Form" in d:
                elements.append(Element("form", ("form", digest, fill, stroke), [_apply(ctm, 0.0, 0.0)]))
            elif b"/Subtype /Image" in d or b"/Subtype/Image" in d:
                corners = [_apply(ctm, 0.0, 0.0), _apply(ctm, 1.0, 0.0),
                           _apply(ctm, 1.0, 1.0), _apply(ctm, 0.0, 1.0)]
                elements.append(Element("image", ("image",), corners,
                                        pixels=_decode_image(d, body or b"")))
            else:
                raise GeometryError(f"unsupported XObject subtype for {name}")
        elif op in ("w", "J", "j", "M", "d", "gs", "ri", "i", "cs", "CS", "sh"):
            pass  # line style, graphics state and colour-space selection do not move geometry
        else:
            raise GeometryError(f"unsupported content operator {op!r}")
        operands = []

    # The figure's background rectangle covers the whole page; its size follows the
    # tight bounding box (label widths), not the data, so it is not compared.
    mb = re.search(rb"/MediaBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\]", data)
    dropped = 0
    if mb:
        px0, py0, px1, py1 = (float(v) for v in mb.groups())
        kept = []
        for e in elements:
            if e.kind == "path" and e.points and len(e.points) == 4:
                xs, ys = [p[0] for p in e.points], [p[1] for p in e.points]
                if (abs(min(xs) - px0) < 0.5 and abs(min(ys) - py0) < 0.5
                        and abs(max(xs) - px1) < 0.5 and abs(max(ys) - py1) < 0.5):
                    dropped += 1
                    continue
            kept.append(e)
        elements = kept
    if clips:
        frame = max(clips, key=lambda r: r[2] * r[3])
        source = "largest clipping rectangle (axes area)"
    else:
        pts = [p for e in elements for p in e.points]
        if not pts:
            raise GeometryError("no geometry recorded")
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        frame = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        source = "bounding box of all drawn geometry"
    if frame[2] <= 0 or frame[3] <= 0:
        raise GeometryError("degenerate reference frame")
    return PageGeometry(elements, frame, source, dropped)


# Tolerances, measured on 2026-11-04 between the committed figures (matplotlib 3.11.0
# for figures 1-2, 3.11.1 for figure 3) and a rebuild with the pinned 3.11.1:
#   vector marks (paths, markers): worst 0.000414 of the frame (tick marks outside the axes)
#   image placement:               worst 0.0046 of the frame (whole-pixel snapping; 1 px = 0.0046)
#   image content:                 worst 0.66 % of samples (cell-boundary rows after resampling)
# A one-unit move of a point in figure 1 is 0.0093 of the frame; one label of 80 is 0.0116.
POSITION_TOLERANCE = 0.001
IMAGE_OFFSET_TOLERANCE = 0.01
IMAGE_SAMPLE_TOLERANCE = 0.02


@dataclass
class Comparison:
    equal_structure: bool          # same element kinds, styles and point counts, in order
    max_deviation: float           # vector marks: largest coordinate difference, frame units
    max_image_offset: float        # image placements: largest corner difference, frame units
    max_image_mismatch: float      # largest share of differing image samples
    detail: str

    def within(self, position_tol: float = POSITION_TOLERANCE,
               image_offset_tol: float = IMAGE_OFFSET_TOLERANCE,
               image_tol: float = IMAGE_SAMPLE_TOLERANCE) -> bool:
        return (self.equal_structure and self.max_deviation <= position_tol
                and self.max_image_offset <= image_offset_tol
                and self.max_image_mismatch <= image_tol)


def compare(a: PageGeometry, b: PageGeometry) -> Comparison:
    """Pair elements in drawing order; styles must match exactly, positions within the frame."""
    na, nb = a.normalised(), b.normalised()
    if len(na) != len(nb):
        return Comparison(False, float("inf"), float("inf"), 1.0,
                          f"{len(na)} vs {len(nb)} drawn elements")
    worst, worst_offset, worst_img = 0.0, 0.0, 0.0
    for idx, ((ka, sa, pa), (kb, sb, pb)) in enumerate(zip(na, nb)):
        if ka != kb or sa != sb:
            return Comparison(False, float("inf"), float("inf"), 1.0,
                              f"element {idx}: {ka} {sa} vs {kb} {sb}")
        if len(pa) != len(pb):
            return Comparison(False, float("inf"), float("inf"), 1.0,
                              f"element {idx}: {len(pa)} vs {len(pb)} points")
        dev = max((max(abs(xa - xb), abs(ya - yb)) for (xa, ya), (xb, yb) in zip(pa, pb)),
                  default=0.0)
        ea, eb = a.elements[idx], b.elements[idx]
        if ka == "image":
            worst_offset = max(worst_offset, dev)
            if ea.pixels is not None and eb.pixels is not None:
                worst_img = max(worst_img, image_mismatch(ea.pixels, eb.pixels))
        else:
            worst = max(worst, dev)
    return Comparison(True, worst, worst_offset, worst_img,
                      f"{len(na)} elements; vector marks {worst:.6f} of the frame; image "
                      f"placement {worst_offset:.6f}; image samples differing {worst_img:.4%}")
