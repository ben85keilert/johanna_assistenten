# Johanna Assistenten - Dienstplan App

Eine PySide6-Anwendung zur Verwaltung und Planung von Assistentendiensten für einen Monat.

**Worum es geht und wie das Programm funktionieren soll, steht in [BESCHREIBUNG.md](BESCHREIBUNG.md)** — das ist die Orientierung für alle Funktionen.

## Features

- **Team-Verwaltung:** Bis zu 10 Assistenten mit individuellen Farben
- **Dienst-Planung:** Interaktives Monatsraster mit Rechtsklick-Menü
- **Constraints:**
  - Nicht verfügbare Einzeltage und Urlaubszeiträume (zwingend)
  - Wunsch-Tage (frei haben) mit Kontingent und Dienstwunsch-Tage (arbeiten
    wollen, z. B. „3 Dienste an 7 Möglichkeiten") mit Kontingent
  - Max. aufeinanderfolgende Arbeitstage, Min. Block, Mindestabstand
  - Min./Max. Dienste pro Monat (oder Auto für Gleichverteilung)
- **Automatische Generierung:** Greedy-Algorithmus respektiert alle Constraints
- **Schicht-Typen:** VOLL (24h), Tag und Nacht (halbe Dienste), Rufbereitschaft
- **Sperren/Entsperren:** Einzelne Dienste vor Neuberechnung fixieren
- **Export:** CSV, Excel (mit Farben), PDF (Hochformat, ohne Urlaube/Wünsche), Notizen als Text
- **Rückmeldungen der Helfer:** HTML-Formular zum Verschicken (offline, auch am Handy) und Import der Antworten (Zwischenablage, Dateien, Ablageordner `Formularantworten` neben dem Programmordner)
- **Persistierung:** JSON-Speicherung / -Laden

## Installation

Das Projekt wird mit [uv](https://docs.astral.sh/uv/) verwaltet. Einmalig uv
installieren:

**Windows**
```powershell
winget install astral-sh.uv
```

**Linux** (Fedora hat uv als Paket; sonst das offizielle Installationsskript,
das uv nach `~/.local/bin` legt):
```bash
sudo dnf install uv                                   # Fedora
curl -LsSf https://astral.sh/uv/install.sh | sh       # alle Distributionen
```

Dann im Projektordner:

```bash
uv sync
```

Das legt automatisch die virtuelle Umgebung `.venv\` (Linux: `.venv/`) an (mit
dem in `.python-version` festgelegten Python, das uv bei Bedarf selbst
herunterlädt) und installiert alle Abhängigkeiten aus `pyproject.toml` exakt in
den Versionen aus `uv.lock`.

### Systembibliotheken unter Linux

PySide6 bringt Qt komplett mit, braucht zum Anzeigen des Fensters aber die
üblichen X11/Wayland-Bibliotheken des Systems. Auf einem Desktop-System sind
die praktisch immer schon da; auf minimalen Installationen fehlen typischerweise
die xcb-Hilfsbibliotheken (Qt startet dann mit
*"Could not load the Qt platform plugin xcb"*):

```bash
# Fedora
sudo dnf install libxcb xcb-util xcb-util-cursor xcb-util-image xcb-util-keysyms \
    xcb-util-renderutil xcb-util-wm libxkbcommon-x11 libglvnd-egl libglvnd-glx \
    fontconfig dbus-libs libwayland-client

# Debian / Ubuntu
sudo apt install libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-render-util0 libxcb-shape0 libxcb-xkb1 libxkbcommon-x11-0 libegl1 libgl1 \
    libfontconfig1 libdbus-1-3 libwayland-client0
```

Welche Bibliothek konkret fehlt, zeigt `ldd` am xcb-Plugin:

```bash
ldd .venv/lib/python3.12/site-packages/PySide6/Qt/plugins/platforms/libqxcb.so | grep "not found"
```

## Starten

```bash
uv run main.py
```

Gilt für Windows und Linux gleichermaßen. Zum Entwickeln/Testen ohne Display
(z. B. per SSH) startet Qt headless mit `QT_QPA_PLATFORM=offscreen uv run main.py`.

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
   uv run pyinstaller --noconsole --onedir --name JohannaAssistenten --add-data "vorlagen;vorlagen" main.py
   ```
5. Das fertige Programm liegt in `dist\JohannaAssistenten\` —
   den ganzen Ordner kopieren und `JohannaAssistenten.exe` starten.

Die Daten (`data\` mit Team, Plänen und Einstellungen) legt das Programm neben der
`.exe` an. Beim Update einfach die neue `.exe`/den neuen Ordner über den alten
kopieren (Programm vorher schließen, alten Ordner **nicht** löschen) — der
`data\`-Ordner bleibt erhalten und alte Dateien werden beim Laden automatisch auf
das neue Format migriert (siehe BESCHREIBUNG.md). Beim ersten Start einer neuen
Version sichert das Programm die bisherigen Daten vorher nach
`data\sicherungen\`; eine Sicherung von Hand gibt es unter
*Datei → Datensicherung erstellen…* (ZIP an beliebigem Ort).

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

## Linux-Build

Derselbe PyInstaller-Aufruf baut unter Linux ein Linux-Programm (PyInstaller
baut immer für das System, auf dem es läuft — eine `.exe` entsteht so nicht).
Voraussetzungen: uv und die Qt-Systembibliotheken aus dem Abschnitt
[Installation](#installation).

1. Abhängigkeiten inkl. PyInstaller installieren:
   ```bash
   uv sync --group build
   ```
2. Build starten:
   ```bash
   uv run pyinstaller --noconsole --onedir --name JohannaAssistenten --add-data "vorlagen:vorlagen" main.py
   ```
3. Das fertige Programm liegt in `dist/JohannaAssistenten/` — den ganzen Ordner
   kopieren und `./JohannaAssistenten` darin starten. Der Ordner ist ca. 220 MB
   groß (Qt liegt vollständig darin).

Hinweise:

- Die Daten (`data/`) legt das Programm wie unter Windows neben der Binary an.
- Der Build läuft nur auf Linux-Systemen mit **gleicher oder neuerer glibc** als
  dem Build-Rechner; wer breit kompatibel sein will, baut auf einer älteren
  Distribution. Die Qt-Systembibliotheken von oben müssen auch auf dem
  Zielrechner vorhanden sein.
- Der **automatische Updater ist unter Linux abgeschaltet** (er tauscht die
  Dateien per `robocopy` und ist auf das Windows-Release-ZIP ausgelegt).
  *Einstellungen → Nach Updates suchen…* meldet nur, dass eine neue Version
  existiert; aktualisiert wird durch erneutes Bauen bzw. Kopieren des neuen
  `dist`-Ordners über den alten (`data/` dabei stehen lassen).
- Ein Linux-Release wird nicht veröffentlicht; `build-windows.yml` baut
  ausschließlich die Windows-Version.

## Updates

Die installierte Windows-Version prüft beim Start automatisch (und jederzeit über
*Einstellungen → Nach Updates suchen…*), ob auf GitHub ein neueres Release liegt.
Gibt es eines, fragt ein Dialog nach; auf Wunsch lädt das Programm das Update
herunter, tauscht sich nach dem Beenden selbst aus und startet neu — der
`data\`-Ordner mit allen Plänen bleibt dabei unangetastet (und wird beim ersten
Start der neuen Version zusätzlich nach `data\sicherungen\` gesichert). Einzelne Versionen
lassen sich überspringen. Schlägt die Prüfung fehl (kein Internet), startet das
Programm einfach normal.

## Verwendung

1. **Team erstellen:** Im "Team"-Tab Assistenten hinzufügen und benennen
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
- **PyInstaller** – Windows-/Linux-Build (Dependency-Group `build`)
