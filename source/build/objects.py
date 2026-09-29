# SPDX-License-Identifier: GPL-3.0-or-later

"""Creating the tree's objects in the scene."""

import bpy


class ObjectFactory:
    """Creates objects in one collection and remembers them, in creation order."""

    def __init__(self, collection):
        self.collection = collection
        self.created = []

    def new(self, name, data, parent=None):
        ob = bpy.data.objects.new(name, data)
        self.collection.objects.link(ob)
        if parent:
            ob.parent = parent
        self.created.append(ob)
        return ob
