# ruff: noqa: ERA001 A003
# bandit:skip-file

from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connections


def _dbinfo(alias: str):
    cfg = settings.DATABASES[alias]
    return {
        "engine": cfg["ENGINE"],
        "name": cfg["NAME"],
        "user": cfg.get("USER"),
        "password": cfg.get("PASSWORD"),
        "host": cfg.get("HOST"),
        "port": cfg.get("PORT"),
    }


def _require_postgres(engine: str):
    if "postgresql" not in engine:
        raise CommandError(f"PostgreSQL only. ENGINE={engine!r}.")


def _maintenance_dsn(info: dict) -> str:
    parts = ["dbname=postgres"]
    if info.get("user"):
        parts.append(f"user={info['user']}")
    if info.get("password"):
        parts.append(f"password={info['password']}")
    if info.get("host"):
        parts.append(f"host={info['host']}")
    if info.get("port"):
        parts.append(f"port={info['port']}")
    return " ".join(parts)


def _pg_connect(dsn: str):
    """
    Return a live psycopg connection (supports psycopg3 or psycopg2).
    """
    try:
        import psycopg  # psycopg3

        return psycopg.connect(dsn)
    except Exception:
        try:
            import psycopg2  # type: ignore

            return psycopg2.connect(dsn)  # type: ignore
        except Exception as e2:
            raise CommandError(
                "Could not import psycopg (v3) or psycopg2. "
                "Install one of them to manage databases."
            ) from e2


def _db_exists(cur, name: str) -> bool:
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
    return cur.fetchone() is not None


def _create_db_if_needed(src_info: dict, name: str, *, recreate: bool = False):
    dsn = _maintenance_dsn(src_info)
    conn = _pg_connect(dsn)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            if _db_exists(cur, name):
                if recreate:
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()",
                        (name,),
                    )
                    cur.execute(f'DROP DATABASE "{name}"')
                else:
                    return
            cur.execute(f'CREATE DATABASE "{name}"')
    finally:
        conn.close()


def _drop_db(src_info: dict, name: str):
    dsn = _maintenance_dsn(src_info)
    conn = _pg_connect(dsn)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (name,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{name}"')
    finally:
        conn.close()


def _switch_process_db(alias: str, new_name: str):
    settings.DATABASES[alias]["NAME"] = new_name
    connections.close_all()


@contextmanager
def _suppress_all_django_signals(active: bool):
    """
    Monkey-patch Django's Signal dispatch to no-op while active is True.
    This suppresses *all* signals (model and custom) during fixture loading.
    """
    if not active:
        # No suppression requested
        yield
        return

    from django.dispatch import dispatcher as _dispatcher

    orig_send = _dispatcher.Signal.send
    orig_send_robust = _dispatcher.Signal.send_robust

    def _no_send(self, sender, **named):
        return []

    def _no_send_robust(self, sender, **named):
        return []

    _dispatcher.Signal.send = _no_send
    _dispatcher.Signal.send_robust = _no_send_robust
    try:
        yield
    finally:
        _dispatcher.Signal.send = orig_send
        _dispatcher.Signal.send_robust = orig_send_robust


class Command(BaseCommand):
    help = (
        "Create (or reuse) a PostgreSQL database, switch the process to it, run "
        "migrate, and load one or more fixtures. Optionally drop the DB afterward."
    )

    def add_arguments(self, p):
        p.add_argument(
            "--db-alias", default="default", help="DATABASES alias (default: default)."
        )
        p.add_argument(
            "--db-name",
            default=None,
            help=(
                "Target DB name (default: <alias.NAME>_lt). If it exists and "
                "--recreate is not set, it will be reused."
            ),
        )
        p.add_argument(
            "--recreate",
            action="store_true",
            help="Drop existing DB first, then create.",
        )
        p.add_argument(
            "--fixtures", required=True, nargs="+", help="Fixture file(s) to load."
        )
        p.add_argument(
            "--drop-after",
            action="store_true",
            help="Drop the DB after loading (validation-only).",
        )
        p.add_argument(
            "--enable-signals",
            action="store_true",
            help="Do NOT suppress Django signals during loaddata (default suppresses).",
        )

    def handle(self, *args, **o):
        alias = o["db_alias"]
        info = _dbinfo(alias)
        _require_postgres(info["engine"])

        base_name = info["name"]
        if not base_name:
            raise CommandError(f"DATABASES[{alias!r}]['NAME'] is empty.")

        db_name = o["db_name"] or f"{base_name}_lt"

        fixture_paths = [Path(f).resolve() for f in o["fixtures"]]
        missing = [str(p) for p in fixture_paths if not p.exists()]
        if missing:
            raise CommandError(f"Fixture(s) not found: {', '.join(missing)}")

        self.stdout.write(self.style.NOTICE(f"Preparing DB {db_name!r}"))
        _create_db_if_needed(info, db_name, recreate=bool(o["recreate"]))

        self.stdout.write(self.style.SUCCESS(f"Switching process to DB {db_name!r}"))
        _switch_process_db(alias, db_name)

        self.stdout.write(self.style.NOTICE("Applying migrations..."))
        call_command("migrate", database=alias, interactive=False, run_syncdb=True)

        # Suppress signals by default; --enable-signals turns suppression off
        suppress = not bool(o.get("enable_signals"))
        if suppress:
            self.stdout.write(
                self.style.NOTICE("Suppressing Django signals during loaddata...")
            )
        else:
            self.stdout.write(self.style.NOTICE("Signals ENABLED during loaddata."))

        self.stdout.write(self.style.NOTICE("Loading fixtures..."))
        with _suppress_all_django_signals(active=suppress):
            for fp in fixture_paths:
                call_command("loaddata", str(fp), database=alias)

        if o["drop_after"]:
            self.stdout.write(self.style.NOTICE(f"Dropping DB {db_name!r}"))
            # switch away to avoid dropping the active DB
            _switch_process_db(alias, base_name)
            _drop_db(info, db_name)
            self.stdout.write(self.style.SUCCESS(f"Dropped {db_name!r}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Loaded fixtures into {db_name!r}"))
