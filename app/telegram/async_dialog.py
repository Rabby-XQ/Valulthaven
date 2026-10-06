import asyncio


async def open_dialog(dialog, delete_on_finish=True):
    """
    Open a Qt dialog without calling dialog.exec().

    This is safe to use with the qasync event loop because it does not
    create a nested Qt event loop.
    """
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def on_finished(result):
        if not future.done():
            future.set_result(result)

    dialog.finished.connect(on_finished)
    dialog.open()

    try:
        return await future
    finally:
        try:
            dialog.finished.disconnect(on_finished)
        except (RuntimeError, TypeError):
            pass
        if delete_on_finish:
            dialog.deleteLater()
