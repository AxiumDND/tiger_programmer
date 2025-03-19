def on_program_scene_levels(self):
    """
    Handle the "Program Scene" button click.
    
    This method:
    1. Prompts the user for a scene number (1-9 or 0) using a custom dialog
    2. Prompts the user for a zone number (0-9) using a custom dialog
    3. Asks for confirmation
    4. Disables the Program Scene button to prevent multiple clicks
    5. Programs the zone
    6. Starts a thread to execute the programming sequence
    
    The programming sequence will program the specified scene for all channels
    in the specified zone with their current scene levels.
    """
    # Use custom SceneDialog to prompt for scene number
    scene_dialog = SceneDialog(self.master.winfo_toplevel(), "Select Scene")
    if scene_dialog.result is None:
        return  # User canceled
    
    scene_digit = scene_dialog.result
    
    # Use custom ZoneDialog to prompt for zone number
    zone_dialog = ZoneDialog(self.master.winfo_toplevel(), "Select Zone")
    if zone_dialog.result is None:
        return  # User canceled
    
    zone = zone_dialog.result
    
    # Ask for confirmation
    if not messagebox.askyesno("Confirmation", f"Program scene {scene_digit} for zone {zone}?"):
        return
    
    # Disable the Program Scene button to prevent multiple clicks
    self.program_button.config(state=tk.DISABLED)
    
    # Program the zone
    self.relay_controller.program_zone(zone)
    
    # Start a thread to execute the programming sequence
    threading.Thread(target=self.program_scene_levels_sequence, 
                     args=(scene_digit, zone), 
                     daemon=True).start()

def on_allocate_to_zones(self):
    """
    Handle the "Allocate to Zones" button click.
    
    This method:
    1. Prompts the user for a zone number (0-9) using a custom dialog
    2. Asks for confirmation
    3. Disables the Allocate to Zones button to prevent multiple clicks
    4. Starts a thread to execute the allocation sequence
    
    The allocation sequence will:
    1. Program the zone (using program_zone)
    2. Exit programming mode
    3. Enter programming mode
    4. For each channel:
       a. Determine if the channel is in the zone (based on its zone value)
       b. Send the channel digits
       c. Send the allocation digit (1 if in the zone, 0 if not)
    5. Exit programming mode
    6. Re-enable the Allocate to Zones button
    """
    # Use custom ZoneDialog to prompt for zone number
    zone_dialog = ZoneDialog(self.master.winfo_toplevel(), "Select Zone")
    if zone_dialog.result is None:
        return  # User canceled
    
    zone = zone_dialog.result
    
    # Ask for confirmation
    if not messagebox.askyesno("Confirmation", f"Allocate channels to zone {zone}?"):
        return
    
    # Disable the Allocate to Zones button to prevent multiple clicks
    self.allocate_button.config(state=tk.DISABLED)
    
    # Define the sequence to execute
    def execute_sequence():
        # Store the relay controller in a local variable for convenience
        rc = self.relay_controller
        
        # First program the zone
        # This already has its own sequence implementation
        rc.program_zone(zone)
        
        # Exit programming mode to ensure we start from a clean state
        exit_thread = threading.Thread(target=rc._single_press_mode_thread, 
                                      args=("Exit Prog Mode", "8"), 
                                      daemon=True)
        exit_thread.start()
        exit_thread.join()  # Wait for the thread to complete
        time.sleep(1.2)  # Increased from 0.8 to 1.2 seconds
        
        # Enter programming mode
        prog_thread = threading.Thread(target=rc._programming_mode_thread, daemon=True)
        prog_thread.start()
        prog_thread.join()  # Wait for the thread to complete
        time.sleep(1.2)  # Increased from 0.8 to 1.2 seconds
        
        # Allocate each channel
        for idx, row in enumerate(self.rows, start=1):
            # Determine if the channel is in the zone
            # 1 = channel is in the zone, 0 = channel is not in the zone
            alloc_digit = "1" if row["zone"].get() == zone else "0"
            
            # Send channel digits (e.g., "01" for channel 1)
            ch_str = str(idx).zfill(2)  # Ensure 2 digits with leading zero if needed
            global_log(f"Allocating channel {idx} with allocation digit {alloc_digit}")
            
            # Send each channel digit
            for digit in ch_str:
                digit_thread = threading.Thread(target=rc._single_press_mode_thread, 
                                              args=("Quick Channel Digit", digit), 
                                              daemon=True)
                digit_thread.start()
                digit_thread.join()  # Wait for the thread to complete
                time.sleep(0.8)  # Increased from 0.5 to 0.8 seconds
            
            # Send allocation digit (1 or 0)
            alloc_thread = threading.Thread(target=rc._single_press_mode_thread, 
                                          args=("Circuit Act Digit", alloc_digit), 
                                          daemon=True)
            alloc_thread.start()
            alloc_thread.join()  # Wait for the thread to complete
            time.sleep(0.8)  # Increased from 0.5 to 0.8 seconds
        
        # Exit programming mode when done
        final_exit_thread = threading.Thread(target=rc._single_press_mode_thread, 
                                           args=("Exit Prog Mode", "8"), 
                                           daemon=True)
        final_exit_thread.start()
        final_exit_thread.join()  # Wait for the thread to complete
        
        # Log that the allocation sequence is complete
        global_log("Allocation sequence complete.")
        
        # Re-enable the Allocate to Zones button
        # Use master.after(0, ...) to ensure this runs in the main thread
        self.master.after(0, lambda: self.allocate_button.config(state=tk.NORMAL))
    
    # Start the sequence in a separate thread
    sequence_thread = threading.Thread(target=execute_sequence, daemon=True)
    sequence_thread.start()
