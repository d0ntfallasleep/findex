import re
from dataclasses import dataclass

from findex.tokenize import tokenize


class Node:
    def __and__(self, other):
        return And(self, other)

    def __or__(self, other):
        return Or(self, other)

    def __invert__(self):
        return Not(self)


@dataclass(frozen=True)
class Term(Node):
    word: str

    def evaluate(self, index):
        return {p.doc_id for p in index.postings.get(self.word, ())}


@dataclass(frozen=True)
class Phrase(Node):
    words: tuple[str, ...]

    def evaluate(self, index):
        if index.positions is None:
            raise ValueError("Перебудуй індекс із --positions")
        lists = [index.positions.get(w, {}) for w in self.words]
        found = set()
        for doc in set.intersection(*(set(row) for row in lists)):
            starts = set(lists[0][doc])
            for offset, row in enumerate(lists[1:], 1):
                starts.intersection_update(pos - offset for pos in row[doc])
            if starts:
                found.add(doc)
        return found


@dataclass(frozen=True)
class And(Node):
    left: Node
    right: Node

    def evaluate(self, index):
        return self.left.evaluate(index) & self.right.evaluate(index)


@dataclass(frozen=True)
class Or(Node):
    left: Node
    right: Node

    def evaluate(self, index):
        return self.left.evaluate(index) | self.right.evaluate(index)


@dataclass(frozen=True)
class Not(Node):
    child: Node

    def evaluate(self, index):
        return set(range(index.num_docs)) - self.child.evaluate(index)


def parse(query):
    tokens = []
    for part in re.findall(r'"[^"]*"|[()"]|[^\s()"]+', query):
        if part == '"':
            raise ValueError("Незакриті лапки")
        if part.startswith('"'):
            words = tuple(tokenize(part[1:-1]))
            if not words:
                raise ValueError("Порожня фраза")
            tokens.append(Phrase(words))
        elif part in ("(", ")", "AND", "OR", "NOT"):
            tokens.append(part)
        else:
            tokens.extend(Term(w) for w in tokenize(part))
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def atom():
        nonlocal pos
        item = peek()
        pos += 1
        if item == "NOT":
            return ~atom()
        if item == "(":
            tree = expression()
            if peek() != ")":
                raise ValueError("Очікується )")
            pos += 1
            return tree
        if isinstance(item, Node):
            return item
        raise ValueError("Очікується слово, фраза або група")

    def conjunction():
        nonlocal pos
        tree = atom()
        while peek() not in (None, ")", "OR"):
            if peek() == "AND":
                pos += 1
            tree = tree & atom()
        return tree

    def expression():
        nonlocal pos
        tree = conjunction()
        while peek() == "OR":
            pos += 1
            tree = tree | conjunction()
        return tree

    tree = expression()
    if peek() is not None:
        raise ValueError("Зайва дужка")
    return tree


def positive_words(node, positive=True):
    if isinstance(node, Not):
        yield from positive_words(node.child, not positive)
    elif isinstance(node, (And, Or)):
        yield from positive_words(node.left, positive)
        yield from positive_words(node.right, positive)
    elif positive:
        if isinstance(node, Term):
            yield node.word
        else:
            yield from node.words
