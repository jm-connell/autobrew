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

log = logging.getLogger("autobrew.ui")

# ──────────────────────────────────────────────────────────────────────
# Styling helpers
# ──────────────────────────────────────────────────────────────────────
FONT_LG = (CFG.UI_FONT_FAMILY, 20, "bold")
FONT_MD = (CFG.UI_FONT_FAMILY, 16)
FONT_SM = (CFG.UI_FONT_FAMILY, 13)
FONT_STAT = (CFG.UI_FONT_FAMILY, 28, "bold")

PAD = 10


def _style_button(btn: tk.Button):
    btn.config(
        font=FONT_MD,
        bg=CFG.UI_BUTTON_BG,
        fg=CFG.UI_FG_COLOR,
        activebackground=CFG.UI_ACCENT,
        activeforeground="#000",
        relief="flat",
        padx=18,
        pady=10,
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

        # Full-screen on Pi; windowed 800×480 elsewhere
        try:
            self.root.attributes("-fullscreen", True)
        except tk.TclError:
            self.root.geometry("800x480")

        self.root.bind("<Escape>", lambda e: self._quit())

        # Container frame for screen switching
        self._container = tk.Frame(self.root, bg=CFG.UI_BG_COLOR)
        self._container.pack(fill="both", expand=True)

        # Decide which screen to show first
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
        lbl.pack(pady=20)

        btn_frame = tk.Frame(frm, bg=CFG.UI_BG_COLOR)
        btn_frame.pack(pady=10)

        btn_yes = tk.Button(btn_frame, text="Yes — Resume", command=lambda: self._resume(saved))
        _style_button(btn_yes)
        btn_yes.config(bg=CFG.UI_OK, fg="#000")
        btn_yes.pack(side="left", padx=10)

        btn_no = tk.Button(btn_frame, text="No — New Cycle", command=self._decline_resume)
        _style_button(btn_no)
        btn_no.config(bg=CFG.UI_WARN, fg="#000")
        btn_no.pack(side="left", padx=10)

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
        title.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        # --- Fertilizer weight ---
        lbl_fw = tk.Label(frm, text="Fertilizer (lb):")
        _style_label(lbl_fw)
        lbl_fw.grid(row=1, column=0, sticky="e", padx=PAD, pady=6)

        self._ent_fert = tk.Entry(frm)
        _style_entry(self._ent_fert)
        self._ent_fert.insert(0, "50")
        self._ent_fert.grid(row=1, column=1, padx=PAD, pady=6)

        # --- Dilution ratio ---
        lbl_dr = tk.Label(frm, text="Dilution (lb water / lb fert):")
        _style_label(lbl_dr)
        lbl_dr.grid(row=2, column=0, sticky="e", padx=PAD, pady=6)

        self._ent_dilution = tk.Entry(frm)
        _style_entry(self._ent_dilution)
        self._ent_dilution.insert(0, str(CFG.DEFAULT_DILUTION_RATIO))
        self._ent_dilution.grid(row=2, column=1, padx=PAD, pady=6)

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
        lbl_dur.grid(row=3, column=0, sticky="e", padx=PAD, pady=6)

        self._ent_duration = tk.Entry(frm)
        _style_entry(self._ent_duration)
        self._ent_duration.insert(0, "24")
        self._ent_duration.grid(row=3, column=1, padx=PAD, pady=6)

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
        chk.grid(row=4, column=0, columnspan=3, pady=10)

        # --- Start button ---
        btn_start = tk.Button(frm, text="▶  Start Brew", command=self._on_start)
        _style_button(btn_start)
        btn_start.config(bg=CFG.UI_OK, fg="#000", font=FONT_LG)
        btn_start.grid(row=5, column=0, columnspan=3, pady=20)

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
        hdr.pack(pady=(0, 8))

        # --- Alert banner ---
        self._lbl_alert = tk.Label(outer, text="", fg=CFG.UI_WARN)
        _style_label(self._lbl_alert, FONT_SM)
        self._lbl_alert.pack()

        # --- Stats grid ---
        grid = tk.Frame(outer, bg=CFG.UI_BG_COLOR)
        grid.pack(fill="both", expand=True, pady=5)

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
            lbl_name.grid(row=row, column=col * 2, sticky="e", padx=(15, 5), pady=6)

            lbl_val = tk.Label(grid, text="—", anchor="w")
            _style_label(lbl_val, FONT_MD)
            lbl_val.config(fg=CFG.UI_ACCENT)
            lbl_val.grid(row=row, column=col * 2 + 1, sticky="w", padx=(0, 15), pady=6)
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
            thickness=22,
        )
        self._progress = ttk.Progressbar(
            outer, orient="horizontal", length=700,
            mode="determinate", style="brew.Horizontal.TProgressbar",
        )
        self._progress.pack(pady=8)

        # --- Button row ---
        btn_frame = tk.Frame(outer, bg=CFG.UI_BG_COLOR)
        btn_frame.pack(pady=6)

        self._btn_end_fill = tk.Button(
            btn_frame, text="End Fill Now", command=self._on_end_fill,
        )
        _style_button(self._btn_end_fill)
        self._btn_end_fill.pack(side="left", padx=8)

        btn_stop = tk.Button(
            btn_frame, text="⛔  Emergency Stop", command=self._on_emergency_stop,
        )
        _style_button(btn_stop)
        btn_stop.config(bg=CFG.UI_WARN, fg="#000")
        btn_stop.pack(side="left", padx=8)

        self._btn_new = tk.Button(
            btn_frame, text="New Cycle", command=self._on_new_cycle, state="disabled",
        )
        _style_button(self._btn_new)
        self._btn_new.pack(side="left", padx=8)

        self._btn_stop_cycle = tk.Button(
            btn_frame, text="Stop Cycle", command=self._on_stop_cycle, state="disabled",
        )
        _style_button(self._btn_stop_cycle)
        self._btn_stop_cycle.pack(side="left", padx=8)

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
        elif phase == Phase.COMPLETE.value:
            self._btn_end_fill.config(state="disabled")
            self._btn_new.config(state="normal")
            self._btn_stop_cycle.config(state="disabled")
        else:
            self._btn_end_fill.config(state="disabled")
            self._btn_new.config(state="disabled")
            self._btn_stop_cycle.config(state=("normal" if phase == Phase.BREW.value else "disabled"))

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
