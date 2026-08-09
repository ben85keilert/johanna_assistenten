# Johanna Assistenten — Beschreibung & Orientierung

Dieses Dokument ist die gemeinsame Referenz dafür, **wofür das Programm da ist** und
**wie es funktionieren soll**. Neue Funktionen orientieren sich an dieser Beschreibung;
wenn sich das Konzept ändert, wird zuerst dieses Dokument angepasst.

## Zweck

Johanna ist eine Person, die **rund um die Uhr von jeweils einer Person assistiert**
wird. Die Assistenz übernimmt ein kleiner Helferkreis (bis zu 10 Personen). Das
Programm erstellt für jeden Monat einen Dienstplan, der die Tage **fair** auf das Team
verteilt und dabei die persönlichen Einschränkungen jedes Helfers berücksichtigt.

Das Programm läuft zunächst als **Desktop-Anwendung** (Windows-Build für den realen
Einsatz, Entwicklung unter Linux). Geplant wird von einer Person am Rechner.

## Dienstarten

| Kürzel | Bedeutung | Abdeckung |
|--------|-----------|-----------|
| VOLL   | Tagesdienst (Regelfall) | deckt den ganzen Tag ab |
| VM     | nur Vormittag (Ausnahme) | halber Tag |
| NM     | nur Nachmittag (Ausnahme) | halber Tag |

Ein Tag gilt als **abgedeckt**, wenn entweder eine Person VOLL übernimmt **oder**
zwei Personen sich den Tag mit VM + NM teilen. Halbe Dienste zählen für die
Verteilung als 0,5 Dienste.

## Fairness-Regeln (Einschränkungen)

Jeder Helfer hat eigene Vorgaben:

- **Ziel-Dienste pro Monat**: feste Anzahl oder „Auto" (gleichmäßige Verteilung).
- **Max. Tage am Stück** (1–7): mehr aufeinanderfolgende Diensttage sind nicht erlaubt.
- **Min. Tage am Stück** (1–7): Helfer mit weiter Anreise kommen immer für mehrere
  Tage hintereinander (z. B. 2er- oder 3er-Blöcke). Der Generator plant sie nur in
  zusammenhängenden Blöcken ein. Muss ≤ „Max. Tage am Stück" sein.
- **Nicht verfügbare Einzeltage** und **Urlaubszeiträume**: an diesen Tagen wird die
  Person nie eingeplant.

Weitere Bedingungen (z. B. Wochenend-Fairness) folgen später und werden hier ergänzt.

## Bedienfreundlichkeit

**Das Programm gehört konsequent nutzerfreundlich gestaltet.** Konkret heißt das:

- Große, gut klickbare Bedienelemente; keine winzigen Auf/Ab-Pfeile. Zahlenwerte
  werden über nebeneinanderliegende Minus/Plus-Buttons gestellt, die beim
  Gedrückthalten automatisch weiterzählen.
- **Zentrale Steuerleiste** zwischen Menü und Tabs, bewusst übergroß: Sie zeigt
  das zuletzt angeklickte Wertefeld und ändert dessen Wert mit großen ▲/▼-Buttons;
  mit ◀/▶ springt man zum vorherigen/nächsten Wertefeld, ohne die Felder in der
  Tabelle treffen zu müssen.
- Große Schrift und Zeilenhöhen. Alle Größen sind zentral im Theme
  (`ui/theme.py`) einstellbar.
- Änderungen sind sofort in beiden Tabs sichtbar — nichts muss doppelt gepflegt
  werden.

## Bedienkonzept

Zwei Tabs:

1. **Dienstplan-Tab**: Monatsraster (Zeile = Helfer, Spalte = Tag).
   - **Zwei Ansichten** (umschaltbar, wird gemerkt): *Breit* (der ganze Monat in
     einer Zeile) oder *Zweigeteilt* (zweite Monatshälfte unter der ersten — man
     scrollt vertikal statt horizontal).
   - Neben dem Namen stehen pro Helfer die **Soll-Dienste** (Minus/Plus-Buttons,
     „Auto" = gleichmäßig verteilen) und die **belegten Dienste** als Tupel
     `VOLL | VM | NM`.
   - **Stempel-Buttons**: Tagesdienst | VM | NM | Urlaub | Fixieren. Ein aktiver
     Stempel wird per Klick auf eine Zelle angewendet; erneuter Klick entfernt den
     Eintrag wieder. Beim Überschreiben vorhandener Einträge wird nachgefragt
     (Nachfrage abschaltbar).
   - **Mehrfachauswahl**: mit Strg/Shift lassen sich mehrere Zellen (auch verstreut)
     markieren; das Rechtsklick-Menü wirkt dann auf alle markierten Zellen.
   - **Urlaub** im Raster: zusammenhängend gestempelte Tage werden automatisch
     zu Urlaubszeiträumen zusammengefasst und erscheinen in der Urlaubsübersicht
     des Team-Tabs; Einzeltage bleiben Einzeltage. Wird ein Tag mitten aus einem
     Zeitraum wieder entfernt, teilt sich der Zeitraum entsprechend.
   - Unter dem Raster: Zusammenfassung pro Helfer als Tupel `Name (VOLL|VM|NM)`
     mit Legende sowie Warnhinweise (unbesetzte/halbe Tage, Zielabweichungen).
2. **Team-Tab**: Helfer anlegen/entfernen, Name und Farbe setzen. **Ziel-Dienste,
   Max. Folge und Min. Block werden direkt in der Tabelle** mit Minus/Plus-Buttons
   gestellt (Min. Block und Max. Folge halten sich dabei automatisch konsistent);
   der Einschränkungen-Dialog bleibt für nicht verfügbare Einzeltage per Kalender.
   Darunter die **Urlaubsübersicht**: alle Abwesenheiten aller Helfer
   chronologisch sortiert — Zeiträume **und Einzeltage**, monatsübergreifend.
   Hinzufügen, **Bearbeiten** (Button oder Doppelklick) und Entfernen über
   Dialoge mit Kalender-Datumsfeldern; überlappende oder angrenzende Zeiträume
   verschmelzen automatisch. In der Tab-Zeile (solange der Team-Tab aktiv ist):
   **Filter** nach Person und Monat sowie „Vergangene anzeigen" — abgelaufene
   Urlaube sind standardmäßig ausgeblendet.

### Generier-Zyklus: Fixieren und Neuwürfeln

1. Man setzt zuerst die **Fixpunkte** von Hand (z. B. „Martha kommt am 1.–2. VOLL,
   am 3. nur VM"). Manuell Gesetztes bleibt immer stehen.
2. **Neu würfeln** füllt die restlichen Tage zufällig, unter Beachtung aller
   Regeln. Zufällig vergebene Dienste tragen einen **Punkt**.
3. Was gefällt, **fixiert** man per Klick (Fixieren-Stempel oder Rechtsklick).
   **Farblogik: fixierte Einträge sind kräftig gefärbt und tragen ein Schloss,
   nicht fixierte sind blasser.**
   „Deterministisch" bedeutet: Mit gleichem Seed und gleichen Fixpunkten liefert
   „Generieren" immer denselben Plan (reproduzierbar); ohne Häkchen würfelt jeder
   Klick anders.
4. Was nicht gefällt, bleibt unfixiert und wird beim nächsten Klick auf
   „Neu würfeln" **neu vergeben**. Schritte 3–4 wiederholt man, bis der Plan passt.

Endet ein manuell gesetzter Block mit einem halben Tag (z. B. Tag 3 nur VM), vergibt
der Generator die fehlende Tageshälfte (NM) an eine andere Person.

## Datenhaltung

Alle Daten liegen als **JSON** im Ordner `data/` neben dem Programm. Das Programm
speichert beim Beenden automatisch und stellt beim Start den letzten Zustand wieder
her (zuletzt geöffneter Monat, Fenstergröße).

### `data/team.json` — das Team (monatsübergreifend)

Enthält neben Name/Farbe auch die **personenbezogenen Einschränkungen**: Urlaube
und Einzeltage (datumsbasiert, gelten in jedem berührten Monat — auch
monatsübergreifende Urlaube), Max. Folge und Min. Block:

```json
{
  "version": 3,
  "assistants": [
    { "id": "f1f04d0e", "name": "Martha", "color": "#3498DB", "active": true,
      "constraints": {
        "assistant_id": "f1f04d0e",
        "unavailable_dates": ["2026-08-15"],
        "vacation_ranges": [["2026-08-28", "2026-09-05"]],
        "max_consecutive_days": 3,
        "min_block_days": 1 } }
  ]
}
```

### `data/plans/plan_JJJJ_MM.json` — ein Plan pro Monat

Enthält den Dienstplan des Monats und als einzige monatsbezogene Vorgabe die
**Soll-Dienste** (`targets`) je Helfer:

```json
{
  "version": 3,
  "year": 2026,
  "month": 8,
  "schedule": {
    "1": [ { "assistant_id": "f1f04d0e", "shift_type": "FULL",
             "locked": true, "generated": false } ]
  },
  "targets": { "f1f04d0e": null },
  "seed": 42,
  "created_at": "…", "modified_at": "…"
}
```

- `locked`: fixiert — übersteht das Neuwürfeln.
- `generated`: wurde vom Zufallsgenerator vergeben (farblich markiert), nicht von Hand.

### `data/settings.json` — App-Zustand

```json
{
  "version": 2,
  "last_year": 2026, "last_month": 8,
  "window_geometry": "…",
  "confirm_overwrite": true,
  "seed": 42, "deterministic": true,
  "split_view": false
}
```

## Updatefähigkeit & Migration

Das Programm wird als Windows-`.exe` verteilt und weiterentwickelt. **Alte
Datendateien müssen nach jedem Update weiter funktionieren.** Dafür gilt:

- Jede Datei trägt eine `version`-Nummer.
- Beim Laden migriert `persistence/migrations.py` ältere Versionen schrittweise auf
  das aktuelle Format (fehlende Felder erhalten Defaults). Gespeichert wird immer im
  aktuellen Format.
- **Regel für Entwickler**: Wer ein Dateiformat ändert, erhöht die Versionsnummer
  und ergänzt einen Migrationsschritt. Loader tolerieren fehlende Felder über
  Defaults.

## Vertraulichkeit

Es geht um eine reale Teamverwaltung — **mit echten Personendaten wird vertraulich
umgegangen; sie gehören nicht ins Git-Repository.** Die im Repo versionierten Daten
(`data/` mit Martha, Jürgen, Bertha …) sind **ausschließlich Dummy-/Beispieldaten**.
Sie sind absichtlich eingecheckt, damit der Aufbau der Dateien nachvollziehbar ist.

## Ausblick (nur notiert, noch nicht umgesetzt)

- **Serverbetrieb**: Später soll das Programm über einen Server laufen. Die
  Assistenten können sich dann selbst einloggen und ihre Urlaube bzw. freien Tage
  eintragen.
