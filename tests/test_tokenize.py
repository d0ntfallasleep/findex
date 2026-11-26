import pytest

from findex.tokenize import tokenize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Mars MARS Straße", ["mars", "mars", "strasse"]),
        ("Їжак і ґанок", ["їжак", "і", "ґанок"]),
        ("cafe\u0301 café", ["café", "café"]),
        ("п’ять пʼять п'ять", ["п'ять"] * 3),
        ("'Don't!' — he said.", ["don't", "he", "said"]),
        ("heat-ray пів_міста", ["heat", "ray", "пів", "міста"]),
        ("1984 М2 3.14", ["1984", "м2", "3", "14"]),
        ("…!? —", []),
        ("", []),
    ],
)
def test_tokenize(text, expected):
    assert list(tokenize(text)) == expected
