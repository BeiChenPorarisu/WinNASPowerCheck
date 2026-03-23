import tkinter as tk
from tkinter import font, messagebox, ttk
import threading
import subprocess
import time
import sys
import os
import json
from PIL import Image, ImageDraw, ImageTk

# 尝试导入系统托盘图标库，如果未安装则优雅降级
try:
    import pystray
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("提示：未安装 pystray，系统托盘功能不可用。如需使用，请执行：pip install pystray pillow")

# ------------------ 默认配置字典 ------------------
# 所有配置项的默认值，当配置文件缺失或损坏时作为后备
DEFAULT_CONFIG = {
    "target_ip": "192.168.1.1",        # 监控目标IP（通常是路由器网关）
    "ping_interval": 60,               # 正常状态下的ping间隔（秒）
    "countdown_seconds": 180,          # 停电后倒计时时长（秒），即允许断电的最大时间
    "probe_seconds": 30,               # 静默期时长（秒），此期间不显示窗口，仅后台高频检测
    "power_action": "hibernate",       # 倒计时结束后执行的操作：休眠/关机/睡眠
    "font_family": "Microsoft YaHei",  # 界面字体
    "dark_mode": True,                 # 是否使用深色主题
    "probe_ping_interval": 5,          # 静默期ping频率（秒），需更快检测网络是否恢复
    "alert_ping_interval": 1           # 警告期ping频率（秒），接近关机时最高频检测
}

class SettingsWindow:
    """
    设置对话框窗口类
    
    提供图形化界面修改配置参数，包括网络设置、时间参数、电源操作等。
    修改后需重启程序以确保所有更改生效（主要是UI主题和字体）。
    """
    
    def __init__(self, parent, config, save_callback, script_path):
        """
        初始化设置窗口
        
        Args:
            parent: 父窗口对象（PowerMonitor的主窗口）
            config: 当前配置字典
            save_callback: 保存配置的回调函数（来自PowerMonitor.apply_config）
            script_path: 当前脚本路径，用于重启功能
        """
        self.parent = parent
        self.config = config.copy()       # 复制配置，避免直接修改原配置
        self.save_callback = save_callback
        self.script_path = script_path

        # 创建模态对话框窗口
        self.window = tk.Toplevel(parent)
        self.window.title("设置")
        self.window.geometry("470x520")
        self.window.resizable(False, False)
        self.window.configure(bg="#2d2d2d" if self.config["dark_mode"] else "#f0f0f0")
        self.window.transient(parent)     # 设置为父窗口的附属窗口
        self.window.grab_set()            # 模态：阻止与主窗口交互直到关闭

        # 继承父窗口图标
        if hasattr(parent, 'window_icon') and parent.window_icon:
            self.window.iconphoto(True, parent.window_icon)

        self.center_window_relative_to_parent()

        # 字体定义
        label_font = font.Font(family="Microsoft YaHei", size=10)
        entry_font = font.Font(family="Microsoft YaHei", size=10)

        # ------------------ 表单布局 ------------------
        row = 0
        # 目标IP设置
        tk.Label(self.window, text="路由器 IP:", bg=self.window.cget("bg"), 
                fg="white" if self.config["dark_mode"] else "black", 
                font=label_font).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        self.ip_var = tk.StringVar(value=self.config["target_ip"])
        tk.Entry(self.window, textvariable=self.ip_var, font=entry_font, width=20).grid(row=row, column=1, padx=10, pady=5)

        # 正常检测间隔
        row += 1
        tk.Label(self.window, text="正常 Ping 间隔 (秒):", bg=self.window.cget("bg"), 
                fg="white" if self.config["dark_mode"] else "black", 
                font=label_font).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        self.interval_var = tk.IntVar(value=self.config["ping_interval"])
        tk.Entry(self.window, textvariable=self.interval_var, font=entry_font, width=10).grid(row=row, column=1, sticky="w", padx=10, pady=5)

        # 静默期检测频率（网络刚断开时的快速确认期）
        row += 1
        tk.Label(self.window, text="静默期 Ping 频率 (秒):", bg=self.window.cget("bg"), 
                fg="white" if self.config["dark_mode"] else "black", 
                font=label_font).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        self.probe_ping_var = tk.IntVar(value=self.config["probe_ping_interval"])
        tk.Entry(self.window, textvariable=self.probe_ping_var, font=entry_font, width=10).grid(row=row, column=1, sticky="w", padx=10, pady=5)

        # 警告期检测频率（即将执行操作前的密集检测期）
        row += 1
        tk.Label(self.window, text="警告期 Ping 频率 (秒):", bg=self.window.cget("bg"), 
                fg="white" if self.config["dark_mode"] else "black", 
                font=label_font).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        self.alert_ping_var = tk.IntVar(value=self.config["alert_ping_interval"])
        tk.Entry(self.window, textvariable=self.alert_ping_var, font=entry_font, width=10).grid(row=row, column=1, sticky="w", padx=10, pady=5)

        # 倒计时总时长（从断网到执行操作的总宽限时间）
        row += 1
        tk.Label(self.window, text="倒计时总时长 (秒):", bg=self.window.cget("bg"), 
                fg="white" if self.config["dark_mode"] else "black", 
                font=label_font).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        self.countdown_var = tk.IntVar(value=self.config["countdown_seconds"])
        tk.Entry(self.window, textvariable=self.countdown_var, font=entry_font, width=10).grid(row=row, column=1, sticky="w", padx=10, pady=5)

        # 静默期单独时长（倒计时开始前的不提醒阶段）
        row += 1
        tk.Label(self.window, text="静默期时长 (秒):", bg=self.window.cget("bg"), 
                fg="white" if self.config["dark_mode"] else "black", 
                font=label_font).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        self.probe_var = tk.IntVar(value=self.config["probe_seconds"])
        probe_entry = tk.Entry(self.window, textvariable=self.probe_var, font=entry_font, width=10)
        probe_entry.grid(row=row, column=1, sticky="w", padx=10, pady=5)
        
        # 电源操作类型选择
        row += 1
        tk.Label(self.window, text="倒计时结束操作:", bg=self.window.cget("bg"), 
                fg="white" if self.config["dark_mode"] else "black", 
                font=label_font).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        action_frame = tk.Frame(self.window, bg=self.window.cget("bg"))
        action_frame.grid(row=row, column=1, columnspan=2, sticky="w", padx=10, pady=5)
        self.action_var = tk.StringVar(value=self.config["power_action"])
        tk.Radiobutton(action_frame, text="休眠", variable=self.action_var, value="hibernate",
               bg=self.window.cget("bg"), fg="white" if self.config["dark_mode"] else "black",
               selectcolor=self.window.cget("bg"), font=label_font).pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(action_frame, text="关机", variable=self.action_var, value="shutdown",
               bg=self.window.cget("bg"), fg="white" if self.config["dark_mode"] else "black",
               selectcolor=self.window.cget("bg"), font=label_font).pack(side=tk.LEFT, padx=5)
        
        # 字体选择
        row += 1
        tk.Label(self.window, text="字体名称:", bg=self.window.cget("bg"), 
                fg="white" if self.config["dark_mode"] else "black", 
                font=label_font).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        self.font_var = tk.StringVar(value=self.config["font_family"])
        common_fonts = ["Microsoft YaHei", "SimHei", "Arial", "Tahoma", "宋体"]
        self.font_combo = ttk.Combobox(self.window, textvariable=self.font_var, values=common_fonts, width=18)
        self.font_combo.grid(row=row, column=1, padx=10, pady=5)

        # 主题切换
        row += 1
        self.dark_mode_var = tk.BooleanVar(value=self.config["dark_mode"])
        tk.Checkbutton(self.window, text="暗黑模式", variable=self.dark_mode_var, 
                      bg=self.window.cget("bg"), fg="white" if self.config["dark_mode"] else "black", 
                      selectcolor=self.window.cget("bg"), font=label_font).grid(row=row, column=0, columnspan=2, pady=10)

        # 操作按钮
        row += 1
        button_frame = tk.Frame(self.window, bg=self.window.cget("bg"))
        button_frame.grid(row=row, column=0, columnspan=3, pady=20)
        tk.Button(button_frame, text="保存", command=self.save, width=10).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="取消", command=self.window.destroy, width=10).pack(side=tk.LEFT, padx=10)

    def center_window_relative_to_parent(self):
        """将设置窗口居中显示在父窗口之上"""
        self.window.update_idletasks()
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        width = self.window.winfo_width()
        height = self.window.winfo_height()
        x = parent_x + (parent_width - width) // 2
        y = parent_y + (parent_height - height) // 2
        self.window.geometry(f"+{x}+{y}")

    def save(self):
        """
        保存设置并验证输入有效性
        
        验证规则：
        - Ping频率必须大于0（避免除零错误）
        - IP地址不能为空
        - 时间间隔必须为正整数
        """
        # 验证ping频率有效性
        probe_ping = self.probe_ping_var.get()
        alert_ping = self.alert_ping_var.get()
        if probe_ping <= 0 or alert_ping <= 0:
            messagebox.showerror("错误", "Ping 频率必须大于0")
            return

        # 构建新配置字典
        new_config = {
            "target_ip": self.ip_var.get().strip(),
            "ping_interval": self.interval_var.get(),
            "probe_ping_interval": probe_ping,
            "alert_ping_interval": alert_ping,
            "countdown_seconds": self.countdown_var.get(),
            "probe_seconds": self.probe_var.get(),
            "power_action": self.action_var.get(),
            "font_family": self.font_var.get(),
            "dark_mode": self.dark_mode_var.get()
        }
        
        # 基础验证
        if not new_config["target_ip"]:
            messagebox.showerror("错误", "IP地址不能为空")
            return
        if new_config["ping_interval"] < 1:
            messagebox.showerror("错误", "正常 Ping 间隔必须大于0")
            return
        if new_config["countdown_seconds"] < 1:
            messagebox.showerror("错误", "倒计时必须大于0")
            return

        # 保存并提示重启
        self.save_callback(new_config)
        self.window.destroy()
        if messagebox.askyesno("重启提示", "部分设置需要重启程序才能完全生效。\n是否立即重启？"):
            self.restart_program()

    def restart_program(self):
        """通过os.execl实现程序自重启（保留命令行参数）"""
        try:
            python = sys.executable
            os.execl(python, python, self.script_path)
        except Exception as e:
            messagebox.showerror("重启失败", f"无法自动重启程序：{e}\n请手动重新运行程序。")

class PowerMonitor:
    """
    停电监控主类
    
    核心功能逻辑：
    1. 后台线程持续ping路由器，检测网络连通性
    2. 状态流转：
       正常状态 → 断网进入静默期 → 静默期结束进入警告期 → 倒计时结束执行操作
          ↑                                     |
          └──────────  网络恢复  ←───────────────┘
    
    静默期：断网初期，窗口隐藏，托盘图标黄色闪烁，高频检测网络是否快速恢复（避免短暂波动触发关机）
    警告期：静默期结束后，窗口强制置顶显示，托盘图标红色闪烁，执行最终倒计时
    """
    
    def __init__(self):
        """初始化监控器：加载配置、构建UI、启动后台线程"""
        # 记录脚本路径用于重启功能
        self.script_path = os.path.abspath(__file__)

        # 加载或创建配置文件
        self.config_file = os.path.join(os.path.dirname(__file__), "config.json")
        self.load_config()

        # 从配置初始化实例变量
        self.target_ip = self.config["target_ip"]
        self.normal_ping_interval = self.config["ping_interval"]  # 正常间隔基准值
        self.ping_interval = self.normal_ping_interval             # 当前动态间隔（会根据状态改变）
        self.countdown_seconds = self.config["countdown_seconds"]
        self.probe_seconds = self.config["probe_seconds"]
        self.power_action = self.config["power_action"]
        self.font_family = self.config["font_family"]
        self.dark_mode = self.config["dark_mode"]
        self.probe_ping_interval = self.config["probe_ping_interval"]
        self.alert_ping_interval = self.config["alert_ping_interval"]

        # 运行时状态变量
        self.remaining = self.countdown_seconds      # 倒计时剩余秒数
        self.probe_remaining = self.probe_seconds    # 静默期剩余秒数
        self.power_outage = False                    # 是否处于停电（断网）状态
        self.is_in_probe = False                     # 是否处于静默期（True=静默期，False=警告期或正常）
        self.paused = False                          # 倒计时是否被用户暂停
        self.last_ping_success = True                # 上一次ping结果（用于状态转换判断）
        self.lock = threading.Lock()                 # 保护ping间隔变量的线程锁
        self.running = True                          # 控制后台线程生命周期

        # 设置颜色主题（根据dark_mode）
        self.set_theme_colors()

        # ------------------ 构建主窗口UI ------------------
        self.window = tk.Tk()
        self.window.title("停电监控")
        self.window.geometry("620x230")
        self.window.configure(bg=self.bg_color)
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.window.withdraw()  # 初始隐藏，等待需要时显示

        # 创建窗口图标（电源符号样式）
        self.window_icon = self.create_window_icon()
        if self.window_icon:
            self.window.iconphoto(True, self.window_icon)

        # 字体定义
        self.label_font = font.Font(family=self.font_family, size=12, weight="normal")
        self.countdown_font = font.Font(family=self.font_family, size=24, weight="bold")

        # 状态标签：显示当前是正常、静默检测还是停电警告
        self.warning_label = tk.Label(
            self.window,
            text="✅ 系统正常：路由已连接 ✅",
            fg=self.normal_fg,
            bg=self.bg_color,
            font=self.label_font
        )
        self.warning_label.pack(pady=10)

        # 倒计时显示（大字体）
        self.countdown_label = tk.Label(
            self.window,
            text="",
            fg=self.fg_color,
            bg=self.bg_color,
            font=self.countdown_font
        )
        self.countdown_label.pack(pady=10)

        # Ping结果状态显示（调试用/状态确认）
        self.ping_result_label = tk.Label(
            self.window,
            text="",
            fg=self.fg_color,
            bg=self.bg_color,
            font=self.label_font
        )
        self.ping_result_label.pack(pady=5)

        # 按钮工具栏
        button_frame = tk.Frame(self.window, bg=self.bg_color)
        button_frame.pack(pady=10)

        self.settings_button = tk.Button(
            button_frame, text="设置", bg=self.button_bg, fg=self.fg_color,
            activebackground=self.button_active_bg, relief=tk.FLAT, width=10,
            font=self.label_font, command=self.open_settings
        )
        self.settings_button.pack(side=tk.LEFT, padx=5)

        # 暂停/恢复按钮（仅在停电状态有效）
        self.pause_resume_button = tk.Button(
            button_frame, text="暂停倒计时", bg=self.button_bg, fg=self.fg_color,
            activebackground=self.button_active_bg, relief=tk.FLAT, width=10,
            font=self.label_font, command=self.toggle_pause
        )
        self.pause_resume_button.pack(side=tk.LEFT, padx=5)

        self.reset_button = tk.Button(
            button_frame, text="重置倒计时", bg=self.button_bg, fg=self.fg_color,
            activebackground=self.button_active_bg, relief=tk.FLAT, width=10,
            font=self.label_font, command=self.reset_countdown
        )
        self.reset_button.pack(side=tk.LEFT, padx=5)

        # 立即执行操作按钮（关机/休眠）
        self.hibernate_button = tk.Button(
            button_frame, text="立即休眠", bg=self.button_bg, fg=self.fg_color,
            activebackground=self.button_active_bg, relief=tk.FLAT, width=10,
            font=self.label_font, command=self.force_action
        )
        self.hibernate_button.pack(side=tk.LEFT, padx=5)
        self.update_action_button_text()  # 根据配置设置按钮文字

        # ------------------ 启动后台线程 ------------------
        # 后台ping线程：独立于UI线程，避免界面卡顿
        self.ping_thread = threading.Thread(target=self.ping_loop, daemon=True)
        self.ping_thread.start()

        # ------------------ 系统托盘初始化 ------------------
        self.tray_icon = None
        self.icon_normal = None      # 正常状态图标（灰色）
        self.icon_probe = None       # 静默期图标（黄色）
        self.icon_alert = None       # 警告期图标（红色）
        self.blink_timer = None      # 闪烁定时器引用
        self.blink_state = False     # 闪烁状态标记（True=显示警告色，False=显示正常色）
        
        if TRAY_AVAILABLE:
            self.create_icons()
            self.setup_tray_icon()

        # ------------------ 启动主循环 ------------------
        # 使用after机制实现每秒一次的UI更新（替代time.sleep避免阻塞）
        self.after_id = self.window.after(1000, self.periodic_check)
        self.window.mainloop()

    # ----------------------------------------------------------
    # 主题与界面配置区域
    # ----------------------------------------------------------
    def set_theme_colors(self):
        """
        根据dark_mode设置配色方案
        
        定义：
        - bg_color: 背景色
        - fg_color: 前景（文字）色
        - button_bg: 按钮背景
        - warning_fg: 警告状态文字色（红）
        - normal_fg: 正常状态文字色（绿）
        """
        if self.dark_mode:
            self.bg_color = "#2d2d2d"
            self.fg_color = "#ffffff"
            self.button_bg = "#3c3c3c"
            self.button_active_bg = "#5a5a5a"
            self.warning_fg = "#ff6666"  # 柔和红
            self.normal_fg = "#66ff66"   # 柔和绿
        else:
            self.bg_color = "#f0f0f0"
            self.fg_color = "#000000"
            self.button_bg = "#e0e0e0"
            self.button_active_bg = "#c0c0c0"
            self.warning_fg = "#ff0000"  # 标准红
            self.normal_fg = "#00aa00"   # 标准绿

    def create_window_icon(self):
        """
        动态生成应用图标（电源符号样式）
        
        使用PIL绘制简单几何图形：
        - 外圈：圆形边框
        - 内杠：垂直线（象征电源符号）
        """
        size = 24
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((3, 3, size-3, size-3), outline='#cccccc', width=1)
        draw.rectangle((size//2-1, size//4, size//2+1, size*3//4), fill='#cccccc')
        return ImageTk.PhotoImage(img)

    def center_window(self):
        """将窗口居中显示于屏幕"""
        self.window.update_idletasks()
        w = self.window.winfo_width()
        h = self.window.winfo_height()
        x = (self.window.winfo_screenwidth() - w) // 2
        y = (self.window.winfo_screenheight() - h) // 2
        self.window.geometry(f"+{x}+{y}")

    # ----------------------------------------------------------
    # 配置管理区域
    # ----------------------------------------------------------
    def load_config(self):
        """
        从JSON文件加载配置，若不存在或损坏则使用默认配置
        
        兼容机制：如果配置文件中缺少某些字段（新版本新增），自动使用默认值补全
        """
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                # 补全缺失字段（向后兼容）
                for key, value in DEFAULT_CONFIG.items():
                    if key not in self.config:
                        self.config[key] = value
                self.save_config()  # 写回补全后的配置
            except:
                self.config = DEFAULT_CONFIG.copy()
        else:
            self.config = DEFAULT_CONFIG.copy()
            self.save_config()

    def save_config(self):
        """将当前配置保存到JSON文件（utf-8编码支持中文）"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except:
            pass

    def apply_config(self, new_config):
        """
        应用新配置（由SettingsWindow回调调用）
        
        区分即时生效项和需重启项：
        - 即时：字体、主题、电源操作类型
        - 需重启：ping间隔（因后台线程已在运行）
        """
        self.config.update(new_config)
        self.save_config()
        
        # 即时生效：字体变更
        if self.font_family != new_config["font_family"]:
            self.font_family = new_config["font_family"]
            self.refresh_fonts()
        
        # 即时生效：主题变更
        if self.dark_mode != new_config["dark_mode"]:
            self.dark_mode = new_config["dark_mode"]
            self.set_theme_colors()
            self.refresh_theme()
        
        # 即时生效：电源操作类型（仅影响按钮文字和最终执行的操作）
        if "power_action" in new_config and new_config["power_action"] != self.power_action:
            self.power_action = new_config["power_action"]
            self.update_action_button_text()

    def refresh_fonts(self):
        """重新应用字体到所有UI组件"""
        self.label_font.config(family=self.font_family)
        self.countdown_font.config(family=self.font_family)
        for widget in [self.warning_label, self.countdown_label, self.ping_result_label,
                       self.settings_button, self.pause_resume_button,
                       self.reset_button, self.hibernate_button]:
            widget.config(font=self.label_font if widget != self.countdown_label else self.countdown_font)

    def refresh_theme(self):
        """重新应用颜色主题到所有UI组件"""
        self.window.configure(bg=self.bg_color)
        self.warning_label.config(bg=self.bg_color, fg=self.normal_fg if not self.power_outage else self.warning_fg)
        self.countdown_label.config(bg=self.bg_color, fg=self.fg_color)
        self.ping_result_label.config(bg=self.bg_color, fg=self.fg_color)
        for btn in [self.settings_button, self.pause_resume_button, self.reset_button, self.hibernate_button]:
            btn.config(bg=self.button_bg, fg=self.fg_color, activebackground=self.button_active_bg)

    def open_settings(self):
        """打开设置对话框"""
        SettingsWindow(self.window, self.config, self.apply_config, self.script_path)

    # ----------------------------------------------------------
    # 系统托盘图标区域
    # ----------------------------------------------------------
    def create_icons(self):
        """
        创建三种状态的托盘图标（使用PIL动态绘制）
        
        图标状态对应：
        - 正常：灰色电源符号（常亮）
        - 静默期：黄色电源符号（闪烁）
        - 警告期：红色电源符号（闪烁）
        """
        size = 24
        # 正常状态：浅灰色
        img_normal = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img_normal)
        draw.ellipse((3, 3, size-3, size-3), outline='#cccccc', width=1)
        draw.rectangle((size//2-1, size//4, size//2+1, size*3//4), fill='#cccccc')
        self.icon_normal = img_normal

        # 静默期：黄色（表示警告但暂不操作）
        img_probe = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img_probe)
        draw.ellipse((3, 3, size-3, size-3), outline='#ffcc00', width=1)
        draw.rectangle((size//2-1, size//4, size//2+1, size*3//4), fill='#ffcc00')
        self.icon_probe = img_probe

        # 警告期：红色（即将执行操作）
        img_alert = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img_alert)
        draw.ellipse((3, 3, size-3, size-3), outline='#ff6666', width=1)
        draw.rectangle((size//2-1, size//4, size//2+1, size*3//4), fill='#ff6666')
        self.icon_alert = img_alert

    def setup_tray_icon(self):
        """在独立线程中启动系统托盘图标"""
        self.tray_icon = pystray.Icon(
            "power_monitor",
            self.icon_normal,
            "停电监控",
            menu=pystray.Menu(
                pystray.MenuItem("显示窗口", self.on_tray_show_window),
                pystray.MenuItem("退出", self.on_tray_quit)
            )
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def start_blink(self):
        """
        启动托盘图标闪烁
        
        闪烁逻辑：每0.5秒在正常图标和警告图标间切换，吸引用户注意
        静默期使用黄色图标，警告期使用红色图标
        """
        if self.blink_timer is not None:
            return
        self.blink_state = False
        self._blink_loop()

    def _blink_loop(self):
        """闪烁定时器回调（递归调用实现循环）"""
        if not self.power_outage:
            self.blink_timer = None
            return
        
        # 根据当前阶段选择图标颜色
        icon = self.icon_probe if self.is_in_probe else self.icon_alert
        
        # 切换显示状态
        if self.blink_state:
            self.tray_icon.icon = self.icon_normal
        else:
            self.tray_icon.icon = icon
        
        self.blink_state = not self.blink_state
        self.blink_timer = threading.Timer(0.5, self._blink_loop)
        self.blink_timer.daemon = True
        self.blink_timer.start()

    def stop_blink(self):
        """停止闪烁，恢复常态图标"""
        if self.blink_timer is not None:
            self.blink_timer.cancel()
            self.blink_timer = None
        if self.tray_icon:
            self.tray_icon.icon = self.icon_normal

    def on_tray_show_window(self, icon=None, item=None):
        """托盘菜单：显示主窗口（通过after确保线程安全）"""
        self.window.after(0, self.show_window_from_tray)

    def show_window_from_tray(self):
        """从托盘恢复窗口显示"""
        if not self.window.winfo_viewable():
            self.window.deiconify()
            self.center_window()
            if not self.power_outage:
                self.window.attributes('-topmost', False)
        else:
            self.window.lift()
            self.window.focus_force()
        self.update_warning_label()

    def on_tray_quit(self, icon=None, item=None):
        """托盘菜单：彻底退出程序"""
        self.running = False
        if self.tray_icon:
            self.tray_icon.stop()
        self.window.quit()
        sys.exit(0)

    # ----------------------------------------------------------
    # 后台网络检测区域
    # ----------------------------------------------------------
    def ping_loop(self):
        """
        后台线程主循环：持续ping目标IP
        
        特点：
        - 使用独立线程，避免阻塞UI
        - 根据当前状态动态调整ping间隔（通过self.ping_interval）
        - 结果存入self.last_ping_success供主线程查询
        """
        while self.running:
            with self.lock:
                interval = self.ping_interval
            success = self.ping_host()
            with self.lock:
                self.last_ping_success = success
            time.sleep(interval)

    def ping_host(self):
        """
        执行一次ping命令
        
        Windows平台优化：
        - 使用STARTUPINFO隐藏控制台窗口
        - 使用creationflags防止弹出CMD窗口
        - 超时设置为1秒（-w 1000）
        
        Returns:
            bool: True=ping成功，False=失败或异常
        """
        try:
            if sys.platform == "win32":
                # Windows隐藏控制台窗口
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = 0x08000000  # CREATE_NO_WINDOW
            else:
                startupinfo = None
                creationflags = 0
            
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "1000", self.target_ip],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            return result.returncode == 0
        except:
            return False

    # ----------------------------------------------------------
    # 核心逻辑：状态机与倒计时控制
    # ----------------------------------------------------------
    def periodic_check(self):
        """
        主定时器回调（每秒执行一次）
        
        这是整个程序的状态机核心，处理：
        1. 网络状态转换（正常↔断网）
        2. 静默期→警告期转换
        3. 倒计时递减
        4. 触发最终操作
        5. UI更新
        """
        with self.lock:
            ping_success = self.last_ping_success

        # ===== 状态转换判断 =====
        if not ping_success and not self.power_outage:
            # 场景1：检测到断网，开始停电处理流程
            self.start_power_outage()
        elif ping_success and self.power_outage:
            # 场景2：网络恢复，取消停电状态
            self.end_power_outage()
        elif not ping_success and self.power_outage:
            # 场景3：持续断网，维持当前状态（静默期或警告期）
            pass

        # ===== 倒计时处理（仅在断网且未暂停时） =====
        if self.power_outage and not self.paused:
            if self.remaining > 0:
                self.remaining -= 1
                
                # 静默期倒计时处理
                if self.is_in_probe and self.probe_remaining > 0:
                    self.probe_remaining -= 1
                    if self.probe_remaining <= 0:
                        self.exit_probe()  # 静默期结束，进入警告期
                
                # 倒计时归零，执行操作
                if self.remaining <= 0:
                    self.perform_action()

        # ===== UI刷新 =====
        self.update_countdown_display()
        
        # 注册下一次定时器（实现循环）
        self.after_id = self.window.after(1000, self.periodic_check)

    def start_power_outage(self):
        """
        进入停电（断网）状态：初始化倒计时流程
        
        状态初始化：
        - 设置停电标记为True
        - 进入静默期（is_in_probe=True）
        - 重置倒计时和静默期计数器
        - 提高ping频率（静默期频率）
        - 窗口保持隐藏（静默期特点）
        - 启动托盘图标闪烁（黄色）
        """
        if self.power_outage:
            return
        
        self.power_outage = True
        self.is_in_probe = True
        self.remaining = self.countdown_seconds
        self.probe_remaining = self.probe_seconds
        self.paused = False
        
        # 切换到静默期高频检测模式
        with self.lock:
            self.ping_interval = self.probe_ping_interval
        
        # 静默期不显示窗口，避免打扰（可能是短暂波动）
        self.window.withdraw()
        self.pause_resume_button.config(text="暂停倒计时")
        self.update_warning_label()
        
        # 托盘提示：黄色闪烁
        if TRAY_AVAILABLE:
            self.start_blink()

    def exit_probe(self):
        """
        静默期结束，进入警告期
        
        关键动作：
        1. 切换状态标记 is_in_probe = False
        2. 进一步提高ping频率（警告期频率）
        3. 强制显示窗口并置顶（用户必须看到）
        4. 托盘图标自动切换为红色闪烁（由_blink_loop处理）
        """
        self.is_in_probe = False
        
        # 切换到最高频检测（争取在最后时刻检测到恢复）
        with self.lock:
            self.ping_interval = self.alert_ping_interval
        
        # 强制用户关注：显示窗口并置顶
        self.window.deiconify()
        self.center_window()
        self.window.attributes('-topmost', True)
        self.update_warning_label()

    def end_power_outage(self):
        """
        网络恢复：取消所有停电状态，恢复正常监控
        
        清理动作：
        - 重置所有状态标记
        - 恢复正常的ping间隔
        - 隐藏窗口（如果已显示）
        - 停止托盘闪烁
        """
        if not self.power_outage:
            return
        
        self.power_outage = False
        self.is_in_probe = False
        self.paused = False
        
        # 恢复正常检测频率
        with self.lock:
            self.ping_interval = self.normal_ping_interval
        
        self.window.withdraw()
        self.update_warning_label()
        
        if TRAY_AVAILABLE:
            self.stop_blink()

    def update_warning_label(self):
        """
        根据当前状态更新顶部警告标签的文本和颜色
        
        状态对应文本：
        - 正常："✅ 系统正常：路由已连接 ✅"（绿色）
        - 静默期："⚠ 网络中断检测中... ⚠"（红色）
        - 警告期："⚠ 停电警告：电脑即将休眠/关机 ⚠"（红色）
        """
        if self.power_outage:
            if self.is_in_probe:
                # 静默期：窗口通常隐藏，但若用户手动打开则显示检测中提示
                if self.window.winfo_viewable():
                    self.warning_label.config(
                        text="⚠ 网络中断检测中... ⚠",
                        fg=self.warning_fg
                    )
                else:
                    # 窗口隐藏时显示正常文本（实际用户看不到，保持状态一致）
                    self.warning_label.config(
                        text="✅ 系统正常：路由已连接 ✅",
                        fg=self.normal_fg
                    )
            else:
                # 警告期：根据操作类型显示不同警告
                if self.power_action == "shutdown":
                    self.warning_label.config(
                        text="⚠ 停电警告：电脑即将关机 ⚠",
                        fg=self.warning_fg
                    )
                else:
                    self.warning_label.config(
                        text="⚠ 停电警告：电脑即将休眠 ⚠",
                        fg=self.warning_fg
                    )
        else:
            # 正常状态
            self.warning_label.config(
                text="✅ 系统正常：路由已连接 ✅",
                fg=self.normal_fg
            )

    def toggle_pause(self):
        """
        切换倒计时暂停状态（仅在停电状态有效）
        
        用户可在警告期点击暂停以获得更多处理时间，
        网络恢复后会自动解除暂停。
        """
        if not self.power_outage:
            return
        self.paused = not self.paused
        self.pause_resume_button.config(text="恢复倒计时" if self.paused else "暂停倒计时")

    def reset_countdown(self):
        """
        重置倒计时（仅在停电状态有效）
        
        将倒计时恢复到初始值，静默期也一并重置。
        用于用户需要时间处理但不想暂停倒计时的情况。
        """
        if not self.power_outage:
            return
        self.remaining = self.countdown_seconds
        if self.is_in_probe:
            self.probe_remaining = self.probe_seconds
        if self.paused:
            self.paused = False
            self.pause_resume_button.config(text="暂停倒计时")
        self.update_countdown_display()

    def force_action(self):
        """立即执行电源操作（用户手动触发）"""
        self.perform_action()

    def perform_action(self):
        """
        执行最终的电源操作（休眠/关机/睡眠）
        
        执行逻辑：
        1. 先隐藏窗口（避免阻碍关机流程）
        2. 根据power_action执行对应Windows命令
           - hibernate: rundll32休眠（参数0,1,0）
           - shutdown: 立即关机（/s /t 0）
           - sleep: 睡眠模式（参数0,1,1）
        3. 清理并退出程序
        
        注意：使用rundll32调用powrprof.dll是Windows标准API调用方式
        """
        self.window.withdraw()
        try:
            if self.power_action == "hibernate":
                # 参数说明：SetSuspendState(Hibernate, ForceCritical, DisableWakeEvent)
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            elif self.power_action == "shutdown":
                os.system("shutdown /s /t 0")
            elif self.power_action == "sleep":
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,1")
            else:
                # 默认休眠（后备方案）
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        except Exception as e:
            print(f"执行操作失败: {e}")
        
        # 清理资源并退出
        self.running = False
        if self.tray_icon:
            self.tray_icon.stop()
        self.window.quit()
        sys.exit(0)

    def update_countdown_display(self):
        """更新倒计时标签和ping状态显示（格式：MM:SS）"""
        minutes = self.remaining // 60
        seconds = self.remaining % 60
        self.countdown_label.config(text=f"{minutes:02d}:{seconds:02d}")
        
        with self.lock:
            ping_status = "成功" if self.last_ping_success else "失败"
        self.ping_result_label.config(text=f"最新 ping 结果: {ping_status}")

    def on_closing(self):
        """
        处理窗口关闭按钮点击（X按钮）
        
        逻辑：
        - 如果处于停电状态：点击X视为取消停电处理（相当于网络恢复）
        - 如果正常状态：点击X最小化到托盘（隐藏窗口）
        """
        if self.power_outage:
            self.end_power_outage()
        else:
            self.window.withdraw()

    def update_action_button_text(self):
        """
        根据当前power_action更新按钮文字以提供准确反馈
        
        当用户在设置中切换操作类型时，立即按钮文字会相应改变：
        - shutdown → "立即关机"
        - hibernate/sleep → "立即休眠"
        """
        if self.power_action == "shutdown":
            self.hibernate_button.config(text="立即关机")
        else:
            self.hibernate_button.config(text="立即休眠")

if __name__ == "__main__":
    monitor = PowerMonitor()