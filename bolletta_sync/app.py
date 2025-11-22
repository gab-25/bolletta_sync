import asyncio
import sys
from datetime import date
from logging import StreamHandler

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QDateEdit, QCheckBox, QPushButton, QTextEdit,
                               QLabel, QGroupBox, QFormLayout)

from bolletta_sync.main import Provider, main, logger


class QTextEditHandler(StreamHandler):
    def __init__(self, text_widget: QTextEdit):
        StreamHandler.__init__(self)
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.append(msg)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Bolletta Sync")
        self.resize(800, 700)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        date_group = QGroupBox("Select Date Range")
        date_layout = QFormLayout()

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addDays(-10))
        self.start_date.dateChanged.connect(self.validate_form)

        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        self.end_date.dateChanged.connect(self.validate_form)

        date_layout.addRow("Start Date:", self.start_date)
        date_layout.addRow("End Date:", self.end_date)
        date_group.setLayout(date_layout)

        main_layout.addWidget(date_group)

        providers_group = QGroupBox("Providers")
        providers_layout = QVBoxLayout()

        self.cb_providers = {}
        for provider in list(Provider):
            cb_provider = QCheckBox(str(provider.value).replace("_", " ").title())
            cb_provider.stateChanged.connect(self.validate_form)
            self.cb_providers[provider.name] = cb_provider
            providers_layout.addWidget(cb_provider)
        providers_group.setLayout(providers_layout)

        main_layout.addWidget(providers_group)

        self.btn_sync = QPushButton("SYNC")
        self.btn_sync.setMinimumHeight(40)
        self.btn_sync.setStyleSheet("font-weight: bold; font-size: 14px; background-color: #0078d7;")
        self.btn_sync.clicked.connect(self.exec_sync)

        main_layout.addWidget(self.btn_sync)

        self.log_area = QTextEdit()
        self.log_area.setPlaceholderText("Your sync logs will appear here...")
        self.log_area.setReadOnly(True)

        logger.addHandler(QTextEditHandler(self.log_area))

        main_layout.addWidget(QLabel("Output:"))
        main_layout.addWidget(self.log_area)

        self.validate_form()

    def validate_form(self):
        is_date_valid = self.end_date.date() > self.start_date.date()
        is_provider_selected = any(cb.isChecked() for cb in self.cb_providers.values())
        self.btn_sync.setEnabled(is_date_valid and is_provider_selected)

    def exec_sync(self):
        selected_start_date: date = self.start_date.date().toPython()
        selected_end_date: date = self.end_date.date().toPython()
        selected_providers: list[Provider] = []
        for value, cb_provider in self.cb_providers.items():
            if cb_provider.isChecked(): selected_providers.append(Provider[value])

        self.log_area.clear()

        asyncio.run(main(selected_providers, selected_start_date, selected_end_date))


if __name__ == "__main__":
    app = QApplication(sys.argv)

    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
