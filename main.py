import sys
import os
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QPushButton, QSlider, QLabel, QLCDNumber, QSpinBox, QTimeEdit, 
                           QProgressBar, QTextEdit, QGridLayout)
from PyQt6.QtCore import QTimer, Qt, QTime
import pyqtgraph as pg
from queue import Queue
from collections import deque
from ble_handler import BLEHandler
from datetime import datetime, timedelta
import statistics

class RoasterMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Coffee Roaster Monitor")
        
        # Data storage
        self.data_queue = Queue()
        self.ble_handler = BLEHandler(self.data_queue)
        self.timestamps = deque(maxlen=3600)  # Store up to 1 hour of data
        self.iso_timestamps = deque(maxlen=3600)
        self.grill_temp_data = deque(maxlen=3600)  # Grill temperature
        self.drum_temp_data = deque(maxlen=3600)  # Drum temperature
        self.ror_data = deque(maxlen=3600)  # Rate of Rise data

        # Roast state
        self.roast_started = False
        self.start_time = None
        self.first_crack_start = None
        self.first_crack_end = None
        self.second_crack_start = None
        self.second_crack_end = None
        self.target_temp_line = None

        # Smoothing window
        self.smooth_window = 10
        
        # ROR calculation settings
        self.ror_window = 30  # Calculate ROR over 30 seconds by default
        
        self.init_ui()
        self.setup_timer()
        
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create plot
        self.graph = pg.PlotWidget()
        self.graph.setTitle("Temperature Graph")
        self.graph.setLabel("left", "Temperature (°F)")
        self.graph.setLabel("bottom", "Time (mm:ss)")
        self.graph.showGrid(x=True, y=True)
        
        # Create a second y-axis for ROR
        self.ror_axis = pg.ViewBox()
        self.graph.scene().addItem(self.ror_axis)
        self.graph.getAxis('right').linkToView(self.ror_axis)
        self.ror_axis.setXLink(self.graph)
        self.graph.getAxis('right').setLabel('Rate of Rise (°F/min)', color='orange')
        
        self.grill_temp_curve = self.graph.plot(pen=pg.mkPen('r', width=3), name="Grill Temp")
        self.drum_temp_curve = self.graph.plot(pen=pg.mkPen('g', width=2), name="Drum Temp")
        self.ghost_drum_curve = self.graph.plot(pen=pg.mkPen((150, 150, 150), width=2, style=Qt.PenStyle.DashLine), name="Ghost Drum")
        self.ghost_grill_curve = self.graph.plot(pen=pg.mkPen((200, 100, 100), width=1, style=Qt.PenStyle.DashLine), name="Ghost Grill")
        
        # ROR curve on secondary axis
        self.ror_curve = pg.PlotCurveItem(pen=pg.mkPen('orange', width=2), name="ROR")
        self.ror_axis.addItem(self.ror_curve)
        
        layout.addWidget(self.graph)
        
        # Temperature displays layout
        temp_displays_layout = QHBoxLayout()
        
        # LCD Display for Grill Temperature
        self.grillT_display = QLCDNumber()
        self.grillT_display.setDigitCount(3)
        self.grillT_display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self.grillT_display.setStyleSheet("background-color: black; color: red;")
        temp_displays_layout.addWidget(QLabel("Grill Temp:"))
        temp_displays_layout.addWidget(self.grillT_display)

        # LCD Display for Drum Temperature
        self.accT_display = QLCDNumber()
        self.accT_display.setDigitCount(3)
        self.accT_display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self.accT_display.setStyleSheet("background-color: black; color: green;")
        temp_displays_layout.addWidget(QLabel("Drum Temp:"))
        temp_displays_layout.addWidget(self.accT_display)
        
        # LCD Display for Rate of Rise
        self.ror_display = QLCDNumber()
        self.ror_display.setDigitCount(4)
        self.ror_display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self.ror_display.setStyleSheet("background-color: black; color: orange;")
        temp_displays_layout.addWidget(QLabel("ROR (°F/min):"))
        temp_displays_layout.addWidget(self.ror_display)
        
        layout.addLayout(temp_displays_layout)
        
        # Roast Info & Controls
        controls_layout = QHBoxLayout()
        
        # Grill Target Temp Input
        self.grill_target_temp = QSpinBox()
        self.grill_target_temp.setRange(100, 700)
        self.grill_target_temp.setValue(640) # grill_target_temp initial
        self.grill_target_temp.valueChanged.connect(self.update_target_lines)

        controls_layout.addWidget(QLabel("Target Temp:"))
        controls_layout.addWidget(self.grill_target_temp)

        # Target Time Input
        self.target_time = QTimeEdit()
        self.target_time.setDisplayFormat("mm:ss")
        self.target_time.setTime(QTime(0, 16, 0))
        self.target_time.timeChanged.connect(self.update_target_lines)

        controls_layout.addWidget(QLabel("Target Time:"))
        controls_layout.addWidget(self.target_time)
        
        # ROR Window Input
        self.ror_window_spinbox = QSpinBox()
        self.ror_window_spinbox.setRange(10, 120)  # 10 seconds to 2 minutes
        self.ror_window_spinbox.setValue(30)
        self.ror_window_spinbox.valueChanged.connect(self.update_ror_window)
        controls_layout.addWidget(QLabel("ROR Window (s):"))
        controls_layout.addWidget(self.ror_window_spinbox)
        
        layout.addLayout(controls_layout)

        # Crack Buttons
        btn_crack_layout = QGridLayout()
        self.first_crack_btn = QPushButton("First Crack")
        self.first_crack_btn.clicked.connect(self.record_first_crack)
        self.second_crack_btn = QPushButton("Second Crack")
        self.second_crack_btn.clicked.connect(self.record_second_crack)
        
        btn_crack_layout.addWidget(self.first_crack_btn, 0, 0, 1, 2)
        btn_crack_layout.addWidget(self.second_crack_btn, 0, 2, 1, 2)
        layout.addLayout(btn_crack_layout)
        
        # Roast Notes
        self.notes = QTextEdit()
        layout.addWidget(QLabel("Roast Notes:"))
        layout.addWidget(self.notes)

        # Smoothing slider
        smooth_layout = QHBoxLayout()
        smooth_label = QLabel("Smoothing:")
        self.smooth_slider = QSlider(Qt.Orientation.Horizontal)
        self.smooth_slider.setMinimum(1)
        self.smooth_slider.setMaximum(40)
        self.smooth_slider.setValue(15)
        self.smooth_slider.valueChanged.connect(self.update_smoothing)
        self.smooth_value_label = QLabel("15s")
        
        smooth_layout.addWidget(smooth_label)
        smooth_layout.addWidget(self.smooth_slider)
        smooth_layout.addWidget(self.smooth_value_label)
        layout.addLayout(smooth_layout)

        # Control Buttons
        btn_control_layout = QGridLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_logging)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_logging)
        self.stop_btn.setEnabled(False)
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self.reset_data)
        self.save_btn = QPushButton("Save Log")
        self.save_btn.clicked.connect(self.save_data)
        
        btn_control_layout.addWidget(self.start_btn, 0, 0)
        btn_control_layout.addWidget(self.stop_btn, 0, 1)
        btn_control_layout.addWidget(self.reset_btn, 0, 2)
        btn_control_layout.addWidget(self.save_btn, 0, 3)
        self.load_ghost_btn = QPushButton("Load Ghost")
        self.load_ghost_btn.clicked.connect(self.load_ghost_profile)
        btn_control_layout.addWidget(self.load_ghost_btn, 1, 0)
        layout.addLayout(btn_control_layout)
        
        self.setGeometry(100, 100, 900, 900)  # Made window taller to accommodate ROR display
        
        # Initialize target temperature line
        self.update_target_lines()
        
        # Connect view box update
        self.graph.getViewBox().sigResized.connect(self.update_views)
        
    def update_views(self):
        """Update the ROR axis to match the main plot view"""
        self.ror_axis.setGeometry(self.graph.getViewBox().sceneBoundingRect())
        
    def update_ror_window(self):
        """Update the ROR calculation window"""
        self.ror_window = self.ror_window_spinbox.value()
        
    def calculate_ror(self, times, temps, window_seconds=30):
        """
        Calculate Rate of Rise (ROR) in °F per minute
        """
        if len(times) < 2 or len(temps) < 2:
            return np.array([])
            
        ror_values = []
        
        for i in range(len(times)):
            if i == 0:
                ror_values.append(0)  # First point has no ROR
                continue
                
            # Find the point that's approximately window_seconds ago
            target_time = times[i] - window_seconds
            
            # Find the closest earlier point
            start_idx = 0
            for j in range(i-1, -1, -1):
                if times[j] <= target_time:
                    start_idx = j
                    break
            
            # Calculate ROR
            time_diff = times[i] - times[start_idx]
            temp_diff = temps[i] - temps[start_idx]
            
            if time_diff > 0:
                # Convert to °F per minute
                ror = (temp_diff / time_diff) * 60
                ror_values.append(ror)
            else:
                ror_values.append(0)
                
        return np.array(ror_values)
        
    def setup_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(100)  # Update every 100ms
        
    def update_smoothing(self):
        self.smooth_window = self.smooth_slider.value()
        self.smooth_value_label.setText(f"{self.smooth_window}s")

    def update_target_lines(self):
        # Clear any existing target line
        if self.target_temp_line:
            self.graph.removeItem(self.target_temp_line)
        
        # Get target temperature
        grill_target_temp = self.grill_target_temp.value()
        
        # Create target temperature line
        self.target_temp_line = pg.InfiniteLine(
            pos=grill_target_temp, 
            angle=0, 
            pen=pg.mkPen('b', width=1, style=Qt.PenStyle.DashLine),
            label=f"{grill_target_temp}°F",
            labelOpts={'position': 0.1, 'color': 'b', 'fill': (0, 0, 0, 0)}
        )
        self.graph.addItem(self.target_temp_line)
        
        # Update x-axis range based on target time
        target_minutes = self.target_time.time().minute()
        target_seconds = self.target_time.time().second()
        target_time_seconds = target_minutes * 60 + target_seconds
        
        # Set x-axis to go from 0 to target_time + 3 minutes (in seconds)
        self.graph.setXRange(0, target_time_seconds + 180)
        
        # Set y-axis to go from 300 to grill_target_temp + 50
        self.graph.setYRange(0, grill_target_temp + 100)
        
        # Set ROR axis range (typically -10 to +50 °F/min for coffee roasting)
        self.ror_axis.setYRange(-10, 50)

    def format_seconds_to_mmss(self, seconds):
        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        return f"{minutes:02d}:{remaining_seconds:02d}"

    def update_plot(self):
        # Process all available data from queue
        while not self.data_queue.empty():
            timestamp, uuid, temp = self.data_queue.get()
            iso_timestamp = datetime.now().astimezone().isoformat()
            self.iso_timestamps.append(iso_timestamp)
            self.timestamps.append(timestamp)
            
            # Ensure both temperature arrays have the same length
            if uuid == self.ble_handler.ENV_SENSE_TEMP1_UUID:
                self.grill_temp_data.append(temp)
                if len(self.grill_temp_data) > len(self.drum_temp_data):
                    self.drum_temp_data.append(self.drum_temp_data[-1] if self.drum_temp_data else None)
            else:
                self.drum_temp_data.append(temp)
                if len(self.drum_temp_data) > len(self.grill_temp_data):
                    self.grill_temp_data.append(self.grill_temp_data[-1] if self.grill_temp_data else None)
        
        if not self.timestamps or len(self.grill_temp_data) == 0 or len(self.drum_temp_data) == 0:
            return
            
        # Convert to numpy arrays for processing
        if self.roast_started and self.start_time:
            # Use elapsed time since roast start in seconds
            # Fix: Handle the case where timestamps are not datetime objects
            if isinstance(self.timestamps[0], datetime):
                times = np.array([(t - self.start_time).total_seconds() for t in self.timestamps])
            else:
                # If timestamps are numeric values, calculate relative time from start_time timestamp
                start_timestamp = self.timestamps[0]
                times = np.array([t - start_timestamp for t in self.timestamps])
        else:
            # Use relative time from first measurement
            first_timestamp = self.timestamps[0]
            times = np.array([t - first_timestamp for t in self.timestamps])
            
        grill_temp = np.array(self.grill_temp_data, dtype=float)
        drum_temp = np.array(self.drum_temp_data, dtype=float)

        # Calculate ROR for drum temperature
        ror = self.calculate_ror(times, drum_temp, self.ror_window)

        # Update LCD displays with latest temperatures
        if len(grill_temp) > 0:
            self.grillT_display.display(int(grill_temp[-1]))
        if len(drum_temp) > 0:
            self.accT_display.display(int(drum_temp[-1]))
        if len(ror) > 0:
            self.ror_display.display(f"{ror[-1]:.1f}")
        
        # Apply smoothing
        if len(times) >= self.smooth_window:
            grill_temp_smooth = np.convolve(grill_temp, np.ones(self.smooth_window)/self.smooth_window, 'valid')
            drum_temp_smooth = np.convolve(drum_temp, np.ones(self.smooth_window)/self.smooth_window, 'valid')
            times_smooth = times[self.smooth_window-1:]
            
            # Smooth ROR data too
            if len(ror) >= self.smooth_window:
                ror_smooth = np.convolve(ror, np.ones(self.smooth_window)/self.smooth_window, 'valid')
                ror_times = times[self.smooth_window-1:]
                # Update ROR plot
                self.ror_curve.setData(ror_times, ror_smooth)
            
            # Update plots
            self.grill_temp_curve.setData(times_smooth, grill_temp_smooth)
            self.drum_temp_curve.setData(times_smooth, drum_temp_smooth)
            
            # Update x-axis tick labels to show mm:ss format
            axis = self.graph.getAxis('bottom')
            ticks = [(t, self.format_seconds_to_mmss(t)) for t in range(0, int(max(times_smooth)) + 60, 60)]
            axis.setTicks([ticks])
        else:
            # If we don't have enough data for smoothing yet, plot raw data
            self.grill_temp_curve.setData(times, grill_temp)
            self.drum_temp_curve.setData(times, drum_temp)
            if len(ror) > 0:
                self.ror_curve.setData(times, ror)

    def record_first_crack(self):
        if not self.roast_started:
            return
            
        current_time = datetime.now()
        elapsed_seconds = (current_time - self.start_time).total_seconds()
        formatted_time = self.format_seconds_to_mmss(elapsed_seconds)
        
        # Get current ROR for logging
        current_ror = self.ror_display.value() if hasattr(self.ror_display, 'value') else 0
        
        if not self.first_crack_start:
            self.first_crack_start = current_time
            note = f"First Crack Start: {formatted_time} (ROR: {current_ror:.1f}°F/min)\n"
            self.first_crack_btn.setText("End First Crack")
        else:
            self.first_crack_end = current_time
            note = f"First Crack End: {formatted_time} (ROR: {current_ror:.1f}°F/min)\n"
            self.first_crack_btn.setEnabled(False)
            self.first_crack_btn.setText("First Crack Recorded")
        
        self.notes.insertPlainText(note)
        
    def load_ghost_profile(self):
        from PyQt6.QtWidgets import QFileDialog
        filename, _ = QFileDialog.getOpenFileName(self, "Open Ghost Profile", "", "CSV Files (*.csv)")
        if not filename:
            return

        times = []
        grill_temps = []
        drum_temps = []

        with open(filename, 'r') as f:
            next(f)  # skip header
            for i, line in enumerate(f):
                parts = line.strip().split(',')
                if len(parts) != 3:
                    continue
                _, grill_str, drum_str = parts
                try:
                    grill = float(grill_str)
                    drum = float(drum_str)
                    grill_temps.append(grill)
                    drum_temps.append(drum)
                    times.append(i)  # simple time base
                except ValueError:
                    continue

        self.ghost_grill_curve.setData(times, grill_temps)
        self.ghost_drum_curve.setData(times, drum_temps)

    def record_second_crack(self):
        if not self.roast_started:
            return
            
        current_time = datetime.now()
        elapsed_seconds = (current_time - self.start_time).total_seconds()
        formatted_time = self.format_seconds_to_mmss(elapsed_seconds)
        
        # Get current ROR for logging
        current_ror = self.ror_display.value() if hasattr(self.ror_display, 'value') else 0
        
        if not self.second_crack_start:
            self.second_crack_start = current_time
            note = f"Second Crack Start: {formatted_time} (ROR: {current_ror:.1f}°F/min)\n"
            self.second_crack_btn.setText("End Second Crack")
        else:
            self.second_crack_end = current_time
            note = f"Second Crack End: {formatted_time} (ROR: {current_ror:.1f}°F/min)\n"
            self.second_crack_btn.setEnabled(False)
            self.second_crack_btn.setText("Second Crack Recorded")
        
        self.notes.insertPlainText(note)

    def start_logging(self):
        self.ble_handler.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.first_crack_btn.setEnabled(True)
        self.second_crack_btn.setEnabled(True)
        
        # Record start time
        self.start_time = datetime.now()
        self.roast_started = True
        
        # Add initial note
        self.notes.clear()
        self.notes.insertPlainText(f"Roast started at {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.notes.insertPlainText(f"Target Temperature: {self.grill_target_temp.value()}°F\n")
        self.notes.insertPlainText(f"Target Time: {self.target_time.time().toString('mm:ss')}\n")
        self.notes.insertPlainText(f"ROR Window: {self.ror_window}s\n\n")
        
    def stop_logging(self):
        self.ble_handler.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        if self.roast_started:
            elapsed_time = (datetime.now() - self.start_time).total_seconds()
            formatted_time = self.format_seconds_to_mmss(elapsed_time)
            self.notes.insertPlainText(f"\nRoast stopped at {formatted_time}\n")
        
    def reset_data(self):
        self.timestamps.clear()
        self.iso_timestamps.clear()
        self.grill_temp_data.clear()
        self.drum_temp_data.clear()
        self.ror_data.clear()
        self.notes.clear()
        self.roast_started = False
        self.start_time = None
        self.first_crack_start = None
        self.first_crack_end = None
        self.second_crack_start = None
        self.second_crack_end = None
        self.first_crack_btn.setText("First Crack")
        self.first_crack_btn.setEnabled(True)
        self.second_crack_btn.setText("Second Crack")
        self.second_crack_btn.setEnabled(True)

        #reset graph
        self.grill_temp_curve.setData([], [])
        self.drum_temp_curve.setData([], [])
        self.ror_curve.setData([], [])
             
    def save_data(self):
        if not self.timestamps:
            return
        
        # Calculate ROR for saving
        if self.roast_started and self.start_time:
            if isinstance(self.timestamps[0], datetime):
                times = np.array([(t - self.start_time).total_seconds() for t in self.timestamps])
            else:
                start_timestamp = self.timestamps[0]
                times = np.array([t - start_timestamp for t in self.timestamps])
        else:
            first_timestamp = self.timestamps[0]
            times = np.array([t - first_timestamp for t in self.timestamps])
            
        drum_temp = np.array(self.drum_temp_data, dtype=float)
        ror = self.calculate_ror(times, drum_temp, self.ror_window)
        
        # Create the data rows as a list of lists
        rows = []
        for i, (time, grill_temp, drum_temp_val) in enumerate(zip(self.iso_timestamps, self.grill_temp_data, self.drum_temp_data)):
            ror_val = ror[i] if i < len(ror) else 0
            rows.append([time, grill_temp, drum_temp_val, ror_val])
        
        filename = datetime.now().strftime('roast_data_%Y%m%d_%H%M%S.csv')
        profiles_folder = 'profiles'

        if not os.path.exists(profiles_folder):
            os.makedirs(profiles_folder)

        # Create full path to CSV file    
        filename = os.path.join(profiles_folder, filename)

        # Write data to CSV file
        with open(filename, 'w') as f:
            # Write header
            f.write('time,grill_temp,drum_temp,ror\n')
            # Write data rows
            for row in rows:
                f.write(f'{row[0]},{row[1]},{row[2]},{row[3]:.2f}\n')
                
        # Also save notes
        notes_filename = os.path.join(profiles_folder, 
                                     datetime.now().strftime('roast_notes_%Y%m%d_%H%M%S.txt'))
        with open(notes_filename, 'w') as f:
            f.write(self.notes.toPlainText())
            
        # Show confirmation message in notes
        self.notes.insertPlainText(f"\nData saved to {filename}\n")
        self.notes.insertPlainText(f"Notes saved to {notes_filename}\n")
        
    def closeEvent(self, event):
        self.stop_logging()
        event.accept()

    def filter_spike(self, new_value, data, window=10, std_multiplier=2.5, grace_period=5):
        """
        Filters out spikes using standard deviation of recent values.
        If a new value is consistently out of expected range, it's eventually accepted.
        """
        if not hasattr(self, '_spike_buffer'):
            self._spike_buffer = []

        if len(data) < window:
            self._spike_buffer.clear()
            return new_value  # Accept due to lack of historical context

        recent_values = list(data)[-window:]
        mean = statistics.mean(recent_values)
        std_dev = statistics.stdev(recent_values)
        if std_dev <= 1: std_dev = 1  # Prevent division by zero or too small std_dev

        # Accept if within normal range
        if abs(new_value - mean) <= std_multiplier:  # Allow a fixed range of 15°F for now
            self._spike_buffer.clear()
            print( f"Accepting value:\t{new_value}")
            return new_value

        # Otherwise treat as potential spike and buffer it
        self._spike_buffer.append(new_value)
        if len(self._spike_buffer) >= grace_period:
            avg = sum(self._spike_buffer) / len(self._spike_buffer)
            self._spike_buffer.clear()
            print (f"Returning buffer avg: {avg}")
            return avg  # Accept the average of buffered outliers
        print (f"Spike:\t{new_value}\tAllowed Range: ({mean - std_multiplier} - {mean + std_multiplier})")
        return data[-1]  # Reject spike for now

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = RoasterMonitor()
    window.show()
    sys.exit(app.exec())