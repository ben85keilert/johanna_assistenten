# Planungslogik — Schema der bisherigen Vergabe

Dieses Dokument schematisiert, **wie der Zufallsgenerator vergibt**
(`scheduling/engine.py`), insbesondere in welcher **Reihenfolge** und mit
welchen **Prioritaeten** — einschliesslich der Stufe-2-Mechanik
(Kandidaten je Tag, Vorrang/Nachrang bei Freiwuenschen, Konflikt-Dialog).
Die fachliche Gesamtbeschreibung steht in `BESCHREIBUNG.md`; hier geht es
nur um den Ablauf der Vergabe.

## Regel-Hierarchie: hart vs. weich

**Harte Regeln** — werden **nie** verletzt, auch nicht als Notloesung.
Im Zweifel bleibt ein Tag unbesetzt und erscheint als Warnung:

| Regel | Bedeutung |
|---|---|
| Urlaub | Person ist an dem Tag nie einplanbar (Dienst und RB) — **zwingend**, wird nie ueberplant |
| Tages-Exklusivitaet | pro Person und Tag entweder Dienst **oder** RB, nie beides |
| Max. Dienste (explizit gesetzt) | hartes Maximum, keine Toleranz |
| Max. Tage am Stueck | je Dienstart getrennt gezaehlt (Dienst / RB) |
| Mindestabstand (`min_gap_days`) | freie Tage zwischen zwei Einsatzbloecken, Dienst+RB kombiniert |
| Fixierte + manuelle Eintraege | bleiben immer stehen und zaehlen fuer alle Ziele mit |

**Weiche Regeln** — Ziele, die der Generator anstrebt und bei Bedarf lockert:

| Regel | Lockerung |
|---|---|
| Faire Verteilung („Auto"-Soll = Tage/Helferzahl + 1,5 Toleranz) | wird ignoriert, wenn ein Tag sonst offen bliebe |
| Min. Dienste | Verteilungsziel: Helfer unter ihrem Minimum kommen zuerst dran |
| RB = Dienste (Gleichstand, ±0,5 bei halben Diensten) | wird zum Fuellen offener RB-Tage ueberschritten, danach Ausgleichsrunde |
| Blockvergabe (`min_block_days` > 1) | Blockfahrer werden fuer einzelne Resttage nur als Notloesung herangezogen |
| Wunsch-Tag mit **Nachrang** (Freiwunsch ueber dem Kontingent) | wird normal respektiert, darf aber als **vorletzte Stufe** ueberplant werden, wenn ein Tag sonst offen bliebe — gemeldet als Konflikt (Dialog) |
| Wunsch-Tag mit **Vorrang** (Freiwunsch innerhalb des Kontingents; ohne Kontingent alle) | wird respektiert wie Urlaub — darf aber als **allerletzte Stufe** ueberplant werden, wenn kein Nachrang-Wunsch den Tag fuellen kann (Konflikt-Dialog, Vorschlag: wenigste Dienste) |
| **Dienstwunsch** (Positivwunsch, `wish_dates`/`wish_ranges` + `work_wish_quota`) | Bevorzugung: vor der allgemeinen Fuellung bekommt die Person auf ihren Wunsch-Tagen Dienste bis zum Kontingent; nimmt nie einem anderen Tag die Abdeckung |

## Ablauf eines „Neu wuerfeln" (Schritt fuer Schritt)

```
Eingabe: Plan mit manuellen + fixierten Eintraegen ("Fixpunkte")

1. AUFRAEUMEN
   Alle Eintraege mit generated=True und locked=False entfernen.
   (Manuelles und Fixiertes bleibt stehen und zaehlt weiter mit.)

2. ZAEHLEN
   Je Helfer: bereits vergebene (gewichtete) Dienste (VOLL=1, Tag/Nacht=0,5)
   und Rufbereitschaften erfassen. Nicht gewaehlte Kandidaten zaehlen
   nirgends mit. "Auto"-Sollwert = Tage im Monat / aktive Helfer
   (+1,5 Toleranz); explizites Max ist hart.

2b. KANDIDATENWAHL DIENST
   Tage mit mehreren manuellen VOLL-Vorschlaegen (Kandidaten) bekommen
   zuerst einen Gewaehlten: unter den nach allen harten Regeln
   zulaessigen Kandidaten entscheidet die uebliche Auswahl (unter dem
   Minimum zuerst, dann wenigste Dienste, dann Zufall). Die weiche
   Auto-Zielgrenze bevorzugt nur; ein explizites Max bleibt hart.
   Kein zulaessiger Kandidat -> Tag geht in die normale Fuellung.

3. DIENST-BLOECKE (Helfer mit min_block_days > 1, zufaellige Reihenfolge)
   Solange das Soll es zulaesst: einen zusammenhaengenden VOLL-Block
   von min_block_days Laenge auf komplett freie Tage legen.
   Mit oncall_attach ("Vorher"/"Nachher"/"Beides") wird der gleich
   lange RB-Block im selben Schritt direkt daneben platziert.
   Jeder Kandidaten-Start muss ALLE harten Regeln erfuellen.
   Hat die Person noch offene Dienstwuensche, werden Starts bevorzugt,
   deren Block ganz auf ihren Wunsch-Tagen liegt.

3b. DIENSTWUENSCHE (Positivwuensche, zufaellige Tagesreihenfolge)
   Fuer jeden noch leeren Tag, den mindestens ein Einzeltag-Helfer als
   Dienstwunsch markiert hat: Kandidaten = diese Helfer mit noch offenem
   Kontingent, die alle harten Regeln erfuellen und unter ihrer
   Soll-Grenze liegen. Auswahl: wer anteilig am wenigsten seiner
   Wuensche erfuellt hat, dann wenigste Dienste, dann Zufall.
   Weiche Vorgabe - kein Tag wird dadurch unbesetzbar.

4. RESTLICHE DIENST-TAGE (zufaellige Tagesreihenfolge)
   Fuer jeden nicht abgedeckten Tag (fehlt VOLL bzw. die zweite
   Haelfte Tag/Nacht):
   a) Kandidaten = Einzeltag-Helfer, die alle harten Regeln erfuellen
      und unter ihrer Soll-Grenze liegen.
   b) Leer? -> Blockfahrer als Notloesung dazunehmen.
   c) Immer noch leer? -> Auto-Sollgrenze lockern (hart bleiben:
      explizites Max, Abstand, Folge, Urlaub, alle Freiwuensche).
   d) Immer noch leer? -> KONFLIKTSTUFE: einen Freiwunsch ueberplanen
      (nie Urlaub, nie harte Grenzen). Zuerst NACHRANG-Wuensche
      (Vorschlag: groesster Wunsch-Ueberhang ueber dem Kontingent, dann
      wenigste Dienste); gibt es keinen, als allerletzte Stufe einen
      VORRANG-Wunsch (Vorschlag: wenigste Dienste). Alle ueberplanbaren
      Personen stehen im Konflikt zur Wahl (Nachrang vor Vorrang);
      ohne Nutzerentscheid gilt der Vorschlag.
   e) Auch das nicht moeglich (nur Urlaub/harte Grenzen)? -> Tag bleibt
      offen (Warnung).
   Auswahl aus den Kandidaten ("pick"):
      1. Helfer unter ihrem Min. Dienste zuerst,
      2. dann die mit den wenigsten Diensten,
      3. Gleichstand entscheidet der Zufall (Seed).
   Danach ggf. RB direkt anhaengen (oncall_attach, best effort).

5. RUFBEREITSCHAFT
   Ziel je Helfer: RB-Tage = eigene (gewichtete) Dienstzahl.
   0) KANDIDATENWAHL RB: Tage mit mehreren manuellen RB-Vorschlaegen
      bekommen zuerst einen Gewaehlten (wie 2b, nie am eigenen
      wirksamen Diensttag).
   a) RB-Bloecke fuer Blockfahrer (wie Schritt 3, nur RB).
   b) Restliche Tage einzeln: Kandidaten wie oben (nie am eigenen
      Diensttag); wer am weitesten unter dem RB-Ziel liegt, zuerst.
   c) Leer? -> RB-Ziel lockern, damit kein Tag ohne RB bleibt.
   d) Immer noch leer? -> KONFLIKTSTUFE wie bei 4d (Nachrang-, dann
      Vorrang-Freiwunsch ueberplanen, als Konflikt gemeldet).

6. AUSGLEICHSRUNDE
   Helfer ueber ihrem RB-Ziel geben generierte, nicht fixierte
   RB-Tage an Helfer unter dem Ziel ab, solange alle harten Regeln
   es zulassen.

Ausgabe: GenerationResult (Plan + Liste der Konflikte). Die UI zeigt
die Konflikte in einem Dialog (Vorschlag vorausgewaehlt, alternativ
andere ueberplanbare Person oder "Tag offen lassen"); weicht die Wahl
ab, laeuft die Generierung mit gleichem Seed und einem Resolver erneut,
der die Entscheidungen beantwortet; bringt der neue Lauf neue Konflikte,
erscheint der Dialog erneut. Der Validator meldet alles, was nicht
aufging (offene Tage, doppelt besetzte Tage, Zielabweichungen,
RB-Ungleichstand, ueberplanter Urlaub/Freiwunsch, nicht erfuellte
Dienstwuensche, Kandidaten ohne Wahl, ...).
```

## Prioritaeten in Kurzform

Bei der Frage „wer bekommt diesen Tag?" gilt, in dieser Reihenfolge:

1. **Manuell/fixiert schlaegt alles** — Fixpunkte werden nie angetastet.
2. **Kandidaten zuerst**: traegt der Tag manuelle Vorschlaege (Kandidaten),
   wird unter ihnen gewaehlt, bevor der allgemeine Pool drankommt.
3. **Harte Regeln filtern** (Urlaub, Exklusivitaet, Max-Grenzen, Folge,
   Abstand); Freiwuensche (Vorrang und Nachrang) gelten bis zur
   Konfliktstufe ebenfalls als gesperrt.
3b. **Dienstwuensche**: wer den Tag als Dienstwunsch markiert hat und
   sein Kontingent noch nicht erfuellt hat, bekommt ihn vor dem
   allgemeinen Pool (anteilig am wenigsten Erfuellte zuerst).
4. **Unter dem Minimum** liegende Helfer haben Vorrang.
5. **Wenigste Dienste zuerst** (Least-loaded, gierig).
6. **Zufall** (seedbar) entscheidet Gleichstaende.
7. **Blockfahrer** werden fuer Einzeltage nur als Notloesung verwendet.
8. **Lockerung** der weichen Ziele; als vorletzte Stufe darf ein
   **Nachrang-Freiwunsch**, als allerletzte ein **Vorrang-Freiwunsch**
   ueberplant werden (Konflikt-Dialog, "Tag offen lassen" moeglich).
   Prioritaet: Urlaub (zwingend) > Kontingent-Wuensche (Vorrang) >
   Zusatz-Wuensche (Nachrang) > Fairness. Lieber ein offener Tag
   (Warnung) als eine verletzte harte Regel - Urlaub und harte Grenzen
   werden nie angetastet, Wuensche sind Wuensche.
