from pathlib import Path
import sqlite3
from datetime import datetime, timezone


class Database:
    def __init__(self, db_path="data/backup.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        conn = sqlite3.connect(
            self.db_path,
            timeout=30,
        )

        conn.execute(
            "PRAGMA busy_timeout = 30000"
        )

        conn.execute(
            "PRAGMA synchronous = NORMAL"
        )

        return conn

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _initialize(self):
        with self._connect() as conn:

            # Enable WAL only during database initialization.
            conn.execute(
                "PRAGMA journal_mode = WAL"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL UNIQUE,
                    file_hash TEXT,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    destination_id INTEGER,
                    telegram_message_id INTEGER,
                    uploaded_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            existing_columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(files)"
                ).fetchall()
            }

            migrations = {
                "telegram_message_id":
                    "ALTER TABLE files ADD COLUMN telegram_message_id INTEGER",

                "uploaded_at":
                    "ALTER TABLE files ADD COLUMN uploaded_at TEXT",

                "last_error":
                    "ALTER TABLE files ADD COLUMN last_error TEXT",

                "destination_id":
                    "ALTER TABLE files ADD COLUMN destination_id INTEGER",
            }

            for column, sql in migrations.items():
                if column not in existing_columns:
                    conn.execute(sql)

            # Permanent upload history.
            # One identical file hash can be uploaded once
            # to each Telegram destination.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_hash TEXT NOT NULL,
                    destination_id INTEGER NOT NULL,
                    telegram_message_id INTEGER,
                    uploaded_at TEXT NOT NULL,
                    UNIQUE(file_hash, destination_id)
                )
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_files_hash
                ON files(file_hash)
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_files_status
                ON files(status)
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_files_status_destination
                ON files(status, destination_id)
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_uploads_hash_destination
                ON uploads(file_hash, destination_id)
                """
            )

    def recover_interrupted_uploads(self):
        """Make uploads interrupted by process exit eligible for retry."""
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE files
                SET
                    status = 'pending',
                    last_error = 'Upload was interrupted; scan and retry it',
                    updated_at = ?
                WHERE status = 'uploading'
                """,
                (now,),
            )
            return cursor.rowcount

    def get_by_path(self, path):
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT
                    path,
                    file_hash,
                    size,
                    mtime_ns,
                    status,
                    destination_id,
                    telegram_message_id,
                    uploaded_at,
                    last_error
                FROM files
                WHERE path = ?
                """,
                (str(path),),
            ).fetchone()

    def get_uploaded_by_hash(
        self,
        file_hash,
        destination_id=None,
    ):
        if not file_hash:
            return None

        with self._connect() as conn:

            if destination_id is None:
                return conn.execute(
                    """
                    SELECT
                        file_hash,
                        destination_id,
                        telegram_message_id,
                        uploaded_at
                    FROM uploads
                    WHERE file_hash = ?
                    LIMIT 1
                    """,
                    (file_hash,),
                ).fetchone()

            return conn.execute(
                """
                SELECT
                    file_hash,
                    destination_id,
                    telegram_message_id,
                    uploaded_at
                FROM uploads
                WHERE file_hash = ?
                  AND destination_id = ?
                LIMIT 1
                """,
                (
                    file_hash,
                    int(destination_id),
                ),
            ).fetchone()

    def get_uploaded_file_signatures(self, destination_id):
        """Return uploaded paths, signatures and Telegram message IDs."""
        if destination_id is None:
            return {}

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT
                    f.path,
                    f.size,
                    f.mtime_ns,
                    f.file_hash,
                    COALESCE(u.telegram_message_id, f.telegram_message_id),
                    COALESCE(u.uploaded_at, f.uploaded_at)
                FROM files AS f
                LEFT JOIN uploads AS u
                    ON u.file_hash = f.file_hash
                   AND u.destination_id = ?
                WHERE (f.status = 'uploaded' AND f.destination_id = ?)
                   OR u.file_hash IS NOT NULL
                """,
                (int(destination_id), int(destination_id)),
            ).fetchall()

        return {
            str(path): {
                "signature": (int(size), int(mtime_ns)),
                "hash": file_hash,
                "telegram_message_id": message_id,
                "uploaded_at": uploaded_at,
            }
            for path, size, mtime_ns, file_hash, message_id, uploaded_at in rows
        }

    def delete_upload_record(self, file_hash, destination_id):
        """Forget a remote upload that no longer exists in Telegram."""
        if not file_hash or destination_id is None:
            return

        now = self._now()
        destination_id = int(destination_id)

        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM uploads
                WHERE file_hash = ? AND destination_id = ?
                """,
                (file_hash, destination_id),
            )
            conn.execute(
                """
                UPDATE files
                SET
                    file_hash = NULL,
                    status = 'pending',
                    destination_id = NULL,
                    telegram_message_id = NULL,
                    uploaded_at = NULL,
                    last_error = 'Telegram backup message was deleted',
                    updated_at = ?
                WHERE file_hash = ?
                  AND (destination_id = ? OR destination_id IS NULL)
                """,
                (now, file_hash, destination_id),
            )

    def has_uploaded_to_destination(
        self,
        file_hash,
        destination_id,
    ):
        if not file_hash or destination_id is None:
            return False

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM uploads
                WHERE file_hash = ?
                  AND destination_id = ?
                LIMIT 1
                """,
                (
                    file_hash,
                    int(destination_id),
                ),
            ).fetchone()

            if row:
                return True

            # Legacy fallback for uploads recorded by the previous
            # destination-aware database version.
            row = conn.execute(
                """
                SELECT 1
                FROM files
                WHERE file_hash = ?
                  AND status = 'uploaded'
                  AND destination_id = ?
                LIMIT 1
                """,
                (
                    file_hash,
                    int(destination_id),
                ),
            ).fetchone()

            return row is not None

    def upsert(
        self,
        path,
        file_hash,
        size,
        mtime_ns,
        status="pending",
        destination_id=None,
    ):
        now = self._now()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO files
                    (
                        path,
                        file_hash,
                        size,
                        mtime_ns,
                        status,
                        destination_id,
                        created_at,
                        updated_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT(path) DO UPDATE SET
                    file_hash = excluded.file_hash,
                    size = excluded.size,
                    mtime_ns = excluded.mtime_ns,
                    status = excluded.status,
                    destination_id = excluded.destination_id,
                    updated_at = excluded.updated_at,

                    telegram_message_id =
                        CASE
                            WHEN excluded.status IN ('pending', 'skipped')
                            THEN NULL
                            ELSE files.telegram_message_id
                        END,

                    uploaded_at =
                        CASE
                            WHEN excluded.status IN ('pending', 'skipped')
                            THEN NULL
                            ELSE files.uploaded_at
                        END,

                    last_error =
                        CASE
                            WHEN excluded.status = 'pending'
                            THEN NULL
                            ELSE files.last_error
                        END
                """,
                (
                    str(path),
                    file_hash,
                    size,
                    mtime_ns,
                    status,
                    destination_id,
                    now,
                    now,
                ),
            )

    def set_status(
        self,
        path,
        status,
        last_error=None,
    ):
        now = self._now()

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE files
                SET
                    status = ?,
                    last_error = ?,
                    updated_at = ?
                WHERE path = ?
                """,
                (
                    status,
                    last_error,
                    now,
                    str(path),
                ),
            )

    def mark_uploading(
        self,
        path,
        destination_id=None,
    ):
        now = self._now()

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE files
                SET
                    status = 'uploading',
                    destination_id = ?,
                    last_error = NULL,
                    updated_at = ?
                WHERE path = ?
                """,
                (
                    destination_id,
                    now,
                    str(path),
                ),
            )

    def mark_uploaded(
        self,
        path,
        file_hash,
        destination_id,
        telegram_message_id,
    ):
        now = self._now()

        with self._connect() as conn:

            conn.execute(
                """
                INSERT INTO uploads
                    (
                        file_hash,
                        destination_id,
                        telegram_message_id,
                        uploaded_at
                    )
                VALUES (?, ?, ?, ?)

                    ON CONFLICT(file_hash, destination_id)
                    DO UPDATE SET
                        telegram_message_id =
                            excluded.telegram_message_id,
                        uploaded_at =
                            excluded.uploaded_at
                """,
                (
                    file_hash,
                    int(destination_id),
                    telegram_message_id,
                    now,
                ),
            )

            conn.execute(
                """
                UPDATE files
                SET
                    status = 'uploaded',
                    destination_id = ?,
                    telegram_message_id = ?,
                    uploaded_at = ?,
                    last_error = NULL,
                    updated_at = ?
                WHERE path = ?
                """,
                (
                    int(destination_id),
                    telegram_message_id,
                    now,
                    now,
                    str(path),
                ),
            )

    def get_upload_record(
        self,
        file_hash,
        destination_id,
    ):
        if not file_hash or destination_id is None:
            return None

        with self._connect() as conn:
            return conn.execute(
                """
                SELECT
                    file_hash,
                    destination_id,
                    telegram_message_id,
                    uploaded_at
                FROM uploads
                WHERE file_hash = ?
                  AND destination_id = ?
                LIMIT 1
                """,
                (
                    file_hash,
                    int(destination_id),
                ),
            ).fetchone()

    def mark_duplicate(
        self,
        path,
        destination_id,
    ):
        now = self._now()

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE files
                SET
                    status = 'skipped',
                    destination_id = ?,
                    last_error = 'Duplicate file already uploaded',
                    updated_at = ?
                WHERE path = ?
                """,
                (
                    int(destination_id),
                    now,
                    str(path),
                ),
            )

    def mark_failed(
        self,
        path,
        error,
    ):
        self.set_status(
            path,
            "failed",
            str(error),
        )

    def get_pending_files(self):
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT
                    path,
                    file_hash,
                    size,
                    mtime_ns,
                    status,
                    destination_id
                FROM files
                WHERE status = 'pending'
                ORDER BY id ASC
                """
            ).fetchall()
