import sys
import os
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel)
from PyQt6.QtCore import QTimer, Qt
import pyqtgraph as pg
from queue import Queue
from collections import deque
from ble_handler import BLEHandler
from datetime import datetime

class RoasterMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Coffee Roaster Monitor")
        
        # Data storage
        self.data_queue = Queue()
        self.ble_handler = BLEHandler(self.data_queue)
        self.timestamps = deque(maxlen=3600)  # Store up to 1 hour of data
        self.iso_timestamps = deque(maxlen=3600)
        self.temp1_data = deque(maxlen=3600)
        self.temp2_data = deque(maxlen=3600)

        # 
        
        # Smoothing window
        self.smooth_window = 5
        
        self.init_ui()
        self.setup_timer()
        
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create plot
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setLabel('left', 'Temperature (°F)')
        self.plot_widget.setLabel('bottom', 'Time (s)')
        
        self.temp1_curve = self.plot_widget.plot(pen=pg.mkPen('b', width=4))
        self.temp2_curve = self.plot_widget.plot(pen=pg.mkPen('r', width=4))
        
        layout.addWidget(self.plot_widget)
        
        # Controls
        controls_layout = QHBoxLayout()
        
        # Buttons
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start_logging)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_logging)
        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self.reset_data)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_data)
        
        # Smoothing slider
        smooth_layout = QHBoxLayout()
        smooth_label = QLabel("Smoothing:")
        self.smooth_slider = QSlider(Qt.Orientation.Horizontal)
        self.smooth_slider.setMinimum(1)
        self.smooth_slider.setMaximum(40)
        self.smooth_slider.setValue(5)
        self.smooth_slider.valueChanged.connect(self.update_smoothing)
        self.smooth_value_label = QLabel("5s")
        
        smooth_layout.addWidget(smooth_label)
        smooth_layout.addWidget(self.smooth_slider)
        smooth_layout.addWidget(self.smooth_value_label)
        
        # Add controls to layout
        for widget in [self.start_button, self.stop_button, 
                      self.reset_button, self.save_button]:
            controls_layout.addWidget(widget)
        
        layout.addLayout(controls_layout)
        layout.addLayout(smooth_layout)
        
        self.setGeometry(100, 100, 800, 600)
        
    def setup_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(100)  # Update every 100ms
        
    def update_smoothing(self):
        self.smooth_window = self.smooth_slider.value()
        self.smooth_value_label.setText(f"{self.smooth_window}s")

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
        times = np.array(self.timestamps) - self.timestamps[0]
        temp1 = np.array(self.temp1_data, dtype=float)
        temp2 = np.array(self.temp2_data, dtype=float)
        
        # Apply smoothing
        if len(times) >= self.smooth_window:
            temp1_smooth = np.convolve(temp1, np.ones(self.smooth_window)/self.smooth_window, 'valid')
            temp2_smooth = np.convolve(temp2, np.ones(self.smooth_window)/self.smooth_window, 'valid')
            times_smooth = times[self.smooth_window-1:]
            
            # Update plots
            self.temp1_curve.setData(times_smooth, temp1_smooth)
            self.temp2_curve.setData(times_smooth, temp2_smooth)
        else:
            # If we don't have enough data for smoothing yet, plot raw data
            self.temp1_curve.setData(times, temp1)
            self.temp2_curve.setData(times, temp2)

    def start_logging(self):
        self.ble_handler.start()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        
    def stop_logging(self):
        self.ble_handler.stop()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        
    def reset_data(self):
        self.timestamps.clear()
        self.temp1_data.clear()
        self.temp2_data.clear()
        
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
        
    def closeEvent(self, event):
        self.stop_logging()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = RoasterMonitor()
    window.show()
    sys.exit(app.exec())