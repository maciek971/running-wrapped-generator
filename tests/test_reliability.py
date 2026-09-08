import io
import json
import zipfile

import pytest

import fetch_garmin
import generate


def test_inline_preserves_hostile_text_without_ending_script(tmp_path, monkeypatch):
    monkeypatch.setattr(generate, 'HERE', tmp_path)
    (tmp_path / 'template.html').write_text('<script>\nconst DATA = {};\n</script>')
    data = {'name': '</ScRiPt><script>alert(1)</script><!-- & Łódź'}
    generate._inline(data)
    html = (tmp_path / 'index.html').read_text()
    assert html.lower().count('</script>') == 1
    serialized = html.split('const DATA = ', 1)[1].split(';\n', 1)[0]
    assert json.loads(serialized) == data


@pytest.mark.parametrize(('seconds', 'expected'), [(359.6, '6:00'), (59.9, '1:00'), (328.28, '5:28'), (None, None)])
def test_pace_rounds_before_splitting_minutes(seconds, expected):
    assert generate.fmt_pace(seconds) == expected


def archive(content=b'fit', filename='activity.fit'):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr(filename, content)
    return buf.getvalue()


class FakeGarmin:
    def __init__(self, blob):
        self.blob = blob

    def get_activities(self, start, limit):
        return [{'activityId': 1, 'activityName': 'Run', 'startTimeGMT': '2026-09-01'}]

    def download_activity(self, aid, dl_fmt):
        if isinstance(self.blob, Exception):
            raise self.blob
        return self.blob


def prepare_fetch(tmp_path, monkeypatch, blob):
    monkeypatch.setattr(fetch_garmin, 'HERE', tmp_path)
    monkeypatch.delenv('WRAPPED_CACHE', raising=False)
    monkeypatch.setattr(fetch_garmin, '_login', lambda: FakeGarmin(blob))
    monkeypatch.setattr(fetch_garmin, 'profile_defaults', lambda g: {})
    monkeypatch.setattr(fetch_garmin, '_save_records', lambda g, cache: None)


@pytest.mark.parametrize('blob', [RuntimeError('download failed'), archive(filename='readme.txt'), archive(content=b'')])
def test_incomplete_download_fails_instead_of_reporting_success(tmp_path, monkeypatch, blob):
    prepare_fetch(tmp_path, monkeypatch, blob)
    with pytest.raises(SystemExit) as error:
        fetch_garmin.main()
    assert error.value.code
    manifest = tmp_path / 'cache/manifest.json'
    assert not manifest.exists() or '1' not in json.loads(manifest.read_text())


@pytest.mark.parametrize('existing', [None, b''])
def test_manifest_entry_without_fit_is_downloaded_again(tmp_path, monkeypatch, existing):
    prepare_fetch(tmp_path, monkeypatch, archive())
    fit = tmp_path / 'cache/fit'
    fit.mkdir(parents=True)
    (tmp_path / 'cache/manifest.json').write_text(json.dumps({'1': {'fit_file': '1.fit'}}))
    if existing is not None:
        (fit / '1.fit').write_bytes(existing)
    fetch_garmin.main()
    assert (fit / '1.fit').read_bytes() == b'fit'


def test_generated_page_validation_rejects_missing_or_changed_data(tmp_path, monkeypatch):
    monkeypatch.setattr(generate, 'HERE', tmp_path)
    (tmp_path / 'template.html').write_text('<html><script>\nconst DATA = {};\n</script></html>')
    data = {'lifetime': {'runs': 1, 'km': 5}, 'years': [{'year': 2026}], 'zones_by_year': []}
    generate._inline(data)
    (tmp_path / 'data.json').write_text(json.dumps(data))
    validate = getattr(generate, 'validate_output', None)
    assert callable(validate), 'generated page needs a validation gate'
    validate(tmp_path)
    (tmp_path / 'index.html').write_text('<html><script>const DATA = {};</script></html>')
    with pytest.raises(ValueError):
        validate(tmp_path)


def test_generated_page_validation_rejects_nonfinite_numbers(tmp_path, monkeypatch):
    monkeypatch.setattr(generate, 'HERE', tmp_path)
    (tmp_path / 'template.html').write_text('<script>\nconst DATA = {};\n</script>')
    data = {'lifetime': {'runs': 1, 'km': float('nan')}, 'years': [2026], 'zones_by_year': []}
    generate._inline(data)
    (tmp_path / 'data.json').write_text(json.dumps(data))
    validate = getattr(generate, 'validate_output', None)
    assert callable(validate), 'generated page needs a validation gate'
    with pytest.raises(ValueError):
        validate(tmp_path)


def test_partial_refresh_keeps_successful_downloads_for_retry(tmp_path, monkeypatch):
    prepare_fetch(tmp_path, monkeypatch, archive())

    class PartialGarmin(FakeGarmin):
        def get_activities(self, start, limit):
            return [{'activityId': 1}, {'activityId': 2}]

        def download_activity(self, aid, dl_fmt):
            if aid == '2':
                raise RuntimeError('temporary outage')
            return self.blob

    monkeypatch.setattr(fetch_garmin, '_login', lambda: PartialGarmin(archive()))
    with pytest.raises(SystemExit):
        fetch_garmin.main()
    assert (tmp_path / 'cache/fit/1.fit').read_bytes() == b'fit'
    assert set(json.loads((tmp_path / 'cache/manifest.json').read_text())) == {'1'}


def test_existing_nonempty_fit_is_not_downloaded_again(tmp_path, monkeypatch):
    prepare_fetch(tmp_path, monkeypatch, RuntimeError('must not download cached activity'))
    fit = tmp_path / 'cache/fit'
    fit.mkdir(parents=True)
    (fit / '1.fit').write_bytes(b'cached')
    (tmp_path / 'cache/manifest.json').write_text(json.dumps({'1': {'fit_file': '1.fit'}}))
    fetch_garmin.main()
    assert (fit / '1.fit').read_bytes() == b'cached'
