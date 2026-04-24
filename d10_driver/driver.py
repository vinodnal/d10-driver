"""
D10 Driver — main orchestrator.

This module wires together all sub-systems (communication, protocol, parsing,
and persistence) into a single :class:`D10Driver` class.  It is the central
component that application code and the CLI interact with.

Typical workflow
----------------
1. Instantiate :class:`D10Driver` with a configured transport and repository.
2. Call :meth:`D10Driver.start` to begin listening for instrument messages.
3. Each received message is parsed and (if ``auto_commit`` is enabled)
   persisted to the database automatically.
4. Call :meth:`D10Driver.stop` (or use the context manager) to shut down
   cleanly.

Extensibility
-------------
The driver accepts any :class:`~d10_driver.communication.base_protocol.BaseProtocol`
transport and any :class:`~d10_driver.database.base_repository.BaseRepository`
back-end, so it can drive different instruments and store data in different
databases without modification.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from d10_driver.communication.base_protocol import BaseProtocol
from d10_driver.config.settings import DriverConfig, get_settings
from d10_driver.database.base_repository import BaseRepository
from d10_driver.logging_utils.logger import get_logger
from d10_driver.models.message import ASTMMessage
from d10_driver.parsers.base_parser import BaseParser
from d10_driver.parsers.d10_parser import D10Parser
from d10_driver.protocol.astm_reader import ASTMReader

log = get_logger(__name__)

#: Callback type called after each successfully parsed message.
MessageCallback = Callable[[ASTMMessage], None]


class D10Driver:
    """Main orchestrator for the Bio-Rad D-10 (and compatible) instrument driver.

    Parameters
    ----------
    transport:
        An open-able byte-stream transport (serial or TCP).
    repository:
        Persistence back-end.  If ``None``, results are not stored.
    parser:
        ASTM message parser.  Defaults to :class:`~d10_driver.parsers.d10_parser.D10Parser`.
    config:
        Driver behaviour settings.  Defaults to the global settings singleton.
    on_message:
        Optional callback invoked with each parsed :class:`~d10_driver.models.message.ASTMMessage`
        in addition to (or instead of) database persistence.
    """

    def __init__(
        self,
        transport: BaseProtocol,
        *,
        repository: Optional[BaseRepository] = None,
        parser: Optional[BaseParser] = None,
        config: Optional[DriverConfig] = None,
        on_message: Optional[MessageCallback] = None,
    ) -> None:
        self._transport = transport
        self._repository = repository
        self._parser: BaseParser = parser or D10Parser()
        self._config: DriverConfig = config or get_settings().driver
        self._on_message = on_message

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._message_count = 0
        self._error_count = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, *, blocking: bool = True) -> None:
        """Start the driver.

        Parameters
        ----------
        blocking:
            If ``True`` (default), runs the receive loop in the calling
            thread, blocking until :meth:`stop` is called (e.g. via a
            signal handler).  If ``False``, the loop runs in a daemon thread
            and this method returns immediately.
        """
        log.info(
            "Starting D10 driver — instrument_id=%s transport=%s",
            self._config.instrument_id,
            self._transport.name,
        )
        self._running = True

        if self._repository:
            log.info("Connecting to database…")
            self._repository.connect()
            self._repository.create_schema()

        self._transport.open()

        if blocking:
            self._receive_loop()
        else:
            self._thread = threading.Thread(
                target=self._receive_loop,
                name="d10-driver-receiver",
                daemon=True,
            )
            self._thread.start()
            log.info("Receiver thread started (non-blocking).")

    def stop(self) -> None:
        """Signal the driver to stop gracefully."""
        log.info("Stopping D10 driver…")
        self._running = False
        self._transport.close()
        if self._repository:
            self._repository.disconnect()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        log.info(
            "Driver stopped — messages processed: %d, errors: %d",
            self._message_count,
            self._error_count,
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "D10Driver":
        self.start(blocking=False)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.stop()
        return False

    # ------------------------------------------------------------------
    # Core receive loop
    # ------------------------------------------------------------------

    def _receive_loop(self) -> None:
        """Main event loop — waits for and processes ASTM messages."""
        reader = ASTMReader(
            self._transport,
            max_retries=self._config.retry_attempts,
            ack_timeout=self._config.ack_timeout,
        )

        log.info("Receive loop started — waiting for instrument messages…")

        while self._running:
            try:
                records = list(reader.receive_message())
                if not records:
                    log.debug("Empty message received — ignoring.")
                    continue

                message = self._parser.parse_message(records)
                self._message_count += 1
                log.info(
                    "Message #%d received:\n%s",
                    self._message_count,
                    message.summary(),
                )

                # Invoke user callback (if any)
                if self._on_message:
                    try:
                        self._on_message(message)
                    except Exception:
                        log.exception("Exception in on_message callback.")

                # Persist to database
                if self._repository and self._config.auto_commit:
                    self._persist(message)

            except TimeoutError as exc:
                # Normal when the instrument is idle
                log.debug("Timeout waiting for message: %s", exc)
                time.sleep(0.1)

            except ValueError as exc:
                self._error_count += 1
                log.error("Protocol error: %s", exc)
                time.sleep(self._config.retry_delay)

            except Exception:
                self._error_count += 1
                log.exception("Unexpected error in receive loop.")
                time.sleep(self._config.retry_delay)

    def _persist(self, message: ASTMMessage) -> None:
        """Attempt to persist *message* to the database, with retry logic."""
        for attempt in range(1, self._config.retry_attempts + 1):
            try:
                msg_id = self._repository.save_message(message)  # type: ignore[union-attr]
                log.info("Message committed to database — id=%d", msg_id)
                return
            except Exception:
                log.exception(
                    "Database save failed (attempt %d/%d).",
                    attempt,
                    self._config.retry_attempts,
                )
                time.sleep(self._config.retry_delay)

        log.error(
            "Failed to persist message after %d attempts.",
            self._config.retry_attempts,
        )
        self._error_count += 1

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def message_count(self) -> int:
        """Total number of messages successfully parsed since driver start."""
        return self._message_count

    @property
    def error_count(self) -> int:
        """Total number of errors since driver start."""
        return self._error_count

    @property
    def is_running(self) -> bool:
        """``True`` if the driver receive loop is active."""
        return self._running
