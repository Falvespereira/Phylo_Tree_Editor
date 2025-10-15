import tkinter as tk
from tkinter import ttk, simpledialog, filedialog, messagebox
import tkinter.font as tkfont
import json
import math
import os
import re

# ---------- Appearance / constants ----------
NODE_WIDTH = 140
NODE_HEIGHT = 50
NODE_RADIUS = 10
NODE_FILL = "#2b6cb0"
NODE_OUTLINE = "#1a4369"
NODE_TEXT = "#ffffff"

LINE_COLOR = "#444444"
LINE_WIDTH = 2

GRID_SIZE = 20
GRID_COLOR = "#e2e8f0"  # light gray grid lines

# Text layout inside nodes
TEXT_MAX_WIDTH = 1000       # large so nodes can fit more text
TEXT_PADDING_X = 20         # left/right padding inside the box
TEXT_PADDING_Y = 12         # top/bottom padding inside the box


class MindMapApp:
    def __init__(self, root):
        self.root = root
        root.title("Mind Map (Tkinter)")
        root.geometry("1200x760")

        self.mode = tk.StringVar(value="select")          # 'select', 'add', 'connect'
        self.label_mode = tk.StringVar(value="subtree")   # 'subtree' or 'component'
        self.label_source = tk.StringVar(value="auto")    # 'auto' or 'manual'
        self.snap_var = tk.BooleanVar(value=False)
        self.scale = 1.0

        # Newick export mode: forest (list) or combined (single super-root)
        self.newick_export = tk.StringVar(value="forest")  # 'forest' or 'combined'
        # Newick view mode (applied after detail transform)
        self.newick_view = tk.StringVar(value="pretty")    # 'compact' or 'pretty'

        # Display detail (what each node shows)
        self.display_detail = tk.StringVar(value="Subtree (pretty)")
        # Global node scale multiplier (applied after text fit)
        self.node_scale = tk.DoubleVar(value=1.2)          # try 1.2–1.6

        # Font for labels (used to measure text)
        self.text_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")

        # Label counters & storage
        self.label_counter = 0                # next label index (A,B,...)
        self.manual_labels = {}               # canvas node id -> manual label (raw)

        # Rebuild throttling & caches
        self._rebuild_scheduled = False
        self._text_cache = {}                 # node_id -> last displayed text
        self._layout_moved = False

        # Bulk import flag (skip per-node rebuild work)
        self._bulk = False

        # ---------- Menubar ----------
        menubar = tk.Menu(root)

        # File menu
        filemenu = tk.Menu(menubar, tearoff=False)
        filemenu.add_command(label="New", command=self.new_document, accelerator="Ctrl+N")
        filemenu.add_command(label="Import…", command=self.import_any, accelerator="Ctrl+O")
        filemenu.add_command(label="Save As… (JSON)", command=self.export_json, accelerator="Ctrl+S")
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=root.quit)
        menubar.add_cascade(label="File", menu=filemenu)

        # Help menu (Tips + About)
        helpmenu = tk.Menu(menubar, tearoff=False)
        helpmenu.add_command(label="Tips", command=self.show_tips)
        helpmenu.add_separator()
        helpmenu.add_command(
            label="About",
            command=lambda: messagebox.showinfo(
                "About",
                "Mind Map (Tkinter)\n\nJSON & Newick import • Forest/Combined Newick export\n"
                "Autosize • Pan/Zoom • Multiselect • Snap grid • Label source/scope\n"
                "Pretty/Compact/Depth display • Collision-free Newick import"
            )
        )
        menubar.add_cascade(label="Help", menu=helpmenu)

        root.config(menu=menubar)
        root.bind("<Control-n>", lambda e: self.new_document())
        root.bind("<Control-o>", lambda e: self.import_any())
        root.bind("<Control-s>", lambda e: self.export_json())

        # ---------- Toolbar ----------
        bar = ttk.Frame(root, padding=6)
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(bar, text="Mode:").pack(side=tk.LEFT, padx=(0, 4))
        for label, val in [("Select/Drag", "select"), ("Add node", "add"), ("Connect", "connect")]:
            ttk.Radiobutton(bar, text=label, value=val, variable=self.mode).pack(side=tk.LEFT)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Checkbutton(bar, text="Snap to grid", variable=self.snap_var, command=self.on_toggle_snap).pack(
            side=tk.LEFT, padx=4
        )

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Label(bar, text="Label shows:").pack(side=tk.LEFT, padx=(0, 4))
        mode_cb = ttk.Combobox(
            bar, state="readonly", width=14,
            values=["subtree", "component"], textvariable=self.label_mode
        )
        mode_cb.pack(side=tk.LEFT)
        mode_cb.bind("<<ComboboxSelected>>", lambda e: self.request_rebuild())

        # --- Display detail selector ---
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Label(bar, text="Display:").pack(side=tk.LEFT, padx=(0, 4))
        detail_cb = ttk.Combobox(
            bar, state="readonly", width=16,
            values=["Label only", "Subtree (compact)", "Subtree (pretty)", "Depth 1", "Depth 2"],
            textvariable=self.display_detail
        )
        detail_cb.pack(side=tk.LEFT)
        detail_cb.bind("<<ComboboxSelected>>", lambda e: self.request_rebuild())

        # --- Newick export mode ---
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Label(bar, text="Newick export:").pack(side=tk.LEFT, padx=(0, 4))
        newick_cb = ttk.Combobox(
            bar, state="readonly", width=10,
            values=["forest", "combined"], textvariable=self.newick_export
        )
        newick_cb.pack(side=tk.LEFT)

        # --- Global node scale ---
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Label(bar, text="Node scale:").pack(side=tk.LEFT, padx=(0, 4))
        scale_entry = ttk.Spinbox(
            bar, from_=0.5, to=3.0, increment=0.1, width=5,
            textvariable=self.node_scale,
            command=self.on_node_scale_change  # apply when arrows/click used
        )
        scale_entry.pack(side=tk.LEFT)
        # also apply when typing
        self._ns_trace_id = self.node_scale.trace_add("write", self.on_node_scale_change)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(bar, text="Export JSON", command=self.export_json).pack(side=tk.LEFT, padx=2)

        self.zoom_label = ttk.Label(bar, text="Zoom: 100%")
        self.zoom_label.pack(side=tk.RIGHT)

        # ---------- Canvas ----------
        self.canvas = tk.Canvas(root, bg="#f7fafc", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw_grid())

        # Data
        self.nodes = {}  # node_id -> {"rect": id, "text": id, "lines": set()}
        self.lines = {}  # line_id -> {"a": node_id, "b": node_id}

        # Selection / interaction state
        self.selected_nodes = set()
        self.selected_line = None
        self.dragging = False
        self.drag_offset = (0, 0)   # for single-node drag
        self.last_drag_pos = None   # for multi-drag
        self.connect_start = None
        self.preview_line = None

        # Rubber-band (Ctrl+drag)
        self.box_select_start = None  # (cx, cy)
        self.box_rect_id = None

        # Bindings
        self.canvas.bind("<Button-1>", self.on_left_down)
        self.canvas.bind("<B1-Motion>", self.on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_up)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.canvas.bind("<Motion>", self.on_motion)

        # Middle button pan
        self.canvas.bind("<Button-2>", self.on_mid_down)
        self.canvas.bind("<B2-Motion>", self.on_mid_drag)
        self.canvas.bind("<ButtonRelease-2>", lambda e: self.draw_grid())

        # Zoom (Ctrl + Mouse Wheel)
        root.bind("<Control-MouseWheel>", self.on_zoom)

        # Keyboard
        root.bind("<BackSpace>", self.on_delete)
        root.bind("<Delete>", self.on_delete)
        root.bind("<Escape>", self.on_escape)
        root.bind("<Control-a>", self.select_all)

        # Setup helpers
        add_round_rect_to_canvas(self.canvas)
        self.update_scrollregion()
        self.draw_grid()

    # ---------- Help ----------
    def show_tips(self):
        tips = (
            "General:\n"
            " • Mode: Select/Drag, Add node, Connect\n"
            " • Double-click a node to edit its label\n"
            " • Right-click deletes the item under the cursor\n"
            " • Delete / Backspace removes selected items\n\n"
            "Selection:\n"
            " • Ctrl+Click toggles node selection\n"
            " • Ctrl+Drag draws a box to multi-select\n"
            " • Ctrl+A selects all nodes\n\n"
            "Connect / Arrows:\n"
            " • In Connect mode, click parent then child to create an arrow\n"
            " • Lines anchor to the edge of each box\n\n"
            "Grid / Snap:\n"
            " • Enable 'Snap to grid' to show the grid and snap on drag end\n"
            " • Grid appears only when snapping is on\n\n"
            "Pan / Zoom:\n"
            " • Middle-mouse drag to pan\n"
            " • Ctrl+MouseWheel to zoom (focus around cursor)\n\n"
            "Display:\n"
            " • Display detail lets you condense nodes: Label only / Depth / Subtree\n"
            " • Node scale globally enlarges boxes after text-fit\n"
        )
        messagebox.showinfo("Tips", tips)

    # ---------- Rebuild throttling ----------
    def request_rebuild(self):
        if self._rebuild_scheduled:
            return
        self._rebuild_scheduled = True
        self.root.after_idle(self._do_rebuild)

    def _do_rebuild(self):
        self._rebuild_scheduled = False
        self.rebuild_all_node_newick()

    # ---------- Node scale handler ----------
    def on_node_scale_change(self, *_):
        """Apply the current node_scale to all nodes and refresh anchors."""
        try:
            s = float(self.node_scale.get())
        except Exception:
            return
        # clamp
        s = max(0.5, min(3.0, s))
        # normalize the value (avoid recursive storms)
        if abs(s - float(self.node_scale.get())) > 1e-6:
            try:
                self.node_scale.trace_remove("write", self._ns_trace_id)
            except Exception:
                pass
            self.node_scale.set(s)
            self._ns_trace_id = self.node_scale.trace_add("write", self.on_node_scale_change)

        # resize all nodes and update lines once
        for nid in list(self.nodes.keys()):
            self.resize_node_to_text(nid)
        self.update_connected_lines(self.nodes.keys())
        self.update_scrollregion()

    # ---------- Grid helpers ----------
    def on_toggle_snap(self):
        if self.snap_var.get():
            self.draw_grid()
        else:
            self.canvas.delete("grid")

    def get_viewport(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        x0 = self.canvas.canvasx(0)
        y0 = self.canvas.canvasy(0)
        x1 = self.canvas.canvasx(w)
        y1 = self.canvas.canvasy(h)
        return x0, y0, x1, y1

    def draw_grid(self):
        self.canvas.delete("grid")
        if not self.snap_var.get():
            return
        x0, y0, x1, y1 = self.get_viewport()
        margin = GRID_SIZE * 4
        x0 -= margin; y0 -= margin; x1 += margin; y1 += margin
        start_x = math.floor(x0 / GRID_SIZE) * GRID_SIZE
        end_x   = math.ceil(x1 / GRID_SIZE) * GRID_SIZE
        start_y = math.floor(y0 / GRID_SIZE) * GRID_SIZE
        end_y   = math.ceil(y1 / GRID_SIZE) * GRID_SIZE
        for x in range(int(start_x), int(end_x + 1), GRID_SIZE):
            self.canvas.create_line(x, y0, x, y1, fill=GRID_COLOR, width=1, tags=("grid",))
        for y in range(int(start_y), int(end_y + 1), GRID_SIZE):
            self.canvas.create_line(x0, y, x1, y, fill=GRID_COLOR, width=1, tags=("grid",))
        self.canvas.tag_lower("grid")

    # ---------- Coordinate helpers ----------
    def to_canvas(self, event):
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def update_scrollregion(self):
        bbox = self.canvas.bbox("all")
        if bbox is None:
            bbox = (0, 0, 2000, 2000)
        self.canvas.config(scrollregion=bbox)

    def label_zoom(self):
        self.zoom_label.config(text=f"Zoom: {int(self.scale * 100)}%")

    def snap(self, x, y):
        if not self.snap_var.get():
            return x, y
        gx = round(x / GRID_SIZE) * GRID_SIZE
        gy = round(y / GRID_SIZE) * GRID_SIZE
        return gx, gy

    # ---------- Node geometry ----------
    def node_center(self, node_id):
        bbox = self.canvas.bbox(f"node_shape_{node_id}") or self.canvas.bbox(node_id)
        if not bbox:
            return (0, 0)
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    def node_dims(self, node_id):
        bbox = self.canvas.bbox(f"node_shape_{node_id}") or self.canvas.bbox(node_id)
        x1, y1, x2, y2 = bbox
        return ((x2 - x1) / 2.0, (y2 - y1) / 2.0)

    def node_anchor(self, node_id, toward_x, toward_y):
        cx, cy = self.node_center(node_id)
        dx = toward_x - cx
        dy = toward_y - cy
        if dx == 0 and dy == 0:
            return (cx, cy)
        hw, hh = self.node_dims(node_id)
        hw = max(1.0, hw - NODE_RADIUS)
        hh = max(1.0, hh - NODE_RADIUS)
        adx = abs(dx)
        ady = abs(dy)
        if adx == 0:
            factor = ady / hh
        elif ady == 0:
            factor = adx / hw
        else:
            factor = max(adx / hw, ady / hh)
        ax = cx + dx / factor
        ay = cy + dy / factor
        return ax, ay

    # ---------- Display transforms ----------
    def _newick_label(self, raw):
        s = (raw or "").replace("'", "''")
        return f"'{s}'"

    def _display_to_raw_label(self, display):
        s = (display or "").strip()
        if s.endswith(";"):
            s = s[:-1].strip()
        if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
            s = s[1:-1].replace("''", "'")
        return s

    def _strip_trailing_semicolon(self, s: str) -> str:
        s = s.rstrip()
        return s[:-1] if s.endswith(";") else s

    def _pretty_newick(self, s: str, indent: str = "  ") -> str:
        s = self._strip_trailing_semicolon(s)
        out = []
        level = 0
        i = 0
        while i < len(s):
            ch = s[i]
            if ch == "'":
                out.append(ch)
                i += 1
                while i < len(s):
                    out.append(s[i])
                    if s[i] == "'":
                        if i + 1 < len(s) and s[i + 1] == "'":
                            out.append(s[i + 1]); i += 2; continue
                        else:
                            i += 1; break
                    i += 1
                continue
            if ch == "(":
                out.append("(\n"); level += 1; out.append(indent * level)
            elif ch == ",":
                out.append(",\n"); out.append(indent * level)
            elif ch == ")":
                level = max(0, level - 1); out.append("\n" + indent * level + ")")
            else:
                out.append(ch)
            i += 1
        return "".join(out) + ";\n"

    def _limit_newick_depth(self, s: str, max_depth: int) -> str:
        s = s.strip()
        if not s.endswith(";"): s += ";"
        out = []
        i = 0
        depth = 0
        while i < len(s):
            ch = s[i]
            if ch == "'":
                out.append(ch); i += 1
                while i < len(s):
                    out.append(s[i])
                    if s[i] == "'":
                        if i + 1 < len(s) and s[i + 1] == "'":
                            out.append(s[i + 1]); i += 2; continue
                        else:
                            i += 1; break
                    i += 1
                continue
            if ch == "(":
                depth += 1
                if depth == max_depth + 1:
                    out.append("(…")
                    inner = 1; i += 1
                    while i < len(s) and inner > 0:
                        if s[i] == "'":
                            i += 1
                            while i < len(s):
                                if s[i] == "'":
                                    if i + 1 < len(s) and s[i + 1] == "'":
                                        i += 2; continue
                                    else:
                                        i += 1; break
                                i += 1
                            continue
                        elif s[i] == "(":
                            inner += 1
                        elif s[i] == ")":
                            inner -= 1
                        i += 1
                    depth -= 1
                    out.append(")")
                    continue
                else:
                    out.append("(")
            elif ch == ")":
                out.append(")"); depth = max(0, depth - 1)
            else:
                out.append(ch)
            i += 1
        return "".join(out)

    def _display_from_newick(self, newick_str: str, label_for_node: str | None) -> str:
        """Apply display detail + view to produce the *display* string."""
        detail = self.display_detail.get()
        s = newick_str
        if detail == "Label only":
            s = f"{self._newick_label(label_for_node or '')};"
        elif detail == "Depth 1":
            s = self._limit_newick_depth(newick_str, 1) + ";"
        elif detail == "Depth 2":
            s = self._limit_newick_depth(newick_str, 2) + ";"
        elif detail == "Subtree (compact)":
            s = newick_str
        else:  # "Subtree (pretty)" will be handled by view step
            s = newick_str

        if self.newick_view.get() == "pretty" and detail != "Subtree (compact)":
            return self._pretty_newick(s)
        return s

    # ---------- Text measuring + node sizing ----------
    def _measure_display_str_wh(self, display_text: str,
                                max_text_w=TEXT_MAX_WIDTH,
                                pad_x=TEXT_PADDING_X,
                                pad_y=TEXT_PADDING_Y,
                                min_w=NODE_WIDTH,
                                min_h=NODE_HEIGHT):
        """Measure how the *display* string will render in a node, with wrap + padding + node scale."""
        tokens = re.findall(r"[^\s,()]+|[(),]", display_text)
        lines = []
        cur = ""
        for tok in tokens:
            sep = "" if (not cur or tok in "(),") else " "
            probe = cur + sep + tok
            if self.text_font.measure(probe) <= max_text_w or not cur:
                cur = probe
            else:
                lines.append(cur)
                cur = tok
        if cur:
            lines.append(cur)

        line_h = self.text_font.metrics("linespace")
        text_w = min(max_text_w, max(self.text_font.measure(L) for L in (lines or [""])))
        text_h = max(line_h, line_h * max(1, len(lines)))

        target_w = max(min_w, pad_x * 2 + text_w)
        target_h = max(min_h, pad_y * 2 + text_h)

        # Apply global node scale
        scale = float(self.node_scale.get())
        target_w *= scale
        target_h *= scale
        return target_w, target_h

    def resize_node_to_text(self, nid,
                            max_text_w=TEXT_MAX_WIDTH,
                            pad_x=TEXT_PADDING_X,
                            pad_y=TEXT_PADDING_Y,
                            min_w=NODE_WIDTH,
                            min_h=NODE_HEIGHT):
        """
        Keep text inside the box:
        - Wrap text to a max width inside the node.
        - Resize the rounded rect to tightly contain the wrapped text + padding.
        - Apply global node scale.
        """
        node = self.nodes.get(nid)
        if not node:
            return
        text_id = node["text"]

        bbox = self.canvas.bbox(f"node_shape_{nid}")
        if not bbox:
            return
        x1, y1, x2, y2 = bbox
        cur_w = max(1.0, (x2 - x1))

        # Start with current inner width, then we will scale to target
        wrap_w = max(1, int(min(max_text_w, cur_w - 2 * pad_x)))
        self.canvas.itemconfigure(text_id, width=wrap_w, justify="center", anchor="center")

        tb = self.canvas.bbox(text_id)
        if not tb:
            return
        tx1, ty1, tx2, ty2 = tb
        text_w = tx2 - tx1
        text_h = ty2 - ty1

        target_w = max(min_w, text_w + 2 * pad_x)
        target_h = max(min_h, text_h + 2 * pad_y)

        # Apply global node scale
        scale_mul = float(self.node_scale.get())
        target_w *= scale_mul
        target_h *= scale_mul

        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        sx = target_w / cur_w
        sy = target_h / (y2 - y1 if (y2 - y1) != 0 else 1.0)

        if abs(sx - 1.0) > 0.01 or abs(sy - 1.0) > 0.01:
            self.canvas.scale(f"node_shape_{nid}", cx, cy, sx, sy)

        # After scaling, fix final wrap width to final inner width
        nb = self.canvas.bbox(f"node_shape_{nid}")
        if not nb:
            return
        nx1, ny1, nx2, ny2 = nb
        final_inner_w = max(1, int(nx2 - nx1 - 2 * pad_x))
        final_wrap_w = max(1, int(min(max_text_w, final_inner_w)))
        self.canvas.itemconfigure(text_id, width=final_wrap_w)

        # Re-anchor connected lines (edge-to-box)
        self._update_lines_for_nodes({nid})

    # ---------- Nodes / Edges ----------
    def _index_to_alpha(self, idx: int) -> str:
        s = ""
        n = idx
        while True:
            s = chr(ord('A') + (n % 26)) + s
            n = n // 26 - 1
            if n < 0:
                break
        return s

    def _next_alpha_label(self):
        s = self._index_to_alpha(self.label_counter)
        self.label_counter += 1
        return s

    def _auto_label_order(self):
        items = []
        for nid in self.nodes.keys():
            x1, y1, x2, y2 = self.canvas.bbox(f"node_shape_{nid}")
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            items.append((cy, cx, nid))
        items.sort()
        return [nid for _, _, nid in items]

    def add_node(self, x, y, text=None, bulk=False):
        x, y = self.snap(x, y)
        rect = self.rounded_rect(
            x, y, NODE_WIDTH, NODE_HEIGHT, NODE_RADIUS, fill=NODE_FILL, outline=NODE_OUTLINE, width=2
        )
        if text is None:
            text = self._next_alpha_label()

        raw_newick = f"{self._newick_label(text)};"
        display = self._display_from_newick(raw_newick, text)
        label = self.canvas.create_text(x, y, text=display, fill=NODE_TEXT, font=self.text_font)
        node_id = rect

        tag_all = f"node_{node_id}"
        tag_shape = f"node_shape_{node_id}"
        self.canvas.addtag_withtag(tag_all, rect)
        self.canvas.addtag_withtag(tag_shape, rect)
        for part in self.canvas.find_withtag(f"roundrect_{rect}"):
            self.canvas.addtag_withtag(tag_all, part)
            self.canvas.addtag_withtag(tag_shape, part)
        self.canvas.addtag_withtag(tag_all, label)

        self.nodes[node_id] = {"rect": rect, "text": label, "lines": set()}
        self._text_cache[node_id] = display

        if self.label_source.get() == "manual":
            self.manual_labels[node_id] = text

        if not bulk:
            self.update_scrollregion()
            self.resize_node_to_text(node_id)
            self.request_rebuild()

        return node_id

    def connect_nodes(self, a_id, b_id):
        if a_id == b_id:
            return None
        bcx, bcy = self.node_center(b_id)
        ax1, ay1 = self.node_anchor(a_id, bcx, bcy)
        acx, acy = self.node_center(a_id)
        bx1, by1 = self.node_anchor(b_id, acx, acy)
        line = self.canvas.create_line(
            ax1, ay1, bx1, by1, width=LINE_WIDTH, fill=LINE_COLOR, capstyle=tk.ROUND, arrow=tk.LAST
        )
        self.lines[line] = {"a": a_id, "b": b_id}
        self.nodes[a_id]["lines"].add(line)
        self.nodes[b_id]["lines"].add(line)
        if not self._bulk:
            self.request_rebuild()
        return line

    def _update_lines_for_nodes(self, node_ids):
        affected = set()
        for nid in node_ids:
            affected |= set(self.nodes[nid]["lines"])
        for lid in affected:
            info = self.lines.get(lid)
            if not info:
                continue
            a_id, b_id = info["a"], info["b"]
            bcx, bcy = self.node_center(b_id)
            ax1, ay1 = self.node_anchor(a_id, bcx, bcy)
            acx, acy = self.node_center(a_id)
            bx1, by1 = self.node_anchor(b_id, acx, acy)
            self.canvas.coords(lid, ax1, ay1, bx1, by1)

    def update_connected_lines(self, moved_node_ids):
        self._update_lines_for_nodes(set(moved_node_ids))

    def delete_node(self, node_id):
        for lid in list(self.nodes[node_id]["lines"]):
            self.delete_line(lid, suppress_rebuild=True)
        self.canvas.delete(f"node_{node_id}")
        del self.nodes[node_id]
        self._text_cache.pop(node_id, None)
        self.manual_labels.pop(node_id, None)
        self.request_rebuild()

    def delete_line(self, line_id, suppress_rebuild=False):
        if line_id not in self.lines:
            return
        a = self.lines[line_id]["a"]
        b = self.lines[line_id]["b"]
        if a in self.nodes:
            self.nodes[a]["lines"].discard(line_id)
        if b in self.nodes:
            self.nodes[b]["lines"].discard(line_id)
        self.canvas.delete(line_id)
        del self.lines[line_id]
        if not suppress_rebuild:
            self.request_rebuild()

    # ---------- Selection helpers ----------
    def clear_styles(self):
        for nid in self.nodes:
            self.canvas.itemconfigure(f"node_shape_{nid}", width=2, outline=NODE_OUTLINE)
        for lid in self.lines:
            self.canvas.itemconfigure(lid, width=LINE_WIDTH, fill=LINE_COLOR)

    def refresh_selection_style(self):
        self.clear_styles()
        for nid in self.selected_nodes:
            self.canvas.itemconfigure(f"node_shape_{nid}", width=3, outline="#ff9800")
        if self.selected_line:
            self.canvas.itemconfigure(self.selected_line, width=3, fill="#ff9800")

    def select_clear(self):
        self.selected_nodes.clear()
        self.selected_line = None
        self.refresh_selection_style()

    def select_only_node(self, nid):
        self.selected_nodes = {nid}
        self.selected_line = None
        self.refresh_selection_style()

    def select_toggle_node(self, nid):
        if nid in self.selected_nodes:
            self.selected_nodes.remove(nid)
        else:
            self.selected_nodes.add(nid)
        self.selected_line = None
        self.refresh_selection_style()

    def select_line_only(self, lid):
        self.selected_nodes.clear()
        self.selected_line = lid
        self.refresh_selection_style()

    def select_all(self, event=None):
        self.selected_nodes = set(self.nodes.keys())
        self.selected_line = None
        self.refresh_selection_style()

    # ---------- Mouse / keyboard events ----------
    def under_cursor(self, event):
        cx, cy = self.to_canvas(event)
        items = self.canvas.find_overlapping(cx - 1, cy - 1, cx + 1, cy + 1)
        for item in reversed(items):
            tags = self.canvas.gettags(item)
            for t in tags:
                if t.startswith("node_shape_") or (t.startswith("node_") and not t.startswith("node_shape_")):
                    try:
                        nid = int(t.split("_")[-1])
                        if nid in self.nodes:
                            return ("node", nid)
                    except ValueError:
                        pass
        for item in reversed(items):
            if item in self.lines:
                return ("line", item)
        return None

    def on_left_down(self, event):
        cx, cy = self.to_canvas(event)
        target = self.under_cursor(event)
        ctrl = (event.state & 0x0004) != 0

        if self.mode.get() == "add":
            self.select_clear()
            nid = self.add_node(cx, cy)
            self.select_only_node(nid)
            return

        if self.mode.get() == "connect":
            if target and target[0] == "node":
                nid = target[1]
                if self.connect_start is None:
                    self.connect_start = nid
                    self.select_only_node(nid)
                    ax, ay = self.node_anchor(nid, cx, cy)
                    self.preview_line = self.canvas.create_line(
                        ax, ay, cx, cy, dash=(4, 2), fill="#999999", arrow=tk.LAST
                    )
                else:
                    self.connect_nodes(self.connect_start, nid)
                    if self.preview_line:
                        self.canvas.delete(self.preview_line)
                        self.preview_line = None
                    self.connect_start = None
                    self.select_only_node(nid)
            else:
                if self.preview_line:
                    self.canvas.delete(self.preview_line)
                    self.preview_line = None
                self.connect_start = None
                self.select_clear()
            return

        if target is None:
            if ctrl:
                self.box_select_start = (cx, cy)
                self.box_rect_id = self.canvas.create_rectangle(
                    cx, cy, cx, cy, dash=(4, 2), outline="#999999"
                )
            else:
                self.select_clear()
            return

        kind, ident = target
        if kind == "node":
            if ctrl:
                self.select_toggle_node(ident)
                self.dragging = True
                self.last_drag_pos = (cx, cy)
            else:
                if ident not in self.selected_nodes:
                    self.select_only_node(ident)
                self.dragging = True
                nx, ny = self.node_center(ident)
                self.drag_offset = (cx - nx, cy - ny)
                self.last_drag_pos = (cx, cy)
        else:
            self.select_line_only(ident)

    def on_left_drag(self, event):
        cx, cy = self.to_canvas(event)

        if self.box_select_start is not None:
            x0, y0 = self.box_select_start
            self.canvas.coords(self.box_rect_id, x0, y0, cx, cy)
            return

        if not self.dragging or not self.selected_nodes:
            return

        self._layout_moved = True

        if len(self.selected_nodes) == 1:
            nid = next(iter(self.selected_nodes))
            nx, ny = self.node_center(nid)
            new_cx = cx - self.drag_offset[0]
            new_cy = cy - self.drag_offset[1]
            dx = new_cx - nx
            dy = new_cy - ny
            self.canvas.move(f"node_{nid}", dx, dy)
            self._update_lines_for_nodes({nid})
        else:
            lx, ly = self.last_drag_pos
            dx = cx - lx
            dy = cy - ly
            if dx or dy:
                for nid in self.selected_nodes:
                    self.canvas.move(f"node_{nid}", dx, dy)
                self._update_lines_for_nodes(set(self.selected_nodes))

        self.last_drag_pos = (cx, cy)

    def on_left_up(self, event):
        cx, cy = self.to_canvas(event)

        if self.box_select_start is not None:
            x0, y0 = self.box_select_start
            x1, y1 = cx, cy
            if x0 > x1:
                x0, x1 = x1, x0
            if y0 > y1:
                y0, y1 = y1, y0
            new_sel = set()
            for nid in self.nodes:
                bx1, by1, bx2, by2 = self.canvas.bbox(f"node_shape_{nid}")
                if not (bx2 < x0 or bx1 > x1 or by2 < y0 or by1 > y1):
                    new_sel.add(nid)
            self.selected_nodes |= new_sel
            self.refresh_selection_style()
            self.canvas.delete(self.box_rect_id)
            self.box_rect_id = None
            self.box_select_start = None
            return

        if not self.dragging:
            return

        moved = set()
        for nid in self.selected_nodes:
            cxn, cyn = self.node_center(nid)
            sx, sy = self.snap(cxn, cyn)
            dx = sx - cxn
            dy = sy - cyn
            if abs(dx) > 0.1 or abs(dy) > 0.1:
                self.canvas.move(f"node_{nid}", dx, dy)
                moved.add(nid)
        if moved:
            self._update_lines_for_nodes(moved)

        self.dragging = False
        self.last_drag_pos = None

        if self.label_source.get() == "auto" and self._layout_moved:
            self.request_rebuild()
        self._layout_moved = False

        self.update_scrollregion()

    def on_double_click(self, event):
        target = self.under_cursor(event)
        if target and target[0] == "node":
            nid = target[1]
            current_display = self.canvas.itemcget(self.nodes[nid]["text"], "text")
            base = self._display_to_raw_label(current_display)
            new_text = simpledialog.askstring("Edit label", "Label:", initialvalue=base, parent=self.root)
            if new_text is not None:
                if self.label_source.get() == "auto":
                    self.label_source.set("manual")
                self.manual_labels[nid] = new_text
                raw = f"{self._newick_label(new_text)};"
                display = self._display_from_newick(raw, new_text)
                self.canvas.itemconfigure(self.nodes[nid]["text"], text=display)
                self._text_cache[nid] = display
                self.request_rebuild()
                self.resize_node_to_text(nid)

    def on_right_click(self, event):
        target = self.under_cursor(event)
        if not target:
            return
        if target[0] == "node":
            nid = target[1]
            if nid in self.selected_nodes and len(self.selected_nodes) > 1:
                for dn in list(self.selected_nodes):
                    if dn in self.nodes:
                        self.delete_node(dn)
                self.selected_nodes.clear()
            else:
                self.delete_node(nid)
                self.selected_nodes.discard(nid)
        else:
            lid = target[1]
            self.delete_line(lid)
            if self.selected_line == lid:
                self.selected_line = None
        self.refresh_selection_style()

    def on_delete(self, event=None):
        if self.selected_line:
            self.delete_line(self.selected_line)
            self.selected_line = None
        elif self.selected_nodes:
            for nid in list(self.selected_nodes):
                if nid in self.nodes:
                    self.delete_node(nid)
            self.selected_nodes.clear()
        self.refresh_selection_style()
        self.update_scrollregion()

    def on_escape(self, event):
        if self.preview_line:
            self.canvas.delete(self.preview_line)
            self.preview_line = None
            self.connect_start = None
        else:
            self.select_clear()

    def on_motion(self, event):
        cx, cy = self.to_canvas(event)
        if self.mode.get() == "connect" and self.connect_start is not None and self.preview_line:
            ax, ay = self.node_anchor(self.connect_start, cx, cy)
            self.canvas.coords(self.preview_line, ax, ay, cx, cy)

    # ----- Pan / Zoom -----
    def on_mid_down(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def on_mid_drag(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def on_zoom(self, event):
        cx, cy = self.to_canvas(event)
        factor = 1.1 if event.delta > 0 else 1 / 1.1
        self.scale *= factor
        self.canvas.scale("all", cx, cy, factor, factor)
        for lid, info in self.lines.items():
            a_id, b_id = info["a"], info["b"]
            bcx, bcy = self.node_center(b_id)
            ax1, ay1 = self.node_anchor(a_id, bcx, bcy)
            acx, acy = self.node_center(a_id)
            bx1, by1 = self.node_anchor(b_id, acx, acy)
            self.canvas.coords(lid, ax1, ay1, bx1, by1)
        self.update_scrollregion()
        self.label_zoom()
        self.draw_grid()

    # ---------- Export helpers (Newick / Parent list) ----------
    def _stable_ids_and_labels(self):
        id_map = {}
        labels = {}
        if self.label_source.get() == "auto":
            order = self._auto_label_order()
            for i, nid in enumerate(order, start=1):
                sid = f"n{i}"
                id_map[nid] = sid
                labels[sid] = self._index_to_alpha(i - 1)
            self.label_counter = len(order)
        else:
            for i, nid in enumerate(self.nodes.keys(), start=1):
                sid = f"n{i}"
                id_map[nid] = sid
            for nid in self.nodes.keys():
                if nid not in self.manual_labels:
                    self.manual_labels[nid] = self._next_alpha_label()
            for nid, sid in id_map.items():
                labels[sid] = self.manual_labels.get(nid, "Node")
            self.label_counter = len(self.manual_labels)
        return id_map, labels

    def _build_forest(self, id_map):
        children_map = {sid: [] for sid in id_map.values()}
        parent_of = {sid: None for sid in id_map.values()}
        indeg = {sid: 0 for sid in id_map.values()}
        warnings = []
        for lid, info in self.lines.items():
            a_sid = id_map.get(info["a"])
            b_sid = id_map.get(info["b"])
            if not a_sid or not b_sid or a_sid == b_sid:
                continue
            children_map[a_sid].append(b_sid)
            indeg[b_sid] += 1
            if parent_of[b_sid] is None:
                parent_of[b_sid] = a_sid
            else:
                warnings.append(f"Node {b_sid} has multiple parents; using {parent_of[b_sid]}, dropping {a_sid}")
        roots = [sid for sid, d in indeg.items() if d == 0]
        if not roots:
            warnings.append("No roots found (every node has a parent). A cycle may exist.")
        return children_map, parent_of, roots, warnings

    def _detect_cycle(self, children_map):
        visiting = set()
        visited = set()
        def dfs(u):
            if u in visiting: return True
            if u in visited: return False
            visiting.add(u)
            for v in children_map.get(u, []):
                if dfs(v): return True
            visiting.remove(u)
            visited.add(u)
            return False
        for u in children_map.keys():
            if dfs(u):
                return True
        return False

    def _to_newick_subtrees(self, children_map, labels):
        memo = {}
        def rec(u):
            if u in memo: return memo[u]
            kids = children_map.get(u, [])
            if not kids:
                s = self._newick_label(labels.get(u, u))
            else:
                inner = ",".join(rec(c)[:-1] for c in kids)
                s = f"({inner}){self._newick_label(labels.get(u, u))}"
            memo[u] = s + ";"
            return memo[u]
        for u in children_map.keys():
            rec(u)
        return memo

    def _parent_list(self, parent_of, labels):
        out = []
        for sid in sorted(parent_of.keys(), key=lambda s: int(s[1:])):
            out.append({"id": sid, "label": labels.get(sid, sid), "parent": parent_of[sid]})
        return out

    def rebuild_all_node_newick(self):
        if not self.nodes:
            return
        id_map, labels = self._stable_ids_and_labels()
        children_map, parent_of, roots, _warnings = self._build_forest(id_map)
        subtree_map = self._to_newick_subtrees(children_map, labels)

        # For component mode: map each sid to its component's full Newick
        component_map = None
        if self.label_mode.get() == "component":
            def find_root(u):
                seen = set()
                while parent_of.get(u) and u not in seen:
                    seen.add(u)
                    u = parent_of[u]
                return u
            component_map = {}
            root_nodes = roots if roots else list(subtree_map.keys())
            root_str = {r: subtree_map.get(r, f"{self._newick_label(labels.get(r, r))};") for r in root_nodes}
            for sid in subtree_map.keys():
                r = find_root(sid)
                component_map[sid] = root_str.get(r, subtree_map[sid])

        # Update each node's display text to match detail + view, then resize
        sid_to_nid = {sid: nid for nid, sid in id_map.items()}
        for sid, nid in sid_to_nid.items():
            txt = component_map.get(sid) if (self.label_mode.get() == "component" and component_map is not None) else subtree_map.get(sid)
            if not txt:
                continue
            display = self._display_from_newick(txt, labels.get(sid))
            if self._text_cache.get(nid) != display:
                self.canvas.itemconfigure(self.nodes[nid]["text"], text=display)
                self._text_cache[nid] = display
                if not self._bulk:
                    self.resize_node_to_text(nid)

    # ----- Export / Import (JSON + Newick) -----
    def export_json(self):
        if not self.nodes:
            messagebox.showinfo("Export JSON", "Nothing to export.")
            return
        id_map, labels = self._stable_ids_and_labels()
        data = {"nodes": [], "edges": []}
        for canvas_id, sid in id_map.items():
            cx, cy = self.node_center(canvas_id)
            text = labels[sid]
            data["nodes"].append({"id": sid, "x": cx, "y": cy, "text": text})
        for lid, info in self.lines.items():
            a_sid = id_map.get(info["a"])
            b_sid = id_map.get(info["b"])
            if a_sid and b_sid and a_sid != b_sid:
                data["edges"].append({"from": a_sid, "to": b_sid})

        children_map, parent_of, roots, warnings = self._build_forest(id_map)
        cycle = self._detect_cycle(children_map)
        if cycle:
            warnings.append("Cycle detected; Newick exported from a spanning forest (may omit some edges).")

        def rec_root(r):
            def rec(u):
                kids = children_map.get(u, [])
                if not kids:
                    return self._newick_label(labels.get(u, u))
                return f"({','.join(rec(c) for c in kids)}){self._newick_label(labels.get(u, u))}"
            return rec(r) + ";"

        newick_forest = [rec_root(r) for r in (roots or list(children_map.keys())[:1])]
        parent_list = self._parent_list(parent_of, labels)

        newick_combined = None
        if self.newick_export.get() == "combined":
            inner = ",".join(s[:-1] for s in newick_forest if s.endswith(";"))
            newick_combined = f"({inner});"

        data["formats"] = {
            "newick": newick_forest,
            "parent_list": parent_list,
            "warnings": warnings
        }
        if newick_combined is not None:
            data["formats"]["newick_combined"] = newick_combined

        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Save Mind Map As",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            messagebox.showerror("Export JSON", f"Failed to save file:\n{e}")
            return

        mode = self.newick_export.get()
        extra = " + combined" if mode == "combined" else ""
        messagebox.showinfo("Export JSON", f"Saved to:\n{path}\n\nFormats: forest{extra}, parent_list")

    def import_any(self):
        path = filedialog.askopenfilename(
            title="Open Mind Map",
            filetypes=[
                ("Mind Map JSON", "*.json"),
                ("Newick", "*.newick *.nwk *.txt"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self._import_from_path(path)

    def _import_from_path(self, path):
        ext = os.path.splitext(path)[1].lower()
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except Exception as e:
            messagebox.showerror("Import", f"Failed to read file:\n{e}")
            return

        is_json = (ext == ".json")
        if not is_json:
            is_json = content[:1] in ("{", "[")

        if is_json:
            self._import_json_string(content)
        else:
            self._import_newick_string(content)

    def import_json(self):  # legacy entrypoint
        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")], title="Open Mind Map (JSON)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                s = f.read()
        except Exception as e:
            messagebox.showerror("Import JSON", f"Failed to read file:\n{e}")
            return
        self._import_json_string(s)

    def _import_json_string(self, s):
        try:
            data = json.loads(s)
        except Exception as e:
            messagebox.showerror("Import JSON", f"Failed to parse JSON:\n{e}")
            return

        nodes_in = data.get("nodes", [])
        edges_in = data.get("edges", [])

        self.new_document(clear_only=True)

        sid_to_nid = {}
        for n in nodes_in:
            sid = n.get("id")
            x = float(n.get("x", 0))
            y = float(n.get("y", 0))
            text = n.get("text", None)
            nid = self.add_node(x, y, text=text)
            sid_to_nid[sid] = nid
            if self.label_source.get() == "manual" and text is not None:
                self.manual_labels[nid] = text

        for e in edges_in:
            a_sid = e.get("from")
            b_sid = e.get("to")
            if a_sid in sid_to_nid and b_sid in sid_to_nid:
                self.connect_nodes(sid_to_nid[a_sid], sid_to_nid[b_sid])

        self.update_scrollregion()
        self.request_rebuild()
        messagebox.showinfo("Import JSON", f"Imported {len(nodes_in)} nodes, {len(edges_in)} edges.")

    # ---------- Newick import (collision-free + bulk) ----------
    class _NWKNode:
        __slots__ = ("name", "children")
        def __init__(self, name=""):
            self.name = name
            self.children = []

    def _parse_newick(self, s):
        s = re.sub(r"\s+", "", s)
        if not s.endswith(";"):
            s += ";"
        i = 0
        stack = []
        current = None

        def read_label(idx):
            start = idx
            while idx < len(s) and s[idx] not in "(),:;":
                idx += 1
            return s[start:idx], idx

        while i < len(s):
            c = s[i]
            if c == "(":
                node = self._NWKNode("")
                if current is not None:
                    stack.append(current)
                    current.children.append(node)
                    current = node
                else:
                    current = node
                i += 1
            elif c == ",":
                i += 1
            elif c == ")":
                i += 1
                label, i = read_label(i)
                if label:
                    current.name = label
                if stack:
                    current = stack.pop()
            elif c == ":":
                i += 1
                while i < len(s) and s[i] not in ",)":
                    i += 1
            elif c == ";":
                break
            else:
                label, i2 = read_label(i)
                leaf = self._NWKNode(label)
                if current is None:
                    current = leaf
                else:
                    current.children.append(leaf)
                i = i2
        while stack:
            current = stack.pop()
        return current

    def _layout_tree_positions(
        self,
        root,
        label_map,
        x0=80,
        y0=80,
        min_w=NODE_WIDTH,
        min_h=NODE_HEIGHT,
        pad_x=TEXT_PADDING_X,
        pad_y=TEXT_PADDING_Y,
        level_gap=None,
        sibling_gap=40,
    ):
        """
        Compute non-overlapping positions for all Newick nodes using their
        actual display sizes (detail+view + wrapped).
        Returns: (positions dict, node_wh dict)
        """
        # Build subtree string for each node (like rebuild does)
        subtree_cache = {}
        def subtree_newick(n):
            if n in subtree_cache:
                return subtree_cache[n]
            if not n.children:
                s = f"{self._newick_label(label_map[n])};"
            else:
                inner = ",".join(subtree_newick(c)[:-1] for c in n.children)
                s = f"({inner}){self._newick_label(label_map[n])};"
            subtree_cache[n] = s
            return s

        # Per-node target width/height based on actual *display* string
        node_wh = {}
        def node_target_wh(n):
            if n in node_wh:
                return node_wh[n]
            s = subtree_newick(n)
            display = self._display_from_newick(s, label_map[n])
            w, h = self._measure_display_str_wh(display, min_w=min_w, min_h=min_h, pad_x=pad_x, pad_y=pad_y)
            node_wh[n] = (w, h)
            return w, h

        # Compute subtree widths (sum of children + gaps; at least own box width)
        subtree_w = {}
        subtree_h = {}
        def compute_width(n):
            w, h = node_target_wh(n)
            if not n.children:
                subtree_w[n] = w
                subtree_h[n] = h
                return w
            total_w = 0
            max_h = h
            for i, ch in enumerate(n.children):
                cw = compute_width(ch)
                total_w += cw
                if i > 0:
                    total_w += sibling_gap
                max_h = max(max_h, subtree_h[ch])
            subtree_w[n] = max(total_w, w)
            subtree_h[n] = max_h
            return subtree_w[n]

        compute_width(root)

        # Dynamic vertical gap based on average node height if not specified
        if level_gap is None:
            all_h = [node_target_wh(n)[1] for n in subtree_w.keys()]
            avg_h = sum(all_h) / max(1, len(all_h))
            level_gap = int(avg_h * 1.2) + 40

        # Assign positions centered above children
        positions = {}
        def layout(n, left, depth):
            total_w = subtree_w[n]
            cx = left + total_w / 2.0
            cy = y0 + depth * level_gap
            positions[n] = (cx, cy)
            if n.children:
                cur_left = left
                for i, ch in enumerate(n.children):
                    layout(ch, cur_left, depth + 1)
                    cur_left += subtree_w[ch]
                    if i < len(n.children) - 1:
                        cur_left += sibling_gap

        layout(root, x0, 0)
        return positions, node_wh

    def _import_newick_string(self, s):
        try:
            root = self._parse_newick(s)
        except Exception as e:
            messagebox.showerror("Import Newick", f"Failed to parse Newick:\n{e}")
            return

        # Build label map first; unnamed internals get A/B/C…
        def collect_labels(n, label_map):
            if n.name:
                label_map[n] = n.name
            else:
                label_map[n] = self._next_alpha_label()
            for ch in n.children:
                collect_labels(ch, label_map)

        # Reset sequence for imports (comment out to keep running sequence)
        self.label_counter = 0
        label_map = {}
        collect_labels(root, label_map)

        # Compute overlap-free positions using actual display sizes
        positions, node_wh = self._layout_tree_positions(root, label_map, x0=80, y0=80, sibling_gap=40)

        # Bulk mode to avoid per-node rebuild thrash
        self._bulk = True
        self.new_document(clear_only=True)
        self.label_source.set("manual")

        # Create nodes in bulk
        node_to_canvas = {}
        for n, (x, y) in positions.items():
            lbl = label_map[n]
            nid = self.add_node(x, y, text=lbl, bulk=True)
            node_to_canvas[n] = nid
            self.manual_labels[nid] = lbl

        # Scale each node once to its target size
        for n, nid in node_to_canvas.items():
            w, h = node_wh[n]
            bbox = self.canvas.bbox(f"node_shape_{nid}")
            if not bbox:
                continue
            x1, y1, x2, y2 = bbox
            cur_w = max(1.0, (x2 - x1))
            cur_h = max(1.0, (y2 - y1))
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            sx = w / cur_w
            sy = h / cur_h
            if abs(sx - 1.0) > 0.01 or abs(sy - 1.0) > 0.01:
                self.canvas.scale(f"node_shape_{nid}", cx, cy, sx, sy)

        # Connect edges parent -> child (still in bulk)
        for n in positions.keys():
            for ch in n.children:
                self.connect_nodes(node_to_canvas[n], node_to_canvas[ch])

        # One-shot updates
        self.update_connected_lines(node_to_canvas.values())
        self.update_scrollregion()

        # Turn off bulk, then align text wrap to final inner widths (cheap)
        self._bulk = False
        for nid in node_to_canvas.values():
            self.resize_node_to_text(nid)

        self.request_rebuild()  # re-render text with current detail/view
        messagebox.showinfo("Import Newick", "Imported Newick tree successfully.")

    # ---------- New / Rounded rect ----------
    def new_document(self, clear_only=False):
        self.canvas.delete("all")
        self.nodes.clear()
        self.lines.clear()
        self._text_cache.clear()
        self.select_clear()
        self.connect_start = None
        self.preview_line = None
        self.box_select_start = None
        self.box_rect_id = None
        self.scale = 1.0
        self.label_counter = 0
        self.manual_labels.clear()
        self.label_zoom()
        self.update_scrollregion()
        self.draw_grid()
        if not clear_only:
            nid = self.add_node(200, 150)
            self.select_only_node(nid)

    def rounded_rect(self, x, y, w, h, r, **kwargs):
        x1, y1 = x - w / 2, y - h / 2
        x2, y2 = x + w / 2, y + h / 2
        if hasattr(self.canvas.__class__, "create_round_rectangle"):
            return self.canvas.create_round_rectangle(x1, y1, x2, y2, r=r, **kwargs)
        return self._fallback_round_rect(x1, y1, x2, y2, r, **kwargs)

    def _fallback_round_rect(self, x1, y1, x2, y2, r, **kwargs):
        outline = kwargs.get("outline", NODE_OUTLINE)
        width = kwargs.get("width", 2)
        fill = kwargs.get("fill", NODE_FILL)
        parts = []
        parts.append(self.canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, style=tk.ARC, outline=outline, width=width))
        parts.append(self.canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, style=tk.ARC, outline=outline, width=width))
        parts.append(self.canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, style=tk.ARC, outline=outline, width=width))
        parts.append(self.canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, style=tk.ARC, outline=outline, width=width))
        body = self.canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="")
        left = self.canvas.create_rectangle(x1, y1 + r, x1 + r, y2 - r, fill=fill, outline="")
        right = self.canvas.create_rectangle(x2 - r, y1 + r, x2, y2 - r, fill=fill, outline="")
        top = self.canvas.create_rectangle(x1 + r, y1, x2 - r, y1 + r, fill=fill, outline="")
        bottom = self.canvas.create_rectangle(x1 + r, y2 - r, x2 - r, y2, fill=fill, outline="")
        group_tag = f"roundrect_{body}"
        for i in parts + [body, left, right, top, bottom]:
            self.canvas.addtag_withtag(group_tag, i)
        return body


# ---------- Canvas helper: create_round_rectangle ----------
def add_round_rect_to_canvas(canvas):
    def _create_round_rectangle(self, x1, y1, x2, y2, r=10, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1
        ]
        return self.create_polygon(points, smooth=True, splinesteps=24, **kwargs)

    if not hasattr(canvas.__class__, "create_round_rectangle"):
        canvas.__class__.create_round_rectangle = _create_round_rectangle


# ---------- Main ----------
if __name__ == "__main__":
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        style.theme_use("clam")
    except tk.TclError:
        pass
    app = MindMapApp(root)
    root.mainloop()
