import asyncio
import logging
import os.path
import tomllib
from datetime import date, datetime, timedelta
from logging import StreamHandler
from threading import Thread

import customtkinter as ctk

from bolletta_sync.main import Provider, main, logger, pyproject, base_path


class TextBoxHandler(StreamHandler):
    def __init__(self, text_widget):
        StreamHandler.__init__(self)
        self.text_widget = text_widget
        self.setFormatter(logger.handlers[0].formatter)

    def emit(self, record):
        if record.exc_info is None and record.levelno >= logging.ERROR and record.args:
            for arg in record.args:
                if isinstance(arg, Exception):
                    record.exc_info = (type(arg), arg, arg.__traceback__)
                    break
        msg = self.format(record) + '\n'
        self.text_widget.after(0, self.append_text, msg)

    def append_text(self, msg):
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", msg)
        self.text_widget.configure(state="disabled")
        self.text_widget.see("end")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.is_syncing = False

        self.title("Bolletta Sync")
        self.geometry("800x700")

        icon_path = os.path.join(base_path, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # Date Group
        self.date_frame = ctk.CTkFrame(self)
        self.date_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.date_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.date_frame, text="Select Date Range (YYYY-MM-DD)",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, columnspan=2, padx=10, pady=10,
                                                                    sticky="w")

        ctk.CTkLabel(self.date_frame, text="Start Date:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.start_date = ctk.CTkEntry(self.date_frame)
        self.start_date.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        start_d = date.today() - timedelta(days=10)
        self.start_date.insert(0, start_d.isoformat())
        self.start_date.bind("<KeyRelease>", lambda e: self.validate_form())

        ctk.CTkLabel(self.date_frame, text="End Date:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.end_date = ctk.CTkEntry(self.date_frame)
        self.end_date.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

        self.end_date.insert(0, date.today().isoformat())
        self.end_date.bind("<KeyRelease>", lambda e: self.validate_form())

        # Providers Group
        self.providers_frame = ctk.CTkFrame(self)
        self.providers_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        ctk.CTkLabel(self.providers_frame, text="Providers",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(padx=10, pady=10, anchor="w")

        self.cb_providers = {}
        for provider in list(Provider):
            cb = ctk.CTkCheckBox(self.providers_frame, text=str(provider.value).replace("_", " ").title(),
                                 command=self.validate_form)
            cb.pack(padx=10, pady=5, anchor="w")
            self.cb_providers[provider.name] = cb

        # Sync Button
        self.btn_sync = ctk.CTkButton(self, text="SYNC", command=self.exec_sync, height=40,
                                      font=ctk.CTkFont(size=14, weight="bold"))
        self.btn_sync.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        # Log Area
        ctk.CTkLabel(self, text="Output:").grid(row=3, column=0, padx=20, pady=(10, 0), sticky="nw")
        self.log_area = ctk.CTkTextbox(self)
        self.log_area.grid(row=4, column=0, padx=20, pady=(5, 10), sticky="nsew")
        self.log_area.insert("0.0", "Your sync logs will appear here...\n")
        self.log_area.configure(state="disabled")

        logger.addHandler(TextBoxHandler(self.log_area))

        # Version
        try:
            with open(pyproject, "rb") as f:
                version = tomllib.load(f)["project"]["version"]
        except Exception:
            version = "Unknown"

        self.lbl_version = ctk.CTkLabel(self, text=f"Version: {version}", text_color="gray")
        self.lbl_version.grid(row=5, column=0, padx=20, pady=(0, 10), sticky="e")

        self.validate_form()

    def validate_form(self):
        if self.is_syncing:
            self.btn_sync.configure(state="disabled")
            return

        try:
            s_date = datetime.strptime(self.start_date.get(), "%Y-%m-%d").date()
            e_date = datetime.strptime(self.end_date.get(), "%Y-%m-%d").date()
            is_date_valid = e_date > s_date
        except ValueError:
            is_date_valid = False

        is_provider_selected = any(cb.get() == 1 for cb in self.cb_providers.values())

        if is_date_valid and is_provider_selected:
            self.btn_sync.configure(state="normal")
        else:
            self.btn_sync.configure(state="disabled")

    def on_sync_finished(self):
        self.is_syncing = False
        self.validate_form()

    def exec_sync(self):
        self.is_syncing = True
        self.validate_form()

        try:
            selected_start_date = datetime.strptime(self.start_date.get(), "%Y-%m-%d").date()
            selected_end_date = datetime.strptime(self.end_date.get(), "%Y-%m-%d").date()
        except ValueError:
            self.on_sync_finished()
            return

        selected_providers = []
        for value, cb_provider in self.cb_providers.items():
            if cb_provider.get() == 1:
                selected_providers.append(Provider[value])

        self.log_area.configure(state="normal")
        self.log_area.delete("0.0", "end")
        self.log_area.configure(state="disabled")

        def run_process():
            try:
                asyncio.run(main(selected_providers, selected_start_date, selected_end_date))
            except Exception as e:
                logger.exception("Error during sync")
            finally:
                self.after(0, self.on_sync_finished)

        Thread(target=run_process, daemon=True).start()


if __name__ == "__main__":
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    app = App()
    app.mainloop()