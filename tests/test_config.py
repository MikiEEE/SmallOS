import json
import os
import sys
import tempfile
import unittest

sys.path.append("..")

from SmallPackage.SmallConfig import SmallOSConfig
from SmallPackage.SmallOS import SmallOS


class TestSmallOSConfig(unittest.TestCase):
    def test_from_dict_accepts_project_aliases(self):
        config = SmallOSConfig.from_dict(
            {
                "oslist_length": 64,
                "num_categories": 7,
                "io_buffer_length": 12,
                "eternal_watchers": True,
            }
        )

        self.assertEqual(64, config.task_capacity)
        self.assertEqual(7, config.priority_levels)
        self.assertEqual(12, config.io_buffer_length)
        self.assertTrue(config.eternal_watchers)

    def test_from_json_file_loads_canonical_keys(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            json.dump(
                {
                    "task_capacity": 128,
                    "priority_levels": 9,
                    "io_buffer_length": 32,
                    "eternal_watchers": False,
                },
                handle,
            )
            path = handle.name

        try:
            config = SmallOSConfig.from_json_file(path)
        finally:
            os.unlink(path)

        self.assertEqual(128, config.task_capacity)
        self.assertEqual(9, config.priority_levels)
        self.assertEqual(32, config.io_buffer_length)
        self.assertFalse(config.eternal_watchers)

    def test_smallos_uses_config_for_runtime_sizing(self):
        config = SmallOSConfig(
            task_capacity=48,
            priority_levels=6,
            io_buffer_length=20,
            eternal_watchers=True,
        )

        runtime = SmallOS(config=config)

        self.assertEqual(48, runtime.tasks.maxPID)
        self.assertEqual(6, runtime.tasks.num_priorities)
        self.assertEqual(20, runtime.buffer_length)
        self.assertTrue(runtime.eternalWatchers)


if __name__ == "__main__":
    unittest.main()
