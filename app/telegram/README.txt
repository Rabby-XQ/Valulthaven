VaultHaven Destination Setup Notes

Files:
- destination_dialog.py
- destination_store.py
- async_dialog.py

Copy these into:
C:\Users\Fozly Rabby\Autobackup\app\telegram\

IMPORTANT:
Do not replace app/ui/main_window.py yet.

The next integration step will connect these files to your CURRENT
main_window.py without disturbing the working upload/database code.

The dialog intentionally does not use dialog.exec(), because the app
uses qasync and nested event loops can break the Telegram login flow.
