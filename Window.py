import tkinter
from tkinter import *
import sv_ttk

window = tkinter.Tk()

# Store last rectangle data
last_rect = None
last_rect_tag = None
box_counter = 0  # give each box a unique id

# top bar menu stuff 
menu = Menu(window)
window.config(menu=menu)
filemenu = Menu(menu)
menu.add_cascade(label='File', menu=filemenu)
filemenu.add_command(label='New')
filemenu.add_command(label='Open...')
filemenu.add_separator()
filemenu.add_command(label='Exit', command=window.quit)

# window size stuff
c = Canvas(window, width=1280, height=900)
c.pack()


def get_closest_edge_center(rect_coords, target_center):
    """Return the center of the edge closest to the target center,
       favouring top/bottom edges over left/right."""
    x0, y0, x1, y1 = rect_coords
    cx, cy = target_center

    # Centers of edges
    edges = {
        "left":   (x0, (y0 + y1) / 2),
        "right":  (x1, (y0 + y1) / 2),
        "top":    ((x0 + x1) / 2, y0),
        "bottom": ((x0 + x1) / 2, y1),
    }

    # Apply a weighting: horizontal edges get a small penalty
    def weighted_dist(p, edge_name):
        dist = (p[0] - cx) ** 2 + (p[1] - cy) ** 2
        if edge_name in ("left", "right"):
            dist *= 1.5
        return dist

    # Pick edge with minimum weighted distance
    closest = min(edges.items(), key=lambda item: weighted_dist(item[1], item[0]))[1]
    return closest


def draw_rectangle_on_click(event):
    global last_rect, last_rect_tag, box_counter

    rect_width = 100
    rect_height = 50

    # rectangle coordinates
    x0 = event.x - (rect_width / 2)
    y0 = event.y - (rect_height / 2)
    x1 = event.x + (rect_width / 2)
    y1 = event.y + (rect_height / 2)

    # assign a unique tag to this box
    box_tag = f"box_{box_counter}"
    box_counter += 1

    # draw rectangle
    rect_id = c.create_rectangle(x0, y0, x1, y1, fill="white", outline="black", tags=("box", box_tag))

    # center of new rectangle
    new_center = (event.x, event.y)
    new_rect = (x0, y0, x1, y1)

    # only connect if there’s already another rectangle
    if last_rect is not None:
        last_x0, last_y0, last_x1, last_y1 = last_rect
        last_center = ((last_x0 + last_x1) / 2, (last_y0 + last_y1) / 2)

        # find closest edge centers (with weighting)
        p1 = get_closest_edge_center(last_rect, new_center)
        p2 = get_closest_edge_center(new_rect, last_center)

        # draw connecting line with tags for both boxes
        c.create_line(
            p1[0], p1[1], p2[0], p2[1],
            fill="red", width=2,
            tags=("line", last_rect_tag, box_tag)
        )

    # update last rectangle
    last_rect = new_rect
    last_rect_tag = box_tag


def delete_on_right_click(event):
    """Delete the box or line under the cursor on right click."""
    global last_rect, last_rect_tag

    item = c.find_closest(event.x, event.y)
    if item:
        tags = c.gettags(item)

        if "box" in tags:
            # delete box
            c.delete(item)
            # delete any connected lines
            for t in tags:
                if t.startswith("box_"):
                    connected_lines = c.find_withtag(t)
                    for line in connected_lines:
                        if "line" in c.gettags(line):
                            c.delete(line)

            # find if there are still boxes left
            all_boxes = c.find_withtag("box")
            if all_boxes:
                # set last_rect to the most recent surviving box
                last_id = all_boxes[-1]
                x0, y0, x1, y1 = c.coords(last_id)
                last_rect = (x0, y0, x1, y1)
                for t in c.gettags(last_id):
                    if t.startswith("box_"):
                        last_rect_tag = t
                        break
            else:
                # no boxes left, reset
                last_rect = None
                last_rect_tag = None

        elif "line" in tags:
            # just delete the line
            c.delete(item)


c.bind("<Button-1>", draw_rectangle_on_click)
c.bind("<Button-3>", delete_on_right_click)

# Dark theme
sv_ttk.set_theme("dark")

window.mainloop()
