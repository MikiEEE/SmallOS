"""Verify that release distributions contain the expected name and version."""

from __future__ import annotations

import argparse
import email.parser
import pathlib
import sys
import tarfile
import zipfile


def _metadata_fields(raw_metadata: bytes) -> tuple[str, str]:
    metadata = email.parser.BytesParser().parsebytes(raw_metadata)
    name = metadata.get("Name")
    version = metadata.get("Version")
    if name is None or version is None:
        raise ValueError("distribution metadata must contain Name and Version")
    return name, version


def wheel_metadata(path: pathlib.Path) -> tuple[str, str]:
    """Return the core metadata name and version stored in a wheel."""

    with zipfile.ZipFile(path) as archive:
        members = [
            member
            for member in archive.namelist()
            if member.endswith(".dist-info/METADATA")
        ]
        if len(members) != 1:
            raise ValueError(f"{path.name} must contain exactly one METADATA file")
        return _metadata_fields(archive.read(members[0]))


def sdist_metadata(path: pathlib.Path) -> tuple[str, str]:
    """Return the core metadata name and version stored in an sdist."""

    with tarfile.open(path, mode="r:gz") as archive:
        members = [
            member
            for member in archive.getmembers()
            if member.isfile()
            and member.name.count("/") == 1
            and member.name.endswith("/PKG-INFO")
        ]
        if len(members) != 1:
            raise ValueError(f"{path.name} must contain exactly one top-level PKG-INFO")
        extracted = archive.extractfile(members[0])
        if extracted is None:
            raise ValueError(f"could not read metadata from {path.name}")
        return _metadata_fields(extracted.read())


def verify_dist(directory: pathlib.Path, expected_name: str, expected_version: str) -> None:
    """Verify one wheel and one sdist in ``directory`` against expectations."""

    wheels = sorted(directory.glob("*.whl"))
    sdists = sorted(directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError(
            f"expected one wheel and one sdist, found {len(wheels)} wheel(s) "
            f"and {len(sdists)} sdist(s)"
        )

    for path, reader in ((wheels[0], wheel_metadata), (sdists[0], sdist_metadata)):
        name, version = reader(path)
        if name.casefold() != expected_name.casefold():
            raise ValueError(
                f"{path.name} contains project name {name!r}, expected {expected_name!r}"
            )
        if version != expected_version:
            raise ValueError(
                f"{path.name} contains version {version!r}, expected {expected_version!r}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=pathlib.Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--version", required=True)
    arguments = parser.parse_args(argv)

    try:
        verify_dist(arguments.directory, arguments.name, arguments.version)
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"Release artifact verification failed: {error}", file=sys.stderr)
        return 1

    print(
        f"Verified wheel and sdist for {arguments.name} {arguments.version} "
        f"in {arguments.directory}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
