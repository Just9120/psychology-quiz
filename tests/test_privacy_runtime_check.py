"""Wrong live command, logging driver or identity must fail before delivery OK."""
from copy import deepcopy
import pytest
from scripts.privacy_runtime_check import verify

SHA = 'a' * 40


def fixture(service='psych_quiz_miniapp_api'):
    return {'Config': {'Cmd': ['python', 'scripts/runtime_log.py', 'api'], 'Labels': {
        'com.docker.compose.project': 'psychology-quiz',
        'com.docker.compose.service': service,
        'org.opencontainers.image.revision': SHA}},
        'HostConfig': {'LogConfig': {'Type': 'none'}}, 'State': {'Running': True}}


def test_correct_runtime_and_rejection_of_old_unbounded_logger():
    owned = fixture()
    verify(owned, 'psych_quiz_miniapp_api', SHA)
    changed = deepcopy(owned)
    changed['HostConfig']['LogConfig']['Type'] = 'json-file'
    with pytest.raises(ValueError, match='settings_mismatch'):
        verify(changed, 'psych_quiz_miniapp_api', SHA)
    changed = deepcopy(owned)
    changed['Config']['Cmd'] = ['uvicorn', 'app.miniapp_fastapi_runtime:app']
    with pytest.raises(ValueError, match='settings_mismatch'):
        verify(changed, 'psych_quiz_miniapp_api', SHA)


@pytest.mark.parametrize('kind', ['revision', 'service', 'stopped'])
def test_foreign_or_stopped_runtime_is_rejected(kind):
    owned = fixture()
    if kind == 'revision':
        owned['Config']['Labels']['org.opencontainers.image.revision'] = 'b' * 40
    elif kind == 'service':
        owned['Config']['Labels']['com.docker.compose.service'] = 'other-project'
    else:
        owned['State']['Running'] = False
    with pytest.raises(ValueError, match='unexpected_runtime_identity'):
        verify(owned, 'psych_quiz_miniapp_api', SHA)
