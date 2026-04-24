"""
Setup script for the D10 Biorad Driver package.

This package provides a modular driver to communicate with the Bio-Rad D-10
hemoglobin analyzer using the ASTM E1381/E1394 protocol, parse results,
and commit them to a MySQL database.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [
        line.strip()
        for line in fh
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="d10-driver",
    version="1.0.0",
    author="D10 Driver Project",
    description=(
        "Modular driver for the Bio-Rad D-10 hemoglobin analyzer "
        "using ASTM E1381/E1394 protocol."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "d10-driver=d10_driver.main:cli",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX :: Linux",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
        "License :: OSI Approved :: MIT License",
    ],
)
