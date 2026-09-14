# Planungslogik — Schema der bisherigen Vergabe

Dieses Dokument schematisiert, **wie der Zufallsgenerator heute vergibt**
(`scheduling/engine.py`), insbesondere in welcher **Reihenfolge** und mit
welchen **Prioritaeten**. Es ist die Grundlage fuer die geplante Stufe 2
(Prioritaeten bei mehreren Kandidaten je Tag, Vorrang/Nachrang bei
Freiwuenschen, Konflikt-Dialoge). Die fachliche Gesamtbeschreibung steht in
`BESCHREIBUNG.md`; hier geht es nur um den Ablauf der Vergabe.

## Regel-Hierarchie: hart vs. weich

**Harte Regeln** — werden **nie** verletzt, auch nicht als Notloesung.
Im Zweifel bleibt ein Tag unbesetzt und erscheint als Warnung:

| Regel | Bedeutung |
|---|---|
| Urlaub | Person ist an dem Tag nie einplanbar (Dienst und RB) — **zwingend** |
| Block | wie Urlaub, eigene Kategorie (sonstige Sperrzeit) — **zwingend** |
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

## Ablauf eines „Neu wuerfeln" (Schritt fuer Schritt)

```
Eingabe: Plan mit manuellen + fixierten Eintraegen ("Fixpunkte")

1. AUFRAEUMEN
   Alle Eintraege mit generated=True und locked=False entfernen.
   (Manuelles und Fixiertes bleibt stehen und zaehlt weiter mit.)

2. ZAEHLEN
   Je Helfer: bereits vergebene (gewichtete) Dienste (VOLL=1, VM/NM=0,5)
   und Rufbereitschaften erfassen. "Auto"-Sollwert = Tage im Monat /
   aktive Helfer (+1,5 Toleranz); explizites Max ist hart.

3. DIENST-BLOECKE (Helfer mit min_block_days > 1, zufaellige Reihenfolge)
   Solange das Soll es zulaesst: einen zusammenhaengenden VOLL-Block
   von min_block_days Laenge auf komplett freie Tage legen.
   Mit oncall_attach ("Vorher"/"Nachher"/"Beides") wird der gleich
   lange RB-Block im selben Schritt direkt daneben platziert.
   Jeder Kandidaten-Start muss ALLE harten Regeln erfuellen.

4. RESTLICHE DIENST-TAGE (zufaellige Tagesreihenfolge)
   Fuer jeden nicht abgedeckten Tag (fehlt VOLL bzw. die zweite
   Tageshaelfte VM/NM):
   a) Kandidaten = Einzeltag-Helfer, die alle harten Regeln erfuellen
      und unter ihrer Soll-Grenze liegen.
   b) Leer? -> Blockfahrer als Notloesung dazunehmen.
   c) Immer noch leer? -> Auto-Sollgrenze lockern (hart bleiben:
      explizites Max, Abstand, Folge, Urlaub/Block).
   d) Immer noch leer? -> Tag bleibt offen (Warnung).
   Auswahl aus den Kandidaten ("pick"):
      1. Helfer unter ihrem Min. Dienste zuerst,
      2. dann die mit den wenigsten Diensten,
      3. Gleichstand entscheidet der Zufall (Seed).
   Danach ggf. RB direkt anhaengen (oncall_attach, best effort).

5. RUFBEREITSCHAFT
   Ziel je Helfer: RB-Tage = eigene (gewichtete) Dienstzahl.
   a) RB-Bloecke fuer Blockfahrer (wie Schritt 3, nur RB).
   b) Restliche Tage einzeln: Kandidaten wie oben (nie am eigenen
      Diensttag); wer am weitesten unter dem RB-Ziel liegt, zuerst.
   c) Leer? -> RB-Ziel lockern, damit kein Tag ohne RB bleibt.

6. AUSGLEICHSRUNDE
   Helfer ueber ihrem RB-Ziel geben generierte, nicht fixierte
   RB-Tage an Helfer unter dem Ziel ab, solange alle harten Regeln
   es zulassen.

Ausgabe: Plan; der Validator meldet alles, was nicht aufging
(offene Tage, Zielabweichungen, RB-Ungleichstand, ...).
```

## Prioritaeten in Kurzform

Bei der Frage „wer bekommt diesen Tag?" gilt heute, in dieser Reihenfolge:

1. **Manuell/fixiert schlaegt alles** — Fixpunkte werden nie angetastet.
2. **Harte Regeln filtern** die Kandidaten (Urlaub/Block, Exklusivitaet,
   Max-Grenzen, Folge, Abstand).
3. **Unter dem Minimum** liegende Helfer haben Vorrang.
4. **Wenigste Dienste zuerst** (Least-loaded, gierig).
5. **Zufall** (seedbar) entscheidet Gleichstaende.
6. **Blockfahrer** werden fuer Einzeltage nur als Notloesung verwendet.
7. **Lockerung** nur der weichen Ziele; lieber ein offener Tag (Warnung)
   als eine verletzte harte Regel.

## Ausblick Stufe 2 (geplant, noch nicht umgesetzt)

- **Mehrere Kandidaten je Tag**: Ein Tag soll mehrere manuell eingetragene
  Personen fuer Dienst/RB tragen koennen. Genau ein manueller Volleintrag =
  fix wie bisher; mehrere Eintraege = Auswahlmenge, aus der (per Wuerfeln
  oder Dialog) einer gewaehlt wird.
- **Freiwunsch-Kontingent (Blocks)**: Es gibt eine vorgegebene Zahl an
  Freiwuenschen (Blocks) je Helfer. Wuensche innerhalb des Kontingents
  haben Vorrang; **zusaetzliche** Wuensche daruber hinaus haben Nachrang
  gegenueber Helfern, die ihr Kontingent noch nicht ausgeschoepft haben.
  Damit wird Block von einer harten zur **priorisierten weichen** Regel —
  Urlaub bleibt zwingend.
- **Konflikt-Dialog beim Wuerfeln**: Ist ein Tag nicht regelkonform
  besetzbar (oder ein Wunsch nicht erfuellbar), fragt ein Dialog nach, wie
  der Konflikt geloest werden soll — die Tage werden trotzdem belegt, am
  Ende steht immer ein vernuenftiger Vorschlag. Prioritaet dabei:
  Urlaub (zwingend) > Kontingent-Wuensche > Zusatz-Wuensche > Fairness.
