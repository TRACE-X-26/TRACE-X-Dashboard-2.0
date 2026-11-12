"""Back up the configured Pi database, including committed WAL transactions."""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values


def backup(project=None):
    project = Path(project or Path(__file__).resolve().parents[2])
    runtime = Path(os.getenv('XDG_CONFIG_HOME', Path.home()/'.config'))/'trace-x/runtime.env'
    settings = dotenv_values(runtime) if runtime.exists() else {}
    database = Path(os.getenv('ADS_DATABASE_PATH', settings.get('ADS_DATABASE_PATH') or 'diagnostics.db'))
    if not database.is_absolute():
        database = project/database
    if not database.is_file():
        raise FileNotFoundError(f'Existing database was not found at {database}')
    destination = project/'backups'/('diagnostics-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.db')
    destination.parent.mkdir(exist_ok=True)
    source = sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return destination


if __name__ == '__main__':
    print(backup())
