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

class RoasterMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Coffee Roaster Monitor")
        
        # Data storage
        self.data_queue = Queue()
        self.ble_handler = BLEHandler(self.data_queue)
        self.timestamps = deque(maxlen=3600)  # Store up to 1 hour of data
        self.iso_timestamps = deque(maxlen=3600)
        self.temp1_data = deque(maxlen=3600)  # Grill temperature
        self.temp2_data = deque(maxlen=3600)  # Ambient temperature

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
        
        self.temp1_curve = self.graph.plot(pen=pg.mkPen('r', width=3), name="Grill Temp")
        self.temp2_curve = self.graph.plot(pen=pg.mkPen('b', width=2), name="Ambient Temp")
        
        layout.addWidget(self.graph)
        
        # Roast Info & Controls
        controls_layout = QHBoxLayout()
        
        # LCD Display for Grill Temperature
        self.grillT_display = QLCDNumber()
        self.grillT_display.setDigitCount(3)
        self.grillT_display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self.grillT_display.setStyleSheet("background-color: black; color: red;")
        controls_layout.addWidget(QLabel("Grill Temp:"))
        controls_layout.addWidget(self.grillT_display)
        
        # Target Temp Input
        self.target_temp = QSpinBox()
        self.target_temp.setRange(100, 700)
        self.target_temp.setValue(640)
        self.target_temp.valueChanged.connect(self.update_target_lines)

        controls_layout.addWidget(QLabel("Target Temp:"))
        controls_layout.addWidget(self.target_temp)

        # Target Time Input
        self.target_time = QTimeEdit()
        self.target_time.setDisplayFormat("mm:ss")
        self.target_time.setTime(QTime(0, 16, 0))
        self.target_time.timeChanged.connect(self.update_target_lines)

        controls_layout.addWidget(QLabel("Target Time:"))
        controls_layout.addWidget(self.target_time)
        
        # LCD Display for Ambient Temperature
        self.accT_display = QLCDNumber()
        self.accT_display.setDigitCount(3)
        self.accT_display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self.accT_display.setStyleSheet("background-color: black; color: blue;")
        controls_layout.addWidget(QLabel("Amb. Temp:"))
        controls_layout.addWidget(self.accT_display)
        
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
        layout.addLayout(btn_control_layout)
        
        self.setGeometry(100, 100, 900, 800)
        
        # Initialize target temperature line
        self.update_target_lines()
        
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
        target_temp = self.target_temp.value()
        
        # Create target temperature line
        self.target_temp_line = pg.InfiniteLine(
            pos=target_temp, 
            angle=0, 
            pen=pg.mkPen('g', width=2, style=Qt.PenStyle.DashLine),
            label=f"Target: {target_temp}°F",
            labelOpts={'position': 0.1, 'color': 'g', 'fill': (0, 0, 0, 0)}
        )
        self.graph.addItem(self.target_temp_line)
        
        # Update x-axis range based on target time
        target_minutes = self.target_time.time().minute()
        target_seconds = self.target_time.time().second()
        target_time_seconds = target_minutes * 60 + target_seconds
        
        # Set x-axis to go from 0 to target_time + 3 minutes (in seconds)
        self.graph.setXRange(0, target_time_seconds + 180)
        
        # Set y-axis to go from 300 to target_temp + 50
        self.graph.setYRange(0, target_temp + 100)

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
                self.temp1_data.append(temp)
                if len(self.temp1_data) > len(self.temp2_data):
                    self.temp2_data.append(self.temp2_data[-1] if self.temp2_data else None)
            else:
                self.temp2_data.append(temp)
                if len(self.temp2_data) > len(self.temp1_data):
                    self.temp1_data.append(self.temp1_data[-1] if self.temp1_data else None)
        
        if not self.timestamps or len(self.temp1_data) == 0 or len(self.temp2_data) == 0:
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
            
        temp1 = np.array(self.temp1_data, dtype=float)
        temp2 = np.array(self.temp2_data, dtype=float)
        
        # Update LCD displays with latest temperatures
        if len(temp1) > 0:
            self.grillT_display.display(int(temp1[-1]))
        if len(temp2) > 0:
            self.accT_display.display(int(temp2[-1]))
        
        # Apply smoothing
        if len(times) >= self.smooth_window:
            temp1_smooth = np.convolve(temp1, np.ones(self.smooth_window)/self.smooth_window, 'valid')
            temp2_smooth = np.convolve(temp2, np.ones(self.smooth_window)/self.smooth_window, 'valid')
            times_smooth = times[self.smooth_window-1:]
            
            # Update plots
            self.temp1_curve.setData(times_smooth, temp1_smooth)
            self.temp2_curve.setData(times_smooth, temp2_smooth)
            
            # Update x-axis tick labels to show mm:ss format
            axis = self.graph.getAxis('bottom')
            ticks = [(t, self.format_seconds_to_mmss(t)) for t in range(0, int(max(times_smooth)) + 60, 60)]
            axis.setTicks([ticks])
        else:
            # If we don't have enough data for smoothing yet, plot raw data
            self.temp1_curve.setData(times, temp1)
            self.temp2_curve.setData(times, temp2)

    def record_first_crack(self):
        if not self.roast_started:
            return
            
        current_time = datetime.now()
        elapsed_seconds = (current_time - self.start_time).total_seconds()
        formatted_time = self.format_seconds_to_mmss(elapsed_seconds)
        
        if not self.first_crack_start:
            self.first_crack_start = current_time
            note = f"First Crack Start: {formatted_time}\n"
            self.first_crack_btn.setText("End First Crack")
        else:
            self.first_crack_end = current_time
            note = f"First Crack End: {formatted_time}\n"
            self.first_crack_btn.setEnabled(False)
            self.first_crack_btn.setText("First Crack Recorded")
        
        self.notes.insertPlainText(note)

    def record_second_crack(self):
        if not self.roast_started:
            return
            
        current_time = datetime.now()
        elapsed_seconds = (current_time - self.start_time).total_seconds()
        formatted_time = self.format_seconds_to_mmss(elapsed_seconds)
        
        if not self.second_crack_start:
            self.second_crack_start = current_time
            note = f"Second Crack Start: {formatted_time}\n"
            self.second_crack_btn.setText("End Second Crack")
        else:
            self.second_crack_end = current_time
            note = f"Second Crack End: {formatted_time}\n"
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
        self.notes.insertPlainText(f"Target Temperature: {self.target_temp.value()}°F\n")
        self.notes.insertPlainText(f"Target Time: {self.target_time.time().toString('mm:ss')}\n\n")
        
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
        self.temp1_data.clear()
        self.temp2_data.clear()
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
        self.temp1_curve.setData([], [])
        self.temp2_curve.setData([], [])
        
        
    def save_data(self):
        if not self.timestamps:
            return
            
        # Create the data rows as a list of lists
        rows = []
        for time, temp1, temp2 in zip(self.iso_timestamps, self.temp1_data, self.temp2_data):
            rows.append([time, temp1, temp2])
        
        filename = datetime.now().strftime('roast_data_%Y%m%d_%H%M%S.csv')
        profiles_folder = 'profiles'

        if not os.path.exists(profiles_folder):
            os.makedirs(profiles_folder)

        # Create full path to CSV file    
        filename = os.path.join(profiles_folder, filename)

        # Write data to CSV file
        with open(filename, 'w') as f:
            # Write header
            f.write('time,temp1,temp2\n')
            # Write data rows
            for row in rows:
                f.write(f'{row[0]},{row[1]},{row[2]}\n')
                
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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = RoasterMonitor()
    window.show()
    sys.exit(app.exec())