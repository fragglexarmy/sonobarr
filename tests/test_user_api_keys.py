"""Per-user settings preserve global defaults and isolate personal endpoints."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import sonobarr_app.services.data_handler as data
from sonobarr_app.models import User
from sonobarr_app.extensions import db

def handler():
    h = object.__new__(data.DataHandler)
    h.openai_api_key = 'FAKE-GLOBAL-KEY'
    h.openai_api_base = 'https://global.example.invalid/v1'
    h.openai_model = 'global-model'
    h.openai_max_seed_artists = 5
    h.openai_extra_headers = '{"X-Private-Token": "FAKE-GLOBAL-HEADER"}'
    h.openai_recommender = SimpleNamespace(model='global-model')
    return h

def test_custom_endpoint_does_not_inherit_global_credentials(monkeypatch):
    monkeypatch.setattr(data, 'OpenAIRecommender', lambda **kw: kw)
    result = handler().get_openai_recommender_for_user(SimpleNamespace(
        openai_api_base='https://user-controlled.example.invalid/v1'))
    assert result['api_key'] != 'FAKE-GLOBAL-KEY', result
    assert result['default_headers'] is None, result

def test_model_only_override_is_honored(monkeypatch):
    monkeypatch.setattr(data, 'OpenAIRecommender', lambda **kw: SimpleNamespace(**kw))
    result = handler().get_openai_recommender_for_user(SimpleNamespace(openai_model='user-model'))
    assert result.model == 'user-model'

@pytest.mark.parametrize('global_available', [False, True])
def test_personal_lastfm_uses_user_keys(monkeypatch, global_available):
    h = handler()
    h.last_fm_user_service = Mock()
    h.last_fm_user_service.get_recommended_artists.return_value = []
    h.last_fm_user_service.get_top_artists.return_value = []
    if not global_available:
        h.last_fm_user_service = None
    personal = Mock()
    personal.get_recommended_artists.return_value = []
    personal.get_top_artists.return_value = []
    factory = Mock(return_value=personal)
    monkeypatch.setattr(data, 'LastFmUserService', factory)
    h._fetch_lastfm_personal_artists('listener', SimpleNamespace(lastfm_api_key='USER-KEY', lastfm_api_secret='USER-SECRET'))
    factory.assert_called_once_with('USER-KEY', 'USER-SECRET')

def test_oidc_users_can_configure_api_keys(app, client):
    with app.app_context():
        user = User(username='oidc-review', oidc_id='review-subject')
        db.session.add(user)
        db.session.commit()
        uid = user.id
    with client.session_transaction() as session:
        session['_user_id'] = str(uid)
        session['_fresh'] = True
    response = client.get('/profile')
    assert response.status_code == 200
    assert b'name="openai_api_key"' in response.data
    assert b'name="new_password"' not in response.data
    client.post('/profile', data={'openai_api_key': 'PERSONAL', 'openai_model': 'my-model'})
    with app.app_context():
        assert db.session.get(User, uid).openai_api_key == 'PERSONAL'
    client.post('/profile', data={'openai_api_key': '', 'openai_model': ''})
    with app.app_context():
        assert db.session.get(User, uid).openai_api_key is None


@pytest.mark.parametrize('user', [None, SimpleNamespace(), SimpleNamespace(openai_api_key='')])
def test_no_overrides_reuse_global_client(user):
    h = handler()
    assert h.get_openai_recommender_for_user(user) is h.openai_recommender


@pytest.mark.parametrize('field,value,argument', [
    ('openai_model', 'personal-model', 'model'),
    ('openai_max_seed_artists', 7, 'max_seed_artists'),
    ('openai_extra_headers', '{"X-Personal": "yes"}', 'default_headers'),
    ('openai_api_key', 'PERSONAL-KEY', 'api_key'),
])
def test_individual_overrides_preserve_global_endpoint(monkeypatch, field, value, argument):
    monkeypatch.setattr(data, 'OpenAIRecommender', lambda **kw: kw)
    result = handler().get_openai_recommender_for_user(SimpleNamespace(**{field: value}))
    expected = {'X-Personal': 'yes'} if argument == 'default_headers' else value
    assert result[argument] == expected
    assert result['base_url'] == 'https://global.example.invalid/v1'
    if field != 'openai_api_key':
        assert result['api_key'] == 'FAKE-GLOBAL-KEY'


@pytest.mark.parametrize('personal_key', [None, 'PERSONAL-KEY'])
def test_real_sdk_client_isolates_personal_endpoint(monkeypatch, personal_key):
    monkeypatch.setenv('OPENAI_API_KEY', 'FAKE-ENV-SECRET')
    h = handler()
    user = SimpleNamespace(openai_api_base='https://personal.example.invalid/v1', openai_api_key=personal_key)
    recommender = h.get_openai_recommender_for_user(user)
    try:
        assert recommender.client.api_key == (personal_key or 'not-provided')
        assert 'X-Private-Token' not in recommender.client.default_headers
    finally:
        recommender.client.close()


@pytest.mark.parametrize('field,global_field', [
    ('lastfm_api_key', 'last_fm_api_key'), ('lastfm_api_secret', 'last_fm_api_secret'),
    ('youtube_api_key', 'youtube_api_key'),
])
def test_service_key_fallback(field, global_field):
    h = handler()
    setattr(h, global_field, 'GLOBAL')
    getter = getattr(h, 'get_' + field)
    assert getter(None) == 'GLOBAL'
    assert getter(SimpleNamespace(**{field: ''})) == 'GLOBAL'
    assert getter(SimpleNamespace(**{field: 'PERSONAL'})) == 'PERSONAL'


def test_personal_lastfm_without_overrides_reuses_global_service():
    h = handler()
    service = Mock()
    service.get_recommended_artists.return_value = [SimpleNamespace(name='Artist')]
    h.last_fm_user_service = service
    assert h._fetch_lastfm_personal_artists('listener', SimpleNamespace()) == ['Artist']
    service.get_recommended_artists.assert_called_once_with('listener', limit=50)


def test_personal_lastfm_orchestration_passes_user(tmp_path, monkeypatch):
    from test_data_handler_core import _make_handler
    h, _ = _make_handler(tmp_path)
    user = SimpleNamespace(username='listener', lastfm_username='listener', lastfm_api_key='PERSONAL', lastfm_api_secret='SECRET')
    h.last_fm_user_service = Mock()
    monkeypatch.setattr(h, '_resolve_user', lambda uid: user)
    fetch = Mock(return_value=[])
    monkeypatch.setattr(h, '_fetch_lastfm_personal_artists', fetch)
    h.personal_recommendations('sid', 'lastfm')
    fetch.assert_called_once_with('listener', user)
