import json

import pytest

import generate

DATA = {'lifetime': {'runs': 1, 'km': 5}, 'years': [{'year': 2026}], 'zones_by_year': [],
        'zodiac': [{'sign': 'Waga'}], 'esoteric': {'p': 0.1}}


def build(tmp_path, monkeypatch, script):
    monkeypatch.setattr(generate, 'HERE', tmp_path)
    (tmp_path / 'template.html').write_text(f'<script>\nconst DATA = {{}};\n{script}\n</script>')
    generate._inline(DATA)
    (tmp_path / 'data.json').write_text(json.dumps(DATA))
    html = (tmp_path / 'index.html').read_text()
    return json.loads(html.split('const DATA = ', 1)[1].split(';\n', 1)[0])


def test_page_carries_only_the_keys_the_template_reads(tmp_path, monkeypatch):
    page = build(tmp_path, monkeypatch,
                 "f(DATA.lifetime.km); DATA.years.map(g); DATA['zones_by_year'].length;")
    assert set(page) == {'lifetime', 'years', 'zones_by_year'}
    generate.validate_output(tmp_path)


@pytest.mark.parametrize('script', [
    '',                                   # template reads nothing we can see
    'const k = "zodiac"; DATA[k];',       # computed key
    'render(DATA);',                      # whole object handed on
    'const {years, zodiac} = DATA;',      # destructuring
])
def test_page_keeps_everything_when_reads_cannot_be_told(tmp_path, monkeypatch, script):
    assert build(tmp_path, monkeypatch, 'DATA.years; ' + script if script else script) == DATA
    generate.validate_output(tmp_path)


def test_validation_rejects_a_page_missing_a_key_the_template_reads(tmp_path, monkeypatch):
    build(tmp_path, monkeypatch, 'DATA.lifetime; DATA.years;')
    (tmp_path / 'index.html').write_text(
        '<script>\nconst DATA = {"lifetime":{"runs":1,"km":5}};\nDATA.lifetime; DATA.years;\n</script>')
    with pytest.raises(ValueError):
        generate.validate_output(tmp_path)
