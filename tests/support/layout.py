# SPDX-License-Identifier: GPL-3.0-or-later

"""A stand-in for Blender's UILayout that records what a page draws."""

from types import SimpleNamespace


class RecordingLayout:
    """Stands in for bpy.types.UILayout: records the properties, buttons and labels drawn, in order."""

    def __init__(self):
        self.props = []
        self.buttons = []
        self.labels = []

    def prop(self, props, name, **options):
        self.props.append(name)

    def prop_search(self, props, name, search_data, search_property, **options):
        self.props.append(name)

    def operator(self, idname, **options):
        button = SimpleNamespace(idname=idname, **options)
        self.buttons.append(button)
        return button

    def label(self, text="", **options):
        self.labels.append(text)

    def separator(self):
        pass

    def row(self):
        return self

    def column(self):
        return self

    def box(self):
        return self

    def split(self):
        return self
