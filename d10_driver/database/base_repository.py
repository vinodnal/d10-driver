"""
Abstract database repository base class.

All database back-ends must subclass :class:`BaseRepository` and implement
the persistence interface defined here.  This decouples the rest of the
driver from any specific database technology, making it straightforward to
add support for PostgreSQL, SQLite, or a REST API without changing any
parsing or communication code.

Usage
-----
::

    class MyRepository(BaseRepository):
        def save_message(self, message): …
        def find_results_by_specimen(self, specimen_id): …
        …
"""

from __future__ import annotations

import abc
from typing import Optional

from d10_driver.logging_utils.logger import get_logger
from d10_driver.models.message import ASTMMessage, ResultRecord

log = get_logger(__name__)


class BaseRepository(abc.ABC):
    """Abstract persistence layer for ASTM messages and results.

    Concrete implementations must override every abstract method.  Shared
    lifecycle methods (:meth:`connect`, :meth:`disconnect`) are provided as
    abstract methods so each back-end can manage its own connection pool or
    session.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def connect(self) -> None:
        """Establish the database connection / acquire a pool connection."""

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Release the database connection / return it to the pool."""

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def save_message(self, message: ASTMMessage) -> int:
        """Persist a complete ASTM message and all its child records.

        Parameters
        ----------
        message:
            The fully parsed :class:`~d10_driver.models.message.ASTMMessage`.

        Returns
        -------
        int
            The auto-generated primary key of the saved message row.
        """

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def find_results_by_specimen(self, specimen_id: str) -> list[ResultRecord]:
        """Return all result records for *specimen_id*.

        Parameters
        ----------
        specimen_id:
            Practice-assigned specimen identifier.

        Returns
        -------
        list[ResultRecord]
            All result records associated with the specimen, or an empty list.
        """

    @abc.abstractmethod
    def find_messages_by_patient(self, patient_id: str) -> list[ASTMMessage]:
        """Return all messages for the given *patient_id*.

        Parameters
        ----------
        patient_id:
            Practice-assigned patient identifier.

        Returns
        -------
        list[ASTMMessage]
            Matching messages, or an empty list.
        """

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def create_schema(self) -> None:
        """Create the database schema (tables, indexes) if they do not exist.

        Implementations must be idempotent — calling this method on an already-
        initialised database must not raise an error or destroy data.
        """

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "BaseRepository":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.disconnect()
        return False
