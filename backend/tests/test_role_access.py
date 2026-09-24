"""Three-role access boundaries and upgrade of existing staff accounts."""
import hashlib
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthRepository, hash_password
from app.main import create_app
from test_auth_api import configure_required_auth, login


@pytest.mark.parametrize('role', ['ADMIN', 'EMPLOYEE', 'CITIZEN'])
def test_role_data_and_account_boundaries(monkeypatch, tmp_path, role):
    configure_required_auth(monkeypatch, tmp_path)
    db = tmp_path / 'roles.db'
    with TestClient(create_app(database_path=db, live_output_dir=tmp_path/'live')) as client:
        users = AuthRepository(db)
        actor = users.create_user('actor', 'actor-password-123', role)
        login(client, 'actor', 'actor-password-123')
        assert client.get('/api/citizen-reports').status_code == 200
        for path in ['/api/events', '/api/scenarios', '/api/audit']:
            assert client.get(path).status_code == (403 if role == 'CITIZEN' else 200)
        for path in ['/api/live-cameras', '/api/analysis/summary', '/api/analytics/summary',
                     '/api/live-cameras/camera-3/snapshot', '/media/scenarios/stopped_vehicle/annotated.mp4',
                     '/evidence/live-cameras/camera-3/anything.jpg', '/api/events/unknown']:
            if role == 'CITIZEN': assert client.get(path).status_code == 403
        for action in ['verify', 'dismiss']:
            assert client.post('/api/events/missing/'+action).status_code == (403 if role == 'CITIZEN' else 404)
        assert client.get('/api/users').status_code == (200 if role == 'ADMIN' else 403)
        for changes in [{'active':False}, {'role':'ADMIN'}]:
            result=client.patch('/api/users/'+actor.user_id, json=changes)
            if role != 'ADMIN': assert result.status_code == 403
        if role != 'ADMIN':
            assert client.post('/api/users', json={'username':'privilege-escalation','password':'safe-password-123','role':'ADMIN'}).status_code == 403
            assert users.authenticate('actor','actor-password-123').role == role


def test_downgrade_takes_effect_on_existing_session(monkeypatch,tmp_path):
    configure_required_auth(monkeypatch,tmp_path)
    db=tmp_path/'roles.db'
    with TestClient(create_app(database_path=db)) as client:
        users=AuthRepository(db);user=users.create_user('staff','staff-password-123','EMPLOYEE')
        login(client,'staff','staff-password-123')
        assert client.get('/api/events').status_code==200
        users.update_user(user.user_id,role='CITIZEN')
        assert client.get('/api/auth/session').json()['user']['role']=='CITIZEN'
        assert client.get('/api/events').status_code==403
        assert client.post('/api/events/missing/verify').status_code==403
        assert client.get('/api/citizen-reports').status_code==200
        assert client.post('/api/auth/logout').status_code==200


def test_old_staff_roles_migrate_without_losing_accounts_or_sessions(tmp_path):
    db=tmp_path/'legacy.db';password=hash_password('legacy-password-123')
    with sqlite3.connect(db) as c:
        c.executescript("""CREATE TABLE users (
            user_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('OPERATOR','REVIEWER','ADMIN')),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE auth_sessions(token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                expires_at REAL NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);""")
        for role in ['OPERATOR','REVIEWER','ADMIN']:
            c.execute('INSERT INTO users(user_id,username,password_hash,role) VALUES(?,?,?,?)',(role,role,password,role))
        c.execute('UPDATE users SET active=0 WHERE user_id=?',('REVIEWER',))
        c.execute('INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)',
                  (hashlib.sha256(b'legacy-token').hexdigest(),'OPERATOR',time.time()+1000))
    repo=AuthRepository(db);repo.initialize();repo.initialize()
    users={u.user_id:u for u in repo.list_users()}
    assert users['OPERATOR'].role==users['REVIEWER'].role=='EMPLOYEE'
    assert users['ADMIN'].role=='ADMIN' and not users['REVIEWER'].active
    assert repo.authenticate('OPERATOR','legacy-password-123').role=='EMPLOYEE'
    assert repo.resolve_session('legacy-token').role=='EMPLOYEE'
    with sqlite3.connect(db) as c:
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert c.execute('SELECT password_hash FROM users WHERE user_id=?',('OPERATOR',)).fetchone()[0]==password
    repo.create_user('citizen','citizen-password-123','CITIZEN')
