from PySide6.QtWidgets import QMainWindow, QTabWidget, QStatusBar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Johanna Assistenten - Dienstplan")
        self.setGeometry(100, 100, 1200, 800)

        self.is_modified = False
        self._title_plan = ""

        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)

        self.team_tab = None
        self.plan_tab = None

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Bereit")

        # Menue wird in main.py verdrahtet

        # Beim Schliessen speichert JohannaApp automatisch (siehe main.py)
        self.on_close_save = None

    def set_plan_tab(self, tab):
        self.plan_tab = tab
        self.tab_widget.insertTab(0, tab, "Dienstplan")
        self.tab_widget.setCurrentIndex(0)

    def set_team_tab(self, tab):
        self.team_tab = tab
        self.tab_widget.addTab(tab, "Team")

    def set_title_plan(self, year: int, month: int):
        self._title_plan = f"Plan {year}-{month:02d}"
        self.update_window_title()

    def update_window_title(self):
        modified = "*" if self.is_modified else ""
        self.setWindowTitle(f"Johanna Assistenten - {self._title_plan}{modified}")

    def mark_modified(self):
        self.is_modified = True
        self.update_window_title()

    def mark_saved(self):
        self.is_modified = False
        self.update_window_title()

    def closeEvent(self, event):
        if self.on_close_save is not None:
            self.on_close_save()
        event.accept()
