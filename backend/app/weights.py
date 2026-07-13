"""Gewichtungs-Engine: Deputats-Kennung -> Gewichtung je Halbjahr.

Die Kennung (Spalte J "Kennung" der Rohdaten) kodiert, wie oft ein Lehrer
eine Klasse tatsächlich unterrichtet:

Ziffern (Wochenrhythmus)
    Die erste Ziffer ist die Länge des Rhythmus in Wochen, die zweite gibt an,
    welche Woche des Rhythmus gemeint ist. Das Gewicht ist daher ``1/erste Ziffer``.

        1           jede Woche                  -> 1.0
        21, 22      jede 2. Woche               -> 0.5
        41 .. 44    jede 4. Woche               -> 0.25

Buchstaben-Präfix (Zeitraum)
    Ohne Präfix gilt die Kennung für das ganze Jahr (beide Halbjahre).

        A           nur 1. Halbjahr             -> (w, 0)
        B           nur 2. Halbjahr             -> (0, w)
        C, D        ein Quartal des 1. Halbjahrs -> (w/2, 0)
        E, F        ein Quartal des 2. Halbjahrs -> (0, w/2)

    Kombinationen wie ``A41`` sind zulässig (0.25 nur im 1. Halbjahr).

Blockunterricht
    ``BLO1``..``BLO4`` richten sich nach dem Wechselplan: Gewicht je Halbjahr ist
    ``Anzahl der Blockwochen / Anzahl der Schulwochen`` des Halbjahrs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Präfix -> (Faktor 1. HJ, Faktor 2. HJ)
PREFIX_FACTORS = {
    "": (1.0, 1.0),
    "A": (1.0, 0.0),
    "B": (0.0, 1.0),
    "C": (0.5, 0.0),
    "D": (0.5, 0.0),
    "E": (0.0, 0.5),
    "F": (0.0, 0.5),
}

_KENNUNG_RE = re.compile(r"^(?P<prefix>[A-F]?)(?P<digits>\d{1,2})$")
_BLOCK_RE = re.compile(r"^BLO(?P<nr>\d+)$")


class KennungError(ValueError):
    """Kennung konnte nicht interpretiert werden."""


@dataclass
class Blockplan:
    """Blockwochen je (Block, Halbjahr) und Schulwochen je Halbjahr."""

    schulwochen: dict[int, int] = field(default_factory=dict)
    bloecke: dict[tuple[str, int], int] = field(default_factory=dict)

    def block_weight(self, block: str, halbjahr: int) -> float:
        wochen = self.schulwochen.get(halbjahr, 0)
        if not wochen:
            return 0.0
        return self.bloecke.get((block, halbjahr), 0) / wochen


def rhythmus_weight(digits: str) -> float:
    """Gewicht aus der Ziffernfolge: 1/erste Ziffer."""
    rhythmus = int(digits[0])
    if rhythmus == 0:
        raise KennungError(f"Ungültiger Rhythmus in '{digits}'")
    if len(digits) > 1:
        woche = int(digits[1])
        if not 1 <= woche <= rhythmus:
            raise KennungError(
                f"Woche {woche} liegt außerhalb des {rhythmus}-Wochen-Rhythmus ('{digits}')"
            )
    return 1.0 / rhythmus


def calculate_weight(kennung: str, blockplan: Blockplan | None = None) -> tuple[float, float]:
    """Liefert (Gewicht 1. HJ, Gewicht 2. HJ) für eine Kennung."""
    code = str(kennung).strip().upper()
    if not code:
        raise KennungError("Leere Kennung")

    block = _BLOCK_RE.match(code)
    if block:
        if blockplan is None:
            raise KennungError(f"Blockunterricht '{code}' benötigt einen Blockplan")
        return (blockplan.block_weight(code, 1), blockplan.block_weight(code, 2))

    m = _KENNUNG_RE.match(code)
    if not m:
        raise KennungError(f"Unbekannte Kennung: '{kennung}'")

    w = rhythmus_weight(m.group("digits"))
    f1, f2 = PREFIX_FACTORS[m.group("prefix")]
    return (w * f1, w * f2)
