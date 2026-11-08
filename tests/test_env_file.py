import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from main import data_url, load_env_file, resolve_env_path


class DataUrlTest(unittest.TestCase):
    def test_joins_the_data_directory(self):
        base = "http://tar1090.local/data"
        self.assertEqual(data_url(base, "stats.json"), base + "/stats.json")
        self.assertEqual(data_url(base + "/", "outline.json"), base + "/outline.json")


class LoadEnvFileTest(unittest.TestCase):
    def test_sets_missing_values_and_keeps_existing_ones(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "\n".join([
                    "# comment",
                    "TAR1090_DEV_FROM_FILE=from-file",
                    "TAR1090_DEV_ALREADY_SET=from-file",
                    "TAR1090_DEV_QUOTED=\"quoted value\"",
                    "",
                ]),
                encoding="utf-8",
            )
            os.environ["TAR1090_DEV_ALREADY_SET"] = "from-shell"
            try:
                load_env_file(path)
                self.assertEqual(os.environ["TAR1090_DEV_FROM_FILE"], "from-file")
                self.assertEqual(os.environ["TAR1090_DEV_ALREADY_SET"], "from-shell")
                self.assertEqual(os.environ["TAR1090_DEV_QUOTED"], "quoted value")
            finally:
                os.environ.pop("TAR1090_DEV_FROM_FILE", None)
                os.environ.pop("TAR1090_DEV_ALREADY_SET", None)
                os.environ.pop("TAR1090_DEV_QUOTED", None)

    def test_override_replaces_existing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.env"
            path.write_text("export TAR1090_DEV_ALREADY_SET=from-file\n", encoding="utf-8")
            os.environ["TAR1090_DEV_ALREADY_SET"] = "from-shell"
            try:
                load_env_file(path, override=True)
                self.assertEqual(os.environ["TAR1090_DEV_ALREADY_SET"], "from-file")
            finally:
                os.environ.pop("TAR1090_DEV_ALREADY_SET", None)


class ResolveEnvPathTest(unittest.TestCase):
    def test_uses_the_first_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.env"
            resolved = resolve_env_path(["main.py", str(path)])
            self.assertEqual(resolved, path.resolve())

    def test_rejects_extra_arguments(self):
        with self.assertRaises(SystemExit):
            resolve_env_path(["main.py", "a.env", "b.env"])


if __name__ == "__main__":
    unittest.main()
