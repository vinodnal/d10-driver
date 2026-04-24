"""
D10 Driver — Top-level package.

This package provides a complete driver for the Bio-Rad D-10 hemoglobin
analyzer (and other ASTM-compatible laboratory instruments).

Modules
-------
config          Configuration management.
communication   Low-level transport layer (serial, TCP).
protocol        ASTM E1381 framing and ASTM E1394 record handling.
parsers         High-level message and record parsers.
models          Domain data models (Patient, Order, Result, Message).
database        Persistence layer (abstract base + MySQL implementation).
logging_utils   Centralised logging configuration.
cli             Terminal / interactive management interface.
driver          Main orchestrator that wires all modules together.
"""

__version__ = "1.0.0"
__author__ = "D10 Driver Project"
