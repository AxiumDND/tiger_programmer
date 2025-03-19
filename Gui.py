#!/usr/bin/env python3
"""
Integrated Levels Sheet and Relay Control Application
--------------------------------------------------------
This application uses a Tkinter Notebook with two pages:

1. Relay Control Page:
   - Provides buttons to control relays via an FTDI device.
   - Offers various relay modes (e.g., Test All, Programming, Reset, etc.).
   - Uses threading to keep the UI responsive during hardware operations.
   - **Keyboard Support:** When the window is focused, pressing keys "0"-"9" triggers the corresponding relay.

2. Levels Sheet Page (Channel Configuration):
   - Displays a configurable table for channels with 15 columns:
     Channel, Zone, Dim Ref, Name, Type, and 10 Scene columns.
   - Each scene cell includes a two‑digit Spinbox (with default values) and a Play button.
   - Supports CSV import/export of the table configuration.
   - Provides a “Program Scene” feature to send level values via relay commands.
   - Provides an “Allocate to Zones” feature that:
       • Prompts for a scene number and a zone.
       • Executes a fixed zone-selection sequence using the relay page’s functions:
         For Zone Left: fixed sequence (R8, R7, R1, R1) then send the zone digit.
         For Zone Right: fixed sequence (R8, R7, R1, R2) then send the zone digit.
       • Then enters programming mode and programs only channels whose zone equals the selected zone.
   - Uses a shared log area (“foot log”) at the bottom of the window.
   - The Program Scene, Allocate, and Play ("P") buttons are locked until their sequences complete.
   - When updating the number of channels, existing data for channels that remain is preserved.

Additional changes:
  - The shared log area has a black background with light-gray text.
  - The extra white area on the right of the table is removed by setting dark backgrounds on the Canvas and its scrollable frame.
  - The scrollable frame in the Levels Sheet now uses a tk.Frame (instead of ttk.Frame) to support the background option.
  - The "Type" combobox options have been updated to: "Dimmed", "Switched", "Switched1to10".
  - The "Zone" combobox in the channel rows now offers options "1" through "9" and "0".
"""

import os
import csv
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from pyftdi.gpio import GpioMpsseController

# Global log text widget; will be assigned in main()
global_log_text = None

def global_log(message):
    """Append a message to the global (shared) log text widget."""
    if global_log_text:
        global_log_text.config(state=tk.NORMAL)
        global_log_text.insert(tk.END, f"{message}\n")
        global_log_text.see(tk.END)
        global_log_text.config(state=tk.DISABLED)

def clear_global_log():
    """Clear the global log text widget."""
    if global_log_text:
        global_log_text.config(state=tk.NORMAL)
        global_log_text.delete("1.0", tk.END)
        global_log_text.config(state=tk.DISABLED)

# Mapping for relays: keys "0" to "9" are mapped to integer pins.
RELAY_PINS = {str(i): i for i in range(10)}

###############################################################################
# RelayControlApp Class
###############################################################################
class RelayControlApp:
    """
    Relay Control page class.
    Manages hardware initialization, relay command sequences,
    and keyboard input to trigger relays.
    """
    def __init__(self, master):
        self.master = master  # Parent frame for Relay Control page.
        self.duration_var = tk.DoubleVar(value=0.5)
        self.status_var = tk.StringVar(value="Initializing...")
        self.hardware_ready = False
        self.current_state = None
        self.state_lock = threading.Lock()
        self.create_widgets()
        self.init_hardware()
        # Bind key events for keyboard control.
        self.master.bind("<Key>", self.key_handler)

    def create_widgets(self):
        main_frame = ttk.Frame(self.master, padding=5)
        main_frame.pack(fill=tk.BOTH, expand=True)
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding=5)
        status_frame.pack(fill=tk.X, pady=3)
        ttk.Label(status_frame, textvariable=self.status_var).pack(fill=tk.X)
        control_frame = ttk.LabelFrame(main_frame, text="Relay Control", padding=5)
        control_frame.pack(fill=tk.BOTH, expand=True, pady=3)
        duration_frame = ttk.Frame(control_frame)
        duration_frame.pack(fill=tk.X, pady=3)
        ttk.Label(duration_frame, text="Duration (s):").pack(side=tk.LEFT, padx=3)
        ttk.Spinbox(duration_frame, from_=0.1, to=10.0, increment=0.1,
                    textvariable=self.duration_var, width=4).pack(side=tk.LEFT, padx=3)
        relay_frame = ttk.Frame(control_frame)
        relay_frame.pack(fill=tk.BOTH, expand=True, pady=3)
        for i in range(10):
            btn = ttk.Button(relay_frame, text=f"R{i}",
                             command=lambda r=str(i): self.toggle_relay(r))
            btn.grid(row=i//5, column=i%5, padx=3, pady=3, sticky="nsew")
        for i in range(2):
            relay_frame.grid_rowconfigure(i, weight=1)
        for i in range(5):
            relay_frame.grid_columnconfigure(i, weight=1)
        ttk.Button(control_frame, text="Test All Relays", command=self.test_all_relays).pack(fill=tk.X, pady=3)
        ttk.Button(control_frame, text="Programming Mode", command=self.programming_mode).pack(fill=tk.X, pady=3)
        ttk.Button(control_frame, text="Exit Prog Mode", command=self.exit_programming_mode).pack(fill=tk.X, pady=3)
        ttk.Button(control_frame, text="Reset", command=self.reset_mode).pack(fill=tk.X, pady=3)
        additional_frame = ttk.LabelFrame(main_frame, text="Additional Modes", padding=5)
        additional_frame.pack(fill=tk.BOTH, expand=True, pady=3)
        modes = [
            ("Scene Mode", lambda: self.scene_mode("1")),
            ("Channel Mode", self.channel_mode),
            ("Level Mode", self.level_mode),
            ("Fade Short", self.fade_short_mode),
            ("Fade Long", self.fade_long_mode),
            ("Circuit Act.", self.circuit_activation),
            ("Copy", self.copy_mode),
            ("Zone Left", self.zone_left),
            ("Zone Right", self.zone_right),
        ]
        for idx, (label, cmd) in enumerate(modes):
            row = idx // 3
            col = idx % 3
            btn = ttk.Button(additional_frame, text=label, command=cmd)
            btn.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")
        for i in range(3):
            additional_frame.grid_columnconfigure(i, weight=1)
        shortcuts_frame = ttk.LabelFrame(main_frame, text="Shortcuts", padding=5)
        shortcuts_frame.pack(fill=tk.BOTH, expand=True, pady=3)
        shortcut_modes = [
            ("Quick Scene", lambda: self._double_press_mode_thread("Quick Scene", "1", "5")),
            ("Quick Circuit", lambda: self._double_press_mode_thread("Quick Circuit", "2", "6")),
            ("Quick Level", lambda: self._double_press_mode_thread("Quick Level", "3", "7")),
            ("Quick Fade", lambda: self._double_press_mode_thread("Quick Fade", "4", "8")),
        ]
        for idx, (label, cmd) in enumerate(shortcut_modes):
            btn = ttk.Button(shortcuts_frame, text=label, command=cmd)
            btn.grid(row=0, column=idx, padx=3, pady=3, sticky="nsew")
        for i in range(4):
            shortcuts_frame.grid_columnconfigure(i, weight=1)

    def key_handler(self, event):
        """Handle keypress events. If a digit key is pressed, trigger the corresponding relay."""
        if event.char in "0123456789":
            self.log(f"Key pressed: {event.char}")
            self.toggle_relay(event.char)

    def log(self, message):
        global_log(message)

    def init_hardware(self):
        threading.Thread(target=self._init_hardware_thread, daemon=True).start()

    def _init_hardware_thread(self):
        try:
            self.gpio = GpioMpsseController()
            self.gpio.configure('ftdi://ftdi:232h/1', direction=0xFFFF, frequency=6000000)
            with self.state_lock:
                self.current_state = 0xFFFF
                self.gpio.write(self.current_state)
            self.hardware_ready = True
            self.status_var.set("Hardware ready")
            self.log("Hardware initialized. All relays OFF.")
        except Exception as e:
            self.hardware_ready = False
            self.status_var.set("Hardware init failed")
            self.log(f"Error: {e}")
            messagebox.showerror("Init Error", str(e))

    def toggle_relay(self, relay_number):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._toggle_relay_thread, args=(relay_number,), daemon=True).start()

    def _toggle_relay_thread(self, relay_number):
        duration = self.duration_var.get()
        pin = RELAY_PINS[relay_number]
        pin_mask = 1 << pin
        self.log(f"R{relay_number} ON")
        with self.state_lock:
            self.current_state &= ~pin_mask
            self.gpio.write(self.current_state)
        time.sleep(duration)
        with self.state_lock:
            self.current_state |= pin_mask
            self.gpio.write(self.current_state)
        self.log(f"R{relay_number} OFF")

    def test_all_relays(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._test_all_relays_thread, daemon=True).start()

    def _test_all_relays_thread(self):
        for relay in sorted(RELAY_PINS.keys()):
            self._toggle_relay_thread(relay)
            time.sleep(0.2)

    def programming_mode(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._programming_mode_thread, daemon=True).start()

    def _programming_mode_thread(self):
        self.log("Prog Mode: Start")
        with self.state_lock:
            self.current_state &= ~((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
        self.log("Prog Mode: R0 & R9 held")
        time.sleep(0.3)
        for relay in ["2", "1", "2", "1"]:
            pin = RELAY_PINS[relay]
            pin_mask = 1 << pin
            self.log(f"Prog Mode: R{relay} ON")
            with self.state_lock:
                self.current_state &= ~pin_mask
                self.gpio.write(self.current_state)
            time.sleep(self.duration_var.get())
            with self.state_lock:
                self.current_state |= pin_mask
                self.gpio.write(self.current_state)
            self.log(f"Prog Mode: R{relay} OFF")
            time.sleep(0.1)
        with self.state_lock:
            self.current_state |= ((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
        self.log("Prog Mode: End")

    def exit_programming_mode(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Exit Prog Mode", "8"), daemon=True).start()

    def reset_mode(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        if messagebox.askyesno("Reset Confirm", "Reset?"):
            threading.Thread(target=self._sequence_mode_thread, args=("Reset", ["4", "5", "6", "6"]), daemon=True).start()
        else:
            self.log("Reset canceled.")

    def _single_press_mode_thread(self, mode_name, relay_key):
        self.log(f"{mode_name}: Start")
        with self.state_lock:
            self.current_state &= ~((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
        self.log(f"{mode_name}: R0 & R9 held")
        time.sleep(0.3)
        pin = RELAY_PINS[relay_key]
        pin_mask = 1 << pin
        self.log(f"{mode_name}: R{relay_key} ON")
        with self.state_lock:
            self.current_state &= ~pin_mask
            self.gpio.write(self.current_state)
        time.sleep(self.duration_var.get())
        with self.state_lock:
            self.current_state |= pin_mask
            self.gpio.write(self.current_state)
        self.log(f"{mode_name}: R{relay_key} OFF")
        time.sleep(0.1)
        with self.state_lock:
            self.current_state |= ((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
        self.log(f"{mode_name}: End")

    def _sequence_mode_thread(self, mode_name, sequence):
        self.log(f"{mode_name}: Start")
        with self.state_lock:
            self.current_state &= ~((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
        self.log(f"{mode_name}: R0 & R9 held")
        time.sleep(0.3)
        for relay in sequence:
            pin = RELAY_PINS[relay]
            pin_mask = 1 << pin
            self.log(f"{mode_name}: R{relay} ON")
            with self.state_lock:
                self.current_state &= ~pin_mask
                self.gpio.write(self.current_state)
            time.sleep(self.duration_var.get())
            with self.state_lock:
                self.current_state |= pin_mask
                self.gpio.write(self.current_state)
            self.log(f"{mode_name}: R{relay} OFF")
            time.sleep(0.1)
        with self.state_lock:
            self.current_state |= ((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
        self.log(f"{mode_name}: End")

    def _double_press_mode_thread(self, mode_name, relay_key1, relay_key2):
        self.log(f"{mode_name}: Start")
        with self.state_lock:
            self.current_state &= ~((1 << RELAY_PINS[relay_key1]) | (1 << RELAY_PINS[relay_key2]))
            self.gpio.write(self.current_state)
        self.log(f"{mode_name}: R{relay_key1} & R{relay_key2} ON")
        time.sleep(self.duration_var.get())
        with self.state_lock:
            self.current_state |= ((1 << RELAY_PINS[relay_key1]) | (1 << RELAY_PINS[relay_key2]))
            self.gpio.write(self.current_state)
        self.log(f"{mode_name}: R{relay_key1} & R{relay_key2} OFF")

    def scene_mode(self, scene_digit):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread,
                         args=(f"Scene Mode ({scene_digit})", scene_digit),
                         daemon=True).start()

    def channel_mode(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Channel Mode", "2"), daemon=True).start()

    def level_mode(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Level Mode", "3"), daemon=True).start()

    def fade_short_mode(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Fade Short", "4"), daemon=True).start()

    def fade_long_mode(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Fade Long", "5"), daemon=True).start()

    def circuit_activation(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Circuit Act.", "6"), daemon=True).start()

    def copy_mode(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Copy", "7"), daemon=True).start()

    def zone_left(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._sequence_mode_thread, args=("Zone Left", ["8", "7", "1", "1"]), daemon=True).start()

    def zone_right(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._sequence_mode_thread, args=("Zone Right", ["8", "7", "1", "2"]), daemon=True).start()

    # UPDATED: program_zone() now implements the desired sequence for both left and right.
    def program_zone(self, zone):
        # Zone Left Sequence:
        self.log("Zone Left: Start")
        with self.state_lock:
            self.current_state &= ~((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
        self.log("Zone Left: R0 & R9 held")
        time.sleep(0.5)
        for relay in ["8", "7", "1", "1"]:
            pin = RELAY_PINS[relay]
            pin_mask = 1 << pin
            self.log(f"Zone Left: {relay} ON")
            with self.state_lock:
                self.current_state &= ~pin_mask
                self.gpio.write(self.current_state)
            time.sleep(0.5)
            with self.state_lock:
                self.current_state |= pin_mask
                self.gpio.write(self.current_state)
            self.log(f"Zone Left: {relay} OFF")
            time.sleep(0.3)
        self.log("Zone Left: R0 & R9 released")
        self.log("Zone Left Digit: Start")
        self._single_press_mode_thread("Zone Left Digit", zone)
        self.log("Zone Left Digit: End")
        self.log("Zone Left: End")
        
        # Zone Right Sequence:
        self.log("Zone Right: Start")
        with self.state_lock:
            self.current_state &= ~((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
        self.log("Zone Right: R0 & R9 held")
        time.sleep(0.5)
        for relay in ["8", "7", "1", "2"]:
            pin = RELAY_PINS[relay]
            pin_mask = 1 << pin
            self.log(f"Zone Right: {relay} ON")
            with self.state_lock:
                self.current_state &= ~pin_mask
                self.gpio.write(self.current_state)
            time.sleep(0.5)
            with self.state_lock:
                self.current_state |= pin_mask
                self.gpio.write(self.current_state)
            self.log(f"Zone Right: {relay} OFF")
            time.sleep(0.3)
        self.log("Zone Right: R0 & R9 released")
        self.log("Zone Right Digit: Start")
        self._single_press_mode_thread("Zone Right Digit", zone)
        self.log("Zone Right Digit: End")
        with self.state_lock:
            self.current_state |= ((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
        self.log("Zone Right: End")

    def allocate_channel(self, channel, allocation_digit):
        ch_str = str(channel).zfill(2)
        self.log(f"Allocating channel {channel} with allocation digit {allocation_digit}")
        for digit in ch_str:
            self._single_press_mode_thread("Quick Channel Digit", digit)
            time.sleep(0.5)
        self._single_press_mode_thread("Circuit Act Digit", allocation_digit)

    def on_allocate_to_zones(self):
        zone = simpledialog.askstring("Select Zone", "Enter zone number (0-9):")
        if zone is None:
            return
        if zone not in [str(i) for i in range(10)]:
            messagebox.showerror("Input Error", "Invalid zone number.")
            return
        if not messagebox.askyesno("Confirmation", f"Allocate channels to zone {zone}?"):
            return
        self.allocate_button.config(state=tk.DISABLED)
        self.relay_controller.program_zone(zone)
        self.relay_controller.exit_programming_mode()
        time.sleep(0.8)
        self.relay_controller.programming_mode()
        time.sleep(0.8)
        for idx, row in enumerate(self.rows, start=1):
            alloc_digit = "1" if row["zone"].get() == zone else "0"
            self.allocate_channel(idx, alloc_digit)
            time.sleep(0.5)
        self.relay_controller.exit_programming_mode()
        global_log("Allocation sequence complete.")
        self.allocate_button.config(state=tk.NORMAL)

    def quick_scene(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._double_press_mode_thread, args=("Quick Scene", "1", "5"), daemon=True).start()

    def quick_circuit(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._double_press_mode_thread, args=("Quick Circuit", "2", "6"), daemon=True).start()

    def quick_level(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._double_press_mode_thread, args=("Quick Level", "3", "7"), daemon=True).start()

    def quick_fade(self):
        if not self.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._double_press_mode_thread, args=("Quick Fade", "4", "8"), daemon=True).start()

    def on_closing(self):
        if self.hardware_ready and self.gpio and self.gpio.is_connected:
            try:
                with self.state_lock:
                    self.current_state = 0xFFFF
                    self.gpio.write(self.current_state)
                self.gpio.close()
            except Exception as e:
                self.log(f"Error closing GPIO: {e}")
        self.master.quit()
        self.master.destroy()

    def play_scene_level(self, channel, scene_digit, level_value, callback=None):
        self.log(f"Play ch {channel}, scene {scene_digit} = {level_value}")
        threading.Thread(target=self._play_scene_level_sequence,
                         args=(channel, scene_digit, level_value, callback),
                         daemon=True).start()

    def _play_scene_level_sequence(self, channel, scene_digit, level_value, callback=None):
        rc = self
        rc.exit_programming_mode()
        time.sleep(0.8)
        rc.programming_mode()
        time.sleep(0.8)
        rc.scene_mode(scene_digit)
        time.sleep(0.8)
        ch_str = str(channel).zfill(2)
        rc.log(f"Channel digits: {ch_str}")
        for digit in ch_str:
            rc._single_press_mode_thread("Quick Circuit Digit", digit)
            time.sleep(0.5)
        lvl_str = str(int(level_value)).zfill(2)
        rc.log(f"Level digits: {lvl_str}")
        for digit in lvl_str:
            rc._single_press_mode_thread("Quick Level Digit", digit)
            time.sleep(0.5)
        rc.exit_programming_mode()
        rc.log(f"Play done for ch {channel}, scene {scene_digit}")
        if callback:
            self.master.after(0, callback)

###############################################################################
# ChannelConfigPage Class
###############################################################################
class ChannelConfigPage:
    """
    Levels Sheet (Channel Configuration) page class.
    Provides a table for channel configuration, CSV import/export functionality.
    """
    def __init__(self, master, relay_controller=None):
        self.master = master
        self.relay_controller = relay_controller
        self.rows = []
        self.scene_labels = [f"Scene {i}" for i in range(1, 10)] + ["Scene 0"]
        self.scene_defaults = ["90", "70", "50", "30", "99", "99", "99", "99", "99", "00"]
        self.create_widgets()

    def create_widgets(self):
        header_frame = ttk.Frame(self.master)
        header_frame.pack(fill=tk.X, pady=5)
        ttk.Label(header_frame, text="Site Name:").grid(row=0, column=0, padx=5)
        self.site_name_entry = ttk.Entry(header_frame)
        self.site_name_entry.grid(row=0, column=1, padx=5)
        ttk.Label(header_frame, text="Date:").grid(row=0, column=2, padx=5)
        self.date_entry = ttk.Entry(header_frame)
        self.date_entry.grid(row=0, column=3, padx=5)
        controls_frame = ttk.Frame(self.master)
        controls_frame.pack(fill=tk.X, pady=5)
        ttk.Label(controls_frame, text="Number of Channels:").pack(side=tk.LEFT, padx=5)
        self.num_channels_entry = ttk.Entry(controls_frame, width=5)
        self.num_channels_entry.pack(side=tk.LEFT, padx=5)
        self.num_channels_entry.insert(0, "18")
        ttk.Button(controls_frame, text="Generate Table", command=self.on_generate_table).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls_frame, text="Save CSV", command=self.on_save_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls_frame, text="Import CSV", command=self.on_import_csv).pack(side=tk.LEFT, padx=5)
        self.program_button = ttk.Button(controls_frame, text="Program Scene", command=self.on_program_scene_levels)
        self.program_button.pack(side=tk.LEFT, padx=5)
        self.allocate_button = ttk.Button(controls_frame, text="Allocate to Zones", command=self.on_allocate_to_zones)
        self.allocate_button.pack(side=tk.LEFT, padx=5)
        table_container = ttk.Frame(self.master)
        table_container.pack(fill=tk.BOTH, expand=True, pady=5)
        self.canvas = tk.Canvas(table_container, bg="#121212")
        scrollbar = ttk.Scrollbar(table_container, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="#121212")
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.create_headers()
        self.on_generate_table()
        global_log("Levels Sheet ready.")

    def create_headers(self):
        headers = ["Channel", "Zone", "Dim Ref", "Name", "Type"] + self.scene_labels
        for col, header in enumerate(headers):
            label = ttk.Label(self.scrollable_frame, text=header)
            label.grid(row=0, column=col, padx=2, pady=2, sticky="nsew")
            if header == "Name":
                self.scrollable_frame.grid_columnconfigure(col, weight=3)
            elif header == "Type":
                self.scrollable_frame.grid_columnconfigure(col, weight=2)
            else:
                self.scrollable_frame.grid_columnconfigure(col, weight=1)

    def create_row(self, row_num):
        row = {}
        ttk.Label(self.scrollable_frame, text=str(row_num)).grid(row=row_num, column=0, padx=2, pady=2)
        row["zone"] = ttk.Combobox(self.scrollable_frame, values=["1","2","3","4","5","6","7","8","9","0"], width=3)
        row["zone"].set("1")
        row["zone"].grid(row=row_num, column=1, padx=2, pady=2)
        row["dim_ref"] = ttk.Entry(self.scrollable_frame, width=8)
        row["dim_ref"].grid(row=row_num, column=2, padx=2, pady=2)
        row["name"] = ttk.Entry(self.scrollable_frame)
        row["name"].grid(row=row_num, column=3, padx=2, pady=2, sticky="ew")
        row["type"] = ttk.Combobox(self.scrollable_frame, values=["Dimmed", "Switched", "Switched1to10"])
        row["type"].set("Dimmed")
        row["type"].grid(row=row_num, column=4, padx=2, pady=2, sticky="ew")
        row["scenes"] = []
        for i in range(10):
            scene_frame = ttk.Frame(self.scrollable_frame)
            scene_frame.grid(row=row_num, column=5+i, padx=2, pady=2)
            default_val = "00" if i==9 else (["90", "70", "50", "30", "99", "99", "99", "99", "99"][i])
            spinbox = ttk.Spinbox(scene_frame, from_=0, to=99, width=3, format="%02.0f",
                                  command=lambda: None, foreground="black")
            spinbox.set(default_val)
            spinbox.pack(side=tk.LEFT)
            scene_digit = str(i + 1) if i < 9 else "0"
            p_button = ttk.Button(scene_frame, text="P", width=2)
            p_button['command'] = lambda b=p_button, ch=row_num, sd=scene_digit, sp=spinbox: self.play_level_with_lock(b, ch, sd, sp.get())
            p_button.pack(side=tk.LEFT, padx=1)
            row["scenes"].append(spinbox)
        return row

    def play_level_with_lock(self, button, channel, scene_digit, level_value):
        button.config(state=tk.DISABLED)
        self.relay_controller.play_scene_level(channel, scene_digit, level_value,
                                               callback=lambda: button.config(state=tk.NORMAL))

    def rebuild_table(self, num_channels):
        old_data = self.read_table_data() if self.rows else []
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.create_headers()
        self.rows = []
        for i in range(1, num_channels + 1):
            row = self.create_row(i)
            self.rows.append(row)
        for i in range(min(num_channels, len(old_data))):
            data = old_data[i]
            row = self.rows[i]
            row["zone"].set(data["zone"])
            row["dim_ref"].delete(0, tk.END)
            row["dim_ref"].insert(0, data["dimRef"])
            row["name"].delete(0, tk.END)
            row["name"].insert(0, data["name"])
            row["type"].set(data["type"])
            for j, spin in enumerate(row["scenes"]):
                spin.delete(0, tk.END)
                spin.insert(0, data["scenes"][j])

    def on_generate_table(self):
        try:
            num_channels = int(self.num_channels_entry.get())
            if num_channels < 1:
                raise ValueError("Number of channels must be positive")
            self.rebuild_table(num_channels)
        except ValueError as e:
            messagebox.showerror("Input Error", str(e))

    def on_save_csv(self):
        csv_data = self.generate_csv_data()
        filename = filedialog.asksaveasfilename(defaultextension=".csv",
                                                filetypes=[("CSV Files", "*.csv")])
        if filename:
            with open(filename, "w", newline="") as f:
                f.write(csv_data)
            global_log("CSV saved successfully.")

    def on_import_csv(self):
        filename = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if filename:
            try:
                with open(filename, "r") as f:
                    csv_text = f.read()
                parsed = self.parse_csv(csv_text)
                self.site_name_entry.delete(0, tk.END)
                self.site_name_entry.insert(0, parsed["siteName"])
                self.date_entry.delete(0, tk.END)
                self.date_entry.insert(0, parsed["siteDate"])
                self.num_channels_entry.delete(0, tk.END)
                self.num_channels_entry.insert(0, str(len(parsed["rows"])))
                self.rebuild_table(len(parsed["rows"]))
                for idx, entry in enumerate(parsed["rows"]):
                    if idx < len(self.rows):
                        row = self.rows[idx]
                        row["zone"].set(entry.get("zone", "1"))
                        row["dim_ref"].delete(0, tk.END)
                        row["dim_ref"].insert(0, entry.get("dimRef", ""))
                        row["name"].delete(0, tk.END)
                        row["name"].insert(0, entry.get("name", ""))
                        row["type"].set(entry.get("type", "Dimmed"))
                        scenes = entry.get("scenes", [])
                        for i, spin in enumerate(row["scenes"]):
                            spin.delete(0, tk.END)
                            if i < len(scenes):
                                spin.insert(0, scenes[i].zfill(2))
                global_log("CSV imported successfully.")
            except Exception as e:
                messagebox.showerror("Import CSV", f"Error importing CSV: {e}")

    def generate_csv_data(self):
        site_name = self.site_name_entry.get().strip()
        site_date = self.date_entry.get().strip()
        lines = []
        line1 = ["Site Name:", site_name] + [""] * 13
        lines.append(",".join(line1))
        line2 = ["Date:", site_date] + [""] * 13
        lines.append(",".join(line2))
        headers = ["Channel", "Zone", "Dim Ref", "Name", "Type"] + self.scene_labels
        lines.append(",".join(headers))
        table_data = self.read_table_data()
        for entry in table_data:
            row = [str(entry["channel"]), entry["zone"], entry["dimRef"], entry["name"], entry["type"]] + entry["scenes"]
            lines.append(",".join(row))
        return "\n".join(lines)

    def read_table_data(self):
        data = []
        for idx, row in enumerate(self.rows, start=1):
            entry = {
                "channel": idx,
                "zone": row["zone"].get(),
                "dimRef": row["dim_ref"].get(),
                "name": row["name"].get(),
                "type": row["type"].get(),
                "scenes": [spin.get() for spin in row["scenes"]]
            }
            data.append(entry)
        return data

    def parse_csv(self, csv_text):
        lines = [line for line in csv_text.splitlines() if line.strip() != ""]
        if len(lines) < 4:
            raise ValueError("CSV does not have enough lines.")
        site_name = lines[0].split(",")[1].strip()
        raw_date = lines[1].split(",")[1].strip()
        site_date = raw_date
        data_rows = []
        for line in lines[3:]:
            cells = [cell.strip() for cell in line.split(",")]
            if len(cells) < 15:
                continue
            entry = {
                "channel": cells[0],
                "zone": cells[1],
                "dimRef": cells[2],
                "name": cells[3],
                "type": cells[4],
                "scenes": cells[5:15]
            }
            data_rows.append(entry)
        return {"siteName": site_name, "siteDate": site_date, "rows": data_rows}

    def on_program_scene_levels(self):
        scene_digit = simpledialog.askstring("Select Scene", "Enter scene number (1-9 or 0):")
        if scene_digit is None:
            return
        if scene_digit not in [str(i) for i in range(1, 10)] + ["0"]:
            messagebox.showerror("Input Error", "Invalid scene number.")
            return
        zone = simpledialog.askstring("Select Zone", "Enter zone number (0-9):")
        if zone is None:
            return
        if zone not in [str(i) for i in range(10)]:
            messagebox.showerror("Input Error", "Invalid zone number.")
            return
        if not messagebox.askyesno("Confirmation", f"Program scene {scene_digit} for zone {zone}?"):
            return
        self.program_button.config(state=tk.DISABLED)
        self.relay_controller.program_zone(zone)
        threading.Thread(target=self.program_scene_levels_sequence, args=(scene_digit, zone), daemon=True).start()

    def program_scene_levels_sequence(self, scene_digit, zone):
        rc = self.relay_controller
        global_log("Starting programming sequence...")
        rc.exit_programming_mode()
        time.sleep(0.8)
        for idx, row in enumerate(self.rows, start=1):
            if row["zone"].get() != zone:
                continue
            scene_index = 9 if scene_digit == "0" else int(scene_digit) - 1
            level_value = row["scenes"][scene_index].get()
            global_log(f"Programming channel {idx} with level {level_value} for scene {scene_digit} (zone {zone})...")
            rc.programming_mode()
            time.sleep(0.8)
            rc.scene_mode(scene_digit)
            time.sleep(0.8)
            ch_str = str(idx).zfill(2)
            for digit in ch_str:
                rc._single_press_mode_thread("Quick Circuit Digit", digit)
                time.sleep(0.5)
            rc._single_press_mode_thread("Circuit Act Digit", "1")
            global_log(f"Channel {idx} programmed.")
            time.sleep(0.8)
        rc.exit_programming_mode()
        global_log("Programming sequence complete.")
        self.master.after(0, lambda: self.program_button.config(state=tk.NORMAL))

    def allocate_channel(self, channel, allocation_digit):
        ch_str = str(channel).zfill(2)
        self.relay_controller.log(f"Allocating channel {channel} with allocation digit {allocation_digit}")
        for digit in ch_str:
            self.relay_controller._single_press_mode_thread("Quick Channel Digit", digit)
            time.sleep(0.5)
        self.relay_controller._single_press_mode_thread("Circuit Act Digit", allocation_digit)

    def on_allocate_to_zones(self):
        zone = simpledialog.askstring("Select Zone", "Enter zone number (0-9):")
        if zone is None:
            return
        if zone not in [str(i) for i in range(10)]:
            messagebox.showerror("Input Error", "Invalid zone number.")
            return
        if not messagebox.askyesno("Confirmation", f"Allocate channels to zone {zone}?"):
            return
        self.allocate_button.config(state=tk.DISABLED)
        self.relay_controller.program_zone(zone)
        self.relay_controller.exit_programming_mode()
        time.sleep(0.8)
        self.relay_controller.programming_mode()
        time.sleep(0.8)
        for idx, row in enumerate(self.rows, start=1):
            alloc_digit = "1" if row["zone"].get() == zone else "0"
            self.allocate_channel(idx, alloc_digit)
            time.sleep(0.5)
        self.relay_controller.exit_programming_mode()
        global_log("Allocation sequence complete.")
        self.allocate_button.config(state=tk.NORMAL)

    def quick_scene(self):
        if not self.relay_controller.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._double_press_mode_thread, args=("Quick Scene", "1", "5"), daemon=True).start()

    def quick_circuit(self):
        if not self.relay_controller.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._double_press_mode_thread, args=("Quick Circuit", "2", "6"), daemon=True).start()

    def quick_level(self):
        if not self.relay_controller.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._double_press_mode_thread, args=("Quick Level", "3", "7"), daemon=True).start()

    def quick_fade(self):
        if not self.relay_controller.hardware_ready:
            messagebox.showwarning("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._double_press_mode_thread, args=("Quick Fade", "4", "8"), daemon=True).start()

    def on_closing(self):
        if self.hardware_ready and self.gpio and self.gpio.is_connected:
            try:
                with self.state_lock:
                    self.current_state = 0xFFFF
                    self.gpio.write(self.current_state)
                self.gpio.close()
            except Exception as e:
                self.log(f"Error closing GPIO: {e}")
        self.master.quit()
        self.master.destroy()

    def play_scene_level(self, channel, scene_digit, level_value, callback=None):
        self.log(f"Play ch {channel}, scene {scene_digit} = {level_value}")
        threading.Thread(target=self._play_scene_level_sequence,
                         args=(channel, scene_digit, level_value, callback),
                         daemon=True).start()

    def _play_scene_level_sequence(self, channel, scene_digit, level_value, callback=None):
        rc = self
        rc.exit_programming_mode()
        time.sleep(0.8)
        rc.programming_mode()
        time.sleep(0.8)
        rc.scene_mode(scene_digit)
        time.sleep(0.8)
        ch_str = str(channel).zfill(2)
        rc.log(f"Channel digits: {ch_str}")
        for digit in ch_str:
            rc._single_press_mode_thread("Quick Circuit Digit", digit)
            time.sleep(0.5)
        lvl_str = str(int(level_value)).zfill(2)
        rc.log(f"Level digits: {lvl_str}")
        for digit in lvl_str:
            rc._single_press_mode_thread("Quick Level Digit", digit)
            time.sleep(0.5)
        rc.exit_programming_mode()
        rc.log(f"Play done for ch {channel}, scene {scene_digit}")
        if callback:
            self.master.after(0, callback)

###############################################################################
# Main
###############################################################################
def main():
    os.environ["BLINKA_FT232H"] = "1"
    os.environ["PYFTDI_BACKEND"] = "libusb1"
    root = tk.Tk()
    root.title("Levels Sheet and Relay Control")
    root.geometry("1366x768")
    style = ttk.Style()
    style.theme_use("clam")
    style.configure(".", background="#121212", foreground="#e0e0e0", font=("Arial", 8))
    style.configure("TLabel", background="#121212", foreground="#e0e0e0")
    style.configure("TEntry", fieldbackground="#ffffff", foreground="#000000")
    style.configure("TButton", background="#1e1e1e", foreground="#e0e0e0")
    style.configure("TCombobox", fieldbackground="#333333", foreground="#ffffff")
    style.configure("TNotebook.Tab", foreground="black", background="#cccccc")
    style.map("TNotebook.Tab", foreground=[("selected", "black")], background=[("selected", "#dddddd")])
    notebook = ttk.Notebook(root)
    notebook.pack(fill=tk.BOTH, expand=True)
    levels_frame = ttk.Frame(notebook, padding=5)
    notebook.add(levels_frame, text="Levels Sheet")
    relay_frame = ttk.Frame(notebook, padding=5)
    notebook.add(relay_frame, text="Relay Control")
    relay_control_app = RelayControlApp(relay_frame)
    levels_page = ChannelConfigPage(levels_frame, relay_controller=relay_control_app)
    global global_log_text
    log_frame = ttk.LabelFrame(root, text="Log", padding=5)
    log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    global_log_text = tk.Text(log_frame, height=8, state=tk.DISABLED, bg="#1c1c1c", fg="#dddddd")
    global_log_text.grid(row=0, column=0, sticky="nsew")
    clear_button = ttk.Button(log_frame, text="Clear Log", command=clear_global_log)
    clear_button.grid(row=0, column=1, sticky="ne", padx=5)
    log_frame.columnconfigure(0, weight=1)
    root.protocol("WM_DELETE_WINDOW", relay_control_app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()

