# Johanna Assistenten — Beschreibung & Orientierung

Dieses Dokument ist die gemeinsame Referenz dafür, **wofür das Programm da ist** und
**wie es funktionieren soll**. Neue Funktionen orientieren sich an dieser Beschreibung;
wenn sich das Konzept ändert, wird zuerst dieses Dokument angepasst.

## Zweck

Johanna ist eine Person, die **rund um die Uhr von jeweils einer Person assistiert**
wird. Die Assistenz übernimmt ein kleiner Helferkreis (bis zu 10 Personen). Zusätzlich
zum Tagesdienst gibt es an jedem Tag eine **Rufbereitschaft** durch eine andere Person
aus dem Team. Das Programm erstellt für jeden Monat einen Dienstplan, der die Tage
**fair** auf das Team verteilt und dabei die persönlichen Einschränkungen jedes
Helfers berücksichtigt.

Das Programm läuft zunächst als **Desktop-Anwendung** (Windows-Build für den realen
Einsatz, Entwicklung unter Linux). Geplant wird von einer Person am Rechner.

## Dienstarten

| Kürzel | Bedeutung | Abdeckung |
|--------|-----------|-----------|
| VOLL   | Tagesdienst (Regelfall) | deckt den ganzen Tag ab |
| VM     | nur Vormittag (Ausnahme) | halber Tag |
| NM     | nur Nachmittag (Ausnahme) | halber Tag |
| RB     | Rufbereitschaft (immer ganztägig, kein halber Tag) | eigener Bedarf: 1 Person pro Tag |

Ein Tag gilt als **abgedeckt**, wenn entweder eine Person VOLL übernimmt **oder**
zwei Personen sich den Tag mit VM + NM teilen — **und** zusätzlich eine weitere
Person die Rufbereitschaft hat. Pro Person und Tag gibt es **entweder Dienst oder
Rufbereitschaft, nie beides**; die Rufbereitschaft übernimmt also nie die Person,
die an dem Tag Dienst hat. Halbe Dienste zählen für die Verteilung als 0,5 Dienste.
Rufbereitschaften zählen in einer **eigenen Zählung** und nie zu den Soll-Diensten.

## Fairness-Regeln (Einschränkungen)

Jeder Helfer hat eigene Vorgaben:

- **Min./Max. Dienste pro Monat**: eine Spanne (z. B. min 3, max 6), beide Werte
  optional („Auto"). Das Minimum ist ein Verteilungsziel, das Maximum eine harte
  Grenze — der Generator überschreitet es nie; im Zweifel bleibt ein Tag unbesetzt
  und es erscheint eine Warnung. Min ≤ Max wird automatisch eingehalten.
- **Rufbereitschaft ≈ Dienste**: jeder Helfer bekommt im Monat etwa so viele
  Rufbereitschaften wie (gewichtete) Dienste.
- **Max. Tage am Stück** (1–7): mehr aufeinanderfolgende Diensttage sind nicht
  erlaubt. Gilt für Dienst **und** Rufbereitschaft, aber **je Art getrennt
  gezählt**: 3 Tage Dienst direkt gefolgt von 3 Tagen Rufbereitschaft sind zwei
  3er-Folgen, keine 6er-Folge.
- **Min. Tage am Stück** (1–7): Helfer mit weiter Anreise kommen immer für mehrere
  Tage hintereinander (z. B. 2er- oder 3er-Blöcke). Der Generator plant sie nur in
  zusammenhängenden Blöcken ein — auch bei der Rufbereitschaft. Muss ≤ „Max. Tage
  am Stück" sein.
- **Urlaub** (nicht verfügbare Einzeltage und Urlaubszeiträume) und **Block**
  (reguläre Sperrzeiten, z. B. andere Verpflichtungen): an diesen Tagen wird die
  Person nie eingeplant — weder für Dienst noch für Rufbereitschaft. Beide Arten
  wirken gleich; der Unterschied ist rein die Kategorie (echter Urlaub bleibt von
  sonstigen geblockten Zeiten unterscheidbar).

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
   - Neben dem Namen stehen pro Helfer die **Soll-Dienste als Min/Max-Spanne**
     (zwei Spalten mit Minus/Plus-Buttons, „Auto" = keine Grenze bzw. gleichmäßig
     verteilen; Min ≤ Max hält sich automatisch konsistent) und die **belegten
     Dienste** als Tupel `VOLL | VM | NM | RB`.
   - **Stempel-Buttons**: Tagesdienst | VM | NM | Rufbereitschaft | Urlaub |
     Block | Fixieren | Löschen.
     Ein aktiver Stempel wird per Klick auf eine Zelle angewendet; erneuter Klick
     auf denselben Stempeltyp entfernt ihn wieder. **Gestempelte Dienste sind
     automatisch fixiert** (Fixpunkte, mit Schloss). Einträge eines *anderen*
     Typs bleiben unangetastet — außer die Checkbox **„Überschreiben"** ist
     bewusst eingeschaltet (Standard: aus), dann ersetzt der Stempel sie.
     **Löschen** entfernt Stempel und Zufalls-Vorschläge per Klick.
   - **Mehrfachauswahl**: mit Strg/Shift lassen sich mehrere Zellen (auch verstreut)
     markieren; das Rechtsklick-Menü wirkt dann auf alle markierten Zellen.
   - **Urlaub und Block** im Raster: zusammenhängend gestempelte Tage werden
     automatisch zu Zeiträumen zusammengefasst und erscheinen in der
     Abwesenheitsübersicht des Team-Tabs; Einzeltage bleiben Einzeltage. Wird ein
     Tag mitten aus einem Zeitraum wieder entfernt, teilt sich der Zeitraum
     entsprechend. Im Raster erscheint Urlaub als graues **„U"**, Block als
     graues **„X"**.
   - Unter dem Raster: Zusammenfassung pro Helfer als Tupel `Name (VOLL|VM|NM|RB)`
     mit Legende sowie Warnhinweise (unbesetzte/halbe Tage, Tage ohne
     Rufbereitschaft, Zielabweichungen, Abweichungen Rufbereitschaft/Dienste).
2. **Team-Tab**: Links die Helferliste (anlegen/entfernen, Name und Farbe;
   **Min./Max. Dienste, Max. Folge und Min. Block direkt in der Tabelle** mit
   Minus/Plus-Buttons; Min./Max. Dienste sowie Min. Block und Max. Folge halten
   sich jeweils automatisch konsistent). Einzelne Abwesenheitstage stempelt man
   direkt im Planraster (Urlaub- oder Block-Stempel). Rechts daneben die
   **Abwesenheitsübersicht**: alle Abwesenheiten aller Helfer chronologisch
   sortiert — Zeiträume **und Einzeltage**, Urlaub und Block (Block-Einträge sind
   mit `[Block]` gekennzeichnet), monatsübergreifend. Hinzufügen, **Bearbeiten**
   (Button oder Doppelklick) und Entfernen über Dialoge mit Kalender-Datumsfeldern
   und Art-Auswahl (Urlaub/Block); überlappende oder angrenzende Zeiträume
   verschmelzen automatisch. In der Tab-Zeile (solange der Team-Tab aktiv ist):
   **Filter** nach Person und Monat sowie „Vergangene anzeigen" — abgelaufene
   Abwesenheiten sind standardmäßig ausgeblendet.

### Generier-Zyklus: Fixieren und Neuwürfeln

1. Man stempelt zuerst die **Fixpunkte** von Hand (z. B. „Martha kommt am 1.–2.
   VOLL, am 3. nur VM"). Gestempelte Dienste sind automatisch fixiert und
   bleiben immer stehen.
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

Nach der Dienstvergabe verteilt der Generator die **Rufbereitschaft**: erst Blöcke
für Helfer mit weiter Anreise, dann die restlichen Tage — Ziel ist, dass jeder etwa
so viele Rufbereitschaften wie Dienste bekommt, nie am eigenen Diensttag. Ein hartes
„Max. Dienste" wird nie überschritten; wenn dadurch (oder in kleinen Teams durch die
Folgen-Grenzen) Tage nicht besetzbar sind, bleiben sie offen und erscheinen als
Warnung unter dem Raster — das ist gewollt, nicht kaputt.

## Datenhaltung

Alle Daten liegen als **JSON** im Ordner `data/` neben dem Programm. Das Programm
speichert beim Beenden automatisch und stellt beim Start den letzten Zustand wieder
her (zuletzt geöffneter Monat, Fenstergröße).

### `data/team.json` — das Team (monatsübergreifend)

Enthält neben Name/Farbe auch die **personenbezogenen Einschränkungen**: Urlaube
und Einzeltage sowie Block-Zeiten (datumsbasiert, gelten in jedem berührten Monat —
auch monatsübergreifend), Max. Folge und Min. Block:

```json
{
  "version": 4,
  "assistants": [
    { "id": "f1f04d0e", "name": "Martha", "color": "#3498DB", "active": true,
      "constraints": {
        "assistant_id": "f1f04d0e",
        "unavailable_dates": ["2026-08-15"],
        "vacation_ranges": [["2026-08-28", "2026-09-05"]],
        "blocked_dates": [],
        "blocked_ranges": [["2026-08-20", "2026-08-22"]],
        "max_consecutive_days": 3,
        "min_block_days": 1 } }
  ]
}
```

### `data/plans/plan_JJJJ_MM.json` — ein Plan pro Monat

Enthält den Dienstplan des Monats und als einzige monatsbezogene Vorgabe die
**Soll-Dienste als Min/Max-Spanne** (`targets`) je Helfer:

```json
{
  "version": 4,
  "year": 2026,
  "month": 8,
  "schedule": {
    "1": [ { "assistant_id": "f1f04d0e", "shift_type": "FULL",
             "locked": true, "generated": false },
           { "assistant_id": "a27b3c91", "shift_type": "ON_CALL",
             "locked": false, "generated": true } ]
  },
  "targets": { "f1f04d0e": { "min": 3, "max": 6 }, "a27b3c91": { "min": null, "max": null } },
  "seed": 42,
  "created_at": "…", "modified_at": "…"
}
```

- `locked`: fixiert — übersteht das Neuwürfeln.
- `generated`: wurde vom Zufallsgenerator vergeben (farblich markiert), nicht von Hand.
- `shift_type: "ON_CALL"`: Rufbereitschaft (im Raster als „RB").

In den CSV-/Excel-/PDF-Exporten hat die Zusammenfassung eine eigene **RB**-Spalte;
„Dienste gesamt" ist die gewichtete Dienstzahl (VOLL = 1, VM/NM = 0,5, ohne RB).

### `data/settings.json` — App-Zustand

```json
{
  "version": 3,
  "last_year": 2026, "last_month": 8,
  "window_geometry": "…",
  "allow_overwrite": false,
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
