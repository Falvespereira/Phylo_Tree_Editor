import tkinter
from tkinter import *
import sv_ttk

window = tkinter.Tk()

# Store last rectangle data
last_rect = None
last_rect_tag = None
box_counter = 0

# Track selected items
selected_items = set()

# Track selection rectangle
sel_rect_id = None
sel_start_x, sel_start_y = None, None

# Add/Select mode
add_mode = BooleanVar(value=True)

# Parent box (locked until changed)
parent_box = None
parent_box_tag = None

# Dragging state
dragging_boxes = False
drag_start_x, drag_start_y = 0, 0

# --- UI Setup ---
menu = Menu(window)
window.config(menu=menu)
filemenu = Menu(menu)
menu.add_cascade(label='File', menu=filemenu)
filemenu.add_command(label='New')
filemenu.add_command(label='Open...')
filemenu.add_separator()
filemenu.add_command(label='Exit', command=window.quit)

# Canvas
c = Canvas(window, width=1280, height=900)
c.pack(fill="both", expand=True)

# Toggle Button
toggle_btn = Checkbutton(window, text="Add Boxes", variable=add_mode, onvalue=True, offvalue=False)
toggle_btn.place(relx=1.0, x=-10, y=10, anchor="ne")


def get_closest_edge_center(rect_coords, target_center):
    x0, y0, x1, y1 = rect_coords
    cx, cy = target_center
    edges = {
        "left":   (x0, (y0 + y1) / 2),
        "right":  (x1, (y0 + y1) / 2),
        "top":    ((x0 + x1) / 2, y0),
        "bottom": ((x0 + x1) / 2, y1),
    }

    def weighted_dist(p, edge_name):
        dist = (p[0] - cx) ** 2 + (p[1] - cy) ** 2
        if edge_name in ("left", "right"):
            dist *= 1.5
        return dist

    return min(edges.values(), key=lambda p: weighted_dist(p, ""))


def handle_left_click(event):
    global dragging_boxes, drag_start_x, drag_start_y
    if add_mode.get():
        draw_rectangle_on_click(event)
    else:
        clicked = c.find_withtag(CURRENT)
        if clicked and "box" in c.gettags(clicked):
            if clicked[0] not in selected_items:
                select_single(clicked[0])
            # Start dragging all selected boxes
            dragging_boxes = True
            drag_start_x, drag_start_y = event.x, event.y
        else:
            start_selection(event)


def draw_rectangle_on_click(event):
    global last_rect, last_rect_tag, box_counter, parent_box, parent_box_tag
    clicked = c.find_withtag(CURRENT)
    if clicked:
        select_single(clicked[0])
        return

    rect_width, rect_height = 100, 50
    x0, y0 = event.x - rect_width / 2, event.y - rect_height / 2
    x1, y1 = event.x + rect_width / 2, event.y + rect_height / 2
    box_tag = f"box_{box_counter}"; box_counter += 1

    c.create_rectangle(x0, y0, x1, y1, fill="white", outline="black", tags=("box", box_tag))
    new_rect = (x0, y0, x1, y1)

    parent_rect, parent_tag = None, None
    if parent_box is not None:
        parent_rect, parent_tag = parent_box, parent_box_tag
    elif last_rect is not None:
        parent_rect, parent_tag = last_rect, last_rect_tag

    if parent_rect is not None:
        parent_center = ((parent_rect[0] + parent_rect[2]) / 2, (parent_rect[1] + parent_rect[3]) / 2)
        p1 = get_closest_edge_center(parent_rect, ((x0+x1)/2, (y0+y1)/2))
        p2 = get_closest_edge_center(new_rect, parent_center)
        c.create_line(p1[0], p1[1], p2[0], p2[1], fill="red", width=2, tags=("line", parent_tag, box_tag))

    last_rect, last_rect_tag = new_rect, box_tag


def update_drag(event):
    global dragging_boxes, drag_start_x, drag_start_y
    if dragging_boxes and selected_items:
        dx, dy = event.x - drag_start_x, event.y - drag_start_y
        for item in selected_items:
            if "box" in c.gettags(item):
                c.move(item, dx, dy)
        drag_start_x, drag_start_y = event.x, event.y

        # Update all lines connected to moved boxes
        affected_lines = set()
        for item in selected_items:
            if "box" in c.gettags(item):
                for t in c.gettags(item):
                    if t.startswith("box_"):
                        for line in c.find_withtag(t):
                            if "line" in c.gettags(line):
                                affected_lines.add(line)
        for line in affected_lines:
            update_line(line)


def stop_drag(event):
    global dragging_boxes
    dragging_boxes = False


def update_line(line_id):
    tags = c.gettags(line_id)
    if not tags or "line" not in tags:
        return
    box_tags = [t for t in tags if t.startswith("box_")]
    if len(box_tags) != 2:
        return

    rects = []
    centers = []
    for bt in box_tags:
        box = c.find_withtag(bt)
        if box:
            coords = c.coords(box[0])
            rects.append(coords)
            centers.append(((coords[0] + coords[2]) / 2, (coords[1] + coords[3]) / 2))

    if len(rects) == 2:
        p1 = get_closest_edge_center(rects[0], centers[1])
        p2 = get_closest_edge_center(rects[1], centers[0])
        c.coords(line_id, p1[0], p1[1], p2[0], p2[1])


def delete_item(item):
    global last_rect, last_rect_tag, parent_box, parent_box_tag
    if not item: return
    tags = c.gettags(item)
    if "box" in tags:
        c.delete(item)
        for t in tags:
            if t.startswith("box_"):
                for line in c.find_withtag(t):
                    if "line" in c.gettags(line):
                        c.delete(line)
        if parent_box_tag in tags:
            parent_box, parent_box_tag = None, None
        all_boxes = c.find_withtag("box")
        if all_boxes:
            last_id = all_boxes[-1]
            last_rect, last_rect_tag = c.coords(last_id), [t for t in c.gettags(last_id) if t.startswith("box_")][0]
        else:
            last_rect = last_rect_tag = None
    elif "line" in tags:
        c.delete(item)


def delete_selected(event=None):
    for item in list(selected_items):
        delete_item(item)
    selected_items.clear()


def select_single(item):
    global parent_box, parent_box_tag
    clear_selection()
    selected_items.add(item)
    highlight_item(item)
    tags = c.gettags(item)
    if "box" in tags:
        parent_box = c.coords(item)
        parent_box_tag = [t for t in tags if t.startswith("box_")][0]


def highlight_item(item):
    tags = c.gettags(item)
    if "box" in tags:
        c.itemconfig(item, outline="blue", width=2)
    elif "line" in tags:
        c.itemconfig(item, fill="blue", width=3)


def unhighlight_item(item):
    tags = c.gettags(item)
    if "box" in tags:
        c.itemconfig(item, outline="black", width=1)
    elif "line" in tags:
        c.itemconfig(item, fill="red", width=2)


def clear_selection():
    for item in list(selected_items):
        unhighlight_item(item)
    selected_items.clear()


def delete_on_right_click(event):
    item = c.find_closest(event.x, event.y)
    if item:
        delete_item(item[0])


# --- Marquee selection ---
def start_selection(event):
    global sel_rect_id, sel_start_x, sel_start_y
    sel_start_x, sel_start_y = event.x, event.y
    clear_selection()
    global sel_rect_id
    sel_rect_id = c.create_rectangle(event.x, event.y, event.x, event.y, outline="blue", dash=(2, 2))


def update_selection(event):
    global sel_rect_id
    if sel_rect_id:
        c.coords(sel_rect_id, sel_start_x, sel_start_y, event.x, event.y)


def end_selection(event):
    global sel_rect_id
    if sel_rect_id:
        x0, y0, x1, y1 = c.coords(sel_rect_id)
        c.delete(sel_rect_id)
        x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
        for item in c.find_overlapping(x0, y0, x1, y1):
            if "box" in c.gettags(item) or "line" in c.gettags(item):
                selected_items.add(item)
                highlight_item(item)
        sel_rect_id = None


# --- Bindings ---
c.bind("<Button-1>", handle_left_click)
c.bind("<B1-Motion>", lambda e: update_drag(e) if dragging_boxes else update_selection(e))
c.bind("<ButtonRelease-1>", stop_drag)

c.bind("<Button-3>", delete_on_right_click)
window.bind("<BackSpace>", delete_selected)

# Dark theme
sv_ttk.set_theme("dark")
window.mainloop()
