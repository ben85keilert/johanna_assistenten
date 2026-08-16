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

```bash
pip install -r requirements.txt
```

## Starten

```bash
python main.py
```

## Struktur

```
├── main.py                 # Einstiegspunkt + App-Logik
├── models/                 # Datenmodelle (ShiftType, Assistant, Plan, etc.)
├── ui/                     # UI-Komponenten (MainWindow, Tabs, Dialogs)
├── scheduling/             # Planungs-Algorithmus + Validator
├── export/                 # CSV, Excel, PDF Export
├── persistence/            # JSON Speichern/Laden
└── requirements.txt        # Abhängigkeiten
```

## Windows-Build (.exe)

Für den realen Einsatz wird das Programm als Windows-Programm gebaut. PyInstaller
erzeugt Windows-Binaries nur unter Windows — der Build läuft also entweder auf
einem Windows-Rechner oder automatisch über GitHub Actions.

### Variante A: Manuell auf einem Windows-Rechner

1. [Python 3.12+](https://www.python.org/downloads/windows/) installieren
   (Häkchen bei „Add python.exe to PATH" setzen).
2. Projekt herunterladen/klonen und in der Eingabeaufforderung in den Projektordner wechseln.
3. Virtuelle Umgebung anlegen und Abhängigkeiten installieren:
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt pyinstaller
   ```
4. Build starten:
   ```bat
   pyinstaller --noconsole --onedir --name JohannaAssistenten main.py
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
- **Release**: beim Pushen eines Tags `v*` wird gebaut und die ZIP-Datei
  automatisch an das GitHub-Release angehängt — siehe nächster Abschnitt.

### Neue Version veröffentlichen (Tag auf `main` setzen)

Der Build für ein Release wird **ausschließlich durch einen Versions-Tag `v*`
ausgelöst**. Der Tag gehört auf `main` — also erst mergen, dann taggen, damit
die gebaute `.exe` genau dem entspricht, was auf `main` liegt.

**1. Sicherstellen, dass alles auf `main` gemerged ist** (Pull Request gemerged):

```bash
git checkout main
git pull origin main
git log --oneline -3          # der oberste Commit wird getaggt
```

**2. Letzte Version nachsehen und um 0.0.1 erhöhen:**

```bash
git fetch origin --tags
git tag -l | sort -V | tail -5
```

Aus dem letzten Tag ergibt sich der neue: `v0.1.2` → `v0.1.3` (Patch +1 für
Fehlerbehebungen und kleinere Erweiterungen). Bei größeren Funktionssprüngen
stattdessen die mittlere Zahl erhöhen (`v0.1.3` → `v0.2.0`).

**3. Tag anlegen und pushen:**

```bash
git tag -a v0.1.3 -m "v0.1.3: kurze Beschreibung der Änderungen"
git push origin v0.1.3
```

`-a` erzeugt einen annotierten Tag (mit Autor, Datum und Nachricht) — für
Releases immer diesem Weg den Vorzug geben. Ohne Angabe eines Commits zeigt der
Tag auf den gerade ausgecheckten Stand, also auf `main`. Soll ein bestimmter
Commit getaggt werden, dessen Hash anhängen:

```bash
git tag -a v0.1.3 dd0c236 -m "v0.1.3: kurze Beschreibung der Änderungen"
```

**4. Build beobachten:** Der Push des Tags startet den Workflow *Windows-Build*
automatisch (Reiter *Actions* auf GitHub, Laufzeit einige Minuten). Danach liegt
`JohannaAssistenten-windows.zip` am GitHub-**Release** zum Tag und zusätzlich als
Artifact am Workflow-Lauf.

> **Hinweis:** `git push` ohne Tag-Namen überträgt **keine** Tags — der Build
> startet dann nicht. Entweder wie oben den Tag einzeln pushen oder
> `git push origin --tags` für alle noch nicht übertragenen Tags verwenden.

**Tag korrigieren**, solange das Release noch nicht verteilt ist (löscht Tag
lokal und auf GitHub, danach neu anlegen):

```bash
git tag -d v0.1.3
git push origin :refs/tags/v0.1.3
```

## Verwendung

1. **Team erstellen:** Im "Team"-Tab Assistenten hinzufügen, Namen und Farben setzen
2. **Constraints setzen:** Doppelklick auf Assistenten -> Einschränkungen bearbeiten
3. **Monat wählen:** Oben Datum wählen (z.B. Juni 2026)
4. **Plan generieren:** Button "Dienstplan generieren"
5. **Manuell anpassen:** Rechtsklick auf Zellen -> Dienst setzen/sperren
6. **Exportieren:** Datei -> Exportieren -> CSV/Excel/PDF

## Technologie

- **PySide6** – Qt für Python
- **openpyxl** – Excel-Export
- **reportlab** – PDF-Export
- **Python 3.10+**
