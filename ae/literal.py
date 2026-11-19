"""
literal type detection and evaluation api
=========================================
"""
import datetime
from collections.abc import Callable
from typing import Any

from ae.base import DEF_ENCODE_ERRORS, UNSET, parse_date                                                # type: ignore
from ae.dynamicod import try_call, try_eval, try_exec                                                   # type: ignore


__version__ = '0.4.36'


_BEG_CHARS = "([{'\""
_END_CHARS = ")]}'\""


def _evaluable_literal(literal: str) -> tuple[Callable | None, str | None]:
    """ check evaluable format of literal string, possibly return appropriate evaluation function and stripped literal.

    :param literal:     string to be checked if it is parsable (matches a
                        :ref:`evaluable literal format <evaluable-literal-formats>`), and if
                        it has to be stripped.
    :return:            tuple of evaluation/conversion function and the (optionally stripped) literal
                        string (removed triple high-commas on expression/code-blocks) - if
                        :paramref:`~_evaluable_literal.literal` is in one of the supported
                        :ref:`evaluable literal formats <evaluable-literal-formats>` - else the tuple
                        (`None`, <empty string>).
    """
    func = None
    stripped = ''
    if (literal.startswith("'''") and literal.endswith("'''")) \
            or (literal.startswith('"""') and literal.endswith('"""')):
        func = try_exec
        stripped = literal[3:-3]                                    # code block
    elif literal and literal[0] in _BEG_CHARS and _BEG_CHARS.find(literal[0]) == _END_CHARS.find(literal[-1]):
        func = try_eval
        stripped = literal                                          # expression/list/dict/tuple/str/... literal
    elif literal in ('False', 'True'):
        func = bool                                                 # bool literal
        if literal == 'True':
            stripped = literal                                      # else return empty string to get bool('') == False
    else:
        try:
            int(literal)
            func = int
            stripped = literal                                      # int literal
        except ValueError:
            try:
                float(literal)
                func = float
                stripped = literal                                  # float literal
            except ValueError:
                pass

    return func, stripped


class Literal:
    """ convert literal string into the corresponding value (and type). """
    def __init__(self, literal_or_value: Any | None = None, value_type: type | None = None, name: str = 'LiT'):
        """ create new Literal instance.

        :param literal_or_value:    initial literal string or a literal value to be checked.
        :param value_type:          type of the value of this instance (def=determined latest by/in the
                                    :attr:`~Literal.value` property getter).
        :param name:                name of the literal (only used for logging and debugging).
        """
        self._name = name
        self._literal_or_value = None
        self._type = None if isinstance(value_type, type(None)) else value_type
        if literal_or_value is not None:
            self.value = literal_or_value

    def __repr__(self):
        return f"Literal({self._literal_or_value!r})"

    @property
    def value(self) -> Any:
        """ property representing the value of a literal.

        :getter:    return the literal value; on the first call the literal will be evaluated
                    (lazy/late) and the value type will be set if still unspecified. further
                    getter calls will directly return the already converted literal value.
        :setter:    assign literal or a new value; can be either a value literal string or directly
                    the represented/resulting value. if the assigned value is not a string
                    and the value type of this instance got still unspecified then this instance
                    will be restricted to the type of the assigned value. assigning a `None` value
                    will be ignored - neither the literal nor the value will change with that!
                    literals of type `bytes` get automatically decoded/converted into a `str` type, if
                    :paramref:`~ae.literal.Literal.value_type` got not explicitly specified as `bytes`.
        :raises:    `ValueError` if the literal cannot be converted or its value type cannot be recognized.
       """
        check_val = self._literal_or_value
        msg = f"Literal {self._name} with value {check_val!r} "
        if isinstance(check_val, str) or self.type_mismatching_with(check_val):
            try:            # first or new late real value conversion/initialization
                check_val = self._determine_value(check_val)
            except Exception as ex:
                raise ValueError(msg + f"throw exception: {ex}") from ex

        self._chk_val_reset_else_set_type(check_val)
        if check_val is not None:
            if self._type and self.type_mismatching_with(check_val):
                raise ValueError(msg + f"type mismatch: {self._type} != {type(check_val)}")
            self._literal_or_value = check_val

        return self._literal_or_value

    @value.setter
    def value(self, lit_or_val: Any):
        if lit_or_val is not None:
            if isinstance(lit_or_val, bytes) and self._type != bytes:       # if not restricted to bytes
                lit_or_val = lit_or_val.decode(errors=DEF_ENCODE_ERRORS)    # convert bytes to 'utf-8'-encoded string
            self._literal_or_value = lit_or_val     # late evaluation: real value will be checked/converted by getter
            if not self._type and not isinstance(lit_or_val, str):          # set type if UNSET and no eval
                self._type = type(lit_or_val)

    def append_value(self, item_value: Any) -> Any:
        """ add new item to the list value of this Literal instance (lazy `self.value` getter call function pointer).

        :param item_value:  value of the item to be appended to the value of this Literal instance.
        :return:            the value (==list) of this Literal instance.
        """
        self.value.append(item_value)
        return self.value

    def convert_value(self, lit_or_val: Any) -> Any:
        """ set/change the literal/value of this :class:`Literal` instance and return the represented value.

        :param lit_or_val:  the new value to be set.
        :return:            the final/converted value of this Literal instance.
        """
        self.value = lit_or_val
        return self.value

    def type_mismatching_with(self, value: Any) -> bool:
        """ check if this literal instance would reject the passed value because of type mismatch.

        :param value:       new literal value.
        :return:            `True` if the passed value would have a type mismatch or if literal type is still not set,
                            else `False`.
        """
        return self._type != type(value)

    def _determine_value(self, lit_or_val: Any) -> Any:
        """ check passed value if it is still a literal determine the represented value.

        :param lit_or_val:  new literal value or the representing literal string.
        :return:            determined/converted value or self._lit_or_val if value could not be recognized/converted.
        """
        if isinstance(lit_or_val, str):
            func, eval_expr = _evaluable_literal(lit_or_val)
            if func:
                lit_or_val = self._chk_val_reset_else_set_type(func(eval_expr))

        if self._type:
            if self.type_mismatching_with(lit_or_val) and isinstance(lit_or_val, str):
                if self._type == bool:
                    lit_or_val = bool(try_eval(lit_or_val))
                elif self._type in (datetime.date, datetime.datetime):
                    lit_or_val = parse_date(lit_or_val, ret_date=self._type == datetime.date)
                lit_or_val = self._chk_val_reset_else_set_type(lit_or_val)

            if self.type_mismatching_with(lit_or_val):          # finally try type conversion with type constructor
                lit_or_val = self._chk_val_reset_else_set_type(
                    try_call(self._type, lit_or_val, ignored_exceptions=(TypeError,)))  # ignore int(None) exception

        return lit_or_val

    def _chk_val_reset_else_set_type(self, value: Any) -> Any:
        """ set value type if not set from the :paramref:`.value` argument, if it is not `None`/:data:`~ae.base.UNSET`.

        :param value:       converted new literal/converted value to be reset to.
        :return:            specified :paramref:`.value` or the literal/value specified on instantiation if
                            :paramref:`.value` is `None` or :data:`~ae.base.UNSET`.
        """
        if value is None or value is UNSET:
            value = self._literal_or_value  # literal evaluation failed, therefore reset to try with type conversion
        elif not self._type and value is not None and value is not UNSET:
            self._type = type(value)
        return value
