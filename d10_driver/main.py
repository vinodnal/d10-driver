"""
Entry point for the D10 Driver command-line application.

This module allows the package to be invoked directly::

    python -m d10_driver [COMMAND] [OPTIONS]

It delegates to the Click CLI group defined in
:mod:`d10_driver.cli.terminal`.
"""

from d10_driver.cli.terminal import cli

if __name__ == "__main__":
    cli()
