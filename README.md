# Johanna Assistenten - Dienstplan App

Eine PySide6-Anwendung zur Verwaltung und Planung von Assistentendiensten für einen Monat.

**Worum es geht und wie das Programm funktionieren soll, steht in [BESCHREIBUNG.md](BESCHREIBUNG.md)** — das ist die Orientierung für alle Funktionen.

## Features

- **Team-Verwaltung:** Bis zu 10 Assistenten mit individuellen Farben
- **Dienst-Planung:** Interaktives Monatsraster mit Rechtsklick-Menü
- **Constraints:**
  - Nicht verfügbare Einzeltage
  - Urlaubszeiträume
  - Max. aufeinanderfolgende Arbeitstage (1-3)
  - Ziel-Dienste pro Monat (oder Auto für Gleichverteilung)
- **Automatische Generierung:** Greedy-Algorithmus respektiert alle Constraints
- **Schicht-Typen:** VOLL (24h), VM (Morgens), NM (Abends)
- **Sperren/Entsperren:** Einzelne Dienste vor Neuberechnung fixieren
- **Export:** CSV, Excel (mit Farben), PDF (Querformat)
- **Persistierung:** JSON-Speicherung / -Laden

## Installation

Das Projekt wird mit [uv](https://docs.astral.sh/uv/) verwaltet. Einmalig uv
installieren (Windows):

```powershell
winget install astral-sh.uv
```

Dann im Projektordner:

```bash
uv sync
```

Das legt automatisch die virtuelle Umgebung `.venv\` an (mit dem in
`.python-version` festgelegten Python) und installiert alle Abhängigkeiten aus
`pyproject.toml` exakt in den Versionen aus `uv.lock`.

## Starten

```bash
uv run main.py
```

## Struktur

```
├── main.py                 # Einstiegspunkt + App-Logik
├── models/                 # Datenmodelle (ShiftType, Assistant, Plan, etc.)
├── ui/                     # UI-Komponenten (MainWindow, Tabs, Dialogs)
├── scheduling/             # Planungs-Algorithmus + Validator
├── export/                 # CSV, Excel, PDF Export
├── persistence/            # JSON Speichern/Laden
├── pyproject.toml          # Projekt-Metadaten + Abhängigkeiten (uv)
└── uv.lock                 # Exakte, reproduzierbare Versionen (uv)
```

## Windows-Build (.exe)

Für den realen Einsatz wird das Programm als Windows-Programm gebaut. PyInstaller
erzeugt Windows-Binaries nur unter Windows — der Build läuft also entweder auf
einem Windows-Rechner oder automatisch über GitHub Actions.

### Variante A: Manuell auf einem Windows-Rechner

1. [uv](https://docs.astral.sh/uv/) installieren:
   ```powershell
   winget install astral-sh.uv
   ```
   (Ein passendes Python lädt uv bei Bedarf selbst herunter.)
2. Projekt herunterladen/klonen und in der Eingabeaufforderung in den Projektordner wechseln.
3. Abhängigkeiten inkl. PyInstaller installieren:
   ```bat
   uv sync --group build
   ```
4. Build starten:
   ```bat
   uv run pyinstaller --noconsole --onedir --name JohannaAssistenten main.py
   ```
5. Das fertige Programm liegt in `dist\JohannaAssistenten\` —
   den ganzen Ordner kopieren und `JohannaAssistenten.exe` starten.

Die Daten (`data\` mit Team, Plänen und Einstellungen) legt das Programm neben der
`.exe` an. Beim Update einfach die neue `.exe`/den neuen Ordner über den alten
kopieren — der `data\`-Ordner bleibt erhalten und alte Dateien werden beim Laden
automatisch auf das neue Format migriert (siehe BESCHREIBUNG.md).

### Variante B: Automatisch über GitHub Actions

Der Workflow [.github/workflows/build-windows.yml](.github/workflows/build-windows.yml)
baut die Windows-Version in der Cloud:

- **Manuell**: auf GitHub unter *Actions → Windows-Build → Run workflow* starten;
  das Ergebnis liegt danach als Artifact (`JohannaAssistenten-windows.zip`) zum
  Download bereit.
- **Release**: beim Pushen eines Tags `v*` (z. B. `git tag v1.0 && git push --tags`)
  wird gebaut und die ZIP-Datei automatisch an das GitHub-Release angehängt.

### Release-Checkliste

1. Version in **`version.py`** (`__version__`) **und** `pyproject.toml` erhöhen —
   beide müssen übereinstimmen; der Workflow bricht sonst beim Tag-Build ab.
2. Committen, dann Tag `v<Version>` pushen (z. B. `git tag v0.3.0 && git push --tags`).
3. Der Workflow baut und hängt `JohannaAssistenten-windows.zip` an das Release.
   **Den Asset-Namen und den Ordnernamen `JohannaAssistenten` im ZIP nie ändern** —
   der automatische Updater sucht genau danach.

## Updates

Die installierte Windows-Version prüft beim Start automatisch (und jederzeit über
*Einstellungen → Nach Updates suchen…*), ob auf GitHub ein neueres Release liegt.
Gibt es eines, fragt ein Dialog nach; auf Wunsch lädt das Programm das Update
herunter, tauscht sich nach dem Beenden selbst aus und startet neu — der
`data\`-Ordner mit allen Plänen bleibt dabei unangetastet. Einzelne Versionen
lassen sich überspringen. Schlägt die Prüfung fehl (kein Internet), startet das
Programm einfach normal.

## Verwendung

1. **Team erstellen:** Im "Team"-Tab Assistenten hinzufügen, Namen und Farben setzen
2. **Constraints setzen:** Doppelklick auf Assistenten -> Einschränkungen bearbeiten
3. **Monat wählen:** Oben Datum wählen (z.B. Juni 2026)
4. **Plan generieren:** Button "Dienstplan generieren"
5. **Manuell anpassen:** Rechtsklick auf Zellen -> Dienst setzen/sperren
6. **Exportieren:** Datei -> Exportieren -> CSV/Excel/PDF

## Technologie

- **uv** – Paket- und Umgebungsverwaltung (`pyproject.toml` + `uv.lock`)
- **PySide6** – Qt für Python (< 6.9, siehe Kommentar in `pyproject.toml`)
- **openpyxl** – Excel-Export
- **reportlab** – PDF-Export
- **Python 3.10+** (Entwicklung: 3.12 via `.python-version`)
