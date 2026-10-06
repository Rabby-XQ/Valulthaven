import hashlib
import asyncio
import threading
from pathlib import Path


def sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()

    with Path(path).open("rb") as file:
        while True:
            chunk = file.read(chunk_size)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


async def sha256_file_async(path):
    """Hash a file off the UI loop without blocking shutdown on the worker."""
    loop = asyncio.get_running_loop()
    result = loop.create_future()

    def finish(value=None, error=None):
        if result.done():
            return
        if error is not None:
            result.set_exception(error)
        else:
            result.set_result(value)

    def calculate():
        try:
            value = sha256_file(path)
            loop.call_soon_threadsafe(finish, value, None)
        except BaseException as exc:
            try:
                loop.call_soon_threadsafe(finish, None, exc)
            except RuntimeError:
                # The app's event loop may already be closed during exit.
                pass

    threading.Thread(
        target=calculate,
        name="VaultHavenHash",
        daemon=True,
    ).start()

    return await result
