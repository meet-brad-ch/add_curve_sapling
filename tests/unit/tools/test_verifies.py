# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of tests/support: the Verifies decorator."""

import unittest

from support.verifies import Verifies


class VerifiesDecorator(unittest.TestCase):
    """Verifies keeps the requirement IDs on a class or a function, adds up the IDs of stacked decorators,
    and refuses bad IDs."""

    def test_ids_are_kept_on_the_target(self):
        @Verifies("SWR-0084")
        class Target:
            pass

        self.assertEqual(Target.__requirements__, ("SWR-0084",))

    def test_ids_add_up(self):
        @Verifies("SWR-0002")
        @Verifies("SWR-0001")
        def target():
            pass

        self.assertEqual(target.__requirements__, ("SWR-0001", "SWR-0002"))

    def test_bad_ids_are_refused(self):
        for ids in ((), ("SWR-84",), ("REQ-0001",)):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                Verifies(*ids)
