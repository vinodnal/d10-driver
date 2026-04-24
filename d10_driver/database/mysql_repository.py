"""
MySQL database repository for the D10 driver.

This module provides :class:`MySQLRepository`, a concrete implementation of
:class:`~d10_driver.database.base_repository.BaseRepository` that persists
ASTM messages, patient records, orders, and results in a MySQL database using
the *mysql-connector-python* library.

Database schema
---------------
The schema consists of four normalised tables:

``d10_messages``
    One row per ASTM transmission (H/L record pair).

``d10_patients``
    One row per patient ``P`` record, linked to a message.

``d10_orders``
    One row per order ``O`` record, linked to a patient.

``d10_results``
    One row per result ``R`` record, linked to an order.

Usage
-----
::

    from d10_driver.database.mysql_repository import MySQLRepository

    repo = MySQLRepository(host="localhost", user="d10driver", password="…")
    with repo:
        repo.create_schema()
        message_id = repo.save_message(message)
"""

from __future__ import annotations

from typing import Optional

from d10_driver.database.base_repository import BaseRepository
from d10_driver.logging_utils.logger import get_logger
from d10_driver.models.message import ASTMMessage, OrderRecord, PatientRecord, ResultRecord

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# DDL statements
# ---------------------------------------------------------------------------

_DDL_MESSAGES = """
CREATE TABLE IF NOT EXISTS d10_messages (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    received_at         DATETIME        NOT NULL,
    sender_name         VARCHAR(64),
    processing_id       VARCHAR(8),
    version             VARCHAR(8),
    message_control_id  VARCHAR(64),
    completion_code     VARCHAR(4),
    instrument_id       VARCHAR(64),
    INDEX idx_received_at (received_at),
    INDEX idx_sender     (sender_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

_DDL_PATIENTS = """
CREATE TABLE IF NOT EXISTS d10_patients (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    message_id              INT NOT NULL,
    sequence_number         INT,
    practice_patient_id     VARCHAR(64),
    laboratory_patient_id   VARCHAR(64),
    patient_name            VARCHAR(128),
    birthdate               VARCHAR(16),
    sex                     VARCHAR(4),
    race                    VARCHAR(32),
    address                 VARCHAR(256),
    telephone               VARCHAR(32),
    attending_physician_id  VARCHAR(64),
    comment                 TEXT,
    FOREIGN KEY (message_id) REFERENCES d10_messages(id) ON DELETE CASCADE,
    INDEX idx_message_id       (message_id),
    INDEX idx_patient_id       (practice_patient_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

_DDL_ORDERS = """
CREATE TABLE IF NOT EXISTS d10_orders (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    message_id              INT NOT NULL,
    patient_id              INT,
    sequence_number         INT,
    specimen_id             VARCHAR(64),
    instrument_specimen_id  VARCHAR(64),
    universal_test_id       VARCHAR(128),
    priority                VARCHAR(8),
    requested_at            VARCHAR(16),
    collected_at            VARCHAR(16),
    action_code             VARCHAR(4),
    relevant_clinical_info  TEXT,
    specimen_received_at    VARCHAR(16),
    specimen_descriptor     VARCHAR(128),
    ordering_physician      VARCHAR(128),
    report_type             VARCHAR(4),
    FOREIGN KEY (message_id) REFERENCES d10_messages(id) ON DELETE CASCADE,
    INDEX idx_message_id  (message_id),
    INDEX idx_specimen_id (specimen_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

_DDL_RESULTS = """
CREATE TABLE IF NOT EXISTS d10_results (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    message_id              INT NOT NULL,
    order_id                INT,
    sequence_number         INT,
    universal_test_id       VARCHAR(128),
    analyte_name            VARCHAR(64),
    value                   VARCHAR(32),
    units                   VARCHAR(16),
    reference_ranges        VARCHAR(64),
    abnormal_flags          VARCHAR(8),
    result_status           VARCHAR(4),
    result_date             VARCHAR(16),
    instrument              VARCHAR(64),
    FOREIGN KEY (message_id) REFERENCES d10_messages(id) ON DELETE CASCADE,
    INDEX idx_message_id   (message_id),
    INDEX idx_analyte      (analyte_name),
    INDEX idx_result_date  (result_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


class MySQLRepository(BaseRepository):
    """MySQL persistence back-end for ASTM messages and D-10 results.

    Parameters
    ----------
    host:
        MySQL server hostname (default: ``"localhost"``).
    port:
        MySQL server port (default: 3306).
    user:
        Database username.
    password:
        Database password.
    database:
        Database / schema name (default: ``"d10_results"``).
    pool_size:
        Number of connections to keep in the pool (default: 5).
    instrument_id:
        An optional identifier for this instrument instance, stored with
        each message row for traceability.
    """

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 3306,
        user: str = "d10driver",
        password: str = "",
        database: str = "d10_results",
        pool_size: int = 5,
        instrument_id: str = "D10-001",
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._pool_size = pool_size
        self._instrument_id = instrument_id
        self._conn = None  # set in connect()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open a MySQL connection.

        Raises
        ------
        mysql.connector.Error
            On connection failure.
        """
        import mysql.connector  # imported lazily to keep startup fast

        log.info(
            "Connecting to MySQL — %s:%d/%s as %s",
            self._host, self._port, self._database, self._user,
        )
        self._conn = mysql.connector.connect(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            database=self._database,
            autocommit=False,
            connection_timeout=10,
        )
        log.info("MySQL connection established.")

    def disconnect(self) -> None:
        """Close the MySQL connection."""
        if self._conn and self._conn.is_connected():
            self._conn.close()
            log.info("MySQL connection closed.")
        self._conn = None

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def create_schema(self) -> None:
        """Create all required tables if they do not already exist.

        This method is idempotent — it is safe to call on an already-
        initialised database.
        """
        log.info("Ensuring database schema is up-to-date…")
        cursor = self._conn.cursor()
        try:
            for ddl in (_DDL_MESSAGES, _DDL_PATIENTS, _DDL_ORDERS, _DDL_RESULTS):
                cursor.execute(ddl)
            self._conn.commit()
            log.info("Schema created / verified successfully.")
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def save_message(self, message: ASTMMessage) -> int:
        """Persist *message* and all child records in a single transaction.

        Parameters
        ----------
        message:
            The fully parsed :class:`~d10_driver.models.message.ASTMMessage`.

        Returns
        -------
        int
            Auto-generated primary key of the ``d10_messages`` row.

        Raises
        ------
        mysql.connector.Error
            On any database error; the transaction is rolled back.
        """
        cursor = self._conn.cursor()
        try:
            # 1. Insert the message header
            message_id = self._insert_message(cursor, message)

            # 2. Insert patient records
            patient_db_ids: list[int] = []
            for patient in message.patients:
                pid = self._insert_patient(cursor, message_id, patient)
                patient_db_ids.append(pid)

            # 3. Insert order records (associate with first patient for now)
            order_db_ids: list[int] = []
            for order in message.orders:
                parent_pid = patient_db_ids[0] if patient_db_ids else None
                oid = self._insert_order(cursor, message_id, parent_pid, order)
                order_db_ids.append(oid)

            # 4. Insert result records
            for result in message.results:
                parent_oid = order_db_ids[0] if order_db_ids else None
                self._insert_result(cursor, message_id, parent_oid, result)

            self._conn.commit()
            log.info(
                "Message saved — id=%d patients=%d orders=%d results=%d",
                message_id,
                len(message.patients),
                len(message.orders),
                len(message.results),
            )
            return message_id

        except Exception:
            self._conn.rollback()
            log.exception("Failed to save message — transaction rolled back.")
            raise
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def find_results_by_specimen(self, specimen_id: str) -> list[ResultRecord]:
        """Return all result records linked to *specimen_id*.

        Parameters
        ----------
        specimen_id:
            Practice-assigned specimen identifier.

        Returns
        -------
        list[ResultRecord]
        """
        cursor = self._conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT r.*
                FROM d10_results r
                JOIN d10_orders o ON r.order_id = o.id
                WHERE o.specimen_id = %s
                ORDER BY r.id
                """,
                (specimen_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_result(row) for row in rows]
        finally:
            cursor.close()

    def find_messages_by_patient(self, patient_id: str) -> list[ASTMMessage]:
        """Return all messages linked to *patient_id*.

        Parameters
        ----------
        patient_id:
            Practice-assigned patient identifier.

        Returns
        -------
        list[ASTMMessage]
        """
        cursor = self._conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT DISTINCT m.*
                FROM d10_messages m
                JOIN d10_patients p ON p.message_id = m.id
                WHERE p.practice_patient_id = %s
                ORDER BY m.received_at DESC
                """,
                (patient_id,),
            )
            rows = cursor.fetchall()
            messages = []
            for row in rows:
                msg = ASTMMessage(
                    sender_name=row.get("sender_name"),
                    processing_id=row.get("processing_id"),
                    version=row.get("version"),
                    message_control_id=row.get("message_control_id"),
                    completion_code=row.get("completion_code"),
                )
                messages.append(msg)
            return messages
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Private insert helpers
    # ------------------------------------------------------------------

    def _insert_message(self, cursor, message: ASTMMessage) -> int:
        """Insert a ``d10_messages`` row and return its ID."""
        cursor.execute(
            """
            INSERT INTO d10_messages
                (received_at, sender_name, processing_id, version,
                 message_control_id, completion_code, instrument_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                message.received_at,
                message.sender_name,
                message.processing_id,
                message.version,
                message.message_control_id,
                message.completion_code,
                self._instrument_id,
            ),
        )
        return cursor.lastrowid

    def _insert_patient(
        self, cursor, message_id: int, patient: PatientRecord
    ) -> int:
        """Insert a ``d10_patients`` row and return its ID."""
        cursor.execute(
            """
            INSERT INTO d10_patients
                (message_id, sequence_number, practice_patient_id,
                 laboratory_patient_id, patient_name, birthdate, sex,
                 race, address, telephone, attending_physician_id, comment)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                message_id,
                patient.sequence_number,
                patient.practice_patient_id,
                patient.laboratory_patient_id,
                patient.patient_name,
                patient.birthdate,
                patient.sex,
                patient.race,
                patient.address,
                patient.telephone,
                patient.attending_physician_id,
                patient.comment,
            ),
        )
        return cursor.lastrowid

    def _insert_order(
        self, cursor, message_id: int, patient_id: Optional[int], order: OrderRecord
    ) -> int:
        """Insert a ``d10_orders`` row and return its ID."""
        cursor.execute(
            """
            INSERT INTO d10_orders
                (message_id, patient_id, sequence_number, specimen_id,
                 instrument_specimen_id, universal_test_id, priority,
                 requested_at, collected_at, action_code,
                 relevant_clinical_info, specimen_received_at,
                 specimen_descriptor, ordering_physician, report_type)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                message_id,
                patient_id,
                order.sequence_number,
                order.specimen_id,
                order.instrument_specimen_id,
                order.universal_test_id,
                order.priority,
                order.requested_at,
                order.collected_at,
                order.action_code,
                order.relevant_clinical_info,
                order.specimen_received_at,
                order.specimen_descriptor,
                order.ordering_physician,
                order.report_type,
            ),
        )
        return cursor.lastrowid

    def _insert_result(
        self, cursor, message_id: int, order_id: Optional[int], result: ResultRecord
    ) -> int:
        """Insert a ``d10_results`` row and return its ID."""
        cursor.execute(
            """
            INSERT INTO d10_results
                (message_id, order_id, sequence_number, universal_test_id,
                 analyte_name, value, units, reference_ranges,
                 abnormal_flags, result_status, result_date, instrument)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                message_id,
                order_id,
                result.sequence_number,
                result.universal_test_id,
                result.analyte_name,
                result.value,
                result.units,
                result.reference_ranges,
                result.abnormal_flags,
                result.result_status,
                result.result_date,
                result.instrument,
            ),
        )
        return cursor.lastrowid

    # ------------------------------------------------------------------
    # Row-to-model converters
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_result(row: dict) -> ResultRecord:
        """Convert a database ``d10_results`` row dict to a :class:`ResultRecord`."""
        return ResultRecord(
            sequence_number=row.get("sequence_number", 1),
            universal_test_id=row.get("universal_test_id"),
            value=row.get("value"),
            units=row.get("units"),
            reference_ranges=row.get("reference_ranges"),
            abnormal_flags=row.get("abnormal_flags"),
            result_status=row.get("result_status"),
            result_date=row.get("result_date"),
            instrument=row.get("instrument"),
        )
