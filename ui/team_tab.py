from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QHeaderView, QTabWidget, QComboBox,
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QFont

from models import (
    Assistant, AssistantConstraints, MonthPlan,
    AssistantSettings, SettingsProfile, apply_settings, month_label,
)
from persistence import default_profiles
import uuid

from . import theme
from .widgets.big_stepper import BigStepper

# Spalten der Vorlagen-Tabellen
COL_NAME = 0

# Auswahl fuer "RB anhaengen": Rufbereitschafts-Block direkt vor/nach dem
# Dienstblock (fuer Helfer mit weiter Anreise, die am Stueck bleiben wollen)
ATTACH_OPTIONS = [
    ("—", "none"),
    ("Vorher", "before"),
    ("Nachher", "after"),
    ("Beides", "both"),
]


class TeamTab(QWidget):
    # Helferliste (Name/Bestand/Reihenfolge) oder Plan-Einstellungen geaendert
    assistants_changed = Signal()
    # Eine Vorlage wurde geaendert (wird beim Speichern mitgesichert)
    profiles_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plan: MonthPlan | None = None
        self.profiles: list[SettingsProfile] = default_profiles()
        self._steppers = {}  # (profile_idx, assistant_id, field) -> BigStepper
        self._refreshing = False
        self.init_ui()

    def init_ui(self):
        # Abwesenheiten (Urlaub/Wunsch) haben einen eigenen Tab - hier geht
        # es nur um Helfer und ihre Planungs-Einstellungen. Die Helferfarbe
        # wird hier bewusst nicht mehr gezeigt: im Plan tragen die
        # Eintragsarten die Farbe, nicht die Personen
        layout = QVBoxLayout()

        # Kopfzeile: Helfer-Buttons links, "In Dienstplan uebernehmen"
        # kraeftig in der Mitte
        left_buttons = QWidget()
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.add_btn = QPushButton("+ Helfer hinzufuegen")
        self.add_btn.clicked.connect(self.add_assistant)
        button_layout.addWidget(self.add_btn)

        self.remove_btn = QPushButton("- Entfernen")
        self.remove_btn.clicked.connect(self.remove_assistant)
        button_layout.addWidget(self.remove_btn)

        # Reihenfolge steuert die Zeilen im Dienstplan (und in team.json)
        self.up_btn = QPushButton("▲ Hoch")
        self.up_btn.setToolTip("Gewaehlten Helfer in der Liste nach oben verschieben")
        self.up_btn.clicked.connect(lambda: self.move_assistant(-1))
        button_layout.addWidget(self.up_btn)

        self.down_btn = QPushButton("▼ Runter")
        self.down_btn.setToolTip("Gewaehlten Helfer in der Liste nach unten verschieben")
        self.down_btn.clicked.connect(lambda: self.move_assistant(1))
        button_layout.addWidget(self.down_btn)
        left_buttons.setLayout(button_layout)

        # Uebertraegt die gerade sichtbare Vorlage (Text nennt Vorlage und
        # Monat, siehe _update_apply_button)
        self.apply_btn = QPushButton("In Dienstplan uebernehmen")
        self.apply_btn.setProperty("role", "primary")
        self.apply_btn.setToolTip(
            "Uebertraegt die Einstellungen der gerade gezeigten Vorlage in den "
            "Dienstplan des aktuell geoeffneten Monats."
        )
        self.apply_btn.clicked.connect(
            lambda: self.apply_profile(self.profile_tabs.currentIndex())
        )

        # Drei Spalten, aussen gleich breit -> der Button sitzt wirklich mittig
        head = QGridLayout()
        head.addWidget(left_buttons, 0, 0)
        head.addWidget(self.apply_btn, 0, 1)
        head.setColumnStretch(0, 1)
        head.setColumnStretch(2, 1)
        head.setColumnMinimumWidth(2, left_buttons.sizeHint().width())
        layout.addLayout(head)

        # Zwei Vorlagen: Einstellungen getrennt vorbereiten und per Button
        # in den Dienstplan des aktuellen Monats uebernehmen
        self.profile_tabs = QTabWidget()
        self.profile_tabs.currentChanged.connect(self._update_apply_button)
        self._tables: list[QTableWidget] = []
        table_font = QFont()
        table_font.setPointSize(theme.TEAM_FONT_PT)
        for idx in range(2):
            table = QTableWidget()
            table.setColumnCount(9)
            # Max steht jeweils links von Min: Max begrenzt Min, wird also
            # zuerst eingestellt (sonst zieht ein spaeter gesetztes Max das
            # Min wieder zurueck)
            table.setHorizontalHeaderLabels([
                "Name", "Max. Dienste", "Min. Dienste",
                "Max. Folge", "Min. Block", "Abstand", "Freiwuensche",
                "Dienstwuensche", "RB anhaengen",
            ])
            # Abwechselnd gefaerbte Zeilen im Ton des Farbschemas
            # (QPalette.AlternateBase = theme.stripe)
            table.setAlternatingRowColors(True)
            table.setFont(table_font)
            table.itemChanged.connect(
                lambda item, i=idx: self.on_name_edited(i, item)
            )
            self.profile_tabs.addTab(table, f"Vorlage {idx + 1}")
            self._tables.append(table)

        layout.addWidget(self.profile_tabs)
        self.setLayout(layout)

    def set_plan(self, plan: MonthPlan):
        self.plan = plan
        self.refresh_table()

    def set_profiles(self, profiles: list[SettingsProfile]):
        self.profiles = profiles
        self.refresh_table()

    def refresh_all(self):
        """Von aussen aufrufen, wenn Einschraenkungen anderswo geaendert wurden."""
        self.refresh_table()

    # --- Vorlagen-Tabellen ---

    def _profile_settings(self, profile_idx: int, assistant_id: str) -> AssistantSettings:
        return self.profiles[profile_idx].settings.setdefault(
            assistant_id, AssistantSettings()
        )

    def _make_stepper(self, profile_idx: int, assistant, field: str, label: str,
                      value: int, minimum: int, maximum: int,
                      special_min_text: str | None = None) -> BigStepper:
        stepper = BigStepper(
            label=f"{assistant.name}: {label}",
            value=value, minimum=minimum, maximum=maximum,
            special_min_text=special_min_text,
        )
        stepper.value_changed.connect(
            lambda v, p=profile_idx, aid=assistant.id, f=field:
            self.on_stepper_changed(p, aid, f, v)
        )
        self._steppers[(profile_idx, assistant.id, field)] = stepper
        return stepper

    def on_stepper_changed(self, profile_idx: int, assistant_id: str,
                           field: str, value: int):
        s = self._profile_settings(profile_idx, assistant_id)

        if field == "min_target":
            s.min_shifts = None if value < 0 else value
            # Max. Dienste mitziehen; "Auto" (None) clampt nie
            if (s.min_shifts is not None and s.max_shifts is not None
                    and s.max_shifts < s.min_shifts):
                s.max_shifts = s.min_shifts
                other = self._steppers.get((profile_idx, assistant_id, "max_target"))
                if other:
                    other.set_value(s.min_shifts)
        elif field == "max_target":
            s.max_shifts = None if value < 0 else value
            if (s.max_shifts is not None and s.min_shifts is not None
                    and s.min_shifts > s.max_shifts):
                s.min_shifts = s.max_shifts
                other = self._steppers.get((profile_idx, assistant_id, "min_target"))
                if other:
                    other.set_value(s.max_shifts)
        elif field == "max":
            s.max_consecutive_days = value
            # Min. Block darf nicht groesser sein als Max. Folge
            if s.min_block_days > value:
                s.min_block_days = value
                other = self._steppers.get((profile_idx, assistant_id, "min"))
                if other:
                    other.set_value(value)
        elif field == "min":
            s.min_block_days = value
            if s.max_consecutive_days < value:
                s.max_consecutive_days = value
                other = self._steppers.get((profile_idx, assistant_id, "max"))
                if other:
                    other.set_value(value)
        elif field == "gap":
            s.min_gap_days = value
        elif field == "quota":
            # Freiwunsch-Kontingent; "Alle" (None) = alle Wunsch-Tage hart
            s.free_wish_quota = None if value < 0 else value
        elif field == "work_quota":
            # Dienstwunsch-Kontingent; "Alle" (None) = alle Wunsch-Tage
            s.work_wish_quota = None if value < 0 else value

        self.profiles_changed.emit()

    def on_attach_changed(self, profile_idx: int, assistant_id: str, value: str):
        s = self._profile_settings(profile_idx, assistant_id)
        s.oncall_attach = value
        self.profiles_changed.emit()

    def on_name_edited(self, profile_idx: int, item: QTableWidgetItem):
        """Namensaenderung in einer der beiden Tabellen sofort uebernehmen
        und in der anderen Tabelle spiegeln."""
        if self._refreshing or item.column() != COL_NAME or not self.plan:
            return
        row = item.row()
        if row >= len(self.plan.assistants):
            return
        assistant = self.plan.assistants[row]
        if assistant.name == item.text():
            return
        assistant.name = item.text()
        other = self._tables[1 - profile_idx].item(row, COL_NAME)
        if other is not None:
            self._refreshing = True
            other.setText(assistant.name)
            self._refreshing = False
        self.assistants_changed.emit()

    def refresh_table(self):
        if not self.plan:
            return

        self._refreshing = True
        self._steppers = {}
        self._update_apply_button()

        for profile_idx, table in enumerate(self._tables):
            self.profile_tabs.setTabText(
                profile_idx, self.profiles[profile_idx].name
            )
            table.setRowCount(len(self.plan.assistants))
            table.verticalHeader().setDefaultSectionSize(theme.TEAM_ROW_HEIGHT)

            for i, assistant in enumerate(self.plan.assistants):
                s = self._profile_settings(profile_idx, assistant.id)

                table.setItem(i, COL_NAME, QTableWidgetItem(assistant.name))

                table.setCellWidget(i, 1, self._make_stepper(
                    profile_idx, assistant, "max_target", "Max. Dienste",
                    -1 if s.max_shifts is None else s.max_shifts, -1, 31,
                    special_min_text="Auto",
                ))
                table.setCellWidget(i, 2, self._make_stepper(
                    profile_idx, assistant, "min_target", "Min. Dienste",
                    -1 if s.min_shifts is None else s.min_shifts, -1, 31,
                    special_min_text="Auto",
                ))
                table.setCellWidget(i, 3, self._make_stepper(
                    profile_idx, assistant, "max", "Max. Folge",
                    s.max_consecutive_days, 1, 7,
                ))
                table.setCellWidget(i, 4, self._make_stepper(
                    profile_idx, assistant, "min", "Min. Block",
                    s.min_block_days, 1, 7,
                ))
                gap_stepper = self._make_stepper(
                    profile_idx, assistant, "gap", "Abstand",
                    s.min_gap_days, 0, 14, special_min_text="Aus",
                )
                gap_stepper.setToolTip(
                    "Mindestabstand in freien Tagen zwischen zwei "
                    "Einsatzbloecken dieser Person (Dienst und "
                    "Rufbereitschaft zusammen). Harte Regel."
                )
                table.setCellWidget(i, 5, gap_stepper)

                quota_stepper = self._make_stepper(
                    profile_idx, assistant, "quota", "Freiwuensche",
                    -1 if s.free_wish_quota is None else s.free_wish_quota,
                    -1, 31, special_min_text="Alle",
                )
                quota_stepper.setToolTip(
                    "Freiwunsch-Kontingent: so viele Wunsch-Tage im Monat "
                    "haben Vorrang (werden nie ueberplant). Weitere "
                    "Wunsch-Tage haben Nachrang und duerfen im Konfliktfall "
                    "ueberplant werden - Urlaub nie.\n"
                    "'Alle' = kein Kontingent, alle Wuensche hart wie Urlaub."
                )
                table.setCellWidget(i, 6, quota_stepper)

                work_quota_stepper = self._make_stepper(
                    profile_idx, assistant, "work_quota", "Dienstwuensche",
                    -1 if s.work_wish_quota is None else s.work_wish_quota,
                    -1, 31, special_min_text="Alle",
                )
                work_quota_stepper.setToolTip(
                    "Dienstwunsch-Kontingent: so viele Dienste im Monat "
                    "sollen auf die Dienstwunsch-Tage der Person fallen "
                    "(z. B. 3 Dienste an 7 gewuenschten Tagen). Weiche "
                    "Vorgabe: der Generator bevorzugt diese Tage, alle "
                    "harten Regeln und die faire Verteilung gelten weiter.\n"
                    "'Alle' = so viele Wunsch-Tage wie moeglich."
                )
                table.setCellWidget(i, 7, work_quota_stepper)

                attach_combo = QComboBox()
                for label, value in ATTACH_OPTIONS:
                    attach_combo.addItem(label, value)
                index = attach_combo.findData(s.oncall_attach)
                attach_combo.setCurrentIndex(index if index >= 0 else 0)
                attach_combo.setToolTip(
                    "Rufbereitschaft als Block direkt vor bzw. nach dem "
                    "Dienstblock einplanen - fuer Helfer mit weiter "
                    "Anreise, die am Stueck vor Ort sein wollen.\n"
                    "'Beides' verteilt denselben RB-Block auf beide Seiten "
                    "(z. B. Min. Block 4: 2 Tage RB davor, 4 Tage Dienst, "
                    "2 Tage RB danach) - die Gesamtzahl bleibt gleich, damit "
                    "RB = Dienste aufgeht."
                )
                attach_combo.currentIndexChanged.connect(
                    lambda _, c=attach_combo, p=profile_idx, aid=assistant.id:
                    self.on_attach_changed(p, aid, c.currentData())
                )
                table.setCellWidget(i, 8, attach_combo)

            # Feste Spalten etwas grosszuegiger als die Stepper selbst;
            # rechts darf Rand bleiben
            header = table.horizontalHeader()
            header.setStretchLastSection(False)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(COL_NAME, theme.TEAM_NAME_COL_W)
            for col in range(1, 8):
                table.setColumnWidth(col, theme.STEPPER_WIDTH + 12)
            table.setColumnWidth(8, 130)

        self._refreshing = False
        self.add_btn.setEnabled(len(self.plan.assistants) < 10)

    def _update_apply_button(self, *_):
        if not self.plan:
            return
        profile = self.profiles[self.profile_tabs.currentIndex()]
        self.apply_btn.setText(
            f"{profile.name} in Dienstplan "
            f"{month_label(self.plan.year, self.plan.month)} uebernehmen"
        )

    def apply_profile(self, profile_idx: int):
        """Uebertraegt die Vorlage in den Dienstplan des aktuellen Monats."""
        if not self.plan:
            return
        profile = self.profiles[profile_idx]
        for assistant in self.plan.assistants:
            apply_settings(
                assistant.constraints,
                profile.settings.setdefault(assistant.id, AssistantSettings()),
            )
        self.assistants_changed.emit()
        QMessageBox.information(
            self, "Uebernommen",
            f"Die Einstellungen aus '{profile.name}' gelten jetzt fuer den "
            f"Dienstplan {month_label(self.plan.year, self.plan.month)}.",
        )

    def add_assistant(self):
        if not self.plan or len(self.plan.assistants) >= 10:
            return

        new_id = str(uuid.uuid4())[:8]
        constraints = AssistantConstraints(assistant_id=new_id)
        assistant = Assistant(
            id=new_id,
            name="Neuer Helfer",
            color="#3498DB",
            constraints=constraints,
        )
        self.plan.assistants.append(assistant)
        self.refresh_table()
        self.assistants_changed.emit()

    def remove_assistant(self):
        if not self.plan:
            return

        table = self._tables[self.profile_tabs.currentIndex()]
        row = table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Warnung", "Bitte waehlen Sie einen Helfer aus.")
            return

        removed = self.plan.assistants[row]
        # Mit dem Autosave ist das nach wenigen Sekunden endgueltig
        reply = QMessageBox.question(
            self, "Helfer entfernen",
            f"{removed.name} wirklich aus dem Team entfernen?\n\n"
            "Abwesenheiten, Wuensche und Vorlagen-Einstellungen dieser "
            "Person gehen verloren; ihre Eintraege im Dienstplan "
            f"{month_label(self.plan.year, self.plan.month)} werden "
            "geloescht (in anderen Monaten beim naechsten Oeffnen).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        del self.plan.assistants[row]
        for profile in self.profiles:
            profile.settings.pop(removed.id, None)
        # Verwaiste Eintraege wuerden sonst unsichtbar als Abdeckung zaehlen
        for day in list(self.plan.schedule.keys()):
            kept = [e for e in self.plan.schedule[day] if e.assistant_id != removed.id]
            if kept:
                self.plan.schedule[day] = kept
            else:
                del self.plan.schedule[day]
        self.refresh_table()
        self.assistants_changed.emit()

    def move_assistant(self, delta: int):
        """Verschiebt den gewaehlten Helfer in der Reihenfolge nach
        oben/unten. Die Listenreihenfolge bestimmt die Zeilen im Dienstplan
        und wird in team.json mitgespeichert."""
        if not self.plan:
            return

        table = self._tables[self.profile_tabs.currentIndex()]
        row = table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Warnung", "Bitte waehlen Sie einen Helfer aus.")
            return

        new_row = row + delta
        if new_row < 0 or new_row >= len(self.plan.assistants):
            return

        assistants = self.plan.assistants
        assistants[row], assistants[new_row] = assistants[new_row], assistants[row]
        self.refresh_table()
        table.setCurrentCell(new_row, COL_NAME)
        self.assistants_changed.emit()

