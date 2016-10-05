# -*- coding: utf-8 -*-
"""Contains the :class:`Multiset` class."""

from collections.abc import MutableSet, Set
from typing import (Generic, Iterable, Mapping, Optional, Tuple, TypeVar)

from sortedcontainers import SortedDict

T = TypeVar('T')


class Multiset(dict, MutableSet, Mapping[T, int], Generic[T]):
    """A multiset implementation.

    A multiset is similar to the builtin :class:`set`, but elements can occur multiple times in the multiset.
    It is also similar to a :class:`list` without ordering of the values and hence no index-based operations.

    The multiset is implemented as a specialized :class:`dict` where the key is the element and the value its
    multiplicity. It supports all operations, that the :class:`set` supports

    In contrast to the builtin :class:`collections.Counter`, no negative counts are allowed, elements with
    zero counts are removed from the :class:`dict`, and set operations are supported.

    :see: https://en.wikipedia.org/wiki/Multiset
    """

    def __init__(self, iterable: Optional[Iterable[T]]=None) -> None:
        """Create a new, empty Multiset object.

        And if given, initialize with elements from input iterable.
        Or, initialize from a mapping of elements to their multiplicity.

        Example:

        >>> ms = Multiset()                 # a new, empty multiset
        >>> ms = Multiset('abc')            # a new multiset from an iterable
        >>> ms = Multiset({'a': 4, 'b': 2}) # a new multiset from a mapping

        :param iterable: An optional iterable or mapping to initialize the multiset from.
        """
        self._total = 0
        super().__init__()
        if iterable is not None:
            self.update(iterable)

    def __missing__(self, element: T):
        """The multiplicity of elements not in the multiset is zero."""
        return 0

    def __setitem__(self, element: T, multiplicity: int):
        """Set the element's multiplicity.
        This will remove the element if the multiplicity is less than or equal to zero.
        '"""
        old = self[element]
        new = multiplicity > 0 and multiplicity or 0
        if multiplicity <= 0:
            if element in self:
                super().__delitem__(element)
        else:
            super().__setitem__(element, multiplicity)
        self._total += new - old

    def __str__(self):
        return '{%s}' % ', '.join(map(str, self))

    def __repr__(self):
        items = ', '.join('%r: %r' % item for item in sorted(self.items()))
        return '%s({%s})' % (type(self).__name__, items)

    def __len__(self):
        """Returns the total number of elements in the multiset.
        
        Note that this is equivalent to the sum of the multiplicities:
        
        >>> ms = Multiset('aab')
        >>> len(ms)
        3
        >>> sum(ms.values())
        3

        If you need the total number of elements, use either the :meth:`keys`() method
        >>> len(ms.keys())
        2

        or convert to a :class:`set`:
        >>> len(set(ms))
        2
        """
        return self._total

    def __iter__(self):
        for element, multiplicity in self.items():
            for _ in range(multiplicity):
                yield element

    def update(self, *others: Iterable[T]) -> None:
        """Like dict.update() but add multiplicities instead of replacing them.

        >>> ms = Multiset('aab')
        >>> ms.update('abc')
        >>> ms
        Multiset({'a': 3, 'b': 2, 'c': 1})
        >>> ms.update(Multiset('bc'))
        >>> ms
        Multiset({'a': 3, 'b': 3, 'c': 2})
        """
        for other in others:
            if isinstance(other, Mapping):
                for elem, multiplicity in other.items():
                    self[elem] += multiplicity
            else:
                for elem in other:
                    self[elem] += 1

    def union_update(self, *others: Iterable[T]) -> None:
        """Update the multiset, adding elements from all others using the maximum multiplicity.

        >>> ms = Multiset('aab')
        >>> ms.union_update(Multiset('bc'))
        >>> ms
        Multiset({'a': 2, 'b': 1, 'c': 1})
        >>> ms = Multiset('aab')
        >>> ms.union_update(Multiset('ccd'))
        >>> ms
        Multiset({'a': 2, 'b': 1, 'c': 2, 'd': 1})
        >>> ms = Multiset('aab')
        >>> ms.union_update(Multiset('a'))
        >>> ms
        Multiset({'a': 2, 'b': 1})
        >>> ms = Multiset('aab')
        >>> ms.union_update(Multiset('aaa'))
        >>> ms
        Multiset({'a': 3, 'b': 1})
        >>> ms = Multiset('aab')
        >>> ms.union_update(Multiset('bc'), Multiset('ccd'))
        >>> ms
        Multiset({'a': 2, 'b': 1, 'c': 2, 'd': 1})
        """
        for other in map(self._as_multiset, others):
            for elem, multiplicity in other.items():
                if multiplicity > self[elem]:
                    self[elem] = multiplicity

    def __ior__(self, other):
        if not isinstance(other, Set):
            return NotImplemented
        self.union_update(other)
        return self

    def intersection_update(self, *others: Iterable[T]) -> None:
        """Update the multiset, keeping only elements found in it and all others.

        >>> a = Multiset('aab')
        >>> a.intersection_update(Multiset('bc'))
        >>> a
        Multiset({'b': 1})
        >>> a = Multiset('aab')
        >>> a.intersection_update(Multiset('ccd'))
        >>> a
        Multiset({})
        >>> a = Multiset('aab')
        >>> a.intersection_update(Multiset('a'))
        >>> a
        Multiset({'a': 1})
        >>> a = Multiset('aab')
        >>> a.intersection_update(Multiset('aaa'))
        >>> a
        Multiset({'a': 2})
        >>> a = Multiset('aab')
        >>> a.intersection_update(Multiset('bc'), Multiset('a'))
        >>> a
        Multiset({})
        """
        for other in map(self._as_multiset, others):
            for elem, current_count in list(self.items()):
                multiplicity = other[elem]
                if multiplicity < current_count:
                    self[elem] = multiplicity

    def __iand__(self, other):
        if not isinstance(other, Set):
            return NotImplemented
        self.intersection_update(other)
        return self

    def difference_update(self, *others: Iterable[T]) -> None:
        """Remove all elements from the others from this multiset.

        >>> ms = Multiset('aab')
        >>> ms.difference_update(Multiset('bc'))
        >>> ms
        Multiset({'a': 2})
        >>> ms = Multiset('aab')
        >>> ms.difference_update(Multiset('ccd'))
        >>> ms
        Multiset({'a': 2, 'b': 1})
        >>> ms = Multiset('aab')
        >>> ms.difference_update(Multiset('a'))
        >>> ms
        Multiset({'a': 1, 'b': 1})
        >>> ms = Multiset('aab')
        >>> ms.difference_update(Multiset('a'), Multiset('a'))
        >>> ms
        Multiset({'b': 1})
        """
        for other in map(self._as_multiset, others):
            for elem, multiplicity in other.items():
                self.discard(elem, multiplicity)

    def __isub__(self, other):
        if not isinstance(other, Set):
            return NotImplemented
        self.difference_update(other)
        return self

    def symmetric_difference_update(self, other: Iterable[T]) -> None:
        """Update the multiset to contain only elements in either this multiset or the other but not both.

        >>> ms = Multiset('aab')
        >>> ms.symmetric_difference_update(Multiset('bc'))
        >>> ms
        Multiset({'a': 2, 'c': 1})
        >>> ms = Multiset('aab')
        >>> ms.symmetric_difference_update(Multiset('ccd'))
        >>> ms
        Multiset({'a': 2, 'b': 1, 'c': 2, 'd': 1})
        >>> ms = Multiset('aab')
        >>> ms.symmetric_difference_update(Multiset('a'))
        >>> ms
        Multiset({'a': 1, 'b': 1})
        >>> ms = Multiset('aab')
        >>> ms.symmetric_difference_update(Multiset('aaa'))
        >>> ms
        Multiset({'a': 1, 'b': 1})
        """
        other = self._as_multiset(other)
        keys = set(self.keys()) | set(other.keys())
        for elem in keys:
            multiplicity = self[elem]
            other_count = other[elem]
            self[elem] = multiplicity > other_count and multiplicity - other_count or other_count - multiplicity

    def __ixor__(self, other):
        if not isinstance(other, Set):
            return NotImplemented
        self.symmetric_difference_update(other)
        return self

    def times_update(self, factor: int) -> None:
        """Update each this multiset by multiplying each element's multiplicity with the given scalar factor.

        >>> ms = Multiset('aab')
        >>> ms.times_update(2)
        >>> ms
        Multiset({'a': 4, 'b': 2})
        """
        if factor <= 0:
            self.clear()
        else:
            for elem in self.keys():
                self[elem] *= factor

    def __imul__(self, factor):
        self.times_update(factor)
        return self

    def add(self, element: T, multiplicity: int=1) -> None: # pylint: disable=arguments-differ
        self[element] = self[element] + multiplicity

    def remove(self, element: T, multiplicity: Optional[int]=None) -> int: # pylint: disable=arguments-differ
        if element not in self:
            raise KeyError
        old_count = self[element]
        if multiplicity is None:
            del self[element]
        else:
            self[element] = self[element] - multiplicity
        return old_count

    def discard(self, element: T, multiplicity: Optional[int]=None) -> int: # pylint: disable=arguments-differ
        """Removes the `element` from the multiset.

        If `multiplicity` is `None`, all occurances of the `element` are removed,
        otherwise the `multiplicity` is subtracted.

        In contrast to :meth:`remove`, this does not raise an error if the
        `element` is not in the multiset.

        >>> ms = Multiset('aab')
        >>> ms.discard('a')
        2
        >>> ms
        Multiset({'b': 1})
        >>> ms = Multiset('aab')
        >>> ms.discard('a', 1)
        2
        >>> ms
        Multiset({'a': 1, 'b': 1})
        >>> ms = Multiset('a')
        >>> ms.discard('b')
        0
        >>> ms
        Multiset({'a': 1})
        """
        if element in self:
            old_count = self[element]
            if multiplicity is None:
                del self[element]
            else:
                self[element] -= multiplicity
            return old_count
        else:
            return 0

    def _as_multiset(self, other: Iterable[T]) -> 'Multiset[T]':
        if not isinstance(other, Multiset):
            if not isinstance(other, Iterable):
                raise TypeError("'%s' object is not iterable" % type(other))
            return type(self)(other)
        return other

    def isdisjoint(self, other: Iterable[T]) -> bool:
        """Return True if the set has no elements in common with other.

        Sets are disjoint if and only if their intersection is the empty set.

        >>> a = Multiset('aab')
        >>> b = Multiset('bc')
        >>> a.isdisjoint(b)
        False
        >>> c = Multiset('ccd')
        >>> a.isdisjoint(c)
        True
        """
        other = self._as_multiset(other)
        for elem in self.keys():
            if elem in other:
                return False
        return True

    def difference(self, *others: Iterable[T]) -> 'Multiset[T]':
        """Return a new multiset with all elements from the others removed.

        >>> a = Multiset('aab')
        >>> b = Multiset('bc')
        >>> a.difference(b)
        Multiset({'a': 2})
        >>> c = Multiset('ccd')
        >>> a.difference(c)
        Multiset({'a': 2, 'b': 1})
        >>> d = Multiset('a')
        >>> a.difference(d)
        Multiset({'a': 1, 'b': 1})
        >>> a.difference(d, d)
        Multiset({'b': 1})
        """
        result = type(self)(self)
        result.difference_update(*others)
        return result

    def __sub__(self, other: Set) -> bool:
        if not isinstance(other, Set):
            return NotImplemented
        return self.difference(other)

    def union(self, *others: Iterable[T]) -> 'Multiset[T]':
        """Return a new multiset with all elements from the multiset and the others with maximal multiplicities.

        >>> a = Multiset('aab')
        >>> b = Multiset('bc')
        >>> a.union(b)
        Multiset({'a': 2, 'b': 1, 'c': 1})
        >>> c = Multiset('ccd')
        >>> a.union(c)
        Multiset({'a': 2, 'b': 1, 'c': 2, 'd': 1})
        >>> d = Multiset('a')
        >>> a.union(d)
        Multiset({'a': 2, 'b': 1})
        >>> e = Multiset('aaa')
        >>> a.union(e)
        Multiset({'a': 3, 'b': 1})
        >>> a.union(b, c)
        Multiset({'a': 2, 'b': 1, 'c': 2, 'd': 1})
        """
        result = type(self)(self)
        result.union_update(*others)
        return result

    def __or__(self, other: Set) -> bool:
        if not isinstance(other, Set):
            return NotImplemented
        return self.union(other)

    __ror__ = __or__

    def combine(self, *others: Iterable[T]) -> 'Multiset[T]':
        """Return a new multiset with all elements from the multiset and the others with their multiplicities summed up.

        >>> a = Multiset('aab')
        >>> b = Multiset('bc')
        >>> a.combine(b)
        Multiset({'a': 2, 'b': 2, 'c': 1})
        >>> c = Multiset('ccd')
        >>> a.combine(c)
        Multiset({'a': 2, 'b': 1, 'c': 2, 'd': 1})
        >>> d = Multiset('a')
        >>> a.combine(d)
        Multiset({'a': 3, 'b': 1})
        >>> e = Multiset('aaa')
        >>> a.combine(e)
        Multiset({'a': 5, 'b': 1})
        >>> a.combine(b, c)
        Multiset({'a': 2, 'b': 2, 'c': 3, 'd': 1})
        """
        result = type(self)(self)
        result.update(*others)
        return result

    def __add__(self, other: Set) -> bool:
        if not isinstance(other, Set):
            return NotImplemented
        return self.combine(other)

    __radd__ = __add__

    def intersection(self, *others: Iterable[T]) -> 'Multiset[T]':
        """Return a new multiset with elements common to the multiset and all others.

        >>> a = Multiset('aab')
        >>> b = Multiset('bc')
        >>> a.intersection(b)
        Multiset({'b': 1})
        >>> c = Multiset('ccd')
        >>> a.intersection(c)
        Multiset({})
        >>> d = Multiset('a')
        >>> a.intersection(d)
        Multiset({'a': 1})
        >>> e = Multiset('aaa')
        >>> a.intersection(e)
        Multiset({'a': 2})
        >>> a.intersection(b, d)
        Multiset({})
        """
        result = type(self)(self)
        result.intersection_update(*others)
        return result

    def __and__(self, other: Set) -> bool:
        if not isinstance(other, Set):
            return NotImplemented
        return self.intersection(other)

    __rand__ = __and__

    def symmetric_difference(self, other: Iterable[T]) -> 'Multiset[T]':
        """Return a new set with elements in either the set or other but not both.

        >>> a = Multiset('aab')
        >>> b = Multiset('bc')
        >>> a.symmetric_difference(b)
        Multiset({'a': 2, 'c': 1})
        >>> c = Multiset('ccd')
        >>> a.symmetric_difference(c)
        Multiset({'a': 2, 'b': 1, 'c': 2, 'd': 1})
        >>> d = Multiset('a')
        >>> a.symmetric_difference(d)
        Multiset({'a': 1, 'b': 1})
        >>> e = Multiset('aaa')
        >>> a.symmetric_difference(e)
        Multiset({'a': 1, 'b': 1})
        """
        result = type(self)(self)
        result.symmetric_difference_update(other)
        return result

    def __xor__(self, other: Set) -> bool:
        if not isinstance(other, Set):
            return NotImplemented
        return self.symmetric_difference(other)

    __rxor__ = __xor__

    def times(self, factor: int) -> 'Multiset[T]':
        """Return a new set with each element's multiplicity multiplied with the given scalar factor.

        >>> a = Multiset('aab')
        >>> a.times(2)
        Multiset({'a': 4, 'b': 2})
        """
        result = type(self)(self)
        result.times_update(factor)
        return result

    def __mul__(self, factor: int) -> 'Multiset[T]':
        if not isinstance(factor, int):
            return NotImplemented
        return self.times(factor)

    __rmul__ = __mul__

    def clear(self) -> None:
        super().clear()
        self._total = 0

    def issubset(self, other: Iterable[T]) -> bool:
        """Return True iff this set is a subset of the other.

        >>> Multiset('ab').issubset(Multiset('aabc'))
        True
        >>> Multiset('aabb').issubset(Multiset('aabc'))
        False
        """
        other = self._as_multiset(other)
        if len(self) > len(other):
            return False
        for elem, multiplicity in self.items():
            if multiplicity > other[elem]:
                return False
        return True

    def __le__(self, other: Set) -> bool:
        if not isinstance(other, Set):
            return NotImplemented
        return self.issubset(other)

    def __lt__(self, other: Set) -> bool:
        if not isinstance(other, Set):
            return NotImplemented
        return self.issubset(other) and self != other

    def issuperset(self, other: Iterable[T]) -> bool:
        """Return True iff this multiset is a superset of the other.

        >>> Multiset('aabc').issuperset(Multiset('ab'))
        True
        >>> Multiset('aabc').issuperset(Multiset('abcc'))
        False
        """
        other = self._as_multiset(other)
        if len(self) < len(other):
            return False
        for elem, multiplicity in other.items():
            if self[elem] < multiplicity:
                return False
        return True

    def __ge__(self, other: Set) -> bool:
        if not isinstance(other, Set):
            return NotImplemented
        return self.issuperset(other)

    def __gt__(self, other: Set) -> bool:
        if not isinstance(other, Set):
            return NotImplemented
        return self.issuperset(other) and self != other

    def copy(self):
        """Return a shallow copy of the multiset."""
        return type(self)(self)

    __copy__ = copy


class SortedMultiset(Multiset[T], SortedDict, Generic[T]):
    def pop(self, index: int=-1) -> Tuple[T, int]: # pylint: disable=arguments-differ
        element = self._list.pop(index)
        multiplicity = self._pop(element)
        return element, multiplicity


if __name__ == '__main__':
    import doctest
    doctest.testmod(exclude_empty=True)
