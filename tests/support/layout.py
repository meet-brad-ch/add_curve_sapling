# SPDX-License-Identifier: GPL-3.0-or-later

"""A stand-in for Blender's UILayout that records what a page draws."""

from types import SimpleNamespace


class RecordingLayout:
    """Stands in for bpy.types.UILayout: records the properties, buttons and labels drawn, in order, and which
    property fields are drawn inactive. A row, column, box or split is a child layout with its own `active` flag that
    shares the parent's records, as a Blender sub-layout does."""

    def __init__(self, parent=None):
        """Start with no records, or share the records of `parent` (a sub-layout); active as Blender's default."""
        self.active = True
        if parent is None:
            self.props = []
            self.buttons = []
            self.labels = []
            self.inactive = []  # (property name, index or None) of each field drawn in an inactive layout
            self.parent_active = True
            return
        self.props = parent.props
        self.buttons = parent.buttons
        self.labels = parent.labels
        self.inactive = parent.inactive
        self.parent_active = parent.parent_active and parent.active

    def prop(self, props, name, **options):
        """Record the property's name, and whether its field is inactive."""
        self.props.append(name)
        if not (self.parent_active and self.active):
            self.inactive.append((name, options.get("index")))

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

    def row(self, **options):
        """A sub-layout for the drawing in the row."""
        return RecordingLayout(self)

    def column(self, **options):
        """A sub-layout for the drawing in the column."""
        return RecordingLayout(self)

    def box(self):
        """A sub-layout for the drawing in the box."""
        return RecordingLayout(self)

    def split(self, **options):
        """A sub-layout for the drawing in the split."""
        return RecordingLayout(self)
