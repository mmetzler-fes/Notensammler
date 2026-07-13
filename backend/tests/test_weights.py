import pytest

from app.weights import Blockplan, KennungError, calculate_weight


@pytest.fixture
def blockplan():
    # Entspricht dem Wechselplan der Beispieldaten: je 19 Schulwochen.
    return Blockplan(
        schulwochen={1: 19, 2: 19},
        bloecke={
            ("BLO1", 1): 5, ("BLO2", 1): 6, ("BLO3", 1): 5, ("BLO4", 1): 3,
            ("BLO1", 2): 6, ("BLO2", 2): 6, ("BLO3", 2): 7,
        },
    )


@pytest.mark.parametrize(
    "kennung,erwartet",
    [
        # Ziffern gelten ohne Präfix für das ganze Jahr.
        ("1", (1.0, 1.0)),
        ("21", (0.5, 0.5)),
        ("22", (0.5, 0.5)),
        ("41", (0.25, 0.25)),
        ("44", (0.25, 0.25)),
        # A/B: ganzes Halbjahr, C-F: nur ein Quartal -> halbe Anrechnung.
        ("A1", (1.0, 0.0)),
        ("B1", (0.0, 1.0)),
        ("A22", (0.5, 0.0)),
        ("B21", (0.0, 0.5)),
        ("A41", (0.25, 0.0)),
        ("C1", (0.5, 0.0)),
        ("D21", (0.25, 0.0)),
        ("E22", (0.0, 0.25)),
        ("F1", (0.0, 0.5)),
    ],
)
def test_ziffern_und_praefixe(kennung, erwartet):
    assert calculate_weight(kennung) == pytest.approx(erwartet)


def test_kleinschreibung_und_leerzeichen(blockplan):
    assert calculate_weight(" b22 ", blockplan) == pytest.approx((0.0, 0.5))


def test_blockunterricht(blockplan):
    assert calculate_weight("BLO1", blockplan) == pytest.approx((5 / 19, 6 / 19))
    assert calculate_weight("BLO3", blockplan) == pytest.approx((5 / 19, 7 / 19))
    # BLO4 findet im 2. Halbjahr nicht statt.
    assert calculate_weight("BLO4", blockplan) == pytest.approx((3 / 19, 0.0))


def test_block_ohne_plan_meldet_fehler():
    with pytest.raises(KennungError):
        calculate_weight("BLO1")


@pytest.mark.parametrize("kennung", ["", "X1", "23", "45", "A", "1-4", "BT"])
def test_ungueltige_kennungen(kennung):
    with pytest.raises(KennungError):
        calculate_weight(kennung)
