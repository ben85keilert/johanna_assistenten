# Johanna Assistenten - Dienstplan App

Eine PySide6-Anwendung zur Verwaltung und Planung von Assistentendiensten für einen Monat.

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
