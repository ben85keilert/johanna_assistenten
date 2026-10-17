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
| Tag    | halber Dienst: nur die Tag-Hälfte (Ausnahme) | halber Tag |
| Nacht  | halber Dienst: nur die Nacht-Hälfte (Ausnahme) | halber Tag |
| RB     | Rufbereitschaft (immer ganztägig, kein halber Tag) | eigener Bedarf: 1 Person pro Tag |

Ein Tag gilt als **abgedeckt**, wenn entweder eine Person VOLL übernimmt **oder**
zwei Personen sich den Tag mit Tag + Nacht teilen — **und** zusätzlich eine weitere
Person die Rufbereitschaft hat. Pro Person und Tag gibt es **entweder Dienst oder
Rufbereitschaft, nie beides**; die Rufbereitschaft übernimmt also nie die Person,
die an dem Tag Dienst hat. Halbe Dienste zählen für die Verteilung als 0,5 Dienste.
Rufbereitschaften zählen in einer **eigenen Zählung** und nie zu den Soll-Diensten.
(Bis Version 0.3 hießen die halben Dienste „VM"/„NM" — Vormittag/Nachmittag; im
Dateiformat heißen sie weiterhin `HALF_MORNING`/`HALF_AFTERNOON`.)

## Fairness-Regeln (Einschränkungen)

Jeder Helfer hat eigene Vorgaben:

- **Min./Max. Dienste pro Monat**: eine Spanne (z. B. min 3, max 6), beide Werte
  optional („Auto"). Das Minimum ist ein Verteilungsziel, das Maximum eine harte
  Grenze — der Generator überschreitet es nie; im Zweifel bleibt ein Tag unbesetzt
  und es erscheint eine Warnung. Min ≤ Max wird automatisch eingehalten.
- **Rufbereitschaft = Dienste**: jeder Helfer bekommt im Monat **genauso viele**
  Rufbereitschaften wie (gewichtete) Dienste — Gleichstand ist Pflicht, nicht
  nur Ziel. Bei halben Diensten (z. B. 4,5) darf auf- oder abgerundet werden.
  Der Generator gleicht Überhänge am Ende aktiv aus; geht der Gleichstand
  wegen anderer Regeln nicht auf, erscheint eine Warnung.
- **Mindestabstand** (einstellbar je Helfer, 0 = aus): so viele **freie Tage**
  müssen zwischen zwei Einsatzblöcken derselben Person liegen (Dienst und
  Rufbereitschaft zusammen gezählt; direkt angrenzende Tage gehören zum selben
  Block). Die Termine werden dadurch gestreut. **Die Abstände sind ein Muss** —
  der Generator unterschreitet sie nie, auch nicht als Notlösung; im Zweifel
  bleibt ein Tag offen.
- **Rufbereitschaft anhängen** („Vorher"/„Nachher"/„Beides", Standard: aus): die
  Rufbereitschaft wird als gleich langer Block **direkt vor bzw. nach dem
  Dienstblock** eingeplant. Wichtig für Helfer mit langer Anreise, die am
  Stück vor Ort sein wollen (z. B. 3 Tage Dienst + 3 Tage Rufbereitschaft
  hintereinander). **„Beides"** verteilt denselben Block auf beide Seiten — bei
  4 Tagen Dienst also 2 Tage Rufbereitschaft davor und 2 danach (bei ungerader
  Länge liegt der längere Teil hinten). Die **Gesamtzahl der angehängten
  RB-Tage bleibt in allen Varianten so groß wie der Dienstblock**, damit die
  Regel „so viele Rufbereitschaften wie Dienste" weiter aufgeht.
  Max. Folge zählt dabei weiter je Art getrennt.
- **Max. Tage am Stück** (1–7): mehr aufeinanderfolgende Diensttage sind nicht
  erlaubt. Gilt für Dienst **und** Rufbereitschaft, aber **je Art getrennt
  gezählt**: 3 Tage Dienst direkt gefolgt von 3 Tagen Rufbereitschaft sind zwei
  3er-Folgen, keine 6er-Folge.
- **Min. Tage am Stück** (1–7): Helfer mit weiter Anreise kommen immer für mehrere
  Tage hintereinander (z. B. 2er- oder 3er-Blöcke). Der Generator plant sie nur in
  zusammenhängenden Blöcken ein — auch bei der Rufbereitschaft. Muss ≤ „Max. Tage
  am Stück" sein.
- **Urlaub** (nicht verfügbare Einzeltage und Urlaubszeiträume): an diesen Tagen
  wird die Person **nie** eingeplant — weder für Dienst noch für Rufbereitschaft.
  Urlaub ist **zwingend** und wird unter keinen Umständen überplant.
- **Wunsch (Freiwünsche)** (früher „Block"; Tage, an denen jemand frei haben
  möchte, z. B. andere Verpflichtungen): wirken grundsätzlich wie Urlaub, sind
  aber **Wünsche, keine Pflicht**. Je Helfer gibt es ein
  **Freiwunsch-Kontingent** („Freiwünsche", einstellbar in den Team-Vorlagen;
  **„Alle"** = kein Kontingent, alle Wunsch-Tage sind hart wie Urlaub — das ist
  der Standard und das bisherige Verhalten).
  Ist ein Kontingent gesetzt, gilt: Die **chronologisch ersten N Wunsch-Tage
  des Monats haben Vorrang** und werden nie überplant; alle **weiteren
  Wunsch-Tage haben Nachrang** — sie werden normalerweise ebenfalls respektiert,
  dürfen aber überplant werden, wenn ein Tag sonst unbesetzt bliebe (siehe
  Konflikt-Dialog unten). Helfer, die ihr Kontingent noch nicht ausgeschöpft
  haben, haben mit ihren Wünschen also Vorrang vor den Zusatz-Wünschen anderer.

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
- Gut lesbare Schrift und Zeilenhöhen — aber **kompakt genug, dass ein ganzer
  Monat auf den Bildschirm passt**. Alle Größen sind zentral im Theme
  (`ui/theme.py`) einstellbar; dort wird auch nachjustiert, wenn der Platz nicht
  reicht.
- Änderungen sind sofort in allen Tabs sichtbar — nichts muss doppelt gepflegt
  werden.
- **Farbschema** (damit das Programm angenehm aussieht): unter
  **Einstellungen → Farbschema** stehen vier Paletten — **Ozean** (Blau),
  **Salbei** (Grün), **Sand** (Terrakotta) und **Lavendel** (Violett) —, jede
  als **helles und dunkles** Schema. Die Wahl gilt sofort und wird gemerkt.
  Sie färbt die Oberfläche (Fenster, Tabellen, Reiter, Buttons,
  Wochenend-Grau, Hinweistexte); die Farben der Eintragsarten bleiben davon
  unabhängig unter **Einstellungen → Farben…** einstellbar. Im dunklen Schema
  wählt das Raster die Schriftfarbe je Zelle automatisch passend (hell auf
  dunkel). Der PDF-Export ist unabhängig vom Schema immer hell (Papier).

## Bedienkonzept

Drei Tabs — mit **einem gemeinsamen Monat**: Jahr und Monat werden einmal
oben rechts in der Tab-Zeile gewählt und gelten für alle Tabs gleichzeitig
(Dienstplan, Urlaub und Notizen, „In Dienstplan … übernehmen" im Team-Tab).
Wechselt man in einem Tab den Monat, gehen die anderen mit — so kann man
nicht versehentlich im Oktober planen und dabei den September ansehen.

1. **Dienstplan-Tab**: Monatsraster (Zeile = Helfer, Spalte = Tag).
   - Die Gruppe **„Würfeln"** (Neu würfeln, Zurücksetzen, Seed,
     Deterministisch) sitzt rechts in der Steuerleiste, direkt über der
     Monats- und Ansichtswahl — so hat die Stempelzeile genug Platz.
   - **Zwei Ansichten** (umschaltbar, wird gemerkt): *Breit* (der ganze Monat in
     einer Zeile) oder *Zweigeteilt* (zweite Monatshälfte unter der ersten — man
     scrollt vertikal statt horizontal).
   - Neben dem Namen stehen pro Helfer die **Soll-Dienste als Max/Min-Spanne**
     (zwei Spalten mit Minus/Plus-Buttons, „Auto" = keine Grenze bzw. gleichmäßig
     verteilen; Min ≤ Max hält sich automatisch konsistent) und die **belegten
     Dienste** als Tupel `VOLL | Tag | Nacht | RB` (Spaltenkopf `V|T|N|RB`).
     **Max steht links, Min rechts daneben** — Max begrenzt Min, wird also zuerst
     eingestellt. Andersherum zöge ein danach gesetztes Max das gerade erhöhte
     Min wieder zurück. Dieselbe Reihenfolge gilt in den Vorlagen des Team-Tabs.
   - **Stempel-Buttons**: Tagesdienst | Tag | Nacht | Rufbereitschaft |
     Urlaub | Wunsch | Notiz | Fixieren | Löschen.
     Ein aktiver Stempel wird per Klick auf eine Zelle angewendet; erneuter Klick
     auf denselben Stempeltyp entfernt ihn wieder. **Gestempelte Dienste sind
     automatisch fixiert** (Fixpunkte, mit Schloss). Einträge eines *anderen*
     Typs bleiben unangetastet — außer die Checkbox **„Überschreiben"** ist
     bewusst eingeschaltet (Standard: aus), dann ersetzt der Stempel sie.
     **Löschen** entfernt Stempel und Zufalls-Vorschläge per Klick.
   - **Kandidaten (mehrere Personen je Tag)**: Für **Tagesdienst (VOLL)** und
     **Rufbereitschaft** dürfen an einem Tag mehrere Personen eingetragen
     werden. Hat ein Tag **genau einen** manuell erstellten Volleintrag, ist
     dieser **fix** (wie bisher, mit Schloss). Stempelt man denselben Typ für
     eine **zweite** Person auf den Tag, werden beide Einträge zu
     **Kandidaten**: blass dargestellt mit **„?"** und gestricheltem Rahmen —
     der Tag ist damit wieder „zu wählen". Weitere Stempel fügen weitere
     Kandidaten hinzu; ein Klick mit demselben Stempel entfernt den eigenen
     Kandidaten wieder (bleibt nur einer übrig, wird er wieder ein normaler
     fixer Eintrag). **Neu würfeln wählt automatisch** einen der Kandidaten
     nach den Fairness-Regeln (die Wahl ist wie jeder Zufallseintrag
     transparent dargestellt und wird beim nächsten Würfeln neu getroffen);
     per Rechtsklick → **„Kandidat fest wählen"** entscheidet man selbst —
     die Wahl ist dann fixiert. Nicht gewählte Kandidaten bleiben sichtbar
     und zählen nicht als Abdeckung oder für die Soll-Dienste.
   - **Mehrfachauswahl**: mit Strg/Shift lassen sich mehrere Zellen (auch verstreut)
     markieren; das Rechtsklick-Menü wirkt dann auf alle markierten Zellen.
   - **Urlaub und Wunsch** im Raster: zusammenhängend gestempelte Tage werden
     automatisch zu Zeiträumen zusammengefasst und erscheinen im Tab
     „Urlaub und Notizen"; Einzeltage bleiben Einzeltage. Wird ein
     Tag mitten aus einem Zeitraum wieder entfernt, teilt sich der Zeitraum
     entsprechend. Im Raster erscheint Urlaub als **„U"**, ein Wunsch-Tag als
     unaufgeregter Schrägstrich **„/"**, jeweils in der Farbe der Eintragsart
     (siehe Farbmanagement unten). *Festgehaltene Alternative:* Wunsch-Tage
     ganz ohne Zeichen, nur mit der Wunsch-Farbe — dafür genügt es,
     `WISH_MARK` in `ui/theme.py` auf `""` zu setzen.
   - **Tagesnotizen**: Zu jedem Tag lässt sich eine Freitext-Notiz hinterlegen
     (Stempel **„Notiz"** + Klick auf eine Zelle des Tages, oder Rechtsklick →
     „Notiz für Tag … bearbeiten…"). Tage mit Notiz tragen im Tageskopf ein
     **Notizsymbol (📝)**; **zusätzlich erscheint das Symbol in den Zellen
     aller an dem Tag aktiven Helfer** (Dienst und Rufbereitschaft — eine
     Notiz wie „Dienst startet um 14:00 Uhr" betrifft alle Eingeteilten),
     dort ebenfalls mit dem Notiztext als Tooltip. Nicht gewählte
     Kandidaten zählen nicht als aktiv. Der Text erscheint als Tooltip auf dem Tageskopf
     und in einer **Notizzeile unter dem Raster**, sobald eine Zelle des Tages
     angeklickt ist. Der Dialog bearbeitet die Notiz mehrzeilig; leerer Text
     löscht sie. Alle Notizen des Monats auf einen Blick gibt es im Reiter
     **„Notizen"** des Tabs „Urlaub und Notizen" (siehe unten).
   - Unter dem Raster: Zusammenfassung pro Helfer als Tupel `Name (VOLL|Tag|Nacht|RB)`
     mit Legende sowie Warnhinweise (unbesetzte/halbe Tage, Tage ohne
     Rufbereitschaft, Zielabweichungen, Abweichungen Rufbereitschaft/Dienste).
2. **Tab „Urlaub und Notizen"**: alles rund um Abwesenheiten an einer Stelle —
   bewusst übersichtlicher als das Dienstplan-Raster, weil es hier nur zwei
   Arten gibt — und dazu alle Tagesnotizen des Monats.
   - **Ganz links die Helfer-Buttons** — ein großer Button je Helfer und
     **„Alle"**: Klick wählt genau diese Person, **Strg+Klick** nimmt weitere
     dazu (oder wieder heraus), „Alle" wählt alle. Für die gewählten Helfer
     wird angezeigt und eingetragen.
   - **Daneben ein Monatskalender** in Wochenform (Spalten Mo–So, Zeilen =
     Kalenderwochen). Bei einer gewählten Person zeigt er deren Abwesenheiten
     in den unter **Einstellungen → Farben…** gewählten Urlaub-/Wunsch-Farben
     (Standard: grün = Urlaub, hellbraun = Wunsch; die Legende unter dem
     Kalender zeigt die aktuellen Farben), der heutige Tag ist fett. Bei
     mehreren (oder allen) stehen in jedem Tag die betroffenen Namen (`U`/`W`
     davor) — zum Einsehen, wer wann weg ist. Tage mit Notiz tragen das
     Notizsymbol (📝).
   - **Eintragen** wie im Dienstplan über Stempel: **Urlaub | Wunsch | Löschen**.
     Klick auf einen Tag setzt bzw. entfernt ihn wieder; Urlaub und Wunsch
     schließen sich gegenseitig aus. Mehrere Tage lassen sich mit Strg/Shift
     markieren und per Rechtsklick gemeinsam setzen oder räumen. Eingetragen
     wird **für alle links gewählten Helfer** (bei mehreren erinnert ein
     Hinweis daran): haben alle den Tag schon, entfernt ein Klick ihn bei
     allen, sonst wird er bei allen gesetzt.
   - **Rechts zwei Reiter** (bewusst schmaler als der Kalender).
     **„Abwesenheiten"**: alle Abwesenheiten der gewählten Helfer
     chronologisch — Zeiträume **und Einzeltage**, Urlaub und Wunsch
     (Wunsch-Einträge mit `[Wunsch]` gekennzeichnet), monatsübergreifend;
     darüber die Filter „Nur dieser Monat" und „Vergangene anzeigen".
     Hinzufügen, **Bearbeiten** (Button oder Doppelklick) und Entfernen über
     Dialoge mit Kalender-Datumsfeldern und Art-Auswahl; überlappende oder
     angrenzende Zeiträume verschmelzen automatisch. Ein Klick auf einen
     Listeneintrag in einem anderen Monat wechselt **alle Tabs** in diesen
     Monat (der Eintrag bleibt gewählt).
   - **„Notizen"** — das Notizen-Fenster, vor allem für die anderen im Team:
     oben **alle Tage des Monats mit ihrer Notiz** (Wochenenden/Feiertage
     grau, Tage mit Notiz fett mit 📝; „Nur Tage mit Notiz" blendet den Rest
     aus). **Ein einfacher Klick in die Notiz-Spalte** bearbeitet die Notiz
     direkt in der Tabelle (Enter übernimmt, Esc verwirft); mehrzeilige
     Notizen stehen dort einzeilig mit `⏎` zwischen den Zeilen und bleiben
     beim Bearbeiten mehrzeilig. Darunter der **Editor** für den gewählten
     Tag — vor allem für mehrzeilige Notizen. Beide Wege gelten sofort,
     leerer Text löscht die Notiz. Ein Klick auf einen Tag im Kalender wählt
     ihn auch hier, ein **Doppelklick** springt direkt in den Editor. **Gesammelt ausgeben**: „Alle kopieren" legt alle Notizen samt
     den an dem Tag Eingeteilten (`VOLL: Benno · RB: Doro`) in die
     Zwischenablage (zum Weitergeben per Mail/Messenger), „Exportieren…"
     (auch **Datei → Exportieren → Notizen (Text)**) speichert sie als
     `notizen_JJJJ_MM.txt`; im PDF-Export stehen sie auf Seite 2.
3. **Team-Tab**: die Helferliste (anlegen/entfernen, Name;
   **„▲ Hoch"/„▼ Runter" verschieben den gewählten Helfer in der
   Reihenfolge** — sie bestimmt die Zeilenreihenfolge im Dienstplan und in
   den Exporten und wird mitgespeichert) in
   **zwei Vorlagen-Tabs** („Vorlage 1"/„Vorlage 2"): jede Vorlage hält einen
   kompletten Satz Einstellungen je Helfer — **Min./Max. Dienste, Max. Folge,
   Min. Block, Abstand (Mindestabstand), Freiwünsche (Freiwunsch-Kontingent,
   „Alle" = kein Kontingent) und RB anhängen** — direkt in der
   Tabelle mit Minus/Plus-Buttons (Min./Max.-Paare halten sich automatisch
   konsistent). Die Tabellen sind etwas größer als sonst und **abwechselnd
   im Ton des Farbschemas gestreift**. Änderungen an einer Vorlage wirken
   **nicht sofort** auf den Plan: erst der kräftige Button **„Vorlage …
   in Dienstplan <Monat> übernehmen"** (Akzentfarbe des Farbschemas, oben
   in der Mitte auf Höhe von Hoch/Runter) überträgt die gerade gezeigte
   Vorlage in den aktuell geöffneten Monat. So lassen sich zwei verschiedene
   Konstellationen vorbereiten und je nach Monat in den Dienstplan migrieren;
   jeder Monat merkt sich die übernommenen Einstellungen selbst. Der Name
   gilt dagegen immer sofort und in beiden Vorlagen. Helfer haben **keine
   eigene Farbe** mehr in der Oberfläche (im Plan tragen die Eintragsarten
   die Farbe). **Abwesenheiten
   gehören nicht hierher** — sie haben ihren eigenen Tab (siehe oben) und
   lassen sich zusätzlich direkt im Planraster stempeln.

### Generier-Zyklus: Fixieren und Neuwürfeln

1. Man stempelt zuerst die **Fixpunkte** von Hand (z. B. „Martha kommt am 1.–2.
   VOLL, am 3. nur Tag"). Gestempelte Dienste sind automatisch fixiert und
   bleiben immer stehen.
2. **Neu würfeln** füllt die restlichen Tage zufällig, unter Beachtung aller
   Regeln. Zufällig vergebene Dienste tragen einen **Punkt**.
3. Was gefällt, **fixiert** man per Klick (Fixieren-Stempel oder Rechtsklick).
   **Farblogik (Farbmanagement): nicht die Helfer, sondern die Eintragsarten
   tragen die Farbe** — VOLL, Tag, Nacht, RB, Urlaub und Wunsch haben je eine
   einheitliche, unter **Einstellungen → Farben…** einstellbare Farbe (mit
   Vorschau und „Standardfarben"-Reset). Wunsch-Tage haben standardmäßig ein
   ruhiges **Hellbraun** statt einer Signalfarbe — es ist ein Wunsch, kein
   Alarm (wer noch das alte Standard-Rot eingestellt hatte, bekommt beim
   Update automatisch das Hellbraun; selbst gewählte Farben bleiben). **Feste Einträge (von Hand gesetzt
   oder fixiert) sind kräftig/voll gefärbt; noch in Planung befindliche
   (gewürfelt, nicht fixiert) erscheinen transparenter** und tragen
   zusätzlich einen Punkt, fixierte ein Schloss. (Die früher im Team-Tab
   einstellbare Helferfarbe steht nur noch in den Daten und färbt allein
   den Excel-Export.) **Wochenenden und die gesetzlichen Feiertage in Bayern** (fest
   hinterlegt, rechnerisch für jedes Jahr bestimmt, inkl. Mariä Himmelfahrt)
   sind im Planraster, im Urlaubs-Kalender und im PDF-Export **grau
   hinterlegt** — der Feiertagsname erscheint als Tooltip im Tageskopf.
   Das ist reine Anzeige: die Planungslogik behandelt Feiertage nicht anders
   als normale Tage.
   „Deterministisch" bedeutet: Mit gleichem Seed und gleichen Fixpunkten liefert
   „Generieren" immer denselben Plan (reproduzierbar); ohne Häkchen würfelt jeder
   Klick anders.
4. Was nicht gefällt, bleibt unfixiert und wird beim nächsten Klick auf
   „Neu würfeln" **neu vergeben**. Schritte 3–4 wiederholt man, bis der Plan passt.

Endet ein manuell gesetzter Block mit einem halben Tag (z. B. am 3. nur „Tag"),
vergibt der Generator die fehlende Hälfte („Nacht") an eine andere Person.

Nach der Dienstvergabe verteilt der Generator die **Rufbereitschaft**: bei
Helfern mit „RB anhängen" wird der RB-Block schon zusammen mit dem Dienstblock
vergeben, dann kommen Blöcke für die übrigen Anreise-Helfer und die restlichen
Tage — jeder bekommt genauso viele Rufbereitschaften wie Dienste, nie am eigenen
Diensttag. Eine abschließende Ausgleichsrunde verschiebt überzählige
Rufbereitschaften zu Helfern unter ihrem Soll. Ein hartes „Max. Dienste" und der
Mindestabstand werden nie verletzt; wenn dadurch (oder in kleinen Teams durch
die Folgen-Grenzen) Tage nicht besetzbar sind, bleiben sie offen und erscheinen
als Warnung unter dem Raster — das ist gewollt, nicht kaputt.

### Konflikt-Dialog: wenn Wünsche nicht erfüllbar sind

Bleibt ein Tag nach allen Regeln unbesetzt, versucht der Generator als letzte
Stufe, einen **Nachrang-Freiwunsch zu überplanen** (nie einen Urlaub, nie einen
Vorrang-Wunsch, nie eine harte Grenze wie Max. Dienste oder Mindestabstand):
Der Tag wird **trotzdem belegt**, bevorzugt bei der Person mit dem größten
Wunsch-Überhang über ihrem Kontingent und den wenigsten Diensten — das ist der
**vernünftige Vorschlag**, der am Ende immer steht. Nach dem Würfeln zeigt ein
**Konflikt-Dialog** alle solchen Entscheidungen: je Konflikt der Tag, die Art
(Dienst/Rufbereitschaft) und eine Auswahl mit dem Vorschlag vorausgewählt,
anderen überplanbaren Personen und **„Tag offen lassen"**. Bestätigen übernimmt
die Auswahl; Abbrechen behält die Vorschläge (sie sind bereits ein gültiger
Plan). **Urlaube sind zwingend, Wünsche nicht.** Ein überplanter Wunsch wird
**nicht gelöscht**: der Wunsch-Tag bleibt eingetragen und sichtbar, die Zelle
trägt eine Warnmarkierung und unter dem Raster erscheint eine Warnung
(„Freiwunsch überplant").

## Datenhaltung

Alle Daten liegen als **JSON** im Ordner `data/` neben dem Programm. Beim Start wird
der letzte Zustand wiederhergestellt (zuletzt geöffneter Monat, Fenstergröße).

### Automatisches Speichern & Datensicherheit

**Es darf keine Arbeit verloren gehen — auch nicht bei Absturz oder Stromausfall.**
Dafür sorgen vier Dinge:

- **Autosave alle 15 Sekunden**: Sobald es ungespeicherte Änderungen gibt, schreibt
  das Programm sie automatisch weg (Statuszeile: „Automatisch gespeichert (hh:mm:ss)").
  Ein Absturz kostet damit höchstens die letzten Sekunden. Zusätzlich wird beim
  Monatswechsel und beim Beenden gespeichert, `Strg+S` speichert jederzeit von Hand.
  **Datei → Speichern unter… (`Strg+Umschalt+S`)** legt darüber hinaus eine frei
  benannte **Kopie** des aktuellen Plans (samt Team) an beliebiger Stelle ab —
  z. B. als Planvariante oder zur Weitergabe; sie lässt sich über
  „Plan-Datei öffnen…" wieder laden. Die automatische Ablage unter
  `data/plans/` läuft davon unabhängig weiter.
- **Nachfrage beim Beenden**: Wird das Fenster geschlossen, während noch Änderungen
  offen sind (also innerhalb der 15 Sekunden bis zum nächsten Autosave), fragt das
  Programm: *Speichern und beenden* / *Ohne Speichern beenden* / *Abbrechen*. Ohne
  offene Änderungen erscheint keine Rückfrage. Scheitert das Speichern, wird der
  Fehler gezeigt und man kann zum Plan zurück, statt die Daten zu verlieren.
  Beim Abmelden oder Herunterfahren (SIGTERM/SIGINT) speichert das Programm noch
  selbstständig. Nur ein hartes Abschießen (Task-Manager, Stromausfall) lässt sich
  nicht abfangen — dagegen schützt der 15-Sekunden-Autosave.
- **Atomares Schreiben mit Sicherungskopie**: Jede Datei wird zuerst vollständig als
  `*.tmp` geschrieben und dann in einem Zug an ihren Platz verschoben; die bisherige
  Fassung bleibt als `*.bak` daneben liegen. So gibt es zu jedem Zeitpunkt eine heile
  Datei — ein Absturz mitten im Speichern kann den alten Stand nicht mehr zerstören.
- **Beschädigte Dateien**: Ist eine Datei unlesbar, greift das Programm automatisch
  auf ihre `*.bak`-Kopie zurück und weist darauf hin. Sind beide beschädigt, startet
  es **nicht** mit leeren Daten, sondern bricht mit einer Meldung ab — damit die
  kaputte Datei nicht auch noch überschrieben wird.

### `data/team.json` — das Team (monatsübergreifend)

Enthält neben Name/Farbe die **personenbezogenen Einschränkungen** (Urlaube
und Einzeltage sowie Wunsch-Tage, im Dateiformat `blocked_dates`/
`blocked_ranges` — datumsbasiert, gelten in jedem berührten
Monat, auch monatsübergreifend — Max. Folge, Min. Block, Mindestabstand,
RB-Anhang) **und die zwei Einstellungs-Vorlagen** des Team-Tabs. Die im Repo
versionierte Datei ist die feste **Beispielvorlage** (Team Anton, Benno,
Anton W., Carla, Doro, Emil, Fenja, Greta):

```json
{
  "version": 6,
  "assistants": [
    { "id": "8cdf0de4", "name": "Benno", "color": "#00aa00", "active": true,
      "constraints": {
        "assistant_id": "8cdf0de4",
        "unavailable_dates": [],
        "vacation_ranges": [],
        "blocked_dates": [],
        "blocked_ranges": [],
        "max_consecutive_days": 4,
        "min_block_days": 3,
        "min_gap_days": 0,
        "oncall_attach": "none",
        "free_wish_quota": null } }
  ],
  "profiles": [
    { "name": "Vorlage 1",
      "settings": {
        "8cdf0de4": { "min_shifts": null, "max_shifts": null,
                      "max_consecutive_days": 4, "min_block_days": 3,
                      "min_gap_days": 0, "oncall_attach": "none",
                      "free_wish_quota": null } } },
    { "name": "Vorlage 2", "settings": { "…": {} } }
  ]
}
```

- `min_gap_days`: Mindestabstand in freien Tagen zwischen zwei Einsatzblöcken
  (0 = aus).
- `oncall_attach`: `"none"`, `"before"` oder `"after"` — Rufbereitschaft als
  Block direkt vor/nach dem Dienstblock.
- `free_wish_quota`: Freiwunsch-Kontingent (`null` = „Alle": alle Wunsch-Tage
  hart wie bisher; Zahl = so viele Wunsch-Tage je Monat haben Vorrang, weitere
  Nachrang).

### `data/plans/plan_JJJJ_MM.json` — ein Plan pro Monat

Enthält den Dienstplan des Monats und den **Schnappschuss der
Planungs-Einstellungen** (`settings`) je Helfer — das, was zuletzt (z. B. per
Vorlage) für diesen Monat übernommen wurde:

```json
{
  "version": 7,
  "year": 2026,
  "month": 9,
  "schedule": {
    "1": [ { "assistant_id": "f6164e36", "shift_type": "FULL",
             "locked": true, "generated": false,
             "candidate": false, "chosen": false },
           { "assistant_id": "8cdf0de4", "shift_type": "ON_CALL",
             "locked": false, "generated": true,
             "candidate": false, "chosen": false } ]
  },
  "notes": { "3": "Arzttermin 10 Uhr" },
  "settings": {
    "f6164e36": { "min": 3, "max": 6, "max_consecutive_days": 1,
                  "min_block_days": 1, "min_gap_days": 0,
                  "oncall_attach": "none", "free_wish_quota": null }
  },
  "seed": 42,
  "created_at": "…", "modified_at": "…"
}
```

Aus Version 4 migrierte Monatsdateien kennen nur die Soll-Spanne (`min`/`max`);
die übrigen Felder kommen dann weiterhin aus `team.json`.

- `locked`: fixiert — übersteht das Neuwürfeln.
- `generated`: wurde vom Zufallsgenerator vergeben (transparenter dargestellt), nicht von Hand.
- `shift_type: "ON_CALL"`: Rufbereitschaft (im Raster als „RB").
- `candidate`/`chosen`: Kandidaten-Mechanik — `candidate` markiert einen von
  mehreren Vorschlägen für den Tag (zählt nicht als Abdeckung/Soll, solange
  nicht gewählt), `chosen` die getroffene Wahl (vom Würfeln oder von Hand).
- `notes`: Freitext-Notiz je Tag (Tag → Text); leere Notizen werden nicht gespeichert.

In den CSV-/Excel-/PDF-Exporten hat die Zusammenfassung eine eigene **RB**-Spalte;
„Dienste gesamt" ist die gewichtete Dienstzahl (VOLL = 1, Tag/Nacht = 0,5,
ohne RB); die halben Dienste heißen in allen Exporten „Tag"/„Nacht".

Der **PDF-Export** (A4 **Hochformat**) ist der Aushang für das ganze Team:
- **Seite 1** zeigt den ganzen Monat — **beide Monatshälften untereinander**
  auf einer Seite (die Zeilenhöhe passt sich der Teamgröße an).
- Er zeigt **nur Dienste und Rufbereitschaften** — keine Urlaube, keine
  Wunsch-Tage und keine Hinweise auf überplante Wünsche: die anderen sollen
  nicht sehen, wer wann Urlaub hat oder frei haben möchte.
- Die Eintragsfarben aus **Einstellungen → Farben…**, **alle Einträge
  einheitlich kräftig** — ob ein Eintrag schon fixiert oder noch gewürfelt
  ist, spielt für den Aushang keine Rolle; Grau für Wochenenden und
  Feiertage; nicht gewählte Kandidaten erscheinen nicht. Hat eine Person an einem Tag Dienst **und** Rufbereitschaft, zeigt
  die Zelle beides (z. B. „VOLL/RB").
- **Tagesnotizen sind deutlich markiert**: der Tageskopf ist gelb hinterlegt
  und trägt „Notiz", die ganze Tagesspalte ist orange umrahmt, und in jeder
  Zelle der an dem Tag Eingeteilten steht nochmals „Notiz" als gelbes
  Schildchen (auf jeder Dienstfarbe lesbar).
- **Seite 2**: die **Notizen** im Wortlaut (je Tag mit den Eingeteilten), die
  **Zusammenfassung**, die angepasste **Legende** (nur Dienstarten, Grau,
  Notiz-Markierung) und die Feiertage des Monats.

### `data/settings.json` — App-Zustand

```json
{
  "version": 6,
  "last_year": 2026, "last_month": 8,
  "window_geometry": "…",
  "allow_overwrite": false,
  "seed": 42, "deterministic": true,
  "split_view": false,
  "entry_colors": {
    "FULL": "#5B9BD5", "HALF_MORNING": "#4DB6AC",
    "HALF_AFTERNOON": "#F2A54A", "ON_CALL": "#9575CD",
    "VACATION": "#81C784", "BLOCK": "#C8A882"
  },
  "skipped_version": "",
  "color_palette": "ozean",
  "dark_mode": false,
  "last_app_version": "0.3.1"
}
```

- `entry_colors`: die unter **Einstellungen → Farben…** gewählte Farbe je
  Eintragsart (fehlende Arten erhalten beim Laden die Standardfarbe).
  `HALF_MORNING`/`HALF_AFTERNOON` sind die halben Dienste „Tag"/„Nacht",
  `BLOCK` die Wunsch-Tage.
- `last_app_version`: die zuletzt gelaufene Programmversion — weicht sie beim
  Start ab, sichert das Programm zuerst den `data`-Ordner (siehe
  Datensicherung unten).
- `color_palette` / `dark_mode`: das unter **Einstellungen → Farbschema**
  gewählte Erscheinungsbild (`ozean`, `salbei`, `sand`, `lavendel`; hell
  oder dunkel).

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

### Automatisches Programm-Update

Die installierte Windows-Version hält sich selbst aktuell:

- Beim Start prüft das Programm im Hintergrund, ob auf GitHub ein neueres
  Release liegt (zusätzlich jederzeit über **Einstellungen → Nach Updates
  suchen…**). Fehler bei der Prüfung (kein Internet, noch kein Release)
  stören den Start nie — es passiert dann einfach nichts.
- Gibt es ein Update, fragt ein Dialog: **„Jetzt installieren"**, **„Später"**
  oder **„Diese Version überspringen"** (übersprungene Versionen meldet der
  Start-Check nicht mehr, der manuelle Check schon).
- Bei „Jetzt installieren" wird zuerst regulär gespeichert, dann das
  Release-ZIP mit Fortschrittsanzeige heruntergeladen und geprüft. Nach dem
  Beenden tauscht ein Hilfsskript den Programmordner aus und startet die
  neue Version — **der `data`-Ordner bleibt dabei unangetastet**, die
  Datendateien werden wie beschrieben beim nächsten Laden migriert.
- Schlägt das Update fehl, läuft das Programm unverändert weiter; das ZIP
  lässt sich immer auch manuell von GitHub herunterladen.
- Die laufende Version steht im Fenstertitel (`version.py` ist die einzige
  Quelle der Versionsnummer; Release-Tag und `pyproject.toml` müssen dazu
  passen, der Build-Workflow prüft das).

### Programm von Hand überschreiben

Programm und Daten sind getrennt: der Programmordner enthält `JohannaAssistenten.exe`
und `_internal\`, die Daten liegen daneben in `data\`. **Das Release-ZIP
enthält keinen `data`-Ordner.** Eine neue Version lässt sich deshalb auch von
Hand einspielen, ohne Pläne zu verlieren: Programm schließen, ZIP entpacken
und den Inhalt des Ordners `JohannaAssistenten` über den bisherigen
Programmordner kopieren („Dateien ersetzen"). Wichtig: den alten Ordner
**nicht löschen** (sonst ist `data\` mit weg) und das Programm vorher
beenden (eine laufende `.exe` lässt sich nicht ersetzen). Der automatische
Updater macht genau das, räumt dabei zusätzlich alte Programmdateien weg und
ist der bequemere Weg.

### Datensicherung

- **Automatisch bei jeder neuen Programmversion**: Startet eine andere
  Version als beim letzten Mal (Update oder von Hand überschrieben), kopiert
  das Programm **vor** dem ersten Speichern — also bevor Dateien ins neue
  Format migriert werden — alle Datendateien nach
  `data\sicherungen\<Datum_Uhrzeit>_v<alt>_vor_v<neu>\`; die Statuszeile
  meldet das. Die letzten 10 Sicherungen bleiben erhalten.
- **Von Hand**: **Datei → Datensicherung erstellen…** speichert den aktuellen
  Stand und legt den ganzen `data`-Ordner als
  `JohannaAssistenten-Daten_<Datum_Uhrzeit>.zip` an einen frei wählbaren Ort
  (z. B. USB-Stick).
- **Zurückholen**: Programm schließen und die Dateien aus der Sicherung (bzw.
  den Ordner `data` aus dem ZIP) zurück in den Programmordner kopieren.

## Vertraulichkeit

Es geht um eine reale Teamverwaltung — **mit echten Personendaten wird vertraulich
umgegangen; sie gehören nicht ins Git-Repository.** Die im Repo versionierten Daten
(`data/` mit dem Beispielteam Anton, Benno, Carla …) sind **ausschließlich
Dummy-/Beispieldaten**. Sie sind absichtlich eingecheckt, damit der Aufbau der
Dateien nachvollziehbar ist und als Beispielvorlage zum Ausprobieren dient.

## Ausblick (nur notiert, noch nicht umgesetzt)

- **Serverbetrieb**: Später soll das Programm über einen Server laufen. Die
  Assistenten können sich dann selbst einloggen und ihre Urlaube bzw. freien Tage
  eintragen.
