# -*- coding: utf-8 -*-
from typing import Any, Dict, Iterator, List, Set, Type, Union, Tuple
from reprlib import recursive_repr

from graphviz import Digraph

from patternmatcher.expressions import (Arity, Atom, Expression, Operation,
                                        Optional, Symbol, SymbolWildcard,
                                        Variable, Wildcard, freeze)


class _OperationEnd(object):
    """Represents the end of an operation expression in a :class:`FlatTerm`.

    Used for :const:`OPERATION_END` as a singleton. Could also be a plain object,
    but the string representation is customized.
    """

    def __str__(self):
        return ')'

    __repr__ = __str__

OPERATION_END = _OperationEnd()
"""Constant used to represent the end of an operation in a :class:`FlatTerm`.

This is a singleton object that has *)* as representation.
Is is also used by the :class:`DiscriminationNet`.
"""

class _Epsilon(object):
    def __str__(self):
        return 'ε'

    __repr__ = __str__

EPSILON = _Epsilon()

def is_operation(term: Any) -> bool:
    """Return True iff the given term is a subclass of :class:`.Operation`."""
    return isinstance(term, type) and issubclass(term, Operation)


def is_symbol_wildcard(term: Any) -> bool:
    """Return True iff the given term is a subclass of :class:`.Symbol`."""
    return isinstance(term, type) and issubclass(term, Symbol)


def _get_symbol_wildcard_label(state: '_State', symbol_type: Type[Symbol]) -> Type[Symbol]:
    """Return the transition target for the given symbol type from the the given state or None if it does not exist."""
    return next((t for t in state.keys() if is_symbol_wildcard(t) and isinstance(symbol_type, t)), None)

# Broken without latest version of the typing package
# TermAtom = Union[Atom, Type[Operation], Type[Symbol], _OperationEnd]
# So for now use the non-generic version
TermAtom = Union[Atom, type, _OperationEnd]


class FlatTerm(List[TermAtom]):
    """A flattened representation of an :class:`.Expression`.

    This is a subclass of list. This representation is similar to the prefix notation generated by
    :meth:`.Expression.preorder_iter`, but contains some additional elements.

    Operation expressions are represented by the :func:`type` of the operation before the operands as well as
    :const:`OPERATION_END` after the last operand of the operation:

    >>> FlatTerm(f(a, b))
    [f, a, b, )]

    Variables are not included in the flatterm representation, only wildcards remain.

    >>> FlatTerm(x_)
    [_]

    Consecutive wildcards are merged, as the :class:`DiscriminationNet` cannot handle multiple consecutive sequence
    wildcards:

    >>> FlatTerm(f(_, _))
    [f, _[2], )]
    >>> FlatTerm(f(_, __, __))
    [f, _[3+], )]

    Furthermore, every :class:`SymbolWildcard` is replaced by its :attr:`~SymbolWildcard.symbol_type`:

    >>> class SpecialSymbol(Symbol):
    ...     pass
    >>> FlatTerm(Wildcard.symbol(SpecialSymbol)) == [SpecialSymbol]
    True

    Symbol wildcards are also not merged like regular wildcards, because they can never be sequence wildcards.
    """

    def __init__(self, expression: Expression) -> None:
        super().__init__(FlatTerm._combined_wildcards_iter(FlatTerm._flatterm_iter(expression)))

    @staticmethod
    def _flatterm_iter(expression: Expression) -> Iterator[TermAtom]:
        """Generator that yields the atoms of the expressions in prefix notation with operation end markers."""
        if isinstance(expression, Variable):
            yield from FlatTerm._flatterm_iter(expression.expression)
        elif isinstance(expression, Operation):
            yield type(expression)
            for operand in expression.operands:
                yield from FlatTerm._flatterm_iter(operand)
            yield OPERATION_END
        elif isinstance(expression, SymbolWildcard):
            yield expression.symbol_type
        elif isinstance(expression, Atom):
            yield expression
        else:
            raise TypeError()

    @staticmethod
    def _combined_wildcards_iter(flatterm: Iterator[TermAtom]) -> Iterator[TermAtom]:
        """Combine consecutive wildcards in a flatterm into a single one."""
        last_wildcard = None  # type: Optional[Wildcard]
        for term in flatterm:
            if isinstance(term, Wildcard) and not isinstance(term, SymbolWildcard):
                if last_wildcard is not None:
                    new_min_count = last_wildcard.min_count + term.min_count
                    new_fixed_size = last_wildcard.fixed_size and term.fixed_size
                    last_wildcard = Wildcard(new_min_count, new_fixed_size)
                else:
                    last_wildcard = term
            else:
                if last_wildcard is not None:
                    yield last_wildcard
                    last_wildcard = None
                yield term
        if last_wildcard is not None:
            yield last_wildcard

    def __str__(self):
        return ' '.join(map(self._term_str, self))

    def __repr__(self):
        return '[%s]' % ', '.join(map(str, self))


def _term_str(term: TermAtom) -> str:  # pragma: no cover
    """Return a string representation of a term atom."""
    if is_operation(term):
        return term.name + '('
    elif is_symbol_wildcard(term):
        return '*%s' % term.__name__
    elif isinstance(term, Wildcard):
        return '*%s%s' % (term.min_count, (not term.fixed_size) and '+' or '')
    elif term == Wildcard:
        return '*'
    else:
        return str(term)


class _State(Dict[TermAtom, Union['_State', List[Expression]]]):
    """An DFA state used by the :class:`DiscriminationNet`.

    This is a dict of transitions mapping terms of a :class:`FlatTerm` to new states.
    Each state has a unique :attr:`id`.

    A transition can also go to a terminal state that is a list of patterns.
    """

    _id = 1

    def __init__(self) -> None:
        super().__init__(self)
        self.id = _State._id
        _State._id += 1

    def _target_str(self, value: Union['_State', List[Expression]]) -> str:  # pragma: no cover
        """Return a string representation of a transition target."""
        if value is self:
            return 'self'
        elif isinstance(value, list):
            return '[%s]' % ', '.join(map(str, value))
        else:
            return str(value)

    @recursive_repr()
    def __repr__(self):
        return '{STATE %s}' % ', '.join('%s:%s' % (_term_str(term), self._target_str(target))
                                            for term, target in self.items())


class _WildcardState:
    """Internal representation of the wildcard state at the current nesting level used by :class:`DiscriminationNet`.

    This state is needed because unless a sequence wildcard is the last operand of an operation, fallback edges are
    required.

    Consider the pattern ``f(___, a, b)``: In order to match for example ``f(a, c, a, b)``, the automaton for
    the pattern needs an edge to fall back to the sequence wildcard after reading the first ``a``, because the ``b`` is
    missing.

    The same applies when trying to match ``f(a, a, b)`` or ``f(a, b, a, b)``, but the position to fall back to is
    different. Hence, not only the :attr:`last_wildcard` is saved in the state, but also the :attr:`symbol_after` it.
    Also, :attr:`all_same` tracks whether all symbols of the pattern so far have been the same, so backtracking only
    jumps back to the most recent state. This is needed for patterns like ``f(___, a, a)`` and subjects like
    ``f(a, a, a)``.

    Things get more complicated, when nested operations are combined with sequence wildcards. For these, a failure state
    is generated and saved in :attr:`fail_state`. This state allows backtracking after a failed match in a nested
    operation.

    Consider the pattern ``f(___, g(a))`` and the subject ``f(g(b), g(a))`` which match. The automaton greedily
    steps into the nested operation ``g(b)`` instead of jumping over it with the wildcard. But after encountering the
    ``b``, it needs to backtrack to the wildcard and start looking for ``g(a)`` again. The failure state allows
    finishing to read the ``g(b)`` and start over.
    """

    def __init__(self):
        self.last_wildcard = None
        """Last unbounded wildcard at the current level of operation nesting (if any)"""

        self.fail_state = None
        """The failure state for the current level of operation nesting"""


class _StateQueueItem(object):
    """Internal data structure used by the product net algorithm.

    It contains a pair of states from each source net (:attr:`state1` and :attr:`state2`), their :attr:`ids <State.id>`
    or ``0`` if the state is ``None`` (:attr:`id1` and :attr:`id2`).

    It also keeps track of the operation nesting :attr:`depth` of the states. A state is
    uniquely identified by its state pair and depth. This is needed to combine patterns with
    varying nesting depths to distinguish between states that have the same states but different depth. While one of the
    original automatons uses a wildcard transition and the other an operation opening transition, the whole nested
    operation has to be processed.
    To track whether this process is complete, the :attr:`depth` is used.

    In addition, :attr:`fixed` tracks which of the two automata is using the wildcard transition. If it is set to ``1``,
    the first automaton is using it. If set to ``2``,  the second automaton is using it. Otherwise it will be set to
    ``0``. :attr:`fixed` can only be non-zero if the depth is greater than zero.
    """
    def __init__(self, state1: _State, state2: _State) -> None:
        self.state1 = state1
        self.state2 = state2
        try:
            self.id1 = state1.id
        except AttributeError:
            self.id1 = 0
        try:
            self.id2 = state2.id
        except AttributeError:
            self.id2 = 0
        self.depth = 0
        self.fixed = 0

    @property
    def labels(self) -> Set[TermAtom]:
        """Return the set of transition labels to examine for this queue state.

        This is the union of the transition label sets for both states.
        However, if one of the states is fixed, it is excluded from this union and a wildcard transition is included
        instead. Also, when already in a failed state (one of the states is ``None``), the :const:`OPERATION_END` is
        also included.
        """
        labels = set()
        if self.state1 is not None and self.fixed != 1:
            labels.update(self.state1.keys())
        if self.state2 is not None and self.fixed != 2:
            labels.update(self.state2.keys())
        if self.fixed != 0:
            if self.fixed == 1 and self.state2 is None:
                labels.add(OPERATION_END)
            elif self.fixed == 2 and self.state1 is None:
                labels.add(OPERATION_END)
            labels.add(Wildcard)
        return labels

    def __repr__(self):
        return 'NQI(%r, %r, %r, %r, %r, %r)' % (self.id1, self.id2, self.depth, self.fixed, self.state1, self.state2)


class DiscriminationNet(object):
    """An automaton to distinguish which patterns match a given expression.

    This is a DFA with an implicit fail state whenever a transition is not actually defined.
    For every pattern added, an automaton is created and then the product automaton with the existing one is used as
    the new automaton.

    The matching assumes that patterns are linear, i.e. it will treat all variables as non-existent and only consider
    the wildcards.
    """

    def __init__(self):
        self._root = _State()

    def add(self, pattern: Expression):
        """TODO"""
        if pattern.is_syntactic:
            net = self._generate_syntactic_net(pattern)
        else:
            net = self._generate_net(pattern)

        if self._root:
            self._root = self._product_net(self._root, net)
        else:
            self._root = net

    @classmethod
    def _generate_syntactic_net(cls, pattern: Expression) -> _State:
        assert pattern.is_syntactic

        root = state = _State()
        flatterm = FlatTerm(pattern)

        for term in flatterm[:-1]:
            if isinstance(term, Wildcard):
                # Generate a chain of #min_count Wildcard edges
                for _ in range(term.min_count):
                    state[Wildcard] = _State()
                    state = state[Wildcard]
            else:
                state[term] = _State()
                state = state[term]

        last_term = flatterm[-1] if not isinstance(flatterm[-1], Wildcard) else Wildcard
        state[last_term] = [pattern]

        return root

    @classmethod
    def _generate_net(cls, pattern: Expression) -> _State:
        """Generates a DFA matching the given pattern."""
        # Capture the last unbounded wildcard for every level of operation nesting on a stack
        # Used to add backtracking edges in case the "match" fails later
        wildcard_states = [_WildcardState()]
        root = state = _State()
        flatterm = FlatTerm(pattern)
        states = {root.id: root}

        for term in flatterm[:-1]:
            wc_state = wildcard_states[-1]
            # For wildcards, generate a chain of #min_count Wildcard edges
            # If the wildcard is unbounded (fixed_size = False),
            # add a wildcard self loop at the end
            if isinstance(term, Wildcard):
                # Generate a chain of #min_count Wildcard edges
                for _ in range(term.min_count):
                    state[Wildcard] = _State()
                    state = state[Wildcard]
                    states[state.id] = state
                # If it is a sequence wildcard, add a self loop
                if not term.fixed_size:
                    state[Wildcard] = state
                    wc_state.last_wildcard = state
            else:
                state[term] = _State()
                state = state[term]
                states[state.id] = state
                if is_operation(term):
                    new_wc_state = _WildcardState()
                    if wc_state.last_wildcard or wc_state.fail_state:
                        new_wc_state.fail_state = fail_state = _State()
                        states[fail_state.id] = fail_state
                        fail_state[OPERATION_END] = wc_state.last_wildcard or wc_state.fail_state
                        fail_state[Wildcard] = fail_state
                    wildcard_states.append(new_wc_state)
                elif term == OPERATION_END:
                    wildcard_states.pop()
                wc_state = wildcard_states[-1]

            if wc_state.last_wildcard != state:
                if wc_state.last_wildcard:
                    state[EPSILON] = wc_state.last_wildcard
                elif wc_state.fail_state:
                    state[EPSILON] = wc_state.fail_state

        last_term = flatterm[-1] if not isinstance(flatterm[-1], Wildcard) else Wildcard
        state[last_term] = [pattern]

        return cls.determinize(root, states)

    @classmethod
    def determinize(cls, root, states):
        new_root = frozenset(cls.closure({root.id}, states))
        queue = [new_root]
        new_states = {new_root: _State()}

        while queue:
            state = queue.pop()
            keys = set().union(*(states[s].keys() for s in state))
            new_state = new_states[state]

            for k in keys:
                if k is EPSILON:
                    continue
                target = cls.goto(state, k, states)
                if isinstance(target, list):
                    new_state[k] = target
                else:
                    target = frozenset(target)
                    if not target in new_states:
                        new_states[target] = _State()
                        queue.append(target)

                    new_state[k] = new_states[target]

        return new_states[new_root]

    @staticmethod
    def closure(state, states):
        output = set(state)

        while True:
            to_add = set()
            for s in output:
                try:
                    new_state = states[s][EPSILON]
                    if new_state.id not in output:
                        to_add.add(new_state.id)
                except KeyError:
                    pass

            if to_add:
                output.update(to_add)
            else:
                break

        return output

    @classmethod
    def goto(cls, state, label, states):
        output = set()

        for s in state:
            if label in states[s]:
                if isinstance(states[s][label], list):
                    return states[s][label]
                output.add(states[s][label].id)
            if isinstance(label, Symbol):
                type_label = _get_symbol_wildcard_label(states[s], type(label))
                if type_label in states[s]:
                    if isinstance(states[s][type_label], list):
                        return states[s][type_label]
                    output.add(states[s][type_label].id)
            if Wildcard in states[s] and not is_operation(label) and label != OPERATION_END:
                if isinstance(states[s][Wildcard], list):
                    return states[s][Wildcard]
                output.add(states[s][Wildcard].id)

        return cls.closure(output, states)

    @staticmethod
    def _get_next_state(state: _State, label: TermAtom, fixed: bool) -> Tuple[_State, bool]:
        if fixed:
            return state, False
        if state is not None:
            try:
                try:
                    return state[label], False
                except KeyError:
                    if label != OPERATION_END:
                        if isinstance(label, Symbol):
                            symbol_wildcard_key = _get_symbol_wildcard_label(state, label)
                            if symbol_wildcard_key is not None:
                                return state[_get_symbol_wildcard_label(state, label)], False
                        return state[Wildcard], True
            except KeyError:
                pass
        return None, False

    @classmethod
    def _product_net(cls, state1, state2):
        root = _State()
        states = {(state1.id, state2.id, 0): root}
        queue = [_StateQueueItem(state1, state2)]

        while len(queue) > 0:
            current_state = queue.pop(0)
            state = states[(current_state.id1, current_state.id2, current_state.depth)]

            for label in list(current_state.labels):
                t1, with_wildcard1 = cls._get_next_state(current_state.state1, label, current_state.fixed == 1)
                t2, with_wildcard2 = cls._get_next_state(current_state.state2, label, current_state.fixed == 2)

                child_state = _StateQueueItem(t1, t2)
                child_state.depth = current_state.depth
                child_state.fixed = current_state.fixed

                if is_operation(label):
                    if current_state.fixed:
                        child_state.depth += 1
                    elif with_wildcard1:
                        child_state.fixed = 1
                        child_state.depth = 1
                        child_state.state1 = current_state.state1
                        child_state.id1 = current_state.id1
                    elif with_wildcard2:
                        child_state.fixed = 2
                        child_state.depth = 1
                        child_state.state2 = current_state.state2
                        child_state.id2 = current_state.id2
                elif label == OPERATION_END and current_state.fixed:
                    child_state.depth -= 1

                    if child_state.depth == 0:
                        if child_state.fixed == 1:
                            child_state.state1 = child_state.state1[Wildcard]
                            try:
                                child_state.id1 = child_state.state1.id
                            except AttributeError:
                                child_state.id1 = 0
                        elif child_state.fixed == 2:
                            child_state.state2 = child_state.state2[Wildcard]
                            try:
                                child_state.id2 = child_state.state2.id
                            except AttributeError:
                                child_state.id2 = 0
                        else:
                            raise AssertionError  # unreachable
                        child_state.fixed = 0

                if child_state.id1 != 0 or child_state.id2 != 0:
                    if (child_state.id1, child_state.id2, child_state.depth) not in states:
                        states[(child_state.id1, child_state.id2, child_state.depth)] = _State()
                        queue.append(child_state)

                    state[label] = states[(child_state.id1, child_state.id2, child_state.depth)]
                else:
                    if isinstance(child_state.state1, list) and isinstance(child_state.state2, list):
                        state[label] = child_state.state1 + child_state.state2
                    elif isinstance(child_state.state1, list):
                        state[label] = child_state.state1
                    elif isinstance(child_state.state2, list):
                        state[label] = child_state.state2

        return root

    def match(self, expression: Expression) -> List[Expression]:
        flatterm = FlatTerm(expression) if isinstance(expression, Expression) else expression
        state = self._root
        depth = 0
        for term in flatterm:
            if depth > 0:
                if is_operation(term):
                    depth += 1
                elif term == OPERATION_END:
                    depth -= 1
            else:
                try:
                    try:
                        state = state[term]
                    except KeyError:
                        if is_operation(term):
                            depth = 1
                            state = state[Wildcard]
                        elif term == OPERATION_END:
                            return []
                        elif isinstance(term, Symbol):
                            symbol_wildcard_key = _get_symbol_wildcard_label(state, term)
                            state = state[symbol_wildcard_key or Wildcard]
                        else:
                            raise TypeError('Expression contains non-terminal atom: %s' % expression)
                except KeyError:
                    return []

                if not isinstance(state, _State):
                    return state

        # Unreachable code: Unless the automaton got manually screwed up, it should be balanced in terms of opening and
        # closing symbols. Reading the expression with such an automaton will always hit a terminal node at the latest
        # after reading the last symbol in the expression term, so the loop will never finish normally.
        raise AssertionError

    def as_graph(self):  # pragma: no cover
        dot = Digraph()

        nodes = set()
        queue = [self._root]
        while queue:
            state = queue.pop(0)
            nodes.add(state.id)
            dot.node('n%s' % state.id, '', {'shape': 'point'})

            for next_state in state.values():
                if isinstance(next_state, _State):
                    if next_state.id not in nodes:
                        queue.append(next_state)
                else:
                    l = '\n'.join(str(x) for x in next_state)
                    dot.node('l%s' % id(next_state), l, {'shape': 'plaintext'})

        nodes = set()
        queue = [self._root]
        while queue:
            state = queue.pop(0)
            if state.id in nodes:
                continue
            nodes.add(state.id)

            for (label, other) in state.items():
                if isinstance(other, _State):
                    dot.edge('n%s' % state.id, 'n%s' % other.id, _term_str(label))
                    if other.id not in nodes:
                        queue.append(other)
                else:
                    dot.edge('n%s' % state.id, 'l%s' % id(other), _term_str(label))

        return dot

if __name__ == '__main__':
    import doctest

    f = Operation.new('f', Arity.variadic)
    a = Symbol('a')
    b = Symbol('b')
    c = Symbol('c')
    x_ = Variable.dot('x')
    _ = Wildcard.dot()
    __ = Wildcard.plus()
    ___ = Wildcard.star()

    pattern = freeze(f(___, a, _, _))

    net = DiscriminationNet()
    net.add(pattern)
    net.as_graph().render('tmp/%s' % pattern)

    doctest.testmod(exclude_empty=True)
