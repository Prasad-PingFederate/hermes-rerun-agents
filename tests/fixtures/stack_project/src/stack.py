class Stack:
    """Simple stack collection."""

    def __init__(self):
        self._items = []

    def push(self, item):
        self._items.append(item)

    def pop(self):
        # Buggy: returns None instead of raising IndexError when empty
        if not self._items:
            return None
        return self._items.pop()

    def is_empty(self):
        return len(self._items) == 0

    def size(self):
        return len(self._items)

