# SPDX-License-Identifier: GPL-3.0-or-later

"""The backend's front door for the user interface: every decision the UI needs, testable without the UI.

source/ui/ imports only this package and source/settings.py (an architecture test checks it).
"""
