"""Offline validation of the pilot-only CRST structured scenarios; no naturalization or model call."""
import argparse
import glob
from pathlib import Path
from typing import Literal

import crst_policies as pol
import crst_scoring as scoring
import validate_b0_calibration_material as b0v
import validate_generator_qualification_fixtures as gq

ROOT = gq.ROOT
DIRECTORY = ROOT / 'data/crst-small-pilot'
PURPOSE = 'CRST-SMALL-PILOT-ONLY'
SCHEMA = 'crst-small-pilot-reference/1.0.0'
MANIFEST_SCHEMA = 'crst-small-pilot-manifest/1.0.0'
ALLOCATION_OFFSET = 5
ALLOCATION_RULE = ('Qualification allocation rule evaluated at domain index i + 5, for the secondary-update '
                   'allocation and for the rotation of the initial-event key order. '
                   'Pilot-only; not a final CRST allocation decision.')
SCENARIOS = (
    {'scenario_id': 'pilot-scheduling-01', 'domain': 'Scheduling', 'slug': 'scheduling', 'generator': 'G1',
     'model': 'openai/gpt-5.6-sol'},
    {'scenario_id': 'pilot-travel-01', 'domain': 'Travel', 'slug': 'travel', 'generator': 'G2',
     'model': 'anthropic/claude-fable-5.1'})
PROHIBITED_USES = ['final confirmatory CRST cases', 'Generator Qualification fixtures',
                   'Model Qualification fixtures', 'Dense Retrieval Qualification material',
                   'B0 calibration material', 'LongMemEval-S material', 'capability probe material',
                   'effect-size estimation, policy ranking or power analysis']
ORIGIN = ('Independently authored synthetic structured truth; no external corpus content, earlier fixture '
          'content or model naturalization.')
PRIOR_SOURCES = (*b0v.PRIOR_SOURCES, 'data/b0-calibration/**/*.json')
LONGMEMEVAL_RAW = ROOT / 'data/longmemeval/raw/longmemeval_s_cleaned.json'
# Words that would encode status or time inside a stored candidate.
STATUS_WORDS = frozenset({'current', 'now', 'latest', 'previous', 'new', 'newest', 'old', 'former', 'prior',
                          'updated', 'changed', 'revised', 'original', 'final', 'recent', 'today', 'next'})


class Fixture(gq.Strict):
    schema_version: Literal['crst-small-pilot-reference/1.0.0']
    fixture_id: gq.Text
    purpose: Literal['CRST-SMALL-PILOT-ONLY']
    reference: gq.Reference


def spec_for(fixture_id):
    matches = [s for s in SCENARIOS if s['scenario_id'] == fixture_id]
    gq.require(len(matches) == 1, 'Unknown pilot scenario')
    return matches[0]


def allocation(index):
    return gq.allocation(index + ALLOCATION_OFFSET)


def initial_keys(index):
    shift = (index + ALLOCATION_OFFSET) % 7
    return list(gq.KEYS[shift:] + gq.KEYS[:shift])


def reference_schema():
    schema = Fixture.model_json_schema()
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    schema['$id'] = 'urn:crst:small-pilot-reference:1.0.0'
    schema['description'] = ('Reference-only truth for the CRST Small Pilot scenarios. Model-facing input is '
                             'derived by the frozen qualification projection. Identifier uniqueness, '
                             'trajectories and cross-file constraints require the validator.')
    return schema


def qualification_view(fixture):
    slug = gq.SLUGS[gq.DOMAINS.index(fixture['reference']['domain'])]
    return {**fixture, 'schema_version': 'generator-qualification-reference/1.0.0',
            'fixture_id': f'gq-{slug}-01', 'purpose': gq.PURPOSE}


def words(text):
    return set(gq.normalized_words(text))


def check_candidates(fixture):
    """Canonical rendering: round trip, time-neutral wording, distinct meanings, distinguishable targets."""
    r = fixture['reference']
    names = {e['entity_id']: e['name'] for e in r['entities']}
    attributes = {a['attribute_id']: a['meaning'] for a in r['attributes']}
    keys = {k['state_key']: k for k in r['state_keys']}
    for entity in r['entities']:
        gq.require(not words(entity['name']) & STATUS_WORDS, f'Status wording in entity name: {entity["name"]}')
        gq.require(', the ' not in entity['name'], 'Entity name would make the rendering ambiguous')
    for meaning in attributes.values():
        gq.require(not words(meaning) & STATUS_WORDS, f'Status wording in attribute meaning: {meaning}')
        gq.require(' is ' not in meaning, 'Attribute meaning would make the rendering ambiguous')
    for key in keys.values():
        for value in key['value_inventory']:
            gq.require(not words(value) & STATUS_WORDS, f'Status wording in value: {value}')
            gq.require(not value.endswith('.'), 'Value would make the rendering ambiguous')
    pairs = [(k['entity_id'], attributes[k['attribute_id']]) for k in keys.values()]
    gq.require(len(set(pairs)) == 7, 'Attribute meanings must be distinct within an entity')
    gq.require(len({(names[e], m) for e, m in pairs}) == 7, 'Duplicate rendered subject')
    for variant in gq.VARIANTS:
        for event in pol.reference_events(r, variant, 'M3'):
            entity, meaning, value = pol.parse_candidate(event['candidate'])
            key = keys[event['state_key']]
            gq.require((entity, meaning) == (names[key['entity_id']], attributes[key['attribute_id']]),
                       'Candidate round trip changed the subject')
            gq.require(event['candidate'] == pol.render_candidate(entity, meaning, value), 'Renderer drift')
        target = pol.target_answer(r, variant)
        scoring.assert_distinct(target['current'], target['superseded'])
    target_values = keys['k_target']['value_inventory']
    normalized = [scoring.normalize(v) for v in [*target_values, *keys['k_hard']['value_inventory']]]
    gq.require(len(set(normalized)) == len(normalized), 'Target and distractor values collide after normalization')
    for value in [v for k in keys.values() for v in k['value_inventory']]:
        gq.require(value == value.strip() and '\n' not in value, 'Value must be single-line without edge whitespace')


def validate_fixture(fixture):
    Fixture.model_validate(fixture)
    spec = spec_for(fixture['fixture_id'])
    gq.require(fixture['reference']['domain'] == spec['domain'], 'Scenario identity/domain mismatch')
    payload = gq.validate_fixture(qualification_view(fixture))
    gq.require(fixture['reference']['initial_order'] == dict(zip(gq.EVENTS[:7], initial_keys(
        gq.DOMAINS.index(spec['domain'])))), 'Initial order rule')
    check_candidates(fixture)
    return payload


def validate_set(fixtures):
    gq.require([f['fixture_id'] for f in fixtures] == [s['scenario_id'] for s in SCENARIOS],
               'Exactly the two pilot scenarios in order')
    return [validate_fixture(f) for f in fixtures]


def manifest_entry(fixture, raw):
    spec = spec_for(fixture['fixture_id'])
    return {**gq.manifest_entry(fixture, raw), 'purpose': PURPOSE, 'generator': spec['generator'],
            'generator_model': spec['model']}


def reserved_exclusions(fixtures):
    base = b0v.reserved_exclusions(fixtures)
    return {**base, 'attribute_meanings': sorted({a['meaning'] for f in fixtures
                                                  for a in f['reference']['attributes']})}


def prior_material():
    strings, text = set(), []
    for pattern in PRIOR_SOURCES:
        for path in sorted(glob.glob(str(ROOT / pattern), recursive=True)):
            for leaf in b0v.leaves(gq.read(path)):
                strings.add(b0v.fold(leaf))
                text.append(b0v.fold(leaf))
    return strings, ' | '.join(text)


_LME = {}


def longmemeval_text():
    if 'text' not in _LME:
        _LME['text'] = ' '.join(gq.normalized_words(LONGMEMEVAL_RAW.read_text(encoding='utf-8'))) \
            if LONGMEMEVAL_RAW.exists() else None
    return _LME['text']


def check_separation(fixtures, longmemeval=True):
    """No pilot identity, name, attribute, value or opaque code may appear in earlier material sets."""
    strings, text = prior_material()
    exclusions = reserved_exclusions(fixtures)
    for kind, atoms in exclusions.items():
        for atom in atoms:
            gq.require(b0v.fold(atom) not in strings, f'Pilot {kind} reuses earlier material: {atom}')
    for name in (*exclusions['entity_names'], *exclusions['entity_ids']):
        gq.require(f' {b0v.fold(name)} ' not in f' {text} ', f'Pilot name appears inside earlier material: {name}')
    codes = [k['initial_value'] for f in fixtures for k in f['reference']['state_keys'] if k['state_key'] == 'k_n2']
    for code in codes:
        gq.require(b0v.fold(code) not in text, f'Pilot opaque code appears inside earlier material: {code}')
    if longmemeval and longmemeval_text() is not None:
        corpus = f' {longmemeval_text()} '
        for atom in (*exclusions['entity_names'], *codes):
            gq.require(f' {b0v.fold(atom)} ' not in corpus, f'Pilot identifier appears in LongMemEval-S: {atom}')


def validate_directory(directory=DIRECTORY, longmemeval=True):
    directory = Path(directory)
    manifest = gq.read(directory / 'manifest.json')
    fields = {'schema_version', 'status', 'total_scenarios', 'purpose', 'versions', 'construction_source_commit',
              'reference_schema_sha256', 'allocation_rule', 'candidate_template', 'generator_assignment',
              'prohibited_uses', 'not_final_crst_data', 'not_generator_qualification_data', 'origin',
              'reserved_exclusions', 'coverage_summary', 'scenarios'}
    gq.require(set(manifest) == fields, 'Manifest fields')
    gq.require(manifest['schema_version'] == MANIFEST_SCHEMA and manifest['status'] == 'FROZEN'
               and manifest['total_scenarios'] == 2 and manifest['purpose'] == PURPOSE
               and manifest['versions'] == gq.VERSIONS and manifest['candidate_template'] == pol.TEMPLATE
               and manifest['generator_assignment'] == {s['scenario_id']: s['generator'] for s in SCENARIOS}
               and manifest['prohibited_uses'] == PROHIBITED_USES and manifest['not_final_crst_data'] is True
               and manifest['not_generator_qualification_data'] is True
               and manifest['allocation_rule'] == ALLOCATION_RULE and manifest['origin'] == ORIGIN,
               'Manifest contract')
    commit = manifest['construction_source_commit']
    gq.require(type(commit) is str and len(commit) == 40 and all(c in '0123456789abcdef' for c in commit),
               'Construction commit')
    schema_file = directory / 'reference-schema.json'
    gq.require(gq.sha(schema_file.read_bytes()) == manifest['reference_schema_sha256']
               and gq.read(schema_file) == reference_schema(), 'Reference schema drift')
    gq.require([e['fixture_path'] for e in manifest['scenarios']] == [f'fixtures/{s["slug"]}.json'
                                                                       for s in SCENARIOS],
               'Manifest paths/order')
    gq.require({p.name for p in (directory / 'fixtures').iterdir()} == {f'{s["slug"]}.json' for s in SCENARIOS},
               'Unexpected/missing scenario files')
    fixtures = [gq.read(directory / e['fixture_path']) for e in manifest['scenarios']]
    validate_set(fixtures)
    for fixture, entry in zip(fixtures, manifest['scenarios']):
        gq.require(entry == manifest_entry(fixture, (directory / entry['fixture_path']).read_bytes()),
                   'Manifest hash/summary mismatch')
    gq.require(manifest['reserved_exclusions'] == reserved_exclusions(fixtures), 'Reserved exclusions')
    gq.require(manifest['coverage_summary'] == sorted({c for f in fixtures for c in f['reference']['coverage']}),
               'Coverage summary')
    check_separation(fixtures, longmemeval)
    return manifest, fixtures


def with_scenario_id(fixture):
    """Reference dict for the policy engine, carrying its scenario identity."""
    return {**fixture['reference'], 'scenario_id': fixture['fixture_id']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path, default=DIRECTORY)
    args = parser.parse_args()
    validate_directory(args.directory)
    print('VALID: 2 pilot-only CRST scenarios; no naturalization or model call executed.')
    print('Manifest SHA-256:', gq.sha((args.directory / 'manifest.json').read_bytes()))


if __name__ == '__main__':
    main()
