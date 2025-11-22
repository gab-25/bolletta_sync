import asyncio
import sys

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton,
                               QCheckBox, QDateEdit, QLabel, QVBoxLayout, QWidget)

from bolletta_sync.main import main, Provider


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bolletta Sync")
        self.setFixedSize(400, 300)
        self.checkboxes: list[QCheckBox] = []
        self.start_button = QPushButton("Start", self)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        for provider in Provider:
            checkbox = QCheckBox(provider.value, self)
            checkbox.stateChanged.connect(self.validate_form)
            self.checkboxes.append(checkbox)
            layout.addWidget(checkbox)

        self.date_label1 = QLabel("Start Date:", self)
        self.date_picker1 = QDateEdit(self, date=QDate.currentDate().addDays(-10))
        self.date_picker1.setDisplayFormat("dd/MM/yyyy")
        self.date_picker1.dateChanged.connect(self.validate_form)
        self.date_label2 = QLabel("End Date:", self)
        self.date_picker2 = QDateEdit(self, date=QDate.currentDate())
        self.date_picker2.setDisplayFormat("dd/MM/yyyy")
        self.date_picker2.dateChanged.connect(self.validate_form)

        layout.addWidget(self.date_label1)
        layout.addWidget(self.date_picker1)
        layout.addWidget(self.date_label2)
        layout.addWidget(self.date_picker2)

        self.start_button.setFixedSize(100, 30)
        layout.addWidget(self.start_button)
        self.start_button.clicked.connect(self.on_button_click)

        self.validate_form()

    def validate_form(self):
        has_provider = any(cb.isChecked() for cb in self.checkboxes)
        valid_dates = self.date_picker1.date() <= self.date_picker2.date()
        self.start_button.setEnabled(has_provider and valid_dates)

    def on_button_click(self):
        asyncio.run(main())


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
