import re
import unicodedata
from collections.abc import Iterator

WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")


def tokenize(text: str) -> Iterator[str]:
    text = unicodedata.normalize("NFC", text).casefold()
    text = text.replace("’", "'").replace("ʼ", "'")
    for match in WORD.finditer(text):
        yield match.group()
