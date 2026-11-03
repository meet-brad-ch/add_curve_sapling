# SPDX-License-Identifier: GPL-3.0-or-later

"""A stand-in for Blender's UILayout that records what a page draws."""

from types import SimpleNamespace


class RecordingLayout:
    """Stands in for bpy.types.UILayout: records the properties, buttons and labels drawn, in order."""

    def __init__(self):
        """Start with no properties, buttons or labels."""
        self.props = []
        self.buttons = []
        self.labels = []

    def prop(self, props, name, **options):
        """Record the property's name."""
        self.props.append(name)

    def prop_search(self, props, name, search_data, search_property, **options):
        """Record the property's name."""
        self.props.append(name)

    def operator(self, idname, **options):
        """Record a button with the operator's idname and options, and return it."""
        button = SimpleNamespace(idname=idname, **options)
        self.buttons.append(button)
        return button

    def label(self, text="", **options):
        """Record the label's text."""
        self.labels.append(text)

    def separator(self):
        """Record nothing: a separator draws no property, button or label."""
        pass

    def row(self):
        """This layout, for the drawing in the row."""
        return self

    def column(self):
        """This layout, for the drawing in the column."""
        return self

    def box(self):
        """This layout, for the drawing in the box."""
        return self

    def split(self):
        """This layout, for the drawing in the split."""
        return self
