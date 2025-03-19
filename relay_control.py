"""
relay_control.py

This module provides the RelayControlApp class—a PyQt5 widget for controlling relays via an FTDI device.
It includes buttons for individual relay control, various sequence modes,
and shortcut buttons for quick operations.

Hardware operations are run in background threads.
UI updates from these threads are performed via signals to avoid cross-thread errors.
"""

import threading
import time
import usb.core

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QDoubleSpinBox, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt, pyqtSignal

from gui_logger import global_log

# Check if FT232H device is connected
SIMULATION_MODE = usb.core.find(idVendor=0x0403, idProduct=0x6014) is None

# If we're in simulation mode, use a dummy controller
if SIMULATION_MODE:
    global_log("[SIMULATION] No FT232H device found, running in simulation mode")
    
    class GpioMpsseController:
        def __init__(self):
            self._current_state = 0xFFFF  # All relays OFF (active low)
            global_log("[SIMULATION] Initializing GPIO controller")
            
        def configure(self, *args, **kwargs):
            global_log("[SIMULATION] Configuring GPIO controller")
            global_log(f"[SIMULATION] Configuration args: {args}")
            global_log(f"[SIMULATION] Configuration kwargs: {kwargs}")
            
        def write(self, state):
            # Calculate which relays changed state
            changed_bits = self._current_state ^ state
            # For each bit that changed, log which relay changed and its new state
            for i in range(10):  # We have relays 0-9
                if changed_bits & (1 << i):
                    relay_state = "OFF" if (state & (1 << i)) else "ON"
                    global_log(f"[SIMULATION] Relay R{i} -> {relay_state}")
            
            # Store the new state (binary state logging removed for clarity)
            self._current_state = state
            
        def close(self):
            global_log("[SIMULATION] Closing GPIO controller")
            global_log("[SIMULATION] Final state: All relays OFF")
            
        @property
        def is_connected(self):
            # In dummy mode, we return False so that hardware is not falsely marked as ready.
            return False
else:
    # Import the real controller if we're not in simulation mode
    from pyftdi.gpio import GpioMpsseController

# Mapping for relay pins: digits "0" to "9" map to integer pins.
RELAY_PINS = {str(i): i for i in range(10)}

class RelayControlApp(QWidget):
    # Signals to update UI elements from background threads.
    updateStatusSignal = pyqtSignal(str)
    errorSignal = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_variables()
        self.init_ui()
        # Connect signals to slots.
        self.updateStatusSignal.connect(self._update_status_slot)
        self.errorSignal.connect(self._show_error_slot)
        self.init_hardware()

    def init_variables(self):
        """Initialize control variables."""
        self.duration = 0.5  # Default duration for relay activation (in seconds).
        self.status_text = "Initializing..."
        self.hardware_ready = False
        self.current_state = 0xFFFF  # All relays OFF (active low).
        self.state_lock = threading.Lock()

    def init_ui(self):
        """Set up the UI components for relay control."""
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Status label.
        self.status_label = QLabel(self.status_text)
        main_layout.addWidget(self.status_label)

        # Duration control.
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Duration (s):"))
        self.duration_spinner = QDoubleSpinBox()
        self.duration_spinner.setRange(0.1, 10.0)
        self.duration_spinner.setValue(self.duration)
        self.duration_spinner.setSingleStep(0.1)
        duration_layout.addWidget(self.duration_spinner)
        main_layout.addLayout(duration_layout)

        # Relay buttons (R0 to R9).
        relay_btn_layout = QHBoxLayout()
        for i in range(10):
            btn = QPushButton(f"R{i}")
            btn.clicked.connect(lambda checked, r=str(i): self.toggle_relay(r))
            relay_btn_layout.addWidget(btn)
        main_layout.addLayout(relay_btn_layout)

        # Basic sequence buttons.
        basic_seq_layout = QHBoxLayout()
        test_all_btn = QPushButton("Test All Relays")
        test_all_btn.clicked.connect(self.test_all_relays)
        basic_seq_layout.addWidget(test_all_btn)

        prog_mode_btn = QPushButton("Programming Mode")
        prog_mode_btn.clicked.connect(self.programming_mode)
        basic_seq_layout.addWidget(prog_mode_btn)

        exit_prog_btn = QPushButton("Exit Prog Mode")
        exit_prog_btn.clicked.connect(self.exit_programming_mode)
        basic_seq_layout.addWidget(exit_prog_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self.reset_mode)
        basic_seq_layout.addWidget(reset_btn)
        main_layout.addLayout(basic_seq_layout)

        # Additional modes group.
        add_modes_box = QGroupBox("Additional Modes")
        add_modes_layout = QHBoxLayout()
        add_modes_box.setLayout(add_modes_layout)

        scene_mode_btn = QPushButton("Scene Mode")
        scene_mode_btn.clicked.connect(lambda: self.scene_mode("1"))
        add_modes_layout.addWidget(scene_mode_btn)

        channel_mode_btn = QPushButton("Channel Mode")
        channel_mode_btn.clicked.connect(self.channel_mode)
        add_modes_layout.addWidget(channel_mode_btn)

        level_mode_btn = QPushButton("Level Mode")
        level_mode_btn.clicked.connect(self.level_mode)
        add_modes_layout.addWidget(level_mode_btn)

        fade_short_btn = QPushButton("Fade Short")
        fade_short_btn.clicked.connect(self.fade_short_mode)
        add_modes_layout.addWidget(fade_short_btn)

        fade_long_btn = QPushButton("Fade Long")
        fade_long_btn.clicked.connect(self.fade_long_mode)
        add_modes_layout.addWidget(fade_long_btn)

        circuit_act_btn = QPushButton("Circuit Act.")
        circuit_act_btn.clicked.connect(self.circuit_activation)
        add_modes_layout.addWidget(circuit_act_btn)

        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self.copy_mode)
        add_modes_layout.addWidget(copy_btn)

        zone_left_btn = QPushButton("Zone Left")
        zone_left_btn.clicked.connect(self.zone_left)
        add_modes_layout.addWidget(zone_left_btn)

        zone_right_btn = QPushButton("Zone Right")
        zone_right_btn.clicked.connect(self.zone_right)
        add_modes_layout.addWidget(zone_right_btn)
        main_layout.addWidget(add_modes_box)

        # Shortcut buttons group.
        shortcut_box = QGroupBox("Shortcuts")
        shortcut_layout = QHBoxLayout()
        shortcut_box.setLayout(shortcut_layout)

        quick_scene_btn = QPushButton("Quick Scene")
        quick_scene_btn.clicked.connect(self.quick_scene)
        shortcut_layout.addWidget(quick_scene_btn)

        quick_circuit_btn = QPushButton("Quick Circuit")
        quick_circuit_btn.clicked.connect(self.quick_circuit)
        shortcut_layout.addWidget(quick_circuit_btn)

        quick_level_btn = QPushButton("Quick Level")
        quick_level_btn.clicked.connect(self.quick_level)
        shortcut_layout.addWidget(quick_level_btn)

        quick_fade_btn = QPushButton("Quick Fade")
        quick_fade_btn.clicked.connect(self.quick_fade)
        shortcut_layout.addWidget(quick_fade_btn)
        main_layout.addWidget(shortcut_box)

    def init_hardware(self):
        """Initialize hardware in a background thread."""
        threading.Thread(target=self._init_hardware_thread, daemon=True).start()

    def _init_hardware_thread(self):
        """Hardware initialization routine."""
        try:
            self.gpio = GpioMpsseController()
            
            if SIMULATION_MODE:
                # In simulation mode, just set up the dummy controller
                self.gpio.configure('ftdi://ftdi:232h/1', direction=0xFFFF, frequency=6000000)
                with self.state_lock:
                    self.current_state = 0xFFFF
                    self.gpio.write(self.current_state)
                self.hardware_ready = True
                self.status_text = "SIMULATION MODE"
                self.updateStatusSignal.emit(self.status_text)
                global_log("[SIMULATION] Hardware initialized in simulation mode. All relays OFF.")
            else:
                # In real hardware mode, configure the actual device
                self.gpio.configure('ftdi://ftdi:232h/1', direction=0xFFFF, frequency=6000000)
                # Don't rely on is_connected property which may not detect properly
                # Instead, try to write to the device to confirm it's working
                with self.state_lock:
                    self.current_state = 0xFFFF
                    self.gpio.write(self.current_state)
                self.hardware_ready = True
                self.status_text = "Hardware ready"
                self.updateStatusSignal.emit(self.status_text)
                global_log("Hardware initialized. All relays OFF.")
        except Exception as e:
            # Set hardware ready to True even though we're in simulation mode
            # This allows the UI to function without real hardware
            self.hardware_ready = True
            self.status_text = "SIMULATION MODE"
            self.updateStatusSignal.emit(self.status_text)
            global_log("[SIMULATION] Hardware not available, running in simulation mode")
            global_log(f"[SIMULATION] Error: {e}")
            # Don't show error dialog in simulation mode
            # self.errorSignal.emit("Init Error", str(e))

    def _update_status_slot(self, text):
        """Update the status label (in the main thread)."""
        self.status_label.setText(text)

    def _show_error_slot(self, title, message):
        """Display an error message (in the main thread)."""
        QMessageBox.critical(self, title, message)

    def toggle_relay(self, relay_number):
        """
        Toggle a relay: turn it on for the specified duration, then off.
        This runs in a separate thread.
        """
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._toggle_relay_thread, args=(relay_number,), daemon=True).start()

    def _toggle_relay_thread(self, relay_number):
        duration = self.duration_spinner.value()
        pin = RELAY_PINS[relay_number]
        pin_mask = 1 << pin
        
        # Log the action with or without simulation prefix
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] R{relay_number} ON")
        else:
            global_log(f"R{relay_number} ON")
            
        with self.state_lock:
            self.current_state &= ~pin_mask
            self.gpio.write(self.current_state)
        time.sleep(duration)
        
        with self.state_lock:
            self.current_state |= pin_mask
            self.gpio.write(self.current_state)
            
        # Log the action with or without simulation prefix
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] R{relay_number} OFF")
        else:
            global_log(f"R{relay_number} OFF")

    def test_all_relays(self):
        """Test all relays sequentially."""
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._test_all_relays_thread, daemon=True).start()

    def _test_all_relays_thread(self):
        for relay in sorted(RELAY_PINS.keys()):
            self._toggle_relay_thread(relay)
            time.sleep(0.2)

    def programming_mode(self):
        """Enter programming mode."""
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._programming_mode_thread, daemon=True).start()

    def _programming_mode_thread(self):
        if SIMULATION_MODE:
            global_log("[SIMULATION] Prog Mode: Start")
        else:
            global_log("Prog Mode: Start")
            
        with self.state_lock:
            self.current_state &= ~((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log("[SIMULATION] Prog Mode: R0 & R9 ON")
        else:
            global_log("Prog Mode: R0 & R9 ON")
            
        time.sleep(0.3)
        for relay in ["2", "1", "2", "1"]:
            pin = RELAY_PINS[relay]
            pin_mask = 1 << pin
            
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] Prog Mode: R{relay} ON")
            else:
                global_log(f"Prog Mode: R{relay} ON")
                
            with self.state_lock:
                self.current_state &= ~pin_mask
                self.gpio.write(self.current_state)
            time.sleep(self.duration_spinner.value())
            with self.state_lock:
                self.current_state |= pin_mask
                self.gpio.write(self.current_state)
                
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] Prog Mode: R{relay} OFF")
            else:
                global_log(f"Prog Mode: R{relay} OFF")
                
            time.sleep(0.1)
        with self.state_lock:
            self.current_state |= ((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log("[SIMULATION] Prog Mode: R0 & R9 OFF")
            global_log("[SIMULATION] Prog Mode: End")
        else:
            global_log("Prog Mode: R0 & R9 OFF")
            global_log("Prog Mode: End")

    def reset_mode(self):
        """Reset sequence after confirmation."""
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        if QMessageBox.question(self, "Reset Confirm", "Reset?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            threading.Thread(target=self._sequence_mode_thread, args=("Reset", ["4", "5", "6", "6"]), daemon=True).start()
        else:
            if SIMULATION_MODE:
                global_log("[SIMULATION] Reset canceled.")
            else:
                global_log("Reset canceled.")

    def _sequence_mode_thread(self, mode_name, sequence):
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] {mode_name}: Start")
        else:
            global_log(f"{mode_name}: Start")
            
        with self.state_lock:
            self.current_state &= ~((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] {mode_name}: R0 & R9 ON")
        else:
            global_log(f"{mode_name}: R0 & R9 ON")
            
        time.sleep(0.3)
        for relay in sequence:
            pin = RELAY_PINS[relay]
            pin_mask = 1 << pin
            
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] {mode_name}: R{relay} ON")
            else:
                global_log(f"{mode_name}: R{relay} ON")
                
            with self.state_lock:
                self.current_state &= ~pin_mask
                self.gpio.write(self.current_state)
            time.sleep(self.duration_spinner.value())
            with self.state_lock:
                self.current_state |= pin_mask
                self.gpio.write(self.current_state)
                
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] {mode_name}: R{relay} OFF")
            else:
                global_log(f"{mode_name}: R{relay} OFF")
                
            time.sleep(0.1)
        with self.state_lock:
            self.current_state |= ((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] {mode_name}: R0 & R9 OFF")
            global_log(f"[SIMULATION] {mode_name}: End")
        else:
            global_log(f"{mode_name}: R0 & R9 OFF")
            global_log(f"{mode_name}: End")

    def _single_press_mode_thread(self, mode_name, relay_key):
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] {mode_name}: Start")
        else:
            global_log(f"{mode_name}: Start")
            
        # Only use R0 & R9 for Exit Prog Mode
        if mode_name.startswith("Exit Prog Mode"):
            with self.state_lock:
                self.current_state &= ~((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
                self.gpio.write(self.current_state)
                
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] {mode_name}: R0 & R9 ON")
            else:
                global_log(f"{mode_name}: R0 & R9 ON")
                
            time.sleep(0.3)
            
        pin = RELAY_PINS[relay_key]
        pin_mask = 1 << pin
        
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] {mode_name}: R{relay_key} ON")
        else:
            global_log(f"{mode_name}: R{relay_key} ON")
            
        with self.state_lock:
            self.current_state &= ~pin_mask
            self.gpio.write(self.current_state)
        time.sleep(self.duration_spinner.value())
        with self.state_lock:
            self.current_state |= pin_mask
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] {mode_name}: R{relay_key} OFF")
        else:
            global_log(f"{mode_name}: R{relay_key} OFF")
            
        time.sleep(0.1)
        
        # Only use R0 & R9 for Exit Prog Mode
        if mode_name.startswith("Exit Prog Mode"):
            with self.state_lock:
                self.current_state |= ((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
                self.gpio.write(self.current_state)
                
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] {mode_name}: R0 & R9 OFF")
            else:
                global_log(f"{mode_name}: R0 & R9 OFF")
        
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] {mode_name}: End")
        else:
            global_log(f"{mode_name}: End")

    def single_press_sequence(self, mode_name, relay_key):
        """Public method to run a single press sequence."""
        threading.Thread(target=self._single_press_mode_thread, args=(mode_name, relay_key), daemon=True).start()

    def _double_press_mode_thread(self, mode_name, relay_key1, relay_key2):
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] {mode_name}: Start")
        else:
            global_log(f"{mode_name}: Start")
            
        with self.state_lock:
            self.current_state &= ~((1 << RELAY_PINS[relay_key1]) | (1 << RELAY_PINS[relay_key2]))
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] {mode_name}: R{relay_key1} & R{relay_key2} ON")
        else:
            global_log(f"{mode_name}: R{relay_key1} & R{relay_key2} ON")
            
        time.sleep(self.duration_spinner.value())
        with self.state_lock:
            self.current_state |= ((1 << RELAY_PINS[relay_key1]) | (1 << RELAY_PINS[relay_key2]))
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] {mode_name}: R{relay_key1} & R{relay_key2} OFF")
            global_log(f"[SIMULATION] {mode_name}: End")
        else:
            global_log(f"{mode_name}: R{relay_key1} & R{relay_key2} OFF")
            global_log(f"{mode_name}: End")
    
    # --- Additional Mode Methods (Single Press Sequences) ---
    
    def scene_mode(self, scene_digit):
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=(f"Scene Mode ({scene_digit})", scene_digit), daemon=True).start()

    def channel_mode(self):
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Channel Mode", "2"), daemon=True).start()

    def level_mode(self):
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Level Mode", "3"), daemon=True).start()

    def fade_short_mode(self):
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Fade Short", "4"), daemon=True).start()

    def fade_long_mode(self):
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Fade Long", "5"), daemon=True).start()

    def circuit_activation(self):
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Circuit Act.", "6"), daemon=True).start()

    def copy_mode(self):
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Copy", "7"), daemon=True).start()
        
    def exit_programming_mode(self):
        """Exit programming mode."""
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._single_press_mode_thread, args=("Exit Prog Mode", "8"), daemon=True).start()

    def zone_left(self):
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._sequence_mode_thread, args=("Zone Left", ["8", "7", "1", "1"]), daemon=True).start()

    def zone_right(self):
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._sequence_mode_thread, args=("Zone Right", ["8", "7", "2", "2"]), daemon=True).start()

    # --- Shortcut Methods (Double Press Sequences) ---
    
    def quick_scene(self):
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._double_press_mode_thread, args=("Quick Scene", "1", "5"), daemon=True).start()

    def quick_circuit(self):
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._double_press_mode_thread, args=("Quick Circuit", "2", "6"), daemon=True).start()

    def quick_level(self):
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._double_press_mode_thread, args=("Quick Level", "3", "7"), daemon=True).start()

    def quick_fade(self):
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
        threading.Thread(target=self._double_press_mode_thread, args=("Quick Fade", "4", "8"), daemon=True).start()

    def close_hardware(self):
        """Safely close hardware on application exit."""
        if self.hardware_ready and hasattr(self, 'gpio') and self.gpio.is_connected:
            try:
                with self.state_lock:
                    self.current_state = 0xFFFF
                    self.gpio.write(self.current_state)
                self.gpio.close()
            except Exception as e:
                global_log(f"Error closing GPIO: {e}")
                
    def program_zone(self, zone, debug_callback=None):
        """
        Program a zone by executing the zone programming sequence.
        
        Args:
            zone: The zone digit (0-9) to program
            debug_callback: Optional callback function to wait for user confirmation in debug mode
        """
        if not self.hardware_ready:
            self._show_error_slot("Not Ready", "Hardware not ready.")
            return
            
        # Helper function to wait for debug confirmation if needed
        def wait_for_debug():
            if debug_callback:
                debug_callback()
            
        # Execute the sequence directly instead of starting a new thread
        if SIMULATION_MODE:
            global_log("[SIMULATION] === STEP 2: Set Zone Left ===")
        else:
            global_log("=== STEP 2: Set Zone Left ===")
        
        wait_for_debug()  # Wait for debug confirmation if needed
            
        # Zone Left Sequence
        if SIMULATION_MODE:
            global_log("[SIMULATION] Zone Left: Start")
        else:
            global_log("Zone Left: Start")
            
        with self.state_lock:
            self.current_state &= ~((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log("[SIMULATION] Zone Left: R0 & R9 ON")
        else:
            global_log("Zone Left: R0 & R9 ON")
            
        time.sleep(0.5)
        
        # First two relays (8, 7)
        for relay in ["8", "7"]:
            pin = RELAY_PINS[relay]
            pin_mask = 1 << pin
            
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] Zone Left: R{relay} ON")
            else:
                global_log(f"Zone Left: R{relay} ON")
                
            with self.state_lock:
                self.current_state &= ~pin_mask
                self.gpio.write(self.current_state)
            time.sleep(0.5)
            with self.state_lock:
                self.current_state |= pin_mask
                self.gpio.write(self.current_state)
                
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] Zone Left: R{relay} OFF")
            else:
                global_log(f"Zone Left: R{relay} OFF")
                
            time.sleep(0.3)
            
        # First R1
        relay = "1"
        pin = RELAY_PINS[relay]
        pin_mask = 1 << pin
        
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Zone Left: R{relay} ON")
        else:
            global_log(f"Zone Left: R{relay} ON")
            
        with self.state_lock:
            self.current_state &= ~pin_mask
            self.gpio.write(self.current_state)
        time.sleep(0.5)
        with self.state_lock:
            self.current_state |= pin_mask
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Zone Left: R{relay} OFF")
        else:
            global_log(f"Zone Left: R{relay} OFF")
            
        # Add explicit wait message
        if SIMULATION_MODE:
            global_log("[SIMULATION] wait 0.3 secs")
        else:
            global_log("wait 0.3 secs")
        time.sleep(0.3)
        
        # Second R1
        relay = "1"
        pin = RELAY_PINS[relay]
        pin_mask = 1 << pin
        
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Zone Left: R{relay} ON")
        else:
            global_log(f"Zone Left: R{relay} ON")
            
        with self.state_lock:
            self.current_state &= ~pin_mask
            self.gpio.write(self.current_state)
        time.sleep(0.5)
        with self.state_lock:
            self.current_state |= pin_mask
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Zone Left: R{relay} OFF")
        else:
            global_log(f"Zone Left: R{relay} OFF")
            
        time.sleep(0.3)
            
        with self.state_lock:
            self.current_state |= ((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log("[SIMULATION] Zone Left: R0 & R9 OFF")
            global_log("[SIMULATION] Zone Left: End")
        else:
            global_log("Zone Left: R0 & R9 OFF")
            global_log("Zone Left: End")
        
        # Send zone digit
        if SIMULATION_MODE:
            global_log("[SIMULATION] Zone Left Digit: Start")
        else:
            global_log("Zone Left Digit: Start")
            
        pin = RELAY_PINS[zone]
        pin_mask = 1 << pin
        
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Zone Left Digit: R{zone} ON")
        else:
            global_log(f"Zone Left Digit: R{zone} ON")
            
        with self.state_lock:
            self.current_state &= ~pin_mask
            self.gpio.write(self.current_state)
        time.sleep(self.duration_spinner.value())
        with self.state_lock:
            self.current_state |= pin_mask
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Zone Left Digit: R{zone} OFF")
            global_log("[SIMULATION] Zone Left Digit: End")
        else:
            global_log(f"Zone Left Digit: R{zone} OFF")
            global_log("Zone Left Digit: End")
            
        # Add explicit wait message
        if SIMULATION_MODE:
            global_log("[SIMULATION] wait 1 sec")
        else:
            global_log("wait 1 sec")
        time.sleep(1.0)
        
        wait_for_debug()  # Wait for debug confirmation if needed
        
        if SIMULATION_MODE:
            global_log("[SIMULATION] === STEP 3: Set Zone Right ===")
        else:
            global_log("=== STEP 3: Set Zone Right ===")
            
        wait_for_debug()  # Wait for debug confirmation if needed
            
        # Zone Right Sequence
        if SIMULATION_MODE:
            global_log("[SIMULATION] Zone Right: Start")
        else:
            global_log("Zone Right: Start")
            
        with self.state_lock:
            self.current_state &= ~((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log("[SIMULATION] Zone Right: R0 & R9 ON")
        else:
            global_log("Zone Right: R0 & R9 ON")
            
        time.sleep(0.5)
        
        # First two relays (8, 7)
        for relay in ["8", "7"]:
            pin = RELAY_PINS[relay]
            pin_mask = 1 << pin
            
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] Zone Right: R{relay} ON")
            else:
                global_log(f"Zone Right: R{relay} ON")
                
            with self.state_lock:
                self.current_state &= ~pin_mask
                self.gpio.write(self.current_state)
            time.sleep(0.5)
            with self.state_lock:
                self.current_state |= pin_mask
                self.gpio.write(self.current_state)
                
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] Zone Right: R{relay} OFF")
            else:
                global_log(f"Zone Right: R{relay} OFF")
                
            time.sleep(0.3)
            
        # First R2
        relay = "2"
        pin = RELAY_PINS[relay]
        pin_mask = 1 << pin
        
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Zone Right: R{relay} ON")
        else:
            global_log(f"Zone Right: R{relay} ON")
            
        with self.state_lock:
            self.current_state &= ~pin_mask
            self.gpio.write(self.current_state)
        time.sleep(0.5)
        with self.state_lock:
            self.current_state |= pin_mask
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Zone Right: R{relay} OFF")
        else:
            global_log(f"Zone Right: R{relay} OFF")
            
        # No wait here, moved after Zone Right: End
        
        # Second R2
        relay = "2"
        pin = RELAY_PINS[relay]
        pin_mask = 1 << pin
        
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Zone Right: R{relay} ON")
        else:
            global_log(f"Zone Right: R{relay} ON")
            
        with self.state_lock:
            self.current_state &= ~pin_mask
            self.gpio.write(self.current_state)
        time.sleep(0.5)
        with self.state_lock:
            self.current_state |= pin_mask
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Zone Right: R{relay} OFF")
        else:
            global_log(f"Zone Right: R{relay} OFF")
            
        time.sleep(0.3)
            
        with self.state_lock:
            self.current_state |= ((1 << RELAY_PINS["0"]) | (1 << RELAY_PINS["9"]))
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log("[SIMULATION] Zone Right: R0 & R9 OFF")
            global_log("[SIMULATION] Zone Right: End")
        else:
            global_log("Zone Right: R0 & R9 OFF")
            global_log("Zone Right: End")
            
        # Add explicit wait message
        if SIMULATION_MODE:
            global_log("[SIMULATION] wait 0.3 secs")
        else:
            global_log("wait 0.3 secs")
        time.sleep(0.3)
        
        # Send zone digit
        if SIMULATION_MODE:
            global_log("[SIMULATION] Zone Right Digit: Start")
        else:
            global_log("Zone Right Digit: Start")
            
        pin = RELAY_PINS[zone]
        pin_mask = 1 << pin
        
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Zone Right Digit: R{zone} ON")
        else:
            global_log(f"Zone Right Digit: R{zone} ON")
            
        with self.state_lock:
            self.current_state &= ~pin_mask
            self.gpio.write(self.current_state)
        time.sleep(self.duration_spinner.value())
        with self.state_lock:
            self.current_state |= pin_mask
            self.gpio.write(self.current_state)
            
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Zone Right Digit: R{zone} OFF")
            global_log("[SIMULATION] Zone Right Digit: End")
        else:
            global_log(f"Zone Right Digit: R{zone} OFF")
            global_log("Zone Right Digit: End")
            
        # Add explicit wait message
        if SIMULATION_MODE:
            global_log("[SIMULATION] wait 2 sec")
        else:
            global_log("wait 2 sec")
        time.sleep(2.0)
        
        wait_for_debug()  # Wait for debug confirmation if needed
        
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Zone programming complete for zone {zone}")
        else:
            global_log(f"Zone programming complete for zone {zone}")
            
        # Add explicit wait message
        if SIMULATION_MODE:
            global_log("[SIMULATION] wait 2 sec")
        else:
            global_log("wait 2 sec")
        time.sleep(2.0)
        
        wait_for_debug()  # Wait for debug confirmation if needed

    # --- Play Scene Level Method ---
    
    def play_scene_level(self, channel, scene_digit, level_value, callback=None):
        """
        Trigger a play sequence for a specific channel and scene.
        This method logs the action and runs the sequence in a background thread.
        """
        if SIMULATION_MODE:
            global_log(f"[SIMULATION] Playing channel {channel}, scene {scene_digit} with level {level_value}")
        else:
            global_log(f"Playing channel {channel}, scene {scene_digit} with level {level_value}")
        threading.Thread(target=self._play_scene_level_sequence, args=(channel, scene_digit, level_value, callback), daemon=True).start()

    def _play_scene_level_sequence(self, channel, scene_digit, level_value, callback=None):
        """
        Simulate a relay sequence for playing a level:
          - Exit programming mode.
          - Enter programming mode.
          - Quick Scene Mode (double press R1 & R5).
          - Quick Scene Digit.
          - Quick Circuit Mode (double press R2 & R6).
          - Circuit Digit.
          - Quick Level Mode (double press R3 & R7).
          - Level Digit.
          - Exit programming mode.
        """
        def execute_sequence():
            # Exit programming mode
            if SIMULATION_MODE:
                global_log("[SIMULATION] === STEP 1: Exit Programming Mode ===")
            else:
                global_log("=== STEP 1: Exit Programming Mode ===")
                
            # Call the thread method directly instead of starting a new thread
            self._single_press_mode_thread("Exit Prog Mode", "8")
            time.sleep(1.0)  # Wait for operation to complete
            
            # Enter programming mode
            if SIMULATION_MODE:
                global_log("[SIMULATION] === STEP 2: Enter Programming Mode ===")
            else:
                global_log("=== STEP 2: Enter Programming Mode ===")
                
            # Call the thread method directly instead of starting a new thread
            self._programming_mode_thread()
            time.sleep(1.0)  # Wait for operation to complete
            
            # Quick Scene Mode (double press R1 & R5)
            if SIMULATION_MODE:
                global_log("[SIMULATION] === STEP 3: Quick Scene Mode ===")
            else:
                global_log("=== STEP 3: Quick Scene Mode ===")
                
            # Call the thread method directly instead of starting a new thread
            self._double_press_mode_thread("Quick Scene", "1", "5")
            time.sleep(1.0)  # Wait for operation to complete
            
            # Quick Scene Digit
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] === STEP 4: Quick Scene Digit ({scene_digit}) ===")
            else:
                global_log(f"=== STEP 4: Quick Scene Digit ({scene_digit}) ===")
                
            # Call the thread method directly instead of starting a new thread
            self._single_press_mode_thread("Quick Scene Digit", scene_digit)
            time.sleep(1.0)  # Wait for operation to complete
            
            # Quick Circuit Mode (double press R2 & R6)
            if SIMULATION_MODE:
                global_log("[SIMULATION] === STEP 5: Quick Circuit Mode ===")
            else:
                global_log("=== STEP 5: Quick Circuit Mode ===")
                
            # Call the thread method directly instead of starting a new thread
            self._double_press_mode_thread("Quick Circuit", "2", "6")
            time.sleep(1.0)  # Wait for operation to complete
            
            # Circuit Digit
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] === STEP 6: Circuit Digit ({channel}) ===")
            else:
                global_log(f"=== STEP 6: Circuit Digit ({channel}) ===")
                
            ch_str = str(channel).zfill(2)
            for digit in ch_str:
                # Call the thread method directly instead of starting a new thread
                self._single_press_mode_thread("Circuit Digit", digit)
                time.sleep(1.0)  # Wait for operation to complete
            
            # Quick Level Mode (double press R3 & R7)
            if SIMULATION_MODE:
                global_log("[SIMULATION] === STEP 7: Quick Level Mode ===")
            else:
                global_log("=== STEP 7: Quick Level Mode ===")
                
            # Call the thread method directly instead of starting a new thread
            self._double_press_mode_thread("Quick Level", "3", "7")
            time.sleep(1.0)  # Wait for operation to complete
            
            # Level Digit
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] === STEP 8: Level Digit ({level_value}) ===")
            else:
                global_log(f"=== STEP 8: Level Digit ({level_value}) ===")
                
            level_digits = level_value.zfill(2)
            for digit in level_digits:
                # Call the thread method directly instead of starting a new thread
                self._single_press_mode_thread("Level Digit", digit)
                time.sleep(1.0)  # Wait for operation to complete
            
            # Exit programming mode
            if SIMULATION_MODE:
                global_log("[SIMULATION] === STEP 9: Exit Programming Mode ===")
            else:
                global_log("=== STEP 9: Exit Programming Mode ===")
                
            # Call the thread method directly instead of starting a new thread
            self._single_press_mode_thread("Exit Prog Mode", "8")
            time.sleep(1.0)  # Wait for operation to complete
            
            # Done
            if SIMULATION_MODE:
                global_log(f"[SIMULATION] === COMPLETE: Play done for channel {channel}, scene {scene_digit} with level {level_value} ===")
            else:
                global_log(f"=== COMPLETE: Play done for channel {channel}, scene {scene_digit} with level {level_value} ===")
                
            if callback:
                callback()
        
        # Start the sequence in a separate thread
        threading.Thread(target=execute_sequence, daemon=True).start()
