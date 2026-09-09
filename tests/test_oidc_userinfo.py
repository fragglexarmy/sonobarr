"""Provider-neutral checks for embedded and fetched OIDC claims."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sonobarr_app.extensions import db
from sonobarr_app.models import User
import sonobarr_app.web.oidc_auth as auth


@pytest.mark.parametrize("claim", ["email", "preferred_username"])
@pytest.mark.parametrize("embedded", [True, False])
def test_login_with_embedded_or_fetched_profile(app, client, monkeypatch, claim, embedded):
    profile = {"sub": "subject", claim: "listener", "groups": ["admins"]}
    fetch = Mock(return_value=profile)
    monkeypatch.setitem(app.config, "OIDC_ADMIN_GROUP", "admins")
    monkeypatch.setattr(auth.oidc, "sonobarr", SimpleNamespace(
        authorize_access_token=lambda: {"userinfo": profile if embedded else {"sub": "subject"}},
        userinfo=fetch,
    ))
    for _ in range(2):
        assert client.get('/oidc/callback').location.endswith('/')
        with app.app_context():
            user = User.query.filter_by(oidc_id="subject").one()
            assert user.username == "listener"
            assert user.is_admin
        with client.session_transaction() as session:
            assert session.get('_user_id')
    assert fetch.call_count == (0 if embedded else 2)


@pytest.mark.parametrize("fetched", [
    {"sub": "other", "email": "victim"}, {"email": "victim"},
    None, [], RuntimeError("provider unavailable"),
])
def test_invalid_userinfo_cannot_login_or_change_existing_account(app, client, monkeypatch, fetched):
    with app.app_context():
        db.session.add(User(username="victim", oidc_id="other", is_admin=True))
        db.session.commit()
    fetch = Mock(side_effect=fetched) if isinstance(fetched, Exception) else Mock(return_value=fetched)
    monkeypatch.setattr(auth.oidc, "sonobarr", SimpleNamespace(
        authorize_access_token=lambda: {"userinfo": {"sub": "authenticated"}}, userinfo=fetch,
    ))
    assert '/login' in client.get('/oidc/callback').location
    with client.session_transaction() as session:
        assert '_user_id' not in session
    with app.app_context():
        assert User.query.count() == 1
        assert User.query.one().is_admin


@pytest.mark.parametrize("claims", [None, {}, {"email": "listener"}, {"sub": ""}])
def test_requires_validated_subject(app, monkeypatch, claims):
    fetch = Mock()
    monkeypatch.setattr(auth.oidc, "sonobarr", SimpleNamespace(userinfo=fetch))
    with app.app_context():
        assert auth._fetch_user_info({"userinfo": claims}) is None
    fetch.assert_not_called()
