import re
from pathlib import Path
from urllib.request import urlopen

# Фіксована версія книги, щоб корпус можна було зібрати повторно.
URL = (
    "https://raw.githubusercontent.com/GITenberg/The-War-of-the-Worlds_36/"
    "8b08fa3a7cbef117c80b2b437adc46e75c37dbf0/36-0.txt"
)


def main():
    with urlopen(URL, timeout=45) as response:
        book = response.read().decode("utf-8-sig").replace("\r\n", "\n")

    start = book.index("\nBOOK ONE\n")
    end = book.index("End of the Project Gutenberg EBook", start)
    parts = book[start:end].split("\nBOOK TWO\n")
    folder = Path("data/war-of-the-worlds")
    folder.mkdir(parents=True, exist_ok=True)
    count = 0
    for part_no, part in enumerate(parts, start=1):
        chapters = re.split(r"(?m)^[IVX]+\.\n+", part)[1:]
        for number, chapter in enumerate(chapters, start=1):
            path = folder / f"book-{part_no}-chapter-{number:02}.txt"
            path.write_text(chapter.strip() + "\n", encoding="utf-8")
            count += 1
    print(f"Збережено розділів: {count} ({folder})")


if __name__ == "__main__":
    main()
