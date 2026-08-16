import io
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

from tools.release_policy import validate_title
from tools.verify_release_artifacts import verify_dist


class TestReleasePolicy(unittest.TestCase):
    def test_accepts_release_types_scopes_and_breaking_marker(self):
        valid_titles = (
            "fix: preserve closed descriptor cleanup",
            "feat(io): add persistent wait sets",
            "feat!: replace the scheduler contract",
            "docs(release/guide): explain recovery",
            "ci: pin the release action",
        )

        for title in valid_titles:
            with self.subTest(title=title):
                self.assertIsNone(validate_title(title))

    def test_rejects_titles_semantic_release_cannot_use(self):
        invalid_titles = (
            "Add persistent wait sets",
            "unknown: change behavior",
            "feat add persistent wait sets",
            "feat: ",
            "feat: first line\nsecond line",
        )

        for title in invalid_titles:
            with self.subTest(title=title):
                self.assertIsNotNone(validate_title(title))


class TestReleaseArtifacts(unittest.TestCase):
    @staticmethod
    def _metadata(name="SmallPackage", version="1.2.3"):
        return f"Metadata-Version: 2.2\nName: {name}\nVersion: {version}\n\n".encode()

    def _write_wheel(self, directory, metadata=None):
        path = directory / "smallpackage-1.2.3-py3-none-any.whl"
        with zipfile.ZipFile(path, mode="w") as archive:
            archive.writestr(
                "smallpackage-1.2.3.dist-info/METADATA",
                metadata or self._metadata(),
            )
        return path

    def _write_sdist(self, directory, metadata=None):
        path = directory / "smallpackage-1.2.3.tar.gz"
        payload = metadata or self._metadata()
        member = tarfile.TarInfo("smallpackage-1.2.3/PKG-INFO")
        member.size = len(payload)
        with tarfile.open(path, mode="w:gz") as archive:
            archive.addfile(member, io.BytesIO(payload))
        return path

    def test_verifies_one_matching_wheel_and_sdist(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            self._write_wheel(directory)
            self._write_sdist(directory)

            verify_dist(directory, "SmallPackage", "1.2.3")

    def test_rejects_a_metadata_version_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            self._write_wheel(directory, self._metadata(version="1.2.4"))
            self._write_sdist(directory)

            with self.assertRaisesRegex(ValueError, "contains version"):
                verify_dist(directory, "SmallPackage", "1.2.3")

    def test_rejects_missing_or_duplicate_distribution_types(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            self._write_wheel(directory)

            with self.assertRaisesRegex(ValueError, "one wheel and one sdist"):
                verify_dist(directory, "SmallPackage", "1.2.3")


if __name__ == "__main__":
    unittest.main()
