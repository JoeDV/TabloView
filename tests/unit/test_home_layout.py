import unittest

from pydantic import ValidationError

from app.routes.system import SettingsUpdate
from app.settings import DEFAULTS


class HomeLayoutSettingsTests(unittest.TestCase):
    """Customize Home: the order of Home's sections and the hidden ones, saved on the PC."""

    def test_saved_as_sent(self):
        u = SettingsUpdate(home_order=["soon", "continue", "recent"], home_hidden=["primetime"])
        self.assertEqual(u.model_dump(exclude_none=True),
                         {"home_order": ["soon", "continue", "recent"], "home_hidden": ["primetime"]})
        # turning every section back on sends an empty list, which must still be saved
        self.assertEqual(SettingsUpdate(home_hidden=[]).model_dump(exclude_none=True), {"home_hidden": []})

    def test_only_known_sections(self):
        with self.assertRaises(ValidationError):
            SettingsUpdate(home_order=["continue", "<script>"])
        with self.assertRaises(ValidationError):
            SettingsUpdate(home_hidden=["recent"] * 21)

    def test_default_is_as_designed(self):
        self.assertEqual(DEFAULTS["home_order"], [])
        self.assertEqual(DEFAULTS["home_hidden"], [])


if __name__ == "__main__":
    unittest.main()
