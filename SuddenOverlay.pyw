import tkinter as tk
from tkinter import colorchooser, filedialog, simpledialog
from PIL import Image, ImageTk, ImageSequence, ImageOps
import os
import json
import keyboard # 🚨 전역 단축키 감지 모듈 추가

class FloatingOverlay:
    instances = []
    is_exiting = False  # 🚨 [핵심 해결책] 프로그램 전체 종료 중인지를 감지하는 플래그

    def __init__(self, master, content_type="color", data="#c6ffdd"):
        self.master = master
        self.window = tk.Toplevel(master)
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        
        self.transparent_color = "#010101"
        self.window.attributes('-transparentcolor', self.transparent_color)
        self.window.configure(bg=self.transparent_color)
        
        self.anim_frames = []
        self.anim_index = 0
        self.anim_timer_id = None
        
        self.content_type = content_type
        self.current_data = data 
        self.tint_color = None   
        self.original_image = None
        self.original_frames = []
        
        self.current_width = 200
        self.current_height = 200
        self.start_width = 200
        self.start_height = 200
        
        self.label = tk.Label(self.window, bg=self.transparent_color, borderwidth=0)
        self.label.pack()

        # 🚨 [핵심 해결책] 콘텐트 로드 중 save_all_config가 호출되므로, 리스트 등록을 최상단으로 이동!
        FloatingOverlay.instances.append(self)
        
        if content_type == "color":
            self.set_color_box(data)
        else:
            self.load_image(data)
            
        self.label.bind("<Motion>", self.check_mouse_edge)
        self.label.bind("<Button-1>", self.start_move_or_resize)
        self.label.bind("<ButtonRelease-1>", self.stop_move)
        self.label.bind("<B1-Motion>", self.on_move_or_resize)   
        self.label.bind("<Button-3>", self.show_menu)        

        self.window.bind("<Destroy>", self.on_destroy)

    def on_destroy(self, event):
        if event.widget == self.window:
            if self in FloatingOverlay.instances:
                FloatingOverlay.instances.remove(self)
            self.stop_animation()
            
            if not FloatingOverlay.is_exiting:
                save_all_config()
                # 🚨 [해결책] 이 창을 지웠을 때 남은 창이 하나도 없다면(인스턴스 리스트가 비었다면) 프로그램 전체 종료!
                if not FloatingOverlay.instances:
                    exit_program(self.master)

    def check_mouse_edge(self, event):
        margin = 15
        w, h = self.current_width, self.current_height
        x, y = event.x, event.y
        
        mode = ""
        if y < margin: mode += "top"
        elif y >= h - margin: mode += "bottom"
        
        if x < margin: mode += ("_" if mode else "") + "left"
        elif x >= w - margin: mode += ("_" if mode else "") + "right"
        
        cursors = {
            "top_left": "size_nw_se", "bottom_right": "size_nw_se",
            "top_right": "size_ne_sw", "bottom_left": "size_ne_sw",
            "left": "sb_h_double_arrow", "right": "sb_h_double_arrow",
            "top": "sb_v_double_arrow", "bottom": "sb_v_double_arrow"
        }
        self.label.config(cursor=cursors.get(mode, ""))

    def start_move_or_resize(self, event):
        self.start_mouse_x = event.x_root
        self.start_mouse_y = event.y_root
        self.start_width = self.current_width
        self.start_height = self.current_height
        self.start_win_x = self.window.winfo_x()
        self.start_win_y = self.window.winfo_y()
        
        margin = 15
        w, h = self.current_width, self.current_height
        x, y = event.x, event.y
        
        self.resize_mode = ""
        if y < margin: self.resize_mode += "top"
        elif y >= h - margin: self.resize_mode += "bottom"
        
        if x < margin: self.resize_mode += ("_" if self.resize_mode else "") + "left"
        elif x >= w - margin: self.resize_mode += ("_" if self.resize_mode else "") + "right"
        
        if not self.resize_mode:
            self.x = event.x
            self.y = event.y

    def on_move_or_resize(self, event):
        if getattr(self, 'resize_mode', ""):
            dx = event.x_root - self.start_mouse_x
            dy = event.y_root - self.start_mouse_y
            
            new_w = self.start_width
            new_h = self.start_height
            new_x = self.start_win_x
            new_y = self.start_win_y
            
            if "left" in self.resize_mode:
                new_w = self.start_width - dx
                new_x = self.start_win_x + dx
            elif "right" in self.resize_mode:
                new_w = self.start_width + dx
                
            if "top" in self.resize_mode:
                new_h = self.start_height - dy
                new_y = self.start_win_y + dy
            elif "bottom" in self.resize_mode:
                new_h = self.start_height + dy

            if new_w < 10:
                if "left" in self.resize_mode: new_x -= (10 - new_w)
                new_w = 10
            if new_h < 10:
                if "top" in self.resize_mode: new_y -= (10 - new_h)
                new_h = 10

            self.resize_to_pixels(new_w, new_h)
            self.window.geometry(f"+{new_x}+{new_y}")
        else:
            dx = event.x - self.x
            dy = event.y - self.y
            self.window.geometry(f"+{self.window.winfo_x() + dx}+{self.window.winfo_y() + dy}")

    def stop_move(self, event):
        self.x = self.y = None
        self.resize_mode = ""
        save_all_config() 

    def resize_to_pixels(self, w, h):
        if w < 10: w = 10
        if h < 10: h = 10
        self.current_width = w
        self.current_height = h

        try:
            resample_filter = getattr(Image, 'Resampling', Image).LANCZOS

            if self.content_type == "color" and self.original_image:
                resized_img = self.original_image.resize((w, h), resample_filter)
                photo = ImageTk.PhotoImage(resized_img)
                self.label.config(image=photo)
                self.label.image = photo
                self.window.geometry(f"{w}x{h}")

            elif self.content_type == "image" and self.original_frames:
                self.anim_frames = []
                for frame_data in self.original_frames:
                    orig_img = frame_data['img']
                    resized_img = orig_img.resize((w, h), resample_filter)
                    photo = ImageTk.PhotoImage(resized_img)
                    self.anim_frames.append({'photo': photo, 'delay': frame_data['delay']})

                if self.anim_frames:
                    self.window.geometry(f"{w}x{h}")
                    if len(self.anim_frames) == 1:
                        self.label.config(image=self.anim_frames[0]['photo'])
                        self.label.image = self.anim_frames[0]['photo']
        except Exception as e:
            print(f"크기 조절 오류: {e}")

    def restore_original_size(self):
        if self.content_type == "color":
            self.resize_to_pixels(200, 200)
        elif self.content_type == "image" and hasattr(self, 'im'): # 💡 im 객체가 있는지 확인
            # 💡 [해결책] 저장해둔 프레임 리스트 대신, 열려있는 이미지 파일 객체의 크기를 참조합니다.
            self.resize_to_pixels(self.im.width, self.im.height)
        save_all_config()

    def set_color_box(self, color_hex):
        self.stop_animation()
        self.content_type = "color"
        self.current_data = color_hex
        self.original_image = Image.new('RGB', (200, 200), color_hex)
        self.resize_to_pixels(self.current_width, self.current_height)
        save_all_config() 

    # 💡 로드 시 전체 프레임을 저장하지 않고 파일 객체만 유지
    def load_image(self, file_path):
        self.stop_animation()
        self.im = Image.open(file_path) # 파일 객체를 인스턴스 변수로 유지
        self.content_type = "image"
        self.current_data = file_path
        
        # 💡 원본 크기를 바로 할당 (중요!)
        self.current_width = self.im.width
        self.current_height = self.im.height
        self.update_animation()

    # 💡 매번 필요할 때만 Seek()로 꺼내오는 방식
    def update_animation(self):
        try:
            self.im.seek(self.anim_index)
           # 💡 연산 속도를 위해 가장 빠른 필터(NEAREST) 사용 또는 필요 시만 리사이즈
            frame = self.im.convert('RGBA')
            if frame.size != (self.current_width, self.current_height):
                frame = frame.resize((self.current_width, self.current_height), Image.NEAREST)
            
            photo = ImageTk.PhotoImage(frame)
            self.label.config(image=photo)
            self.label.image = photo
            
            # 💡 delay를 가져올 때 0ms인 경우 최소값 보장
            delay = self.im.info.get('duration', 100)
            if delay <= 0: delay = 100 
            
            self.anim_index += 1
            self.anim_timer_id = self.window.after(delay, self.update_animation)
        except EOFError:
            self.anim_index = 0
            self.update_animation()

    def stop_animation(self):
        if self.anim_timer_id:
            self.window.after_cancel(self.anim_timer_id)
            self.anim_timer_id = None

    def show_menu(self, event):
        menu = tk.Menu(self.window, tearoff=0)
        menu.add_command(label="새 컬러 박스 추가", command=lambda: FloatingOverlay(self.master))
        menu.add_command(label="새 그림 추가", command=self.add_new_image)
        menu.add_separator()
        menu.add_command(label="이 창 색상 변경", command=self.change_my_color)
        menu.add_command(label="이 창 투명도 조절", command=self.show_opacity_slider)
        
        size_menu = tk.Menu(menu, tearoff=0)
        size_menu.add_command(label="가로/세로 픽셀 직접 입력", command=self.show_pixel_size_dialog)
        size_menu.add_command(label="원본 크기 및 비율로 복구", command=self.restore_original_size)
        menu.add_cascade(label="이 창 크기 조절", menu=size_menu)
        
        menu.add_separator()
        menu.add_command(label="이 창 지우기", command=self.window.destroy)
        menu.add_command(label="전체 종료", command=lambda: exit_program(self.master)) 
        menu.tk_popup(event.x_root, event.y_root)

    def add_new_image(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.gif;*.webp")])
        if path: FloatingOverlay(self.master, "image", path)

    def change_my_color(self):
        color = colorchooser.askcolor()[1]
        if color: 
            self.apply_color_tint(color)

    def apply_color_tint(self, color_hex):
        try:
            if self.content_type == "color":
                self.original_image = Image.new('RGB', (200, 200), color_hex)
                self.current_data = color_hex
                self.resize_to_pixels(self.current_width, self.current_height)
                
            elif self.content_type == "image" and self.original_frames:
                self.tint_color = color_hex
                for frame_data in self.original_frames:
                    img = frame_data['img']
                    alpha = img.getchannel('A')
                    gray_img = img.convert('L')
                    tinted_img = ImageOps.colorize(gray_img, black="black", white=color_hex).convert('RGBA')
                    tinted_img.putalpha(alpha)
                    frame_data['img'] = tinted_img
                
                self.resize_to_pixels(self.current_width, self.current_height)
            save_all_config() 
        except Exception as e:
            print(f"색상/채도 변환 중 오류 발생: {e}")

    def show_opacity_slider(self):
        slider_win = tk.Toplevel(self.window)
        slider_win.title("투명도")
        slider_win.geometry(f"300x70+{self.window.winfo_pointerx()}+{self.window.winfo_pointery()}")
        slider_win.attributes('-topmost', True)
        
        var = tk.IntVar(value=int(self.window.attributes('-alpha') * 100))
        def update(*args):
            try:
                v = var.get()
                self.window.attributes('-alpha', max(1, min(100, v)) / 100.0)
                save_all_config() 
            except: pass
            
        var.trace_add('write', update)
        f = tk.Frame(slider_win); f.pack(fill='both', expand=True, padx=15, pady=15)
        tk.Scale(f, from_=1, to=100, orient='horizontal', variable=var, showvalue=False).pack(side='left', fill='x', expand=True)
        tk.Entry(f, textvariable=var, width=4).pack(side='left'); tk.Label(f, text="%").pack(side='left')

    def show_pixel_size_dialog(self):
        win = tk.Toplevel(self.window)
        win.title("크기 및 비율 설정")
        win.geometry(f"320x110+{self.window.winfo_pointerx()}+{self.window.winfo_pointery()}")
        win.attributes('-topmost', True)
        
        frame = tk.Frame(win)
        frame.pack(expand=True, fill='both', padx=10, pady=10)

        # 💡 수정된 부분: 이미지 객체(self.im)가 있다면 그 크기를, 없다면 기본값 200을 사용합니다.
        if hasattr(self, 'im') and self.im:
            orig_w, orig_h = self.im.width, self.im.height
        elif self.content_type == "color":
            orig_w, orig_h = 200, 200
        else:
            orig_w, orig_h = 200, 200

        w_var = tk.IntVar(value=self.current_width)
        h_var = tk.IntVar(value=self.current_height)
        current_pct = int((self.current_width / orig_w) * 100)
        p_var = tk.IntVar(value=current_pct)
        
        self.is_updating_dialog = False
        
        def on_w_change(*args):
            if self.is_updating_dialog: return
            self.is_updating_dialog = True
            try:
                w = w_var.get()
                p_var.set(int((w / orig_w) * 100)) 
            except: pass
            self.is_updating_dialog = False

        def on_h_change(*args):
            if self.is_updating_dialog: return
            self.is_updating_dialog = True
            try:
                h = h_var.get()
                p_var.set(int((h / orig_h) * 100)) 
            except: pass
            self.is_updating_dialog = False

        def on_p_change(*args):
            if self.is_updating_dialog: return
            self.is_updating_dialog = True
            try:
                p = p_var.get()
                w_var.set(max(10, int(orig_w * (p / 100))))
                h_var.set(max(10, int(orig_h * (p / 100))))
            except: pass
            self.is_updating_dialog = False

        w_trace = w_var.trace_add('write', on_w_change)
        h_trace = h_var.trace_add('write', on_h_change)
        p_trace = p_var.trace_add('write', on_p_change)
        
        tk.Label(frame, text="가로(W):").grid(row=0, column=0, padx=2, pady=5)
        tk.Entry(frame, textvariable=w_var, width=5, justify='center').grid(row=0, column=1, padx=2, pady=5)
        
        tk.Label(frame, text="세로(H):").grid(row=0, column=2, padx=4, pady=5)
        tk.Entry(frame, textvariable=h_var, width=5, justify='center').grid(row=0, column=3, padx=2, pady=5)
        
        tk.Label(frame, text="비율(%):").grid(row=0, column=4, padx=4, pady=5)
        tk.Entry(frame, textvariable=p_var, width=4, justify='center').grid(row=0, column=5, padx=2, pady=5)
        
        def apply_size():
            try:
                w = w_var.get()
                h = h_var.get()
                self.resize_to_pixels(w, h)
                save_all_config()
            except tk.TclError:
                pass
                
        tk.Button(frame, text="크기 및 비율 최종 적용", command=apply_size, bg="#c6ffdd").grid(row=1, column=0, columnspan=6, pady=10, sticky="we")

    def start_move(self, event):
        self.x, self.y = event.x, event.y
        
    def on_move(self, event):
        dx, dy = event.x - self.x, event.y - self.y
        self.window.geometry(f"+{self.window.winfo_x() + dx}+{self.window.winfo_y() + dy}")

# =========================================================================
# 전역 헬퍼 구조
# =========================================================================

# 🚨 [새로 추가할 토글 시스템]
is_topmost = True
was_pressed = False

def check_hotkey(master):
    global is_topmost, was_pressed
    try:
        # 💡 'f4' 자리에 원하는 키(예: 'f8', 'ctrl+shift+a' 등)를 넣으시면 됩니다.
        if keyboard.is_pressed('f8'):
            if not was_pressed: # 키를 꾹 누르고 있을 때 여러 번 토글되는 것 방지
                was_pressed = True
                is_topmost = not is_topmost
                
                for instance in FloatingOverlay.instances:
                    if instance.window.winfo_exists():
                        instance.window.attributes('-topmost', is_topmost)
                        if not is_topmost:
                            instance.window.lower() # 다른 창들 뒤로 보내기
                        else:
                            instance.window.lift()  # 다시 맨 앞으로 끌어오기
        else:
            was_pressed = False
    except Exception:
        pass
        
    # 50ms 마다 키 눌림을 백그라운드에서 안전하게 감지 (Tkinter 충돌 완벽 제어)
    master.after(50, lambda: check_hotkey(master))

def save_all_config():
    config_data = []
    for instance in FloatingOverlay.instances:
        try:
            if instance.window.winfo_exists():
                config_data.append({
                    "content_type": instance.content_type,
                    "data": instance.current_data,
                    "width": instance.current_width,
                    "height": instance.current_height,
                    "x": instance.window.winfo_x(),
                    "y": instance.window.winfo_y(),
                    "alpha": instance.window.attributes('-alpha'),
                    "tint_color": getattr(instance, 'tint_color', None)
                })
        except Exception:
            pass
    with open("overlay_config.json", "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=4)

def load_all_config(master):
    config_file = "overlay_config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            if config_data:
                for item in config_data:
                    # 🚨 캡처된 데이터를 기반으로 먼저 인스턴스를 빈 껍데기로 생성한 뒤 수치 강제 주입
                    overlay = FloatingOverlay(
                        master, 
                        content_type=item["content_type"], 
                        data=item["data"]
                    )
                    if item.get("tint_color") and item["content_type"] == "image":
                        overlay.apply_color_tint(item["tint_color"])
                    
                    overlay.resize_to_pixels(item["width"], item["height"])
                    overlay.window.geometry(f"+{item['x']}+{item['y']}")
                    overlay.window.attributes('-alpha', item["alpha"])
                return
        except Exception as e:
            print(f"설정 로드 실패: {e}")
            
    FloatingOverlay(master)

def exit_program(master):
    # 🚨 [핵심 해결책] 전체 종료 플래그를 먼저 활성화하여 창이 파괴될 때 빈 저장이 일어나는 연쇄 반응을 차단합니다.
    FloatingOverlay.is_exiting = True
    save_all_config()
    master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw() 
    load_all_config(root)
    check_hotkey(root) # 🚨 메인 루프가 돌기 직전에 단축키 감지 시스템 가동!
    root.mainloop()