"""
Abstract base class for ASTM message parsers.

All instrument-specific parsers must subclass :class:`BaseParser` and
implement :meth:`parse_message`.  This ensures any instrument driver
built on this framework follows the same interface, and switching between
parsers (e.g. from D-10 to another HPLC analyser) requires only swapping
the parser implementation without touching the communication or database
layers.
"""

from __future__ import annotations

import abc
from typing import Iterable

from d10_driver.logging_utils.logger import get_logger
from d10_driver.models.message import ASTMMessage

log = get_logger(__name__)


class BaseParser(abc.ABC):
    """Abstract ASTM E1394 message parser.

    Subclasses must implement :meth:`parse_message` to convert a sequence of
    raw ASTM record strings into a populated :class:`~d10_driver.models.message.ASTMMessage`.
    """

    @abc.abstractmethod
    def parse_message(self, records: Iterable[str]) -> ASTMMessage:
        """Parse an iterable of raw ASTM record strings into a domain model.

        Parameters
        ----------
        records:
            Iterable of stripped ASCII strings, each representing one ASTM
            E1394 logical record (e.g. ``"H|\\^&|||D-10||20240101120000"``).

        Returns
        -------
        ASTMMessage
            Fully populated message model.
        """

    def parse_field(self, record: str, index: int, delimiter: str = "|") -> str:
        """Safely extract the field at *index* from a ``|``-delimited record.

        Parameters
        ----------
        record:
            Raw ASTM record string.
        index:
            Zero-based field index.
        delimiter:
            Field separator (default ``"|"``).

        Returns
        -------
        str
            The field value, or an empty string if the index is out of range.
        """
        fields = record.split(delimiter)
        if index < len(fields):
            return fields[index]
        return ""

    def parse_component(self, field: str, index: int, delimiter: str = "^") -> str:
        """Safely extract a component from a ``^``-delimited compound field.

        Parameters
        ----------
        field:
            The compound field string.
        index:
            Zero-based component index.
        delimiter:
            Component separator (default ``"^"``).

        Returns
        -------
        str
            The component value, or an empty string if out of range.
        """
        components = field.split(delimiter)
        if index < len(components):
            return components[index]
        return ""
