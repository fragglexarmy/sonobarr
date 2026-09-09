"""Exercise the bundled migration chain on existing SQLite user data."""
from flask import Flask
from flask_migrate import Migrate, upgrade, downgrade
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
import pytest


@pytest.mark.parametrize('preexisting_columns', [False, True])
def test_api_key_upgrade_preserves_users(tmp_path, preexisting_columns):
    app = Flask('migration-test')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{tmp_path / "migration.db"}'
    database = SQLAlchemy(app)
    Migrate(app, database)
    with app.app_context():
        # The app creates base tables before Alembic runs, including on first boot.
        with database.engine.begin() as connection:
            connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(120) NOT NULL UNIQUE, password_hash VARCHAR(256), is_admin BOOLEAN NOT NULL, is_active BOOLEAN NOT NULL)'))
        upgrade(revision='20260303_01')
        with database.engine.begin() as connection:
            connection.execute(text("INSERT INTO users (username, password_hash, is_admin, is_active) VALUES ('existing', 'hash', 0, 1)"))
            if preexisting_columns:
                connection.execute(text('ALTER TABLE users ADD COLUMN openai_api_key VARCHAR(512)'))
                connection.execute(text("UPDATE users SET openai_api_key = 'PERSONAL'"))
        upgrade()
        upgrade()
        columns = {column['name'] for column in inspect(database.engine).get_columns('users')}
        assert {'lastfm_api_key', 'lastfm_api_secret', 'youtube_api_key', 'openai_api_key',
                'openai_api_base', 'openai_model', 'openai_extra_headers', 'openai_max_seed_artists'} <= columns
        with database.engine.connect() as connection:
            assert connection.execute(text('SELECT username FROM users')).scalar_one() == 'existing'
            assert connection.execute(text('SELECT openai_api_key FROM users')).scalar_one() == ('PERSONAL' if preexisting_columns else None)
        downgrade(revision='20260303_01')
        assert 'openai_api_key' not in {column['name'] for column in inspect(database.engine).get_columns('users')}
        with database.engine.connect() as connection:
            assert connection.execute(text('SELECT username FROM users')).scalar_one() == 'existing'


def test_fresh_app_schema_accepts_bundled_migrations(tmp_path):
    from sonobarr_app.extensions import db
    app = Flask('fresh-migration-test')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{tmp_path / "fresh.db"}'
    database = SQLAlchemy(app)
    Migrate(app, database)
    with app.app_context():
        db.metadata.create_all(database.engine)
        upgrade()
        with database.engine.connect() as connection:
            assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '20251223_01'
