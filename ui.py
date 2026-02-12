"""
ui.py — Touch-optimised Tkinter GUI for the AutoBrew system.

Designed for the Raspberry Pi Official 7" DSI Touch Display (800 × 480).
All widgets are sized for finger-friendly interaction.

Screens:
    1. Resume prompt   — shown when a saved state exists on startup
    2. New cycle setup — inputs for fertilizer weight, dilution, duration
    3. Monitoring       — real-time status during fill / brew / complete
"""

import logging
import tkinter as tk
from tkinter import ttk, messagebox

import config as CFG
from controller import BrewController
from hardware import HardwareManager
from state_manager import load_state, clear_state, new_state
from shared_types import Phase
from settings_manager import load_settings, save_settings, merge_with_defaults

log = logging.getLogger("autobrew.ui")

# ──────────────────────────────────────────────────────────────────────
# Styling helpers
# ──────────────────────────────────────────────────────────────────────
UI_SCALE = 1.0
UI_WIDTH = int(getattr(CFG, "UI_BASE_WIDTH", 800))
UI_HEIGHT = int(getattr(CFG, "UI_BASE_HEIGHT", 480))


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _px(value: float) -> int:
    """Scale a pixel value relative to the baseline 800×480 design."""
    return max(1, int(round(float(value) * float(UI_SCALE))))


def _content_width() -> int:
    # Conservative content width used for wraplength/progress sizing.
    # Keeps UI readable even if the window is slightly smaller.
    return max(240, int(UI_WIDTH - _px(2 * 10) - _px(40)))


def _wraplength(frac: float = 0.90, cap_px: int | None = None) -> int:
    w = int(_content_width() * float(frac))
    if cap_px is not None:
        w = min(w, _px(cap_px))
    return max(200, w)


def _apply_ui_metrics(width: int, height: int):
    """Compute UI scale + derived fonts/padding for the current display."""
    global UI_SCALE, UI_WIDTH, UI_HEIGHT
    global FONT_LG, FONT_MD, FONT_SM, FONT_STAT, FONT_ICON, PAD

    base_w = int(getattr(CFG, "UI_BASE_WIDTH", 800))
    base_h = int(getattr(CFG, "UI_BASE_HEIGHT", 480))
    min_scale = float(getattr(CFG, "UI_SCALE_MIN", 0.85))
    max_scale = float(getattr(CFG, "UI_SCALE_MAX", 1.40))

    UI_WIDTH = int(width) if width else base_w
    UI_HEIGHT = int(height) if height else base_h

    scale = min(UI_WIDTH / base_w, UI_HEIGHT / base_h)
    UI_SCALE = _clamp(scale, min_scale, max_scale)

    FONT_LG = (CFG.UI_FONT_FAMILY, _px(20), "bold")
    FONT_MD = (CFG.UI_FONT_FAMILY, _px(16))
    FONT_SM = (CFG.UI_FONT_FAMILY, _px(13))
    FONT_STAT = (CFG.UI_FONT_FAMILY, _px(28), "bold")
    FONT_ICON = (CFG.UI_FONT_FAMILY, _px(18), "bold")
    PAD = _px(10)


# Defaults (overridden at runtime once the root window exists)
FONT_LG = (CFG.UI_FONT_FAMILY, 20, "bold")
FONT_MD = (CFG.UI_FONT_FAMILY, 16)
FONT_SM = (CFG.UI_FONT_FAMILY, 13)
FONT_STAT = (CFG.UI_FONT_FAMILY, 28, "bold")
FONT_ICON = (CFG.UI_FONT_FAMILY, 18, "bold")
PAD = 10


def _style_button(btn: tk.Button):
    btn.config(
        font=FONT_MD,
        bg=CFG.UI_BUTTON_BG,
        fg=CFG.UI_FG_COLOR,
        activebackground=CFG.UI_ACCENT,
        activeforeground="#000",
        relief="flat",
        padx=_px(18),
        pady=_px(10),
        cursor="hand2",
    )


def _style_label(lbl: tk.Label, font=FONT_MD):
    lbl.config(font=font, bg=CFG.UI_BG_COLOR, fg=CFG.UI_FG_COLOR)


def _style_entry(ent: tk.Entry):
    ent.config(
        font=FONT_MD,
        bg=CFG.UI_ENTRY_BG,
        fg=CFG.UI_FG_COLOR,
        insertbackground=CFG.UI_FG_COLOR,
        relief="flat",
        width=10,
    )


# ======================================================================
#  Main Application Window
# ======================================================================
class BrewApp:
    """Root Tkinter application for the 7" touchscreen."""

    def __init__(self, hw: HardwareManager, ctrl: BrewController):
        self.hw = hw
        self.ctrl = ctrl

        self.root = tk.Tk()
        self.root.title("AutoBrew Controller")
        self.root.configure(bg=CFG.UI_BG_COLOR)

        # Full-screen on Pi; windowed elsewhere (avoid giant scaling on dev desktops)
        from hardware import ON_PI
        fullscreen_on_pi = bool(getattr(CFG, "UI_FULLSCREEN_ON_PI", True))
        windowed_geometry = str(getattr(CFG, "UI_WINDOWED_GEOMETRY", "800x480"))
        use_fullscreen = bool(ON_PI and fullscreen_on_pi)

        if use_fullscreen:
            try:
                self.root.attributes("-fullscreen", True)
            except tk.TclError:
                use_fullscreen = False

        if not use_fullscreen:
            self.root.geometry(windowed_geometry)

        # Derive scale/fonts/padding from the active display/window size
        self.root.update_idletasks()
        if use_fullscreen:
            w, h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        else:
            w, h = self.root.winfo_width(), self.root.winfo_height()
        _apply_ui_metrics(w, h)

        self.root.bind("<Escape>", lambda e: self._quit())

        # Container frame for screen switching
        self._container = tk.Frame(self.root, bg=CFG.UI_BG_COLOR)
        self._container.pack(fill="both", expand=True)

        # Decide which screen to show first
        # If calibration hasn't been completed, force first-time setup.
        self._settings = merge_with_defaults(load_settings())
        if not CFG.CALIBRATION_COMPLETE or not self._settings.get("calibration_complete"):
            self._show_hardware_check_screen(first_time=True)
            return

        saved = load_state()
        if saved and saved.get("phase") in (Phase.FILL.value, Phase.BREW.value):
            self._show_resume_screen(saved)
        else:
            clear_state()
            self._show_setup_screen()

    # ------------------------------------------------------------------
    #  Screen management helpers
    # ------------------------------------------------------------------
    def _clear_container(self):
        for w in self._container.winfo_children():
            w.destroy()

    def run(self):
        self.root.mainloop()

    def _quit(self):
        # Non-blocking exit: request stop, then poll until the worker stops
        # before cleaning up GPIO resources.
        self.ctrl.stop_async(emergency=False, cancel_state=True)
        self._begin_exit_poll()

    def _begin_exit_poll(self):
        if self.ctrl.running:
            self.root.after(100, self._begin_exit_poll)
            return
        self.hw.cleanup()
        self.root.destroy()

    # ==================================================================
    #  Screen 1: Resume Prompt
    # ==================================================================
    def _show_resume_screen(self, saved: dict):
        self._clear_container()
        frm = tk.Frame(self._container, bg=CFG.UI_BG_COLOR)
        frm.place(relx=0.5, rely=0.5, anchor="center")

        phase = saved.get("phase", "?")
        if phase == Phase.FILL.value:
            added = saved.get("added_gallons", 0)
            target = saved.get("target_gallons", 0)
            last_save = saved.get("last_save_wallclock")

            est_pct = self.hw.level.read_level_pct()
            est_gal = self.hw.level.read_gallons()
            est_line = ""
            if est_pct is not None and est_gal is not None:
                est_line = f"\nEstimated tank level: {est_pct:.0f}% (~{est_gal:.0f} gal)"

            last_line = ""
            if last_save:
                last_line = f"\nLast saved: {last_save} (flow-counted: {added:.1f} gal)"
            msg = (
                f"Previous fill incomplete.\n"
                f"{added:.1f} of {target:.1f} gallons added.\n\n"
                f"Resume filling?"
                f"{est_line}"
                f"{last_line}"
            )
        else:
            total = saved.get("brew_duration_sec", 0)
            elapsed = saved.get("brew_elapsed_sec", 0)
            remaining_h = max(0, (total - elapsed)) / 3600
            msg = (
                f"Previous brew interrupted.\n"
                f"{remaining_h:.1f} hours remaining.\n\n"
                f"Resume brewing?"
            )

        lbl = tk.Label(frm, text=msg, justify="center")
        _style_label(lbl, FONT_LG)
        lbl.pack(pady=_px(20))

        btn_frame = tk.Frame(frm, bg=CFG.UI_BG_COLOR)
        btn_frame.pack(pady=_px(10))

        btn_yes = tk.Button(btn_frame, text="Yes — Resume", command=lambda: self._resume(saved))
        _style_button(btn_yes)
        btn_yes.config(bg=CFG.UI_OK, fg="#000")
        btn_yes.pack(side="left", padx=_px(10))

        btn_no = tk.Button(btn_frame, text="No — New Cycle", command=self._decline_resume)
        _style_button(btn_no)
        btn_no.config(bg=CFG.UI_WARN, fg="#000")
        btn_no.pack(side="left", padx=_px(10))

    def _resume(self, saved: dict):
        self.ctrl.resume_cycle(saved)
        self._show_monitor_screen()

    def _decline_resume(self):
        clear_state()
        self._show_setup_screen()

    # ==================================================================
    #  Screen 2: New Cycle Setup
    # ==================================================================
    def _show_setup_screen(self):
        self._clear_container()
        frm = tk.Frame(self._container, bg=CFG.UI_BG_COLOR)
        frm.place(relx=0.5, rely=0.5, anchor="center")

        # Title
        title = tk.Label(frm, text="New Brew Cycle")
        _style_label(title, FONT_LG)
        title.grid(row=0, column=0, columnspan=3, pady=(0, _px(20)))

        # --- Fertilizer weight ---
        lbl_fw = tk.Label(frm, text="Fertilizer (lb):")
        _style_label(lbl_fw)
        lbl_fw.grid(row=1, column=0, sticky="e", padx=PAD, pady=_px(6))

        self._ent_fert = tk.Entry(frm)
        _style_entry(self._ent_fert)
        self._ent_fert.insert(0, "50")
        self._ent_fert.grid(row=1, column=1, padx=PAD, pady=_px(6))

        # --- Dilution ratio ---
        lbl_dr = tk.Label(frm, text="Dilution (lb water / lb fert):")
        _style_label(lbl_dr)
        lbl_dr.grid(row=2, column=0, sticky="e", padx=PAD, pady=_px(6))

        self._ent_dilution = tk.Entry(frm)
        _style_entry(self._ent_dilution)
        self._ent_dilution.insert(0, str(CFG.DEFAULT_DILUTION_RATIO))
        self._ent_dilution.grid(row=2, column=1, padx=PAD, pady=_px(6))

        # Calculated gallons indicator
        self._lbl_calc_gal = tk.Label(frm, text="")
        _style_label(self._lbl_calc_gal, FONT_SM)
        self._lbl_calc_gal.grid(row=2, column=2, padx=PAD)

        # Live calculation update
        self._ent_fert.bind("<KeyRelease>", lambda e: self._update_calc())
        self._ent_dilution.bind("<KeyRelease>", lambda e: self._update_calc())
        self._update_calc()

        # --- Brew duration ---
        lbl_dur = tk.Label(frm, text="Brew Duration (hours):")
        _style_label(lbl_dur)
        lbl_dur.grid(row=3, column=0, sticky="e", padx=PAD, pady=_px(6))

        self._ent_duration = tk.Entry(frm)
        _style_entry(self._ent_duration)
        self._ent_duration.insert(0, "24")
        self._ent_duration.grid(row=3, column=1, padx=PAD, pady=_px(6))

        # --- Skip fill checkbox ---
        self._skip_fill_var = tk.IntVar(value=0)
        chk = tk.Checkbutton(
            frm,
            text="Skip water fill (go straight to brewing)",
            variable=self._skip_fill_var,
            bg=CFG.UI_BG_COLOR,
            fg=CFG.UI_FG_COLOR,
            selectcolor=CFG.UI_ENTRY_BG,
            activebackground=CFG.UI_BG_COLOR,
            activeforeground=CFG.UI_FG_COLOR,
            font=FONT_SM,
        )
        chk.grid(row=4, column=0, columnspan=3, pady=_px(10))

        # --- Start button ---
        btn_start = tk.Button(frm, text="▶  Start Brew", command=self._on_start)
        _style_button(btn_start)
        btn_start.config(bg=CFG.UI_OK, fg="#000", font=FONT_LG)
        btn_start.grid(row=5, column=0, columnspan=3, pady=_px(20))

        btn_cal = tk.Button(frm, text="Calibration / Setup", command=lambda: self._show_calibration_screen(first_time=False))
        _style_button(btn_cal)
        btn_cal.grid(row=6, column=0, columnspan=3, pady=(0, _px(10)))

    def _update_calc(self):
        """Update the live 'calculated gallons' label."""
        try:
            fw = float(self._ent_fert.get())
            dr = float(self._ent_dilution.get())
            gal = BrewController.calc_target_gallons(fw, dr)
            self._lbl_calc_gal.config(text=f"≈ {gal:.1f} gal", fg=CFG.UI_ACCENT)
        except ValueError:
            self._lbl_calc_gal.config(text="", fg=CFG.UI_FG_COLOR)

    def _on_start(self):
        try:
            fert = float(self._ent_fert.get())
            dilution = float(self._ent_dilution.get())
            hours = float(self._ent_duration.get())
        except ValueError:
            messagebox.showerror("Input Error", "Please enter valid numbers.")
            return

        if fert <= 0 or dilution <= 0:
            messagebox.showerror("Input Error", "Weight and dilution must be > 0.")
            return
        if not (CFG.BREW_MIN_HOURS <= hours <= CFG.BREW_MAX_HOURS):
            messagebox.showerror(
                "Input Error",
                f"Duration must be {CFG.BREW_MIN_HOURS}–{CFG.BREW_MAX_HOURS} hours.",
            )
            return

        target_gal = BrewController.calc_target_gallons(fert, dilution)
        if target_gal > CFG.TANK_CAPACITY_GALLONS and not self._skip_fill_var.get():
            messagebox.showwarning(
                "Exceeds Tank",
                f"Calculated {target_gal:.1f} gal exceeds tank capacity "
                f"({CFG.TANK_CAPACITY_GALLONS} gal).\nAdjust inputs or skip fill.",
            )
            return

        skip = bool(self._skip_fill_var.get())
        self.ctrl.start_cycle(fert, dilution, hours, skip)
        self._show_monitor_screen()

    # ==================================================================
    #  Screen 3: Real-time Monitoring
    # ==================================================================
    def _show_monitor_screen(self):
        self._clear_container()
        outer = tk.Frame(self._container, bg=CFG.UI_BG_COLOR)
        outer.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        # --- Header ---
        hdr = tk.Label(outer, text="AutoBrew — Live Status")
        _style_label(hdr, FONT_LG)
        hdr.pack(pady=(0, _px(8)))

        # --- Alert banner ---
        self._lbl_alert = tk.Label(outer, text="", fg=CFG.UI_WARN)
        _style_label(self._lbl_alert, FONT_SM)
        self._lbl_alert.pack()

        # --- Stats grid ---
        grid = tk.Frame(outer, bg=CFG.UI_BG_COLOR)
        grid.pack(fill="both", expand=True, pady=_px(5))

        self._stat_labels: dict[str, tk.Label] = {}
        stat_defs = [
            ("Phase",           "phase"),
            ("Temperature",     "temp"),
            ("Gallons Added",   "gallons"),
            ("Target Gallons",  "target"),
            ("Water Level",     "level"),
            ("Elapsed",         "elapsed"),
            ("Remaining",       "remaining"),
            ("Stirring",        "stir"),
        ]

        for i, (display, key) in enumerate(stat_defs):
            row, col = divmod(i, 2)  # 2-column layout
            lbl_name = tk.Label(grid, text=display, anchor="e")
            _style_label(lbl_name, FONT_SM)
            lbl_name.grid(row=row, column=col * 2, sticky="e", padx=(_px(15), _px(5)), pady=_px(6))

            lbl_val = tk.Label(grid, text="—", anchor="w")
            _style_label(lbl_val, FONT_MD)
            lbl_val.config(fg=CFG.UI_ACCENT)
            lbl_val.grid(row=row, column=col * 2 + 1, sticky="w", padx=(0, _px(15)), pady=_px(6))
            self._stat_labels[key] = lbl_val

        # Even column weights
        for c in range(4):
            grid.columnconfigure(c, weight=1)

        # --- Progress bar ---
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "brew.Horizontal.TProgressbar",
            troughcolor=CFG.UI_ENTRY_BG,
            background=CFG.UI_ACCENT,
            thickness=_px(22),
        )
        self._progress = ttk.Progressbar(
            outer, orient="horizontal", length=int(_content_width() * 0.92),
            mode="determinate", style="brew.Horizontal.TProgressbar",
        )
        self._progress.pack(pady=_px(8))

        # --- Button row ---
        btn_frame = tk.Frame(outer, bg=CFG.UI_BG_COLOR)
        btn_frame.pack(pady=_px(6))

        self._btn_end_fill = tk.Button(
            btn_frame, text="End Fill Now", command=self._on_end_fill,
        )
        _style_button(self._btn_end_fill)
        self._btn_end_fill.pack(side="left", padx=_px(8))

        btn_stop = tk.Button(
            btn_frame, text="⛔  Emergency Stop", command=self._on_emergency_stop,
        )
        _style_button(btn_stop)
        btn_stop.config(bg=CFG.UI_WARN, fg="#000")
        btn_stop.pack(side="left", padx=_px(8))

        self._btn_new = tk.Button(
            btn_frame, text="New Cycle", command=self._on_new_cycle, state="disabled",
        )
        _style_button(self._btn_new)
        self._btn_new.pack(side="left", padx=_px(8))

        self._btn_stop_cycle = tk.Button(
            btn_frame, text="Stop Cycle", command=self._on_stop_cycle, state="disabled",
        )
        _style_button(self._btn_stop_cycle)
        self._btn_stop_cycle.pack(side="left", padx=_px(8))

        self._btn_cal = tk.Button(
            btn_frame, text="Calibration", command=lambda: self._show_calibration_screen(first_time=False), state="disabled",
        )
        _style_button(self._btn_cal)
        self._btn_cal.pack(side="left", padx=_px(8))

        # Start periodic refresh
        self._refresh_monitor()

    # ------------------------------------------------------------------
    #  Monitor refresh (runs every UI_REFRESH_INTERVAL_MS)
    # ------------------------------------------------------------------
    def _refresh_monitor(self):
        st = self.ctrl.state
        phase = st.get("phase") or Phase.IDLE.value

        # Phase
        phase_labels = {
            Phase.FILL.value: "Filling",
            Phase.BREW.value: "Brewing",
            Phase.COMPLETE.value: "Complete",
            Phase.IDLE.value: "Idle",
            Phase.STOPPED.value: "Stopped",
            Phase.ERROR.value: "Error",
        }
        self._stat_labels["phase"].config(text=phase_labels.get(phase, phase))

        # Temperature
        tf = st.get("last_temp_f")
        tc = st.get("last_temp_c")
        if tf is not None and tc is not None:
            self._stat_labels["temp"].config(text=f"{tf:.1f} °F  /  {tc:.1f} °C")
        else:
            self._stat_labels["temp"].config(text="— (reading…)")

        # Read live temperature in the UI tick as well (non-blocking best effort)
        self._bg_temp_read()

        # Gallons added
        added = st.get("added_gallons", 0)
        self._stat_labels["gallons"].config(text=f"{added:.2f} gal")

        # Target
        target = st.get("target_gallons", 0)
        self._stat_labels["target"].config(text=f"{target:.1f} gal")

        # Water level (show % and estimated gallons if available)
        level_pct = self.hw.level.read_level_pct()
        level_gal = self.hw.level.read_gallons()
        if level_pct is not None and level_gal is not None:
            self._stat_labels["level"].config(text=f"{level_pct:.0f}%  (~{level_gal:.0f} gal)")
        elif level_pct is not None:
            self._stat_labels["level"].config(text=f"{level_pct:.0f}%")
        else:
            self._stat_labels["level"].config(text="N/A")

        # Elapsed / remaining
        brew_dur = st.get("brew_duration_sec", 0)
        brew_el = st.get("brew_elapsed_sec", 0)
        self._stat_labels["elapsed"].config(text=self._fmt_time(brew_el))
        remaining = max(0, brew_dur - brew_el)
        self._stat_labels["remaining"].config(text=self._fmt_time(remaining))

        # Stirring status
        stir_cyc = st.get("stir_cycle_elapsed_sec", 0)
        if phase == Phase.BREW.value and stir_cyc <= CFG.STIR_ON_SECONDS:
            secs_left = int(CFG.STIR_ON_SECONDS - stir_cyc)
            self._stat_labels["stir"].config(
                text=f"ON  ({secs_left}s left)", fg=CFG.UI_OK,
            )
        elif phase == Phase.BREW.value:
            next_stir = int(CFG.STIR_CYCLE_SECONDS - stir_cyc)
            self._stat_labels["stir"].config(
                text=f"OFF  (next in {self._fmt_time(next_stir)})", fg=CFG.UI_FG_COLOR,
            )
        else:
            self._stat_labels["stir"].config(text="—", fg=CFG.UI_FG_COLOR)

        # Progress bar
        if phase == Phase.FILL.value and target > 0:
            self._progress["maximum"] = target
            self._progress["value"] = min(added, target)
        elif phase == Phase.BREW.value and brew_dur > 0:
            self._progress["maximum"] = brew_dur
            self._progress["value"] = min(brew_el, brew_dur)
        elif phase == Phase.COMPLETE.value:
            self._progress["value"] = self._progress["maximum"] or 100

        # Alert banner
        alert = self.ctrl.alert_msg
        self._lbl_alert.config(text=alert if alert else "")

        # Button states
        if phase == Phase.FILL.value:
            self._btn_end_fill.config(state="normal")
            self._btn_new.config(state="disabled")
            self._btn_stop_cycle.config(state="normal")
            self._btn_cal.config(state="disabled")
        elif phase == Phase.COMPLETE.value:
            self._btn_end_fill.config(state="disabled")
            self._btn_new.config(state="normal")
            self._btn_stop_cycle.config(state="disabled")
            self._btn_cal.config(state="normal")
        else:
            self._btn_end_fill.config(state="disabled")
            self._btn_new.config(state="disabled")
            self._btn_stop_cycle.config(state=("normal" if phase == Phase.BREW.value else "disabled"))
            # Only allow calibration when not actively brewing
            self._btn_cal.config(state=("normal" if phase in (Phase.IDLE.value, Phase.STOPPED.value) else "disabled"))

        # Schedule next refresh
        self.root.after(CFG.UI_REFRESH_INTERVAL_MS, self._refresh_monitor)

    # ------------------------------------------------------------------
    def _bg_temp_read(self):
        """Non-blocking best-effort temperature update."""
        c, f = self.hw.temp.read()
        if c is not None:
            self.ctrl.state["last_temp_c"] = c
            self.ctrl.state["last_temp_f"] = f

    # ------------------------------------------------------------------
    #  Button handlers
    # ------------------------------------------------------------------
    def _on_end_fill(self):
        self.ctrl.manual_end_fill()

    def _on_emergency_stop(self):
        # Non-blocking so Tkinter never freezes on join
        self.ctrl.stop_async(emergency=True)
        clear_state()
        self.ctrl.alert_msg = "Emergency stop activated. Cycle cancelled."
        self._stat_labels["phase"].config(text="STOPPED", fg=CFG.UI_WARN)
        self._btn_new.config(state="normal")

    def _on_stop_cycle(self):
        # Normal (non-emergency) stop.
        # If filling: closes solenoid. If brewing: stops paddle.
        self.ctrl.stop_async(emergency=False, cancel_state=True)
        clear_state()
        self.ctrl.alert_msg = "Cycle stopped."
        self.ctrl.state["phase"] = Phase.STOPPED.value
        self._btn_new.config(state="normal")

    def _on_new_cycle(self):
        clear_state()
        self.ctrl.state = new_state()
        self._show_setup_screen()

    # ==================================================================
    #  Hardware Check Screen
    # ==================================================================
    def _show_hardware_check_screen(self, first_time: bool = False):
        """Display detection status for every registered device."""
        self._clear_container()
        self._hc_first_time = first_time

        outer = tk.Frame(self._container, bg=CFG.UI_BG_COLOR)
        outer.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        title = tk.Label(outer, text="Hardware Check")
        _style_label(title, FONT_LG)
        title.pack(pady=(0, _px(4)))

        desc = tk.Label(
            outer,
            text="Verifying connected sensors and devices.\n"
                 "Tap any item to expand or collapse wiring details.",
            justify="center",
        )
        _style_label(desc, FONT_SM)
        desc.pack(pady=(0, _px(6)))

        # Summary line (updated after checks run)
        self._hc_summary = tk.Label(outer, text="")
        _style_label(self._hc_summary, FONT_MD)
        self._hc_summary.pack(pady=(0, _px(4)))

        # Footer buttons — pack bottom-first so they stay visible
        footer = tk.Frame(outer, bg=CFG.UI_BG_COLOR)
        footer.pack(side="bottom", fill="x", pady=_px(6))

        btn_recheck = tk.Button(
            footer, text="\u27F3  Recheck All", command=self._hc_recheck,
        )
        _style_button(btn_recheck)
        btn_recheck.pack(side="left", padx=_px(8))

        btn_continue = tk.Button(
            footer, text="Continue  \u2192", command=self._hc_continue,
        )
        _style_button(btn_continue)
        btn_continue.config(bg=CFG.UI_OK, fg="#000")
        btn_continue.pack(side="right", padx=_px(8))

        # Scrollable device list area
        list_container = tk.Frame(outer, bg=CFG.UI_BG_COLOR)
        list_container.pack(fill="both", expand=True)

        self._hc_canvas = tk.Canvas(
            list_container, bg=CFG.UI_BG_COLOR, highlightthickness=0,
        )
        scrollbar = tk.Scrollbar(
            list_container, orient="vertical", command=self._hc_canvas.yview,
        )
        self._hc_list_frame = tk.Frame(self._hc_canvas, bg=CFG.UI_BG_COLOR)
        self._hc_list_frame.bind(
            "<Configure>",
            lambda e: self._hc_canvas.configure(
                scrollregion=self._hc_canvas.bbox("all"),
            ),
        )
        self._hc_canvas_window = self._hc_canvas.create_window(
            (0, 0), window=self._hc_list_frame, anchor="nw",
        )
        self._hc_canvas.bind(
            "<Configure>",
            lambda e: self._hc_canvas.itemconfig(
                self._hc_canvas_window, width=e.width,
            ),
        )
        self._hc_canvas.configure(yscrollcommand=scrollbar.set)
        self._hc_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Run checks
        self._hc_recheck()

    def _hc_recheck(self):
        """Run all device checks and rebuild the result list."""
        from hardware_check import run_all_checks

        for w in self._hc_list_frame.winfo_children():
            w.destroy()

        results = run_all_checks(self.hw)
        passed = sum(1 for r in results if r.detected)
        total = len(results)

        if passed == total:
            self._hc_summary.config(
                text=f"All {total} devices detected  \u2713", fg=CFG.UI_OK,
            )
        else:
            self._hc_summary.config(
                text=f"{passed} of {total} detected \u2014 expand items below for help",
                fg=CFG.UI_WARN,
            )

        for result in results:
            self._hc_add_device_row(result)

    def _hc_add_device_row(self, result):
        """Add one device entry to the hardware-check list."""
        dev = result.device
        detected = result.detected

        row = tk.Frame(self._hc_list_frame, bg=CFG.UI_ENTRY_BG)
        row.pack(fill="x", pady=_px(3), padx=_px(4))

        # Header: icon + name + pin badge
        header = tk.Frame(row, bg=CFG.UI_ENTRY_BG)
        header.pack(fill="x", padx=_px(8), pady=(_px(6), 0))

        icon_text = "\u2713" if detected else "\u2717"
        icon_color = CFG.UI_OK if detected else CFG.UI_WARN

        lbl_icon = tk.Label(
            header, text=icon_text,
            font=FONT_ICON,
            fg=icon_color, bg=CFG.UI_ENTRY_BG,
        )
        lbl_icon.pack(side="left", padx=(0, _px(8)))

        lbl_name = tk.Label(
            header, text=dev.name, font=FONT_MD,
            fg=CFG.UI_FG_COLOR, bg=CFG.UI_ENTRY_BG, anchor="w",
        )
        lbl_name.pack(side="left")

        lbl_pins = tk.Label(
            header, text=f"[{dev.pins}]", font=FONT_SM,
            fg=CFG.UI_ACCENT, bg=CFG.UI_ENTRY_BG,
        )
        lbl_pins.pack(side="right")

        # Detail / troubleshoot frame (collapsible)
        detail_frame = tk.Frame(row, bg=CFG.UI_ENTRY_BG)

        detail_text = dev.troubleshoot
        if result.detail:
            detail_text += f"\n\nError detail: {result.detail}"

        lbl_detail = tk.Label(
            detail_frame, text=detail_text, font=FONT_SM,
            fg=CFG.UI_FG_COLOR, bg=CFG.UI_ENTRY_BG,
            justify="left", wraplength=_wraplength(frac=0.92, cap_px=650), anchor="w",
        )
        lbl_detail.pack(fill="x", padx=(_px(36), _px(8)), pady=(_px(2), _px(6)))

        # Not-detected → expanded by default; detected → collapsed
        if not detected:
            detail_frame.pack(fill="x")

        def _toggle(event=None, df=detail_frame):
            if df.winfo_manager():
                df.pack_forget()
            else:
                df.pack(fill="x")

        for widget in (row, header, lbl_icon, lbl_name, lbl_pins):
            widget.bind("<Button-1>", _toggle)
            widget.config(cursor="hand2")

    def _hc_continue(self):
        """Proceed from hardware check to calibration."""
        self._show_calibration_screen(first_time=self._hc_first_time)

    # ==================================================================
    #  Calibration / First-Time Setup Wizard
    # ==================================================================
    def _show_calibration_screen(self, first_time: bool):
        """Guided calibration process for flow meter + ultrasonic."""
        self._clear_container()

        self._settings = merge_with_defaults(load_settings())
        self._cal_first_time = bool(first_time)

        outer = tk.Frame(self._container, bg=CFG.UI_BG_COLOR)
        outer.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        title_txt = "First-Time Setup" if first_time else "Calibration / Setup"
        title = tk.Label(outer, text=title_txt)
        _style_label(title, FONT_LG)
        title.pack(pady=(0, _px(8)))

        desc = (
            "This wizard calibrates sensors for THIS unit.\n"
            "You can rerun it any time from the main screens."
        )
        lbl_desc = tk.Label(outer, text=desc, justify="center")
        _style_label(lbl_desc, FONT_SM)
        lbl_desc.pack(pady=(0, _px(10)))

        # --- Flow calibration block ---
        flow_box = tk.Frame(outer, bg=CFG.UI_ENTRY_BG)
        flow_box.pack(fill="x", pady=_px(8))

        lbl_flow = tk.Label(flow_box, text="Flow Meter Calibration (pulses per gallon)")
        lbl_flow.config(font=FONT_MD, bg=CFG.UI_ENTRY_BG, fg=CFG.UI_FG_COLOR)
        lbl_flow.pack(anchor="w", padx=PAD, pady=(_px(8), 0))

        instructions = (
            "1) Put discharge into a measured container or to drain.\n"
            "2) Press 'Run Water' to open the solenoid and count pulses.\n"
            "3) Press 'Stop Water' when done, enter ACTUAL gallons dispensed, then Save."
        )
        lbl_inst = tk.Label(flow_box, text=instructions, justify="left")
        lbl_inst.config(font=FONT_SM, bg=CFG.UI_ENTRY_BG, fg=CFG.UI_FG_COLOR)
        lbl_inst.pack(anchor="w", padx=PAD, pady=_px(6))

        self._flow_pulses_start = 0
        self._flow_running = False

        row = tk.Frame(flow_box, bg=CFG.UI_ENTRY_BG)
        row.pack(fill="x", padx=PAD, pady=(0, _px(8)))

        self._lbl_flow_pulses = tk.Label(row, text="Pulses: 0")
        self._lbl_flow_pulses.config(font=FONT_SM, bg=CFG.UI_ENTRY_BG, fg=CFG.UI_ACCENT)
        self._lbl_flow_pulses.pack(side="left", padx=(0, _px(12)))

        tk.Label(row, text="Actual gallons:", font=FONT_SM, bg=CFG.UI_ENTRY_BG, fg=CFG.UI_FG_COLOR).pack(side="left")
        self._ent_flow_actual_gal = tk.Entry(row)
        _style_entry(self._ent_flow_actual_gal)
        self._ent_flow_actual_gal.insert(0, "10")
        self._ent_flow_actual_gal.pack(side="left", padx=_px(8))

        self._btn_flow_run = tk.Button(row, text="Run Water", command=self._on_flow_run)
        _style_button(self._btn_flow_run)
        self._btn_flow_run.pack(side="left", padx=_px(8))

        self._btn_flow_stop = tk.Button(row, text="Stop Water", command=self._on_flow_stop, state="disabled")
        _style_button(self._btn_flow_stop)
        self._btn_flow_stop.pack(side="left", padx=_px(8))

        self._lbl_flow_result = tk.Label(flow_box, text="")
        self._lbl_flow_result.config(font=FONT_SM, bg=CFG.UI_ENTRY_BG, fg=CFG.UI_OK)
        self._lbl_flow_result.pack(anchor="w", padx=PAD, pady=(0, _px(8)))

        # --- Ultrasonic calibration block ---
        ultra_box = tk.Frame(outer, bg=CFG.UI_ENTRY_BG)
        ultra_box.pack(fill="x", pady=_px(8))

        lbl_ultra = tk.Label(ultra_box, text="Ultrasonic Tank Geometry")
        lbl_ultra.config(font=FONT_MD, bg=CFG.UI_ENTRY_BG, fg=CFG.UI_FG_COLOR)
        lbl_ultra.pack(anchor="w", padx=PAD, pady=(_px(8), 0))

        ultra_hint = (
            "Tip: You do NOT have to fill the tank to calibrate. You can hold a target under the sensor\n"
            "at the desired distance and press 'Use current as EMPTY/FULL'. A flat target (clipboard/board)\n"
            "is more repeatable than a hand, but a hand can work in a pinch."
        )
        lbl_ultra_hint = tk.Label(ultra_box, text=ultra_hint, justify="left")
        lbl_ultra_hint.config(font=FONT_SM, bg=CFG.UI_ENTRY_BG, fg=CFG.UI_FG_COLOR)
        lbl_ultra_hint.pack(anchor="w", padx=PAD, pady=_px(6))

        urow = tk.Frame(ultra_box, bg=CFG.UI_ENTRY_BG)
        urow.pack(fill="x", padx=PAD, pady=_px(8))

        tk.Label(urow, text="Empty dist (cm):", font=FONT_SM, bg=CFG.UI_ENTRY_BG, fg=CFG.UI_FG_COLOR).pack(side="left")
        self._ent_empty_cm = tk.Entry(urow)
        _style_entry(self._ent_empty_cm)
        self._ent_empty_cm.insert(0, str(self._settings.get("tank_empty_distance_cm", CFG.TANK_EMPTY_DISTANCE_CM)))
        self._ent_empty_cm.pack(side="left", padx=_px(6))

        tk.Label(urow, text="Full dist (cm):", font=FONT_SM, bg=CFG.UI_ENTRY_BG, fg=CFG.UI_FG_COLOR).pack(side="left")
        self._ent_full_cm = tk.Entry(urow)
        _style_entry(self._ent_full_cm)
        self._ent_full_cm.insert(0, str(self._settings.get("tank_full_distance_cm", CFG.TANK_FULL_DISTANCE_CM)))
        self._ent_full_cm.pack(side="left", padx=_px(6))

        tk.Label(urow, text="Capacity (gal):", font=FONT_SM, bg=CFG.UI_ENTRY_BG, fg=CFG.UI_FG_COLOR).pack(side="left")
        self._ent_capacity = tk.Entry(urow)
        _style_entry(self._ent_capacity)
        self._ent_capacity.insert(0, str(self._settings.get("tank_capacity_gallons", CFG.TANK_CAPACITY_GALLONS)))
        self._ent_capacity.pack(side="left", padx=_px(6))

        btns = tk.Frame(ultra_box, bg=CFG.UI_ENTRY_BG)
        btns.pack(fill="x", padx=PAD, pady=(0, _px(8)))

        b_empty = tk.Button(btns, text="Use current as EMPTY", command=self._use_current_as_empty)
        _style_button(b_empty)
        b_empty.pack(side="left", padx=_px(6))

        b_full = tk.Button(btns, text="Use current as FULL", command=self._use_current_as_full)
        _style_button(b_full)
        b_full.pack(side="left", padx=_px(6))

        self._lbl_ultra_read = tk.Label(btns, text="")
        self._lbl_ultra_read.config(font=FONT_SM, bg=CFG.UI_ENTRY_BG, fg=CFG.UI_ACCENT)
        self._lbl_ultra_read.pack(side="left", padx=_px(10))

        # --- Footer buttons ---
        footer = tk.Frame(outer, bg=CFG.UI_BG_COLOR)
        footer.pack(fill="x", pady=_px(10))

        btn_save = tk.Button(footer, text="Save Calibration", command=self._save_calibration)
        _style_button(btn_save)
        btn_save.config(bg=CFG.UI_OK, fg="#000")
        btn_save.pack(side="left", padx=_px(8))

        btn_cancel = tk.Button(footer, text="Cancel", command=self._cancel_calibration)
        _style_button(btn_cancel)
        btn_cancel.pack(side="left", padx=_px(8))

        btn_hw = tk.Button(
            footer, text="Hardware Check",
            command=lambda: self._show_hardware_check_screen(
                first_time=self._cal_first_time,
            ),
        )
        _style_button(btn_hw)
        btn_hw.pack(side="right", padx=_px(8))

        # start pulse refresh
        self._refresh_cal_pulses()

    def _refresh_cal_pulses(self):
        if not hasattr(self, "_lbl_flow_pulses"):
            return
        if self._flow_running:
            pulses_now = self.hw.flow.pulse_count - self._flow_pulses_start
            self._lbl_flow_pulses.config(text=f"Pulses: {pulses_now}")
        self.root.after(250, self._refresh_cal_pulses)

    def _on_flow_run(self):
        # Safety: do not allow this while a brew cycle is running
        if self.ctrl.running and self.ctrl.state.get("phase") in (Phase.FILL.value, Phase.BREW.value):
            messagebox.showwarning("Busy", "Stop the current cycle before calibrating.")
            return
        self.hw.flow.reset()
        self._flow_pulses_start = 0
        self._flow_running = True
        self._lbl_flow_result.config(text="")
        self.hw.solenoid.on()
        self._btn_flow_run.config(state="disabled")
        self._btn_flow_stop.config(state="normal")

    def _on_flow_stop(self):
        self.hw.solenoid.off()
        self._flow_running = False
        self._btn_flow_run.config(state="normal")
        self._btn_flow_stop.config(state="disabled")

        pulses = self.hw.flow.pulse_count
        try:
            actual_gal = float(self._ent_flow_actual_gal.get())
            if actual_gal <= 0:
                raise ValueError
        except ValueError:
            self._lbl_flow_result.config(text="Enter a valid ACTUAL gallons value.", fg=CFG.UI_WARN)
            return
        ppg = int(round(pulses / actual_gal))
        self._lbl_flow_result.config(text=f"Computed calibration: {ppg} pulses/gal", fg=CFG.UI_OK)
        self._settings["flow_pulses_per_gallon"] = ppg

    def _use_current_as_empty(self):
        dist = self.hw.level.read_distance_cm()
        if dist is None:
            self._lbl_ultra_read.config(text="No reading", fg=CFG.UI_WARN)
            return
        self._ent_empty_cm.delete(0, tk.END)
        self._ent_empty_cm.insert(0, f"{dist:.1f}")
        self._lbl_ultra_read.config(text=f"Current: {dist:.1f} cm", fg=CFG.UI_ACCENT)

    def _use_current_as_full(self):
        dist = self.hw.level.read_distance_cm()
        if dist is None:
            self._lbl_ultra_read.config(text="No reading", fg=CFG.UI_WARN)
            return
        self._ent_full_cm.delete(0, tk.END)
        self._ent_full_cm.insert(0, f"{dist:.1f}")
        self._lbl_ultra_read.config(text=f"Current: {dist:.1f} cm", fg=CFG.UI_ACCENT)

    def _save_calibration(self):
        # Validate + persist
        try:
            ppg = int(self._settings.get("flow_pulses_per_gallon", CFG.FLOW_PULSES_PER_GALLON))
            empty_cm = float(self._ent_empty_cm.get())
            full_cm = float(self._ent_full_cm.get())
            cap = float(self._ent_capacity.get())
        except ValueError:
            messagebox.showerror("Calibration", "Please enter valid numbers.")
            return

        if ppg <= 0:
            messagebox.showerror("Calibration", "Flow calibration must be > 0.")
            return
        if empty_cm <= full_cm:
            messagebox.showerror("Calibration", "Empty distance must be greater than full distance.")
            return

        self._settings["flow_pulses_per_gallon"] = ppg
        self._settings["tank_empty_distance_cm"] = empty_cm
        self._settings["tank_full_distance_cm"] = full_cm
        self._settings["tank_capacity_gallons"] = cap
        self._settings["calibration_complete"] = True

        if not save_settings(self._settings):
            messagebox.showerror("Calibration", "Could not save settings file.")
            return

        # Apply to runtime config + hardware instances
        CFG.apply_runtime_settings(self._settings)
        self.hw.flow.set_pulses_per_gallon(ppg)
        self.hw.level.set_geometry(empty_cm, full_cm, cap)

        messagebox.showinfo("Calibration", "Calibration saved.")

        # Return to main flow
        if self._cal_first_time:
            saved = load_state()
            if saved and saved.get("phase") in (Phase.FILL.value, Phase.BREW.value):
                self._show_resume_screen(saved)
            else:
                self._show_setup_screen()
        else:
            # If we came from monitor, go back there if a cycle is active; otherwise setup
            if self.ctrl.running:
                self._show_monitor_screen()
            else:
                self._show_setup_screen()

    def _cancel_calibration(self):
        # Ensure solenoid is closed if user cancels mid-flow
        try:
            self.hw.solenoid.off()
        except Exception:
            pass

        if self._cal_first_time:
            messagebox.showwarning(
                "Setup Required",
                "Calibration is required before using the system.",
            )
            self._show_calibration_screen(first_time=True)
        else:
            if self.ctrl.running:
                self._show_monitor_screen()
            else:
                self._show_setup_screen()

    # ------------------------------------------------------------------
    #  Utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_time(seconds: float) -> str:
        """Format seconds into H:MM:SS."""
        s = int(max(0, seconds))
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}:{m:02d}:{sec:02d}"
