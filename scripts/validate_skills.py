#!/usr/bin/env python3
"""Validate registry entries and every published skill."""

from __future__ import print_function

import sys

from skillhub import validate_catalog


def main():
    errors, warnings, components, records = validate_catalog()
    for warning in warnings:
        print("WARNING: {}".format(warning))
    for error in errors:
        print("ERROR: {}".format(error))
    if errors:
        print("Validation failed with {} error(s).".format(len(errors)))
        return 1
    print("Validated {} skill(s) across {} component(s).".format(len(records), len(components)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
