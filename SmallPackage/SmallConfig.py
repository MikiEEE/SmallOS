"""
Configuration helpers for smallOS runtime sizing.

The scheduler already exposes a few core sizing knobs through constructor
arguments, but a small project-level config object makes those settings easier
to document, load from disk, and share between desktop and MicroPython entry
points.
"""


def _import_json_module():
    """Import ``json`` or ``ujson`` depending on the active Python runtime."""
    for module_name in ("json", "ujson"):
        try:
            return __import__(module_name)
        except ImportError:
            continue
    raise ImportError("smallOS requires json or ujson to load config files.")


class SmallOSConfig:
    """
    Small, portable runtime configuration container.

    Canonical field names are:
    - ``task_capacity``: max tracked tasks / PID slots
    - ``priority_levels``: number of scheduler queues/categories
    - ``io_buffer_length``: buffered app output length when the terminal is hidden
    - ``eternal_watchers``: whether watcher-only runtimes should stay alive

    ``from_dict`` also accepts a couple of project-flavored aliases so existing
    notes like "OS list length" and "number of categories" map cleanly onto the
    current runtime.
    """

    def __init__(
        self,
        task_capacity=2**10,
        priority_levels=10,
        io_buffer_length=1024,
        eternal_watchers=False,
    ):
        self.task_capacity = self._validate_positive_int("task_capacity", task_capacity)
        self.priority_levels = self._validate_positive_int("priority_levels", priority_levels)
        if self.priority_levels < 2:
            raise ValueError("priority_levels must be at least 2.")
        self.io_buffer_length = self._validate_non_negative_int("io_buffer_length", io_buffer_length)
        self.eternal_watchers = bool(eternal_watchers)

    @staticmethod
    def _validate_positive_int(name, value):
        if not isinstance(value, int):
            raise TypeError("{} must be an int.".format(name))
        if value <= 0:
            raise ValueError("{} must be greater than 0.".format(name))
        return value

    @staticmethod
    def _validate_non_negative_int(name, value):
        if not isinstance(value, int):
            raise TypeError("{} must be an int.".format(name))
        if value < 0:
            raise ValueError("{} must be 0 or greater.".format(name))
        return value

    @classmethod
    def default(cls):
        """Return a fresh config populated with the runtime defaults."""
        return cls()

    @classmethod
    def from_dict(cls, data):
        """Build a config from canonical keys or supported aliases."""
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data.copy()
        if not isinstance(data, dict):
            raise TypeError("SmallOSConfig.from_dict expects a dict-like config.")

        return cls(
            task_capacity=data.get("task_capacity", data.get("oslist_length", 2**10)),
            priority_levels=data.get("priority_levels", data.get("num_categories", 10)),
            io_buffer_length=data.get("io_buffer_length", 1024),
            eternal_watchers=data.get("eternal_watchers", False),
        )

    @classmethod
    def from_json_file(cls, path):
        """Load a config from a JSON file on desktop Python or MicroPython."""
        json_mod = _import_json_module()
        with open(path, "r") as handle:
            return cls.from_dict(json_mod.load(handle))

    def copy(self, **updates):
        """Return a new config with a few fields replaced."""
        data = self.to_dict()
        data.update(updates)
        return type(self).from_dict(data)

    def to_dict(self):
        """Return a plain-serializable dictionary with canonical config keys."""
        return {
            "task_capacity": self.task_capacity,
            "priority_levels": self.priority_levels,
            "io_buffer_length": self.io_buffer_length,
            "eternal_watchers": self.eternal_watchers,
        }
