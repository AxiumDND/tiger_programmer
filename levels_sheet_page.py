"""
levels_sheet_page.py

This module contains the LevelsSheetPage class.
It provides a table for channel (level) configuration with 15 columns:
Channel, Zone, Dim Ref, Name, Type, plus 10 Scene columns.
Each scene cell includes a two‑digit Spinbox and an adjacent "P" button.
CSV import/export is supported and relay commands (via a provided relay controller)
can be triggered from the table (e.g. via the "P" button).
 
Additional modifications:
  - The Zone combobox now defaults to "1".
  - The Name column is made wider by increasing its column weight and setting a larger width
    for the corresponding Entry widget.
"""

import csv
import threading
import time
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QPushButton, QComboBox, QLineEdit, QSpinBox, QFileDialog,
    QMessageBox, QInputDialog, QFrame, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot

# Import relay controller and logging utilities
from relay_control import RelayControlApp
from gui_logger import global_log

class LevelsSheetPage(QWidget):
    def __init__(self, master, relay_controller=None):
        super().__init__(master)
        self.master = master
        self.relay_controller = relay_controller
        self.rows = []
        # Define scene labels for columns: Scene 1 ... Scene 9, then Scene 0.
        self.scene_labels = [f"Scene {i}" for i in range(1, 10)] + ["Scene 0"]
        # Default scene values for each scene column (as strings).
        self.scene_defaults = ["90", "70", "50", "30", "99", "99", "99", "99", "99", "00"]
        # Debug mode flag and step control
        self.debug_mode = False
        self.step_ready = threading.Event()
        self.create_widgets()

    def create_widgets(self):
        # Main layout
        main_layout = QVBoxLayout(self)
        
        # Header section
        header_frame = QFrame()
        header_layout = QGridLayout(header_frame)
        
        header_layout.addWidget(QLabel("Site Name:"), 0, 0)
        self.site_name_entry = QLineEdit()
        header_layout.addWidget(self.site_name_entry, 0, 1)
        
        header_layout.addWidget(QLabel("Date:"), 0, 2)
        self.date_entry = QLineEdit()
        header_layout.addWidget(self.date_entry, 0, 3)
        
        main_layout.addWidget(header_frame)
        
        # Controls section
        controls_frame = QFrame()
        controls_layout = QHBoxLayout(controls_frame)
        
        controls_layout.addWidget(QLabel("Number of Channels:"))
        self.num_channels_entry = QLineEdit("18")
        self.num_channels_entry.setFixedWidth(50)
        controls_layout.addWidget(self.num_channels_entry)
        
        generate_btn = QPushButton("Generate Table")
        generate_btn.clicked.connect(self.on_generate_table)
        controls_layout.addWidget(generate_btn)
        
        save_csv_btn = QPushButton("Save CSV")
        save_csv_btn.clicked.connect(self.on_save_csv)
        controls_layout.addWidget(save_csv_btn)
        
        import_csv_btn = QPushButton("Import CSV")
        import_csv_btn.clicked.connect(self.on_import_csv)
        controls_layout.addWidget(import_csv_btn)
        
        self.program_button = QPushButton("Program Scene")
        self.program_button.clicked.connect(self.on_program_scene_levels)
        controls_layout.addWidget(self.program_button)
        
        self.allocate_button = QPushButton("Allocate to Zones")
        self.allocate_button.clicked.connect(self.on_allocate_to_zones)
        controls_layout.addWidget(self.allocate_button)
        
        # Debug mode toggle button
        self.debug_button = QPushButton("Debug Mode: OFF")
        self.debug_button.setCheckable(True)
        self.debug_button.clicked.connect(self.toggle_debug_mode)
        controls_layout.addWidget(self.debug_button)
        
        # Next Step button (initially disabled)
        self.next_step_button = QPushButton("Next Step")
        self.next_step_button.clicked.connect(self.on_next_step)
        self.next_step_button.setEnabled(False)
        controls_layout.addWidget(self.next_step_button)
        
        controls_layout.addStretch()
        main_layout.addWidget(controls_frame)
        
        # Table section with scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        self.table_widget = QWidget()
        self.table_layout = QGridLayout(self.table_widget)
        
        scroll_area.setWidget(self.table_widget)
        main_layout.addWidget(scroll_area, 1)  # Give table section more stretch
        
        # Create headers and initial table
        self.create_headers()
        self.on_generate_table()
        
        global_log("Levels Sheet ready.")

    def create_headers(self):
        headers = ["Channel", "Zone", "Dim Ref", "Name", "Type"] + self.scene_labels
        
        # Add header labels
        for col, header in enumerate(headers):
            label = QLabel(header)
            label.setAlignment(Qt.AlignCenter)
            self.table_layout.addWidget(label, 0, col)
            
            # Set column stretch factors
            if header == "Name":
                self.table_layout.setColumnStretch(col, 5)
            elif header == "Type":
                self.table_layout.setColumnStretch(col, 2)
            else:
                self.table_layout.setColumnStretch(col, 1)

    def create_row(self, row_num):
        row = {}
        
        # Channel number
        channel_label = QLabel(str(row_num))
        channel_label.setAlignment(Qt.AlignCenter)
        self.table_layout.addWidget(channel_label, row_num, 0)
        
        # Zone combobox
        row["zone"] = QComboBox()
        row["zone"].addItems(["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"])
        row["zone"].setCurrentText("1")
        self.table_layout.addWidget(row["zone"], row_num, 1)
        
        # Dim Ref
        row["dim_ref"] = QLineEdit()
        self.table_layout.addWidget(row["dim_ref"], row_num, 2)
        
        # Name
        row["name"] = QLineEdit()
        self.table_layout.addWidget(row["name"], row_num, 3)
        
        # Type
        row["type"] = QComboBox()
        row["type"].addItems(["Dimmed", "Switched", "Switched1to10"])
        row["type"].setCurrentText("Dimmed")
        self.table_layout.addWidget(row["type"], row_num, 4)
        
        # Scene columns
        row["scenes"] = []
        for i in range(10):
            # Create a frame for each scene cell
            scene_frame = QFrame()
            scene_layout = QHBoxLayout(scene_frame)
            scene_layout.setContentsMargins(2, 2, 2, 2)
            
            # Default value
            default_val = "00" if i == 9 else self.scene_defaults[i]
            
            # Spinbox for scene level
            spinbox = QSpinBox()
            spinbox.setRange(0, 99)
            spinbox.setValue(int(default_val))
            spinbox.setFixedWidth(50)
            spinbox.setAlignment(Qt.AlignCenter)
            scene_layout.addWidget(spinbox)
            
            # "P" button
            scene_digit = str(i + 1) if i < 9 else "0"
            p_button = QPushButton("P")
            p_button.setFixedWidth(30)
            p_button.clicked.connect(
                lambda checked=False, b=p_button, ch=row_num, sd=scene_digit, sp=spinbox: 
                self.play_level_with_lock(b, ch, sd, f"{sp.value():02d}")
            )
            scene_layout.addWidget(p_button)
            
            self.table_layout.addWidget(scene_frame, row_num, 5 + i)
            row["scenes"].append(spinbox)
            
        return row

    def play_level_with_lock(self, button, channel, scene_digit, level_value):
        button.setEnabled(False)
        self.relay_controller.play_scene_level(
            channel, scene_digit, level_value,
            callback=lambda: button.setEnabled(True)
        )

    def rebuild_table(self, num_channels):
        # Save current data if any
        old_data = self.read_table_data() if self.rows else []
        
        # Clear existing table
        for i in reversed(range(self.table_layout.count())): 
            widget = self.table_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()
        
        # Recreate headers
        self.create_headers()
        
        # Clear rows list
        self.rows = []
        
        # Create new rows
        for i in range(1, num_channels + 1):
            row = self.create_row(i)
            self.rows.append(row)
        
        # Restore data for existing channels
        for i in range(min(num_channels, len(old_data))):
            data = old_data[i]
            row = self.rows[i]
            
            row["zone"].setCurrentText(data["zone"])
            row["dim_ref"].setText(data["dimRef"])
            row["name"].setText(data["name"])
            row["type"].setCurrentText(data["type"])
            
            for j, spin in enumerate(row["scenes"]):
                if j < len(data["scenes"]):
                    spin.setValue(int(data["scenes"][j]))

    def on_generate_table(self):
        try:
            num_channels = int(self.num_channels_entry.text())
            if num_channels < 1:
                raise ValueError("Number of channels must be positive")
            self.rebuild_table(num_channels)
        except ValueError as e:
            QMessageBox.critical(self, "Input Error", str(e))

    def on_save_csv(self):
        csv_data = self.generate_csv_data()
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", "", "CSV Files (*.csv)"
        )
        
        if filename:
            with open(filename, "w", newline="") as f:
                f.write(csv_data)
            global_log("CSV saved successfully.")

    def on_import_csv(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import CSV", "", "CSV Files (*.csv)"
        )
        
        if filename:
            try:
                with open(filename, "r") as f:
                    csv_text = f.read()
                
                parsed = self.parse_csv(csv_text)
                
                self.site_name_entry.setText(parsed["siteName"])
                self.date_entry.setText(parsed["siteDate"])
                self.num_channels_entry.setText(str(len(parsed["rows"])))
                
                self.rebuild_table(len(parsed["rows"]))
                
                for idx, entry in enumerate(parsed["rows"]):
                    if idx < len(self.rows):
                        row = self.rows[idx]
                        row["zone"].setCurrentText(entry.get("zone", "1"))
                        row["dim_ref"].setText(entry.get("dimRef", ""))
                        row["name"].setText(entry.get("name", ""))
                        row["type"].setCurrentText(entry.get("type", "Dimmed"))
                        
                        scenes = entry.get("scenes", [])
                        for i, spin in enumerate(row["scenes"]):
                            if i < len(scenes):
                                spin.setValue(int(scenes[i]))
                
                global_log("CSV imported successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Import CSV", f"Error importing CSV: {e}")

    def generate_csv_data(self):
        site_name = self.site_name_entry.text().strip()
        site_date = self.date_entry.text().strip()
        
        lines = []
        line1 = ["Site Name:", site_name] + [""] * 13
        lines.append(",".join(line1))
        
        line2 = ["Date:", site_date] + [""] * 13
        lines.append(",".join(line2))
        
        headers = ["Channel", "Zone", "Dim Ref", "Name", "Type"] + self.scene_labels
        lines.append(",".join(headers))
        
        table_data = self.read_table_data()
        for entry in table_data:
            row = [
                str(entry["channel"]), 
                entry["zone"], 
                entry["dimRef"], 
                entry["name"], 
                entry["type"]
            ] + entry["scenes"]
            lines.append(",".join(row))
        
        return "\n".join(lines)

    def read_table_data(self):
        data = []
        for idx, row in enumerate(self.rows, start=1):
            entry = {
                "channel": idx,
                "zone": row["zone"].currentText(),
                "dimRef": row["dim_ref"].text(),
                "name": row["name"].text(),
                "type": row["type"].currentText(),
                "scenes": [f"{spin.value():02d}" for spin in row["scenes"]]
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
        scene_digit, ok = QInputDialog.getItem(
            self, "Select Scene", "Enter scene number:",
            [str(i) for i in range(1, 10)] + ["0"], 0, False
        )
        
        if not ok:
            return
            
        zone, ok = QInputDialog.getItem(
            self, "Select Zone", "Enter zone number:",
            [str(i) for i in range(10)], 0, False
        )
        
        if not ok:
            return
            
        confirm = QMessageBox.question(
            self, "Confirmation", 
            f"Program scene {scene_digit} for zone {zone}?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm != QMessageBox.Yes:
            return
            
        self.program_button.setEnabled(False)
        # Remove the program_zone call from here to prevent overlapping operations
        threading.Thread(
            target=self.program_scene_levels_sequence, 
            args=(scene_digit, zone), 
            daemon=True
        ).start()

    def toggle_debug_mode(self):
        """Toggle debug mode on/off"""
        self.debug_mode = not self.debug_mode
        if self.debug_mode:
            self.debug_button.setText("Debug Mode: ON")
            self.next_step_button.setEnabled(True)
        else:
            self.debug_button.setText("Debug Mode: OFF")
            self.next_step_button.setEnabled(False)
            # Signal any waiting threads to continue
            self.step_ready.set()
        global_log(f"Debug mode {'enabled' if self.debug_mode else 'disabled'}")
    
    def on_next_step(self):
        """Signal that the next step can proceed"""
        global_log("Proceeding to next step...")
        self.step_ready.set()
    
    def wait_for_next_step(self):
        """Wait for user to click Next Step button if in debug mode"""
        if self.debug_mode:
            global_log("Waiting for Next Step button...")
            self.step_ready.clear()
            self.step_ready.wait()
    
    def program_scene_levels_sequence(self, scene_digit, zone):
        rc = self.relay_controller
        global_log("=== Starting programming sequence ===")
        
        # Step 1: Exit Programming Mode (once at the beginning)
        global_log("=== STEP 1: Exit Programming Mode ===")
        rc._single_press_mode_thread("Exit Prog Mode", "8")
        time.sleep(0.2)  # Wait for operation to complete
        self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
        
        # Step 2-3: Set Zone Left and Zone Right
        rc.program_zone(zone, debug_callback=self.wait_for_next_step if self.debug_mode else None)
        time.sleep(0.5)  # Wait for operation to complete
        
        # Step 4: Enter Programming Mode (once for the entire operation)
        global_log("=== STEP 4: Enter Programming Mode ===")
        rc._programming_mode_thread()
        time.sleep(0.5)  # Wait for operation to complete
        
        # Add explicit wait message
        global_log("wait 0.2secs")
        time.sleep(0.2)
        
        self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
        
        # Process each channel in the selected zone
        channels_to_program = []
        for idx, row in enumerate(self.rows, start=1):
            if row["zone"].currentText() == zone:
                scene_index = 9 if scene_digit == "0" else int(scene_digit) - 1
                level_value = f"{row['scenes'][scene_index].value():02d}"
                channels_to_program.append((idx, level_value))
        
        # Step 5: Quick Scene operation (once for all channels)
        global_log("=== STEP 5: Quick Scene Operation ===")
        rc._double_press_mode_thread("Quick Scene", "1", "5")
        time.sleep(0.5)  # Wait for operation to complete
        
        # Add explicit wait message
        global_log("wait 0.2secs")
        time.sleep(0.2)
        
        self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
        
        # Step 6: Scene Digit operation (once for all channels)
        global_log(f"=== STEP 6: Scene Digit {scene_digit} ===")
        rc._single_press_mode_thread("Scene digit", scene_digit)
        time.sleep(0.5)  # Wait for operation to complete
        
        # Add explicit wait message
        global_log("wait 0.2secs")
        time.sleep(0.2)
        
        self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
        
        # Process each channel
        for idx, level_value in channels_to_program:
            global_log(f"=== Programming channel {idx} with level {level_value} for scene {scene_digit} (zone {zone}) ===")
            
            # Step 7: Quick Circuit operation
            global_log(f"=== STEP 7: Quick Circuit Operation (Channel {idx}) ===")
            rc._double_press_mode_thread("Quick Circuit", "2", "6")
            time.sleep(0.5)  # Wait for operation to complete
            
            # Add explicit wait message
            global_log("wait 0.2secs")
            time.sleep(0.2)
            
            self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
            
            # Step 8: Circuit Digits operation
            global_log(f"=== STEP 8: Circuit Digits {idx} (Channel {idx}) ===")
            ch_str = str(idx).zfill(2)
            for digit in ch_str:
                rc._single_press_mode_thread("Circuit Digit", digit)
                time.sleep(0.5)  # Wait for operation to complete
                self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
            
            # Add explicit wait message
            global_log("wait 0.2secs")
            time.sleep(0.2)
            
            # Step 9: Quick Level operation
            global_log(f"=== STEP 9: Quick Level Operation (Channel {idx}) ===")
            rc._double_press_mode_thread("Quick Level", "3", "7")
            time.sleep(0.5)  # Wait for operation to complete
            
            # Add explicit wait message
            global_log("wait 0.2secs")
            time.sleep(0.2)
            
            self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
            
            # Step 10: Level Digits operation
            global_log(f"=== STEP 10: Level Digits {level_value} (Channel {idx}) ===")
            level_digits = level_value.zfill(2)
            for digit in level_digits:
                rc._single_press_mode_thread("Level Digit", digit)
                time.sleep(0.5)  # Wait for operation to complete
                self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
            
            # Add explicit wait message
            global_log("wait 0.2secs")
            time.sleep(0.2)
            
            global_log(f"=== Channel {idx} programmed ===")
        
        # Step 11: Exit Programming Mode (once at the end)
        global_log("=== STEP 11: Exit Programming Mode ===")
        rc._single_press_mode_thread("Exit Prog Mode", "8")
        time.sleep(0.5)  # Wait for operation to complete
        self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
        
        global_log("=== Programming sequence complete ===")
        
        # Re-enable the button
        self.program_button.setEnabled(True)

    def allocate_channel(self, channel, allocation_digit):
        ch_str = str(channel).zfill(2)
        global_log(f"Allocating channel {channel} with allocation digit {allocation_digit}")
        
        for digit in ch_str:
            self.relay_controller._single_press_mode_thread("Quick Circuit Digit", digit)
            time.sleep(0.2)
            
        self.relay_controller._single_press_mode_thread("Circuit Act Digit", allocation_digit)

    def on_allocate_to_zones(self):
        zone, ok = QInputDialog.getItem(
            self, "Select Zone", "Enter zone number:",
            [str(i) for i in range(10)], 0, False
        )
        
        if not ok:
            return
            
        confirm = QMessageBox.question(
            self, "Confirmation", 
            f"Allocate channels to zone {zone}?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm != QMessageBox.Yes:
            return
            
        self.allocate_button.setEnabled(False)
        # Remove the program_zone call from here to prevent overlapping operations
        threading.Thread(
            target=self.allocate_to_zones_sequence, 
            args=(zone,), 
            daemon=True
        ).start()
        
    def allocate_to_zones_sequence(self, zone):
        # Execute the sequence in a single thread to prevent overlapping operations
        def execute_sequence():
            rc = self.relay_controller
            global_log("=== Starting allocation sequence ===")
            
            # Step 1: Exit Programming Mode (once at the beginning)
            global_log("=== STEP 1: Exit Programming Mode ===")
            rc._single_press_mode_thread("Exit Prog Mode", "8")
            time.sleep(0.5)  # Wait for operation to complete
            self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
            
            # Step 2-3: Set Zone Left and Zone Right
            rc.program_zone(zone, debug_callback=self.wait_for_next_step if self.debug_mode else None)
            time.sleep(0.5)  # Wait for operation to complete
            
            # Step 4: Enter Programming Mode
            global_log("=== STEP 4: Enter Programming Mode ===")
            rc._programming_mode_thread()
            time.sleep(0.5)  # Wait for operation to complete
            self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
            
            # Step 5: Allocate Channels
            global_log("=== STEP 5: Allocate Channels ===")
            for idx, row in enumerate(self.rows, start=1):
                alloc_digit = "1" if row["zone"].currentText() == zone else "0"
                
                global_log(f"=== Allocating channel {idx} with digit {alloc_digit} ===")
                
                # Circuit digits
                ch_str = str(idx).zfill(2)
                for digit in ch_str:
                    rc._single_press_mode_thread("Circuit Digit", digit)
                    time.sleep(0.5)  # Wait for operation to complete
                    self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
                    
                # Circuit activation
                rc._single_press_mode_thread("Circuit Act Digit", alloc_digit)
                time.sleep(0.5)  # Wait for operation to complete
                self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
                
            # Step 6: Exit Programming Mode
            global_log("=== STEP 6: Exit Programming Mode ===")
            rc._single_press_mode_thread("Exit Prog Mode", "8")
            time.sleep(0.5)  # Wait for operation to complete
            self.wait_for_next_step()  # Wait for user to click Next Step if in debug mode
            
            global_log("=== Allocation sequence complete ===")
            
            # Re-enable the button
            self.allocate_button.setEnabled(True)
            
        # Start the sequence in a separate thread
        threading.Thread(target=execute_sequence, daemon=True).start()
