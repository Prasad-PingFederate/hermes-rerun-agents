import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from stack import Stack


def test_push_and_pop():
    s = Stack()
    s.push(10)
    s.push(20)
    assert s.pop() == 20
    assert s.pop() == 10


def test_pop_empty_raises_index_error():
    s = Stack()
    with pytest.raises(IndexError):
        s.pop()
