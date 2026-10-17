"""
SUDDEN + SUDDEN-style Lane Cover v14 (Windows)

Visual-only overlay. It does not inspect or modify the game and does not send game inputs.

Install:
    py -m pip install pynput pillow

Run:
    pythonw.exe djmax_lane_cover_v14.pyw

Hotkeys:
    F6 = show/hide cover
    F8 = quit

Mouse modes:
    Move mode: drag the cover body to move its position.
    Resize mode: drag the blue bottom-right handle to change its size.
    Locked mode: cover movement and resizing are disabled.
"""

import ctypes
import json
import random
import os
import tkinter as tk
from tkinter import colorchooser
from tkinter import ttk, messagebox, filedialog

try:
    from pynput.keyboard import Listener, Key
    from PIL import Image, ImageTk
except ImportError:
    raise SystemExit("Install dependencies with: py -m pip install pynput pillow")

if os.name != "nt":
    raise SystemExit("This version is for Windows.")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(APP_DIR, "SuddenOverlay_plus_settings.json")

DEFAULTS = {
    "x": 0, "y": 0, "width": 900, "height": 180,
    "opacity": 100, "color": "#000000", "image_path": "", "visible": True,
    "icon_path": "",
    "always_on_top": False,
    "overlay_always_on_top": False,
    "settings_always_on_top": False,
    "dark_mode": True,
    "move_key": "m", "resize_key": "r", "visibility_key": "f6", "quit_key": "f8",
}

def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        result = DEFAULTS.copy()
        result.update({k: loaded[k] for k in DEFAULTS if k in loaded})
        # Multi-cover data is not part of DEFAULTS, but must survive startup.
        result["extra_covers"] = loaded.get("extra_covers", [])
        return result
    except Exception:
        return DEFAULTS.copy()

settings = load_settings()
visible = bool(settings["visible"])
mouse_mode = "locked"  # "locked", "move", or "resize"
overlay_photo = None
source_image = None
loaded_image_path = None
drag_state = {
    "start_x": 0, "start_y": 0, "left": 0, "top": 0,
    "width": 0, "height": 0, "resize": False, "active": False,
}

root = tk.Tk()
root.title("SUDDEN + SUDDEN-style Lane Cover")
root.geometry("900x800")
root.minsize(820, 700)
root.resizable(True, True)

# Main lane-cover overlay window (separate from the settings window).
overlay = tk.Toplevel(root)
overlay.overrideredirect(True)
overlay.geometry(f'{settings["width"]}x{settings["height"]}+{settings["x"]}+{settings["y"]}')
overlay.configure(bg=settings["color"])
overlay.attributes("-topmost", bool(settings.get("overlay_always_on_top", settings.get("always_on_top", False))))
if not visible:
    overlay.withdraw()


def safe_int(var, minimum=None, maximum=None):
    value = int(var.get())
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value

def current_values():
    return {
        "x": int(x_var.get()), "y": int(y_var.get()),
        "width": safe_int(width_var, 50), "height": safe_int(height_var, 1),
        "opacity": safe_int(opacity_var, 0, 100),
        "color": color_var.get().strip(), "image_path": image_var.get().strip(),
        "visible": visible,
            "settings_always_on_top": bool(settings_topmost_var.get()),
        "overlay_always_on_top": bool(overlay_topmost_var.get()),
        "always_on_top": bool(overlay_topmost_var.get()),
        "dark_mode": bool(dark_mode_var.get()),
        "visibility_key": visibility_key_var.get().strip().lower(),
        "quit_key": quit_key_var.get().strip().lower(),
    }

def save_settings():
    try:
        values = current_values()
        # Never erase additional covers when saving main-cover settings.
        if "extra_covers" in globals():
            values["extra_covers"] = [
                {key: (item[key].get() if key in item and hasattr(item[key], "get") else item.get(key))
                 for key in ("name", "x", "y", "width", "height", "opacity", "color", "image", "visible")}
                for item in extra_covers
            ]
        else:
            values["extra_covers"] = settings.get("extra_covers", [])
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(values, f, indent=2)
    except Exception as exc:
        messagebox.showwarning("Settings", f"Could not save settings:\n{exc}")

def set_click_through(enabled):
    """In locked mode, let clicks pass through. In edit mode, receive mouse input."""
    try:
        overlay.update_idletasks()
        hwnd = overlay.winfo_id()
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED
        if enabled:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        # Only solid-color mode uses the Opacity setting. Image mode remains
        # fully opaque at the window level so image rendering isn't dimmed.
        is_image_mode = bool(image_var.get().strip())
        opacity = 100 if is_image_mode else safe_int(opacity_var, 0, 100)
        alpha = int(opacity * 255 / 100)
        user32.SetLayeredWindowAttributes(hwnd, 0, alpha, 0x00000002)
    except Exception:
        pass

def ensure_image_label():
    if not hasattr(render_cover, "image_label"):
        label = tk.Label(overlay, bd=0, highlightthickness=0, padx=0, pady=0, anchor="nw")
        label.place(x=0, y=0, relwidth=1, relheight=1)
        # Child widgets receive mouse events instead of the Toplevel, so bind them too.
        render_cover.image_label = label
    return render_cover.image_label

def render_cover(show_errors=True):
    """Keep image aspect ratio, align at top, and crop excess from its bottom."""
    global overlay_photo, source_image, loaded_image_path
    try:
        x = int(x_var.get())
        y = int(y_var.get())
        width = safe_int(width_var, 50)
        height = safe_int(height_var, 1)
        opacity = safe_int(opacity_var, 0, 100)
        path = image_var.get().strip()

        if not path:
            # Solid-color mode: do not open, resize, or otherwise process any image.
            source_image = None
            loaded_image_path = None
            overlay_photo = None
            if hasattr(render_cover, "image_label"):
                render_cover.image_label.configure(image="")
                render_cover.image_label.image = None
                render_cover.image_label.place_forget()
            color = color_var.get().strip()
            if not (len(color) == 7 and color.startswith("#")):
                color = "#000000"
                color_var.set(color)
            overlay.configure(bg=color)
        else:
            # Image mode: image processing only runs when a path is provided.
            if not os.path.isfile(path):
                raise ValueError("The selected image file does not exist.")
            if source_image is None or loaded_image_path != path:
                with Image.open(path) as im:
                    source_image = im.convert("RGBA")
                loaded_image_path = path

            src_w, src_h = source_image.size
            if src_w < 1 or src_h < 1:
                raise ValueError("The selected image is empty.")
            scaled_h = max(1, round(src_h * width / src_w))
            resized = source_image.resize((width, scaled_h), Image.Resampling.LANCZOS)

            # Crop from the bottom: show the image's top edge first.
            visible_h = min(height, scaled_h)
            cropped = resized.crop((0, 0, width, visible_h))

            # Tk's normal Toplevel doesn't reliably support per-pixel alpha on Windows.
            # Composite transparent PNG pixels against the selected fallback color, then
            # use Windows layered-window alpha for the overall opacity.
            color = color_var.get().strip()
            if not (color.startswith("#") and len(color) == 7):
                color = "#000000"
            background = Image.new("RGBA", cropped.size, color)
            background.alpha_composite(cropped)
            rgb = background.convert("RGB")

            # If the cover is taller than the scaled image, fill the remainder with
            # the fallback color (without stretching the image).
            if visible_h < height:
                fill = Image.new("RGB", (width, height), color)
                fill.paste(rgb, (0, 0))
                rgb = fill

            overlay_photo = ImageTk.PhotoImage(rgb)
            label = ensure_image_label()
            label.configure(image=overlay_photo, bg=color)
            label.image = overlay_photo
            label.place(x=0, y=0, width=width, height=height, anchor="nw")
            overlay.configure(bg=color)

        # Apply geometry through Tk and Win32. SetWindowPos makes X/Y changes
        # take effect immediately on layered, borderless Windows overlay windows.
        overlay.geometry(f"{width}x{height}+{x}+{y}")
        overlay.attributes("-topmost", bool(overlay_topmost_var.get()) if "always_on_top_var" in globals() else True)
        overlay.update_idletasks()
        if visible:
            overlay.deiconify()
            overlay.lift()
            try:
                hwnd = overlay.winfo_id()
                HWND_TOPMOST = -1
                SWP_NOACTIVATE = 0x0010
                SWP_SHOWWINDOW = 0x0040
                ctypes.windll.user32.SetWindowPos(
                    hwnd, HWND_TOPMOST, x, y, width, height,
                    SWP_NOACTIVATE | SWP_SHOWWINDOW
                )
            except Exception:
                pass
        else:
            overlay.withdraw()
        # Opacity is intended for solid-color covers only. Image mode keeps
        # its image rendering independent from whole-window alpha to avoid
        # the black/grey artifacts caused by compositing the entire image window.
        if path:
            set_window_opacity = 100
        else:
            set_window_opacity = opacity
        try:
            hwnd = overlay.winfo_id()
            ctypes.windll.user32.SetLayeredWindowAttributes(
                hwnd, 0, int(set_window_opacity * 255 / 100), 0x00000002
            )
        except Exception:
            pass
        set_click_through(mouse_mode == "locked")
        if mouse_mode != "locked":
            ensure_resize_handle()
        return True
    except Exception as exc:
        if show_errors:
            messagebox.showerror("Cover error", str(exc))
        return False

def ensure_resize_handle():
    if not hasattr(ensure_resize_handle, "handle"):
        handle = tk.Label(
            overlay, text="◢", fg="white", bg="#2878d0",
            cursor="size_nw_se", font=("Malgun Gothic", 12, "bold"), bd=1
        )
        ensure_resize_handle.handle = handle
    if mouse_mode == "resize" and visible:
        ensure_resize_handle.handle.place(relx=1.0, rely=1.0, anchor="se", width=24, height=24)
        ensure_resize_handle.handle.lift()
    else:
        ensure_resize_handle.handle.place_forget()

def apply_settings():
    global source_image, loaded_image_path
    # The unified cover editor has its own variables; commit them when Apply Settings
    # is pressed so the selected cover is not left with stale values.
    try:
        if selected_extra_cover == "main":
            for target, source in (
                (x_var, extra_x_var), (y_var, extra_y_var),
                (width_var, extra_w_var), (height_var, extra_h_var),
                (opacity_var, extra_opacity_var), (color_var, extra_color_var),
                (image_var, extra_image_var),
            ):
                target.set(source.get())
        elif selected_extra_cover is not None:
            item = selected_extra_cover
            for key, var in (
                ("x", extra_x_var), ("y", extra_y_var), ("width", extra_w_var),
                ("height", extra_h_var), ("opacity", extra_opacity_var),
                ("color", extra_color_var), ("image", extra_image_var),
            ):
                item[key].set(var.get())
            _extra_cover_render(item)
            save_multi_covers()
    except Exception as exc:
        messagebox.showerror("설정 오류", str(exc))
        return
    try:
        int(x_var.get())
        int(y_var.get())
        if int(width_var.get()) < 50 or int(height_var.get()) < 1:
            raise ValueError("Width must be at least 50 and height at least 1.")
        if not 0 <= int(opacity_var.get()) <= 100:
            raise ValueError("Opacity must be between 0 and 100.")
    except Exception as exc:
        messagebox.showerror("Invalid settings", str(exc))
        return
    if image_var.get().strip() != loaded_image_path:
        source_image = None
        loaded_image_path = None
    if render_cover():
        save_settings()

def browse_image():
    path = filedialog.askopenfilename(
        title="Choose lane-cover image",
        filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("All files", "*.*")]
    )
    if path:
        image_var.set(path)
        apply_settings()



def use_color():
    image_var.set("")
    apply_settings()

def set_main_cover_color():
    chosen = colorchooser.askcolor(color=color_var.get(), title="커버 색상 선택")
    if chosen and chosen[1]:
        color_var.set(chosen[1])
        apply_settings()

def set_visible(value):
    global visible
    visible = value
    if visible:
        render_cover()
    else:
        overlay.withdraw()
    for item in extra_covers:
        item["visible"].set(bool(value))
        _extra_cover_render(item)
    ensure_resize_handle()
    save_multi_covers()
    save_settings()

def toggle_visible():
    root.after(0, lambda: set_visible(not visible))

def set_mouse_mode(mode):
    global mouse_mode
    # Clicking the active editing mode again returns to the safe locked default.
    if mode == mouse_mode:
        mode = "locked"
    mouse_mode = mode
    drag_state["active"] = False
    if mode == "move":
        edit_status.set("이동 모드 켜짐: 커버 본체를 드래그해 이동하세요.\n이동 버튼을 다시 누르면 잠깁니다.")
    elif mode == "resize":
        edit_status.set("크기 조절 모드 켜짐: 파란색 모서리를 드래그해 크기를 조절하세요.\n크기 조절 버튼을 다시 누르면 잠깁니다.")
    else:
        edit_status.set("잠금 상태: 커버 이동과 크기 조절이 잠겨 있습니다.")
    # Keep the selected edit mode visibly highlighted until it is toggled off.
    try:
        move_btn.configure(style="Accent.TButton" if mode == "move" else "TButton")
        resize_btn.configure(style="Accent.TButton" if mode == "resize" else "TButton")
    except Exception:
        pass
    set_click_through(mode == "locked")
    ensure_resize_handle()
    for item in extra_covers:
        _extra_cover_render(item)
        if visible and item["visible"].get():
            item["window"].lift()
    if visible:
        overlay.lift()


def begin_drag(event, resize=False):
    if mouse_mode == "locked" or not visible:
        return "break"
    # Only allow the relevant action for the selected mode.
    if mouse_mode == "move" and resize:
        return "break"
    if mouse_mode == "resize" and not resize:
        return "break"
    drag_state.update({
        "start_x": event.x_root, "start_y": event.y_root,
        "left": overlay.winfo_x(), "top": overlay.winfo_y(),
        "width": overlay.winfo_width(), "height": overlay.winfo_height(),
        "resize": (mouse_mode == "resize"), "active": True,
    })
    return "break"

def drag_motion(event):
    if mouse_mode == "locked" or not drag_state["active"]:
        return "break"
    dx = event.x_root - drag_state["start_x"]
    dy = event.y_root - drag_state["start_y"]
    if drag_state["resize"]:
        # Resize mode: update dimensions and rerender the image.
        width_var.set(str(max(50, drag_state["width"] + dx)))
        height_var.set(str(max(1, drag_state["height"] + dy)))
        x_var.set(str(drag_state["left"]))
        y_var.set(str(drag_state["top"]))
        render_cover(show_errors=False)
    else:
        # Move mode: do NOT rerender/recreate the image on every mouse event.
        # Move the existing overlay window directly so the visual position
        # tracks the pointer in real time without image/widget reconfiguration.
        new_x = drag_state["left"] + dx
        new_y = drag_state["top"] + dy
        x_var.set(str(new_x))
        y_var.set(str(new_y))
        overlay.geometry(f"+{new_x}+{new_y}")
        overlay.update_idletasks()
    return "break"

def end_drag(_event):
    if drag_state["active"]:
        drag_state["active"] = False
        save_settings()
    return "break"

def save_hotkey_settings(*_args):
    """Persist hotkey edits immediately, even if no other setting is changed."""
    try:
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if not isinstance(saved, dict):
                saved = {}
        except (OSError, json.JSONDecodeError):
            saved = {}
        saved.update({
            "visibility_key": visibility_key_var.get().strip().lower() or "f6",
            "quit_key": quit_key_var.get().strip().lower() or "f8",
        })
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(saved, f, indent=2)
    except Exception as exc:
        messagebox.showwarning("설정 저장", f"단축키 설정을 저장하지 못했어:\n{exc}")

def quit_app():
    # Save the latest hotkey values before closing, as a final safeguard.
    save_hotkey_settings()
    try:
        save_settings()
    except Exception:
        pass
    root.destroy()

pressed_keys = set()
visibility_key_var = tk.StringVar(value=str(settings.get("visibility_key", "f6")).lower())
quit_key_var = tk.StringVar(value=str(settings.get("quit_key", "f8")).lower())

# Save hotkey edits as they change; no separate Save button is required.
for _hotkey_var in (visibility_key_var, quit_key_var):
    _hotkey_var.trace_add("write", save_hotkey_settings)

def key_name(key):
    try:
        if key.char:
            return key.char.lower()
    except AttributeError:
        pass
    name = str(key)
    if name.startswith("Key."):
        return name[4:].lower()
    return name.lower()

def on_key_press(key):
    name = key_name(key)
    pressed_keys.add(name)
    ctrl_down = any(k in pressed_keys for k in ("Key.ctrl_l", "Key.ctrl_r"))
    alt_down = any(k in pressed_keys for k in ("Key.alt_l", "Key.alt_r", "Key.alt_gr"))
    if name == visibility_key_var.get().strip().lower():
        root.after(0, toggle_visible)
    elif name == quit_key_var.get().strip().lower():
        root.after(0, quit_app)

def on_key_release(key):
    pressed_keys.discard(key_name(key))


# ---- Multi lane-cover support ------------------------------------------------
# Each additional cover has its own window, image/color, geometry and visibility.
# The global Move/Resize mode is shared; each window can be edited independently.
extra_covers = []
selected_extra_cover = None

def _extra_cover_render(item):
    win = item["window"]
    if not win.winfo_exists():
        return
    try:
        w = max(50, int(item["width"].get()))
        h = max(1, int(item["height"].get()))
        x, y = int(item["x"].get()), int(item["y"].get())
        color = item["color"].get().strip() or "#000000"
        path = item["image"].get().strip()
        if path and os.path.isfile(path):
            with Image.open(path) as im:
                im = im.convert("RGBA")
                sw, sh = im.size
                scaled_h = max(1, round(sh * w / max(1, sw)))
                im = im.resize((w, scaled_h), Image.Resampling.LANCZOS)
                im = im.crop((0, 0, w, min(h, scaled_h)))
                bg = Image.new("RGBA", im.size, color)
                bg.alpha_composite(im)
                rgb = bg.convert("RGB")
                if rgb.height < h:
                    fill = Image.new("RGB", (w, h), color)
                    fill.paste(rgb, (0, 0))
                    rgb = fill
            photo = ImageTk.PhotoImage(rgb)
            item["photo"] = photo
            item["label"].configure(image=photo, bg=color)
            item["label"].image = photo
            item["label"].place(x=0, y=0, width=w, height=h)
        else:
            item["label"].place_forget()
            win.configure(bg=color)
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.attributes("-topmost", bool(overlay_topmost_var.get()))
        if item["visible"].get():
            win.deiconify()
        else:
            win.withdraw()
        # All covers obey the shared edit mode: click-through while locked.
        try:
            hwnd = win.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20) | 0x00080000
            if mouse_mode == "locked":
                style |= 0x00000020
            else:
                style &= ~0x00000020
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
            alpha = 255 if path else int(max(0, min(100, int(item["opacity"].get()))) * 255 / 100)
            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, alpha, 0x00000002)
        except Exception:
            pass
        if mouse_mode == "resize" and item["visible"].get():
            item["handle"].place(relx=1, rely=1, anchor="se", width=24, height=24)
        else:
            item["handle"].place_forget()
    except Exception:
        pass

def _extra_begin_drag(item, event, resize=False):
    if mouse_mode == "locked" or not item["visible"].get():
        return "break"
    if mouse_mode == "move" and resize:
        return "break"
    if mouse_mode == "resize" and not resize:
        return "break"
    item["drag"] = {
        "sx": event.x_root, "sy": event.y_root,
        "x": item["window"].winfo_x(), "y": item["window"].winfo_y(),
        "w": item["window"].winfo_width(), "h": item["window"].winfo_height(),
        "resize": mouse_mode == "resize"
    }
    return "break"

def _extra_drag_motion(item, event):
    d = item.get("drag")
    if not d or mouse_mode == "locked":
        return "break"
    dx, dy = event.x_root-d["sx"], event.y_root-d["sy"]
    if d["resize"]:
        item["width"].set(str(max(50, d["w"]+dx)))
        item["height"].set(str(max(1, d["h"]+dy)))
        _extra_cover_render(item)
    else:
        x, y = d["x"]+dx, d["y"]+dy
        item["x"].set(str(x)); item["y"].set(str(y))
        item["window"].geometry(f"+{x}+{y}")
    return "break"

def _extra_end_drag(item, _event):
    item["drag"] = None
    save_multi_covers()
    return "break"

restoring_extra_covers = False

def save_multi_covers():
    if restoring_extra_covers:
        return
    try:
        base = current_values()
        base["extra_covers"] = [{
            k: (v.get() if isinstance(v, (tk.StringVar, tk.BooleanVar)) else v)
            for k, v in item.items()
            if k in ("name", "x", "y", "width", "height", "opacity", "color", "image", "visible")
        } for item in extra_covers]
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(base, f, indent=2)
    except Exception:
        pass

def add_lane_cover():
    idx = len(extra_covers) + 2
    item = {
        "name": f"Lane Cover {idx}",
        "x": tk.StringVar(value=str(100 + idx*20)),
        "y": tk.StringVar(value="100"),
        "width": tk.StringVar(value="200"),
        "height": tk.StringVar(value="500"),
        "opacity": tk.StringVar(value="100"),
        "color": tk.StringVar(value="#%06X" % random.randint(0, 0xFFFFFF)),
        "image": tk.StringVar(value=""),
        "visible": tk.BooleanVar(value=True),
        "drag": None, "photo": None,
    }
    win = tk.Toplevel(root)
    item["window"] = win
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.configure(bg="#000000")
    label = tk.Label(win, bd=0, highlightthickness=0, padx=0, pady=0, anchor="nw")
    label.place(x=0, y=0, relwidth=1, relheight=1)
    item["label"] = label
    handle = tk.Label(win, text="◢", fg="white", bg="#2878d0",
                      cursor="size_nw_se", font=("Malgun Gothic", 12, "bold"), bd=1)
    item["handle"] = handle
    for target in (win, label):
        target.bind("<ButtonPress-1>", lambda e, it=item: _extra_begin_drag(it, e, False))
        target.bind("<B1-Motion>", lambda e, it=item: _extra_drag_motion(it, e))
        target.bind("<ButtonRelease-1>", lambda e, it=item: _extra_end_drag(it, e))
    handle.bind("<ButtonPress-1>", lambda e, it=item: _extra_begin_drag(it, e, True))
    handle.bind("<B1-Motion>", lambda e, it=item: _extra_drag_motion(it, e))
    handle.bind("<ButtonRelease-1>", lambda e, it=item: _extra_end_drag(it, e))
    extra_covers.append(item)
    cover_list.insert("end", item["name"])
    cover_list.selection_clear(0, "end")
    cover_list.selection_set("end")
    select_lane_cover()
    _extra_cover_render(item)
    save_multi_covers()

def delete_selected_lane_cover():
    selection = cover_list.curselection()
    if not selection:
        messagebox.showinfo("Lane covers", "Select an added lane cover to delete.")
        return
    index = selection[0]
    if index == 0:
        messagebox.showinfo("Lane covers", "The main cover cannot be deleted. You can hide it instead.")
        return
    item_index = index - 1
    if not (0 <= item_index < len(extra_covers)):
        return
    item = extra_covers.pop(item_index)
    try:
        item["window"].destroy()
    except Exception:
        pass
    cover_list.delete(index)
    if extra_covers:
        new_index = min(index, len(extra_covers))
        cover_list.selection_clear(0, "end")
        cover_list.selection_set(new_index)
        select_lane_cover()
    else:
        cover_list.selection_clear(0, "end")
        cover_list.selection_set(0)
        select_lane_cover()
    save_multi_covers()


def select_lane_cover(_event=None):
    global selected_extra_cover
    selection = cover_list.curselection()
    if not selection:
        selected_extra_cover = None
        return
    i = selection[0]
    if i == 0:
        selected_extra_cover = "main"
        extra_x_var.set(x_var.get()); extra_y_var.set(y_var.get())
        extra_w_var.set(width_var.get()); extra_h_var.set(height_var.get())
        extra_opacity_var.set(opacity_var.get()); extra_color_var.set(color_var.get())
        extra_image_var.set(image_var.get())
        return
    selected_extra_cover = extra_covers[i-1]
    item = selected_extra_cover
    extra_x_var.set(item["x"].get()); extra_y_var.set(item["y"].get())
    extra_w_var.set(item["width"].get()); extra_h_var.set(item["height"].get())
    extra_opacity_var.set(item["opacity"].get()); extra_color_var.set(item["color"].get())
    extra_image_var.set(item["image"].get())

def apply_selected_lane_cover():
    if selected_extra_cover is None:
        messagebox.showinfo("Lane covers", "Select a cover from the list first.")
        return
    if selected_extra_cover == "main":
        for target, source in (
            (x_var, extra_x_var), (y_var, extra_y_var),
            (width_var, extra_w_var), (height_var, extra_h_var),
            (opacity_var, extra_opacity_var), (color_var, extra_color_var),
            (image_var, extra_image_var)
        ):
            target.set(source.get())
        apply_settings()
        save_multi_covers()
        return
    item = selected_extra_cover
    for key, var in (("x", extra_x_var), ("y", extra_y_var), ("width", extra_w_var),
                     ("height", extra_h_var), ("opacity", extra_opacity_var),
                     ("color", extra_color_var), ("image", extra_image_var)):
        item[key].set(var.get())
    _extra_cover_render(item)
    save_multi_covers()

def browse_extra_cover_image():
    path = filedialog.askopenfilename(
        title="Choose lane-cover image",
        filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files", "*.*")]
    )
    if path:
        extra_image_var.set(path)
        apply_selected_lane_cover()

def set_extra_cover_color():
    chosen = colorchooser.askcolor(title="Choose lane-cover color")
    if chosen and chosen[1]:
        extra_color_var.set(chosen[1])
        apply_selected_lane_cover()

def set_all_extra_visibility(value):
    global visible
    visible = bool(value)
    if visible:
        render_cover()
    else:
        overlay.withdraw()
    for item in extra_covers:
        item["visible"].set(bool(value))
        _extra_cover_render(item)
    save_multi_covers()
    save_settings()

# UI for extra covers is added after the existing cover settings widgets are built.


x_var = tk.StringVar(value=str(settings["x"]))
y_var = tk.StringVar(value=str(settings["y"]))
width_var = tk.StringVar(value=str(settings["width"]))
height_var = tk.StringVar(value=str(settings["height"]))
opacity_var = tk.StringVar(value=str(settings["opacity"]))
color_var = tk.StringVar(value=str(settings["color"]))
image_var = tk.StringVar(value=str(settings["image_path"]))
settings_topmost_var = tk.BooleanVar(value=bool(settings.get("settings_always_on_top", False)))
overlay_topmost_var = tk.BooleanVar(value=bool(settings.get("overlay_always_on_top", settings.get("always_on_top", False))))
dark_mode_var = tk.BooleanVar(value=bool(settings.get("dark_mode", True)))
edit_status = tk.StringVar(value="잠금 상태: 커버 이동과 크기 조절이 잠겨 있습니다.")

def apply_preferences():
    # Apply the settings-window and overlay always-on-top preferences independently.
    try:
        root.attributes("-topmost", bool(settings_topmost_var.get()))
        overlay.attributes("-topmost", bool(overlay_topmost_var.get()))
        for item in extra_covers:
            try:
                item["window"].attributes("-topmost", bool(overlay_topmost_var.get()))
            except Exception:
                pass
    except Exception:
        pass
    apply_theme()
    save_settings()

# Polished dark UI built with standard ttk; no extra UI package required.
try:
    style = ttk.Style(root)
    style.theme_use("clam")
except Exception:
    style = ttk.Style(root)

BG = "#10141D"
PANEL = "#191F2B"
PANEL_ALT = "#202838"
TEXT = "#E8EDF7"
MUTED = "#9AA7BC"
ACCENT = "#7C5CFC"
ACCENT_HOVER = "#927AFF"
BORDER = "#2D3749"

root.configure(bg=BG)
style.configure(".", font=("Malgun Gothic", 10))
style.configure("TFrame", background=BG)
style.configure("Panel.TFrame", background=PANEL)
style.configure("PanelAlt.TFrame", background=PANEL_ALT)
style.configure("TLabel", background=BG, foreground=TEXT)
style.configure("Muted.TLabel", background=BG, foreground=MUTED)
style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
style.configure("Hero.TLabel", background=BG, foreground=TEXT, font=("Malgun Gothic", 19, "bold"))
style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Malgun Gothic", 10))
style.configure("Section.TLabel", background=PANEL, foreground=TEXT, font=("Malgun Gothic", 11, "bold"))
style.configure("TEntry", fieldbackground="#111722", foreground=TEXT, insertcolor=TEXT,
                bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=7)
style.configure("TButton", background=PANEL_ALT, foreground=TEXT, bordercolor=BORDER,
                padding=(12, 8), focusthickness=0)
style.map("TButton", background=[("active", "#303B50"), ("pressed", "#283246")],
          foreground=[("disabled", MUTED)])
style.configure("Accent.TButton", background=ACCENT, foreground="#FFFFFF",
                bordercolor=ACCENT, padding=(12, 9), font=("Malgun Gothic", 10, "bold"))
style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("pressed", "#6847E8")])
style.configure("TSeparator", background=BORDER)

def apply_theme():
    global BG, PANEL, PANEL_ALT, TEXT, MUTED, ACCENT, ACCENT_HOVER, BORDER
    if dark_mode_var.get():
        BG, PANEL, PANEL_ALT = "#10141D", "#191F2B", "#202838"
        TEXT, MUTED = "#E8EDF7", "#9AA7BC"
        ACCENT, ACCENT_HOVER, BORDER = "#7C5CFC", "#927AFF", "#2D3749"
        entry_bg = "#111722"
        active_bg, pressed_bg = "#303B50", "#283246"
    else:
        BG, PANEL, PANEL_ALT = "#F2F4F8", "#FFFFFF", "#E7EBF2"
        TEXT, MUTED = "#202636", "#5D687A"
        ACCENT, ACCENT_HOVER, BORDER = "#6547D8", "#765BE5", "#CDD4E0"
        entry_bg = "#FFFFFF"
        active_bg, pressed_bg = "#DCE2EC", "#D1D8E5"

    root.configure(bg=BG)
    style.configure(".", font=("Malgun Gothic", 10))
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("PanelAlt.TFrame", background=PANEL_ALT)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("PanelAlt.TFrame", background=PANEL_ALT)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
    style.configure("Hero.TLabel", background=BG, foreground=TEXT, font=("Malgun Gothic", 19, "bold"))
    style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Malgun Gothic", 10))
    style.configure("Section.TLabel", background=PANEL, foreground=TEXT, font=("Malgun Gothic", 11, "bold"))
    style.configure("TEntry", fieldbackground=entry_bg, foreground=TEXT, insertcolor=TEXT,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=7)
    style.configure("TButton", background=PANEL_ALT, foreground=TEXT, bordercolor=BORDER,
                    padding=(12, 8), focusthickness=0)
    style.map("TButton", background=[("active", active_bg), ("pressed", pressed_bg)],
              foreground=[("disabled", MUTED)])
    style.configure("Accent.TButton", background=ACCENT, foreground="#FFFFFF",
                    bordercolor=ACCENT, padding=(12, 9), font=("Malgun Gothic", 10, "bold"))
    style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("pressed", ACCENT)])
    style.configure("TSeparator", background=BORDER)
    page_canvas_widget = globals().get("page_canvas")
    if page_canvas_widget is not None:
        try:
            page_canvas_widget.configure(bg=BG)
        except Exception:
            pass
    style.configure("TCheckbutton", background=PANEL, foreground=TEXT)
    style.map("TCheckbutton", background=[("active", PANEL)], foreground=[("active", TEXT)])
    for widget in (sidebar, preferences_page, mode_buttons):
        try:
            widget.configure(style="Panel.TFrame")
        except Exception:
            pass

app_shell = ttk.Frame(root, padding=12)
app_shell.pack(fill="both", expand=True)

sidebar = ttk.Frame(app_shell, style="Panel.TFrame", padding=(12, 16))
sidebar.pack(side="left", fill="y", padx=(0, 12))
main_area = ttk.Frame(app_shell)
main_area.pack(side="left", fill="both", expand=True)

ttk.Label(sidebar, text="SUDDEN +", style="Hero.TLabel").pack(anchor="w", pady=(0, 4))
ttk.Label(sidebar, text="레인 커버 오버레이", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 18))

nav_cover = ttk.Button(sidebar, text="커버 설정", command=lambda: show_page("cover"))
nav_cover.pack(fill="x", pady=3)
nav_preferences = ttk.Button(sidebar, text="환경 설정", command=lambda: show_page("preferences"))
nav_preferences.pack(fill="x", pady=3)

sidebar_spacer = ttk.Frame(sidebar, style="Panel.TFrame")
sidebar_spacer.pack(fill="both", expand=True)
sidebar_quit_btn = ttk.Button(sidebar, text="종료", command=quit_app)
sidebar_quit_btn.pack(side="bottom", fill="x", pady=(12, 0))

header = ttk.Frame(main_area)
header.pack(fill="x", pady=(4, 16))
ttk.Label(header, text="SUDDEN + / 레인 커버 오버레이", style="Hero.TLabel").pack(anchor="w")
ttk.Label(header, text="화면 표시 전용 도구", style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))

page_scroll_area = ttk.Frame(main_area)
page_scroll_area.pack(fill="both", expand=True)
page_canvas = tk.Canvas(page_scroll_area, bd=0, highlightthickness=0, bg=BG)
page_scrollbar = ttk.Scrollbar(page_scroll_area, orient="vertical", command=page_canvas.yview)
page_canvas.configure(yscrollcommand=page_scrollbar.set)
page_scrollbar.pack(side="right", fill="y")
page_canvas.pack(side="left", fill="both", expand=True)
page_container = ttk.Frame(page_canvas)
page_canvas_window = page_canvas.create_window((0, 0), window=page_container, anchor="nw")

def _update_page_scroll_region(_event=None):
    page_canvas.configure(scrollregion=page_canvas.bbox("all"))

def _resize_page_canvas(event):
    page_canvas.itemconfigure(page_canvas_window, width=event.width)

page_container.bind("<Configure>", _update_page_scroll_region)
page_canvas.bind("<Configure>", _resize_page_canvas)

def _mousewheel_scroll(event):
    page_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

page_canvas.bind_all("<MouseWheel>", _mousewheel_scroll)

# Appearance / position panel
settings_panel = ttk.Frame(page_container, style="Panel.TFrame", padding=16)
settings_panel.pack(fill="x", pady=(0, 12))
ttk.Label(settings_panel, text="커버 모양 및 위치", style="Section.TLabel").grid(
    row=0, column=0, columnspan=4, sticky="w", pady=(0, 12)
)

fields = [("X 좌표", x_var), ("Y 좌표", y_var),
          ("너비", width_var), ("높이", height_var),
          ("불투명도 · 단색 전용", opacity_var), ("기본 색상 · HEX", color_var)]
for i, (label_text, var) in enumerate(fields):
    r = 1 + i // 2
    c = (i % 2) * 2
    ttk.Label(settings_panel, text=label_text, style="PanelMuted.TLabel").grid(
        row=r, column=c, sticky="w", padx=(0, 10), pady=6
    )
    if var is color_var:
        ttk.Entry(settings_panel, textvariable=var, width=10).grid(
            row=r, column=c + 1, sticky="ew", pady=6
        )
        ttk.Button(settings_panel, text="색상 선택", command=set_main_cover_color).grid(
            row=r, column=c + 2, sticky="ew", padx=(5, 0), pady=6
        )
    else:
        ttk.Entry(settings_panel, textvariable=var, width=13).grid(
            row=r, column=c + 1, sticky="ew", pady=6
        )
for c in range(4):
    settings_panel.columnconfigure(c, weight=1)

opacity_help = ttk.Label(
    settings_panel, text="※ 단색 모드에서만 불투명도 설정 적용",
    style="PanelMuted.TLabel", wraplength=600, justify="left"
)
# Use the full row so the hint has enough space and cannot overlap the image field.
opacity_help.grid(row=4, column=0, columnspan=4, sticky="w", pady=(0, 6))
ttk.Separator(settings_panel).grid(row=5, column=0, columnspan=4, sticky="ew", pady=(12, 8))
ttk.Label(settings_panel, text="커버 이미지", style="PanelMuted.TLabel").grid(
    row=6, column=0, sticky="w", pady=5
)
ttk.Entry(settings_panel, textvariable=image_var).grid(
    row=6, column=1, columnspan=2, sticky="ew", padx=(0, 8), pady=5
)
ttk.Button(settings_panel, text="찾아보기…", command=browse_image).grid(
    row=6, column=3, sticky="ew", pady=5
)

# Taskbar icon panel

# Primary actions
actions = ttk.Frame(page_container)
actions.pack(fill="x", pady=(0, 12))
apply_settings_btn = ttk.Button(actions, text="설정 적용", style="Accent.TButton", command=apply_settings)
apply_settings_btn.pack(side="left", expand=True, fill="x", padx=(0, 5))
solid_color_btn = ttk.Button(actions, text="단색", command=use_color)
solid_color_btn.pack(side="left", expand=True, fill="x", padx=5)

# Editing controls and status
mode_panel = ttk.Frame(page_container, style="Panel.TFrame", padding=16)
mode_panel.pack(fill="x", pady=(0, 12))
edit_title = ttk.Label(mode_panel, text="편집 모드", style="Section.TLabel")
edit_title.pack(anchor="w", pady=(0, 10))
mode_buttons = ttk.Frame(mode_panel, style="Panel.TFrame")
mode_buttons.pack(fill="x")
move_btn = ttk.Button(mode_buttons, text="이동",
                      command=lambda: set_mouse_mode("move"))
move_btn.pack(side="left", expand=True, fill="x", padx=(0, 5))
resize_btn = ttk.Button(mode_buttons, text="크기 조절",
                        command=lambda: set_mouse_mode("resize"))
resize_btn.pack(side="left", expand=True, fill="x", padx=(5, 0))
ttk.Label(mode_panel, textvariable=edit_status, style="PanelMuted.TLabel",
          wraplength=480).pack(anchor="w", pady=(10, 0))

footer = ttk.Frame(page_container)
footer.pack(fill="x", side="bottom")
ttk.Label(footer, text="기본값 F6 표시/숨기기     •     F8 종료 (환경 설정에서 변경 가능)", style="Subtitle.TLabel").pack(anchor="w")


# Unified cover manager: the main cover and all added covers share one settings editor.
multi_cover_panel = ttk.Frame(page_container, style="Panel.TFrame", padding=16)
multi_title = ttk.Label(multi_cover_panel, text="레인 커버 목록", style="Section.TLabel")
multi_title.pack(anchor="w")
cover_list = tk.Listbox(multi_cover_panel, height=4, exportselection=False,
                        bg="#111722", fg="#E8EDF7", selectbackground="#7C5CFC",
                        highlightthickness=0, relief="flat")
cover_list.pack(fill="x", pady=(8, 8))
cover_list.insert("end", "메인 커버")
cover_list.selection_set(0)
cover_list.bind("<<ListboxSelect>>", select_lane_cover)
multi_buttons = ttk.Frame(multi_cover_panel, style="Panel.TFrame")
multi_buttons.pack(fill="x")
add_cover_btn = ttk.Button(multi_buttons, text="레인 커버 추가", command=add_lane_cover)
add_cover_btn.pack(side="left")
delete_cover_btn = ttk.Button(multi_buttons, text="선택한 커버 삭제", command=delete_selected_lane_cover)
delete_cover_btn.pack(side="left", padx=6)
show_all_btn = ttk.Button(multi_buttons, text="모두 표시", command=lambda: set_all_extra_visibility(True))
show_all_btn.pack(side="left", padx=6)
hide_all_btn = ttk.Button(multi_buttons, text="모두 숨기기", command=lambda: set_all_extra_visibility(False))
hide_all_btn.pack(side="left")
extra_x_var = tk.StringVar(value="100")
extra_y_var = tk.StringVar(value="100")
extra_w_var = tk.StringVar(value="200")
extra_h_var = tk.StringVar(value="500")
extra_opacity_var = tk.StringVar(value="100")
extra_color_var = tk.StringVar(value="#000000")
extra_image_var = tk.StringVar(value="")
extra_editor = ttk.Frame(multi_cover_panel, style="Panel.TFrame")
extra_editor.pack(fill="x", pady=(12, 0))
extra_editor.columnconfigure(1, weight=1)
extra_editor.columnconfigure(3, weight=1)

extra_fields = [
    ("X 좌표", extra_x_var, 0, 0),
    ("Y 좌표", extra_y_var, 0, 2),
    ("너비", extra_w_var, 1, 0),
    ("높이", extra_h_var, 1, 2),
    ("불투명도 (%)", extra_opacity_var, 2, 0),
    ("색상 HEX", extra_color_var, 2, 2),
]
for label_text, var, row, col in extra_fields:
    field_label = ttk.Label(extra_editor, text=label_text, style="PanelMuted.TLabel")
    field_label.grid(row=row, column=col, sticky="w", padx=(4, 6), pady=4)
    if var is extra_color_var:
        ttk.Entry(extra_editor, textvariable=var, width=10).grid(
            row=row, column=col+1, sticky="ew", padx=(0, 4), pady=4
        )
        ttk.Button(extra_editor, text="색상 선택", command=set_extra_cover_color).grid(
            row=row, column=4, sticky="ew", padx=(0, 4), pady=4
        )
    else:
        ttk.Entry(extra_editor, textvariable=var, width=12).grid(
            row=row, column=col+1, sticky="ew", padx=(0, 10), pady=4
        )
ttk.Label(
    extra_editor, text="※ 단색 모드에서만 불투명도 설정 적용",
    style="PanelMuted.TLabel", wraplength=260, justify="left"
).grid(row=3, column=0, columnspan=2, sticky="nw", padx=4, pady=(0, 6))

image_field_label = ttk.Label(extra_editor, text="이미지", style="PanelMuted.TLabel")
image_field_label.grid(row=4, column=0, sticky="w", padx=4, pady=4)
ttk.Entry(extra_editor, textvariable=extra_image_var).grid(
    row=4, column=1, columnspan=3, sticky="ew", padx=4, pady=4
)
browse_cover_btn = ttk.Button(extra_editor, text="찾아보기…", command=browse_extra_cover_image)
browse_cover_btn.grid(row=4, column=4, padx=4, pady=4)
apply_cover_btn = ttk.Button(extra_editor, text="선택한 커버 적용", command=apply_selected_lane_cover)
apply_cover_btn.grid(row=5, column=2, columnspan=3, sticky="ew", padx=4, pady=4)

# Navigation pages: Cover Settings combines cover geometry, image, icon, action and edit-mode controls.
preferences_page = ttk.Frame(page_container, style="Panel.TFrame", padding=20)
ttk.Label(preferences_page, text="환경 설정", style="Section.TLabel").pack(anchor="w", pady=(0, 16))

topmost_label = ttk.Label(preferences_page, text="항상 위에 표시", style="Panel.TLabel")
topmost_label.pack(anchor="w", pady=(14, 6))
settings_topmost_check = ttk.Checkbutton(
    preferences_page, text="설정 창", variable=settings_topmost_var,
    command=apply_preferences
)
settings_topmost_check.pack(anchor="w")

overlay_topmost_check = ttk.Checkbutton(
    preferences_page, text="레인 커버 오버레이", variable=overlay_topmost_var,
    command=apply_preferences
)
overlay_topmost_check.pack(anchor="w")

dark_mode_label = ttk.Label(preferences_page, text="앱 다크 모드", style="Panel.TLabel")
dark_mode_label.pack(anchor="w", pady=(18, 6))
dark_mode_check = ttk.Checkbutton(
    preferences_page, text="사용", variable=dark_mode_var,
    command=lambda: (apply_theme(), save_settings())
)
dark_mode_check.pack(anchor="w")

# Hotkey settings are integrated into Preferences.
hotkey_title = ttk.Label(preferences_page, text="단축키 설정", style="Section.TLabel")
hotkey_title.pack(anchor="w", pady=(24, 10))
hotkey_grid = ttk.Frame(preferences_page, style="Panel.TFrame")
hotkey_grid.pack(fill="x")
hotkey_fields = [
    ("커버 표시/숨기기", visibility_key_var),
    ("프로그램 종료", quit_key_var),
]
hotkey_labels = []
for row, (label_text, variable) in enumerate(hotkey_fields):
    label = ttk.Label(hotkey_grid, text=label_text, style="Panel.TLabel")
    label.grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
    hotkey_labels.append(label)
    ttk.Entry(hotkey_grid, textvariable=variable, width=14).grid(row=row, column=1, sticky="w", pady=5)

hint = ttk.Label(
    preferences_page,
    text="변경 사항은 즉시 적용",
    style="PanelMuted.TLabel", wraplength=500
)
hint.pack(anchor="w", pady=(18, 0))

def show_page(page):
    # Hide the existing main controls, then show the selected page.
    for widget in (settings_panel, actions, mode_panel, footer, multi_cover_panel, preferences_page):
        widget.pack_forget()
    if page == "cover":
        multi_cover_panel.pack(fill="x", pady=(0, 12))
        actions.pack(fill="x", pady=(0, 12))
        mode_panel.pack(fill="x", pady=(0, 12))
        footer.pack(fill="x", side="bottom")
    elif page == "preferences":
        preferences_page.pack(fill="both", expand=True)

def restore_extra_covers():
    global restoring_extra_covers
    saved_covers = settings.get("extra_covers", [])
    if not isinstance(saved_covers, list):
        saved_covers = []
    restoring_extra_covers = True
    try:
        for saved in saved_covers:
            if not isinstance(saved, dict):
                continue
            try:
                add_lane_cover()
                item = extra_covers[-1]
                item["name"] = str(saved.get("name", item["name"]))
                for key in ("x", "y", "width", "height", "opacity", "color", "image", "visible"):
                    if key in saved:
                        item[key].set(saved[key])
                cover_list.delete("end")
                cover_list.insert("end", item["name"])
                _extra_cover_render(item)
            except Exception:
                continue
    finally:
        restoring_extra_covers = False
    save_multi_covers()

# Attach optional UI references only after their widgets are created.
show_page("cover")
apply_theme()
restore_extra_covers()
# Re-apply the persisted topmost preference after all windows/covers are created.
# On Windows, setting -topmost only during Toplevel construction can be missed
# when the window is shown later; schedule it once Tk has completed startup.
root.after(150, apply_preferences)
# Always start with Main cover selected so its values are immediately editable.
cover_list.selection_clear(0, "end")
cover_list.selection_set(0)
cover_list.activate(0)
select_lane_cover()

# Centralize mouse handling. Tk sends clicks to the deepest child widget
# (usually the image Label), so handle press/move/release globally and only
# start a drag when the click originated inside the overlay window.
def global_mouse_down(event):
    if mouse_mode == "locked" or not visible:
        return
    try:
        if event.widget.winfo_toplevel() != overlay:
            return
    except Exception:
        return
    is_handle = (
        hasattr(ensure_resize_handle, "handle")
        and event.widget == ensure_resize_handle.handle
    )
    if mouse_mode == "move":
        if not is_handle:
            begin_drag(event, False)
    elif mouse_mode == "resize":
        if is_handle:
            begin_drag(event, True)

root.bind_all("<ButtonPress-1>", global_mouse_down, add="+")
root.bind_all("<B1-Motion>", drag_motion, add="+")
root.bind_all("<ButtonRelease-1>", end_drag, add="+")

listener = Listener(on_press=on_key_press, on_release=on_key_release)
listener.daemon = True
listener.start()

root.protocol("WM_DELETE_WINDOW", quit_app)
root.after(500, lambda: (render_cover(), ensure_resize_handle(), set_click_through(mouse_mode == "locked")))
root.mainloop()
try:
    listener.stop()
except Exception:
    pass
