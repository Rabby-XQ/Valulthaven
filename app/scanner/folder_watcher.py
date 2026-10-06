from pathlib import Path
import os
import time


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",

    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
    ".m4v",
}

TEMP_EXTENSIONS = {
    ".tmp",
    ".temp",
    ".part",
    ".crdownload",
    ".download",
}


def get_media_files(folder):
    return [path for path, _ in iter_media_files(folder)]


def iter_media_files(folder):
    """Yield supported files with one cached stat result per directory entry."""
    folder_path = Path(folder)

    if not folder_path.exists():
        return

    if not folder_path.is_dir():
        return

    directories = [folder_path]

    while directories:
        directory = directories.pop()

        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            directories.append(Path(entry.path))
                            continue

                        suffix = Path(entry.name).suffix.lower()
                        if (
                            suffix in TEMP_EXTENSIONS
                            or suffix not in SUPPORTED_EXTENSIONS
                            or not entry.is_file(follow_symlinks=False)
                        ):
                            continue

                        stat = entry.stat(follow_symlinks=False)
                        if stat.st_size > 0:
                            yield Path(entry.path), stat
                    except OSError:
                        continue
        except OSError:
            continue


def get_file_signature(file_path):
    """
    Return the current size and modification time of a file.

    This does not read the whole file.
    It is only used to detect whether the file is still changing.
    """

    path = Path(file_path)

    try:
        stat = path.stat()

        return (
            stat.st_size,
            stat.st_mtime_ns,
        )

    except (OSError, FileNotFoundError):
        return None


def is_file_stable(
    file_path,
    wait_seconds=2,
):
    """
    Check whether a file remains unchanged for wait_seconds.

    Returns True only when:
    - file exists
    - file is a regular file
    - file size is greater than zero
    - size and modification time remain unchanged
    """

    path = Path(file_path)

    first_signature = get_file_signature(path)

    if first_signature is None:
        return False

    first_size, _ = first_signature

    if first_size <= 0:
        return False

    if wait_seconds > 0:
        time.sleep(wait_seconds)

    second_signature = get_file_signature(path)

    if second_signature is None:
        return False

    return first_signature == second_signature


def is_file_ready(
    file_path,
    wait_seconds=2,
):
    """
    Backward-compatible wrapper.

    Existing scanner code can continue calling is_file_ready().
    """

    return is_file_stable(
        file_path,
        wait_seconds=wait_seconds,
    )
