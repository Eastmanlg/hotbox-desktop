from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSlider, QLCDNumber, QLabel, QSpinBox, QProgressBar, QTabWidget,
    QGroupBox, QTextEdit, QTimeEdit, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer, QTime
import pyqtgraph as pg
import sys

class CoffeeRoasterUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Coffee Roaster Monitor")
        self.setGeometry(100, 100, 800, 600)
        
        layout = QVBoxLayout()
        
        # Graph for temperature
        self.graph = pg.PlotWidget()
        self.graph.setTitle("Temperature Graph")
        self.graph.setLabel("left", "Temperature (°F)")
        self.graph.setLabel("bottom", "Time (s)")
        self.graph.showGrid(x=True, y=True)
        layout.addWidget(self.graph)
        
        # Roast Info & Controls
        controls_layout = QHBoxLayout()
        
        # LCD Display for Grill Temperature
        self.grillT_display = QLCDNumber()
        self.grillT_display.setDigitCount(3)
        controls_layout.addWidget(QLabel("Grill Temp:"))
        controls_layout.addWidget(self.grillT_display)
        
        # Target Temp Input
        self.target_temp = QSpinBox()
        self.target_temp.setRange(350, 700)
        self.target_temp.setValue(640)

        controls_layout.addWidget(QLabel("Target Temp:"))
        controls_layout.addWidget(self.target_temp)

        # Target Time Input
        self.target_time = QTimeEdit()
        self.target_time.setDisplayFormat("mm:ss")
        self.target_time.setTime(QTime(0,16, 0))

        controls_layout.addWidget(QLabel("Target Time:"))
        controls_layout.addWidget(self.target_time)
        
        # LCD Display for Ambient Temperature
        self.accT_display = QLCDNumber()
        self.accT_display.setDigitCount(3)
        controls_layout.addWidget(QLabel("Amb. Temp:"))
        controls_layout.addWidget(self.accT_display)
        
        layout.addLayout(controls_layout)
        
        # Roast Progress Bar
        self.progress_bar = QProgressBar()
        layout.addWidget(QLabel("Roast Progress:"))
        layout.addWidget(self.progress_bar)

        # Buttons
        btn_crack_layout = QGridLayout()
        self.first_crack_btn = QPushButton("First Crack")
        self.second_crack_btn = QPushButton("Second Crack")

        
        

        
        btn_crack_layout.addWidget(self.first_crack_btn,0,0,1,2)
        btn_crack_layout.addWidget(self.second_crack_btn,0,2,1,2)
        layout.addLayout(btn_crack_layout)
        
        
        # Roast Notes
        self.notes = QTextEdit()
        layout.addWidget(QLabel("Roast Notes:"))
        layout.addWidget(self.notes)

        btn_control_layout = QGridLayout()
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.reset_btn = QPushButton("Reset")
        self.save_btn = QPushButton("Save Log")
        btn_control_layout.addWidget(self.start_btn, 0, 0)
        btn_control_layout.addWidget(self.stop_btn, 0, 1)
        btn_control_layout.addWidget(self.reset_btn, 0, 2)
        btn_control_layout.addWidget(self.save_btn, 0, 3)
        layout.addLayout(btn_control_layout)
        
        self.setLayout(layout)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CoffeeRoasterUI()
    window.show()
    sys.exit(app.exec())
