"""Offline validation of the calibration-only B0 structured scenarios; no naturalization or model call."""
import argparse
from collections import Counter
import glob
import json
from pathlib import Path
from typing import Literal

import validate_generator_qualification_fixtures as gq

ROOT = gq.ROOT
DIRECTORY = ROOT / 'data/b0-calibration'
PURPOSE = 'B0-CALIBRATION-ONLY'
SCHEMA = 'b0-calibration-reference/1.0.0'
MANIFEST_SCHEMA = 'b0-calibration-manifest/1.0.0'
ID_PREFIX = 'b0cal-'
ALLOCATION_OFFSET = 3
ALLOCATION_RULE = ('Qualification allocation rule evaluated at domain index i + 3, for the secondary-update '
                   'allocation and for the rotation of the initial-event key order. '
                   'Calibration-only; not a final CRST allocation decision.')
PROHIBITED_USES = ['final confirmatory CRST cases', 'Generator Qualification fixtures',
                   'Model Qualification fixtures', 'LongMemEval-S material', 'capability probe material']
ORIGIN = ('Independently authored synthetic structured truth; no external corpus content, qualification '
          'fixture content or model naturalization.')
PRIOR_SOURCES = ('data/generator-qualification/**/*.json', 'data/generator-capability-probe/*.json',
                 'data/retrieval-calibration/calibration.json', 'results/model-qualification/*/qualification.json')


class Fixture(gq.Strict):
    schema_version: Literal['b0-calibration-reference/1.0.0']
    fixture_id: gq.Text
    purpose: Literal['B0-CALIBRATION-ONLY']
    reference: gq.Reference


def scenario_id(index):
    return f'{ID_PREFIX}{gq.SLUGS[index]}-01'


def allocation(index):
    return gq.allocation(index + ALLOCATION_OFFSET)


def initial_keys(index):
    shift = (index + ALLOCATION_OFFSET) % 7
    return list(gq.KEYS[shift:] + gq.KEYS[:shift])


def reference_schema():
    schema = Fixture.model_json_schema()
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    schema['$id'] = 'urn:crst:b0-calibration-reference:1.0.0'
    schema['description'] = ('Reference-only truth for B0 calibration scenarios. Model-facing input is derived by '
                             'the frozen qualification projection. Identifier uniqueness, trajectories and '
                             'cross-file constraints require the validator.')
    return schema


def qualification_view(fixture):
    """The frozen reference-layer validator sees the same structure; only identity fields differ."""
    slug = gq.SLUGS[gq.DOMAINS.index(fixture['reference']['domain'])]
    return {**fixture, 'schema_version': 'generator-qualification-reference/1.0.0',
            'fixture_id': f'gq-{slug}-01', 'purpose': gq.PURPOSE}


def validate_fixture(fixture):
    Fixture.model_validate(fixture)
    index = gq.DOMAINS.index(fixture['reference']['domain'])
    gq.require(fixture['fixture_id'] == scenario_id(index), 'Scenario identity/domain mismatch')
    return gq.validate_fixture(qualification_view(fixture))


def validate_set(fixtures):
    gq.require(len(fixtures) == 12, 'Exactly twelve scenarios required')
    gq.require(len({f['fixture_id'] for f in fixtures}) == 12, 'Duplicate scenario ID')
    gq.require(Counter(f['reference']['domain'] for f in fixtures) == Counter(gq.DOMAINS),
               'One scenario per domain')
    return [validate_fixture(f) for f in fixtures]


def manifest_entry(fixture, raw):
    return {**gq.manifest_entry(fixture, raw), 'purpose': PURPOSE}


def reserved_exclusions(fixtures):
    """Identifiers and values that later final-CRST construction must not reuse."""
    entities = [e for f in fixtures for e in f['reference']['entities']]
    return {'scenario_ids': sorted(f['fixture_id'] for f in fixtures),
            'entity_ids': sorted(e['entity_id'] for e in entities),
            'entity_names': sorted(e['name'] for e in entities),
            'attribute_ids': sorted({a['attribute_id'] for f in fixtures for a in f['reference']['attributes']}),
            'state_values': sorted({v for f in fixtures for k in f['reference']['state_keys']
                                    for v in k['value_inventory']})}


def leaves(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from leaves(item)


def fold(text):
    return ' '.join(gq.normalized_words(text))


def prior_material():
    """Exact folded string leaves and folded full text of every known earlier material set."""
    strings, text = set(), []
    for pattern in PRIOR_SOURCES:
        for path in sorted(glob.glob(str(ROOT / pattern), recursive=True)):
            for leaf in leaves(gq.read(path)):
                strings.add(fold(leaf))
                text.append(fold(leaf))
    return strings, ' | '.join(text)


def check_separation(fixtures):
    """No B0 identity, name, attribute, value or opaque code may appear in earlier material sets."""
    strings, text = prior_material()
    exclusions = reserved_exclusions(fixtures)
    meanings = sorted({a['meaning'] for f in fixtures for a in f['reference']['attributes']})
    for kind, atoms in (*exclusions.items(), ('attribute_meanings', meanings)):
        for atom in atoms:
            gq.require(fold(atom) not in strings, f'B0 {kind} reuses earlier material: {atom}')
    for name in (*exclusions['entity_names'], *exclusions['entity_ids']):
        gq.require(f' {fold(name)} ' not in f' {text} ', f'B0 name appears inside earlier material: {name}')
    codes = [k['initial_value'] for f in fixtures for k in f['reference']['state_keys']
             if k['state_key'] == 'k_n2']
    for code in codes:
        gq.require(fold(code) not in text, f'B0 opaque code appears inside earlier material: {code}')


def validate_directory(directory=DIRECTORY):
    directory = Path(directory)
    manifest = gq.read(directory / 'manifest.json')
    fields = {'schema_version', 'status', 'total_scenarios', 'purpose', 'versions', 'construction_source_commit',
              'reference_schema_sha256', 'allocation_rule', 'same_set_for', 'prohibited_uses',
              'not_final_crst_data', 'not_generator_qualification_data', 'origin', 'reserved_exclusions',
              'coverage_summary', 'scenarios'}
    gq.require(set(manifest) == fields, 'Manifest fields')
    gq.require(manifest['schema_version'] == MANIFEST_SCHEMA and manifest['status'] == 'FROZEN'
               and manifest['total_scenarios'] == 12 and manifest['purpose'] == PURPOSE
               and manifest['versions'] == gq.VERSIONS and manifest['same_set_for'] == ['G1', 'G2']
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
    gq.require([e['fixture_path'] for e in manifest['scenarios']] == [f'fixtures/{s}.json' for s in gq.SLUGS],
               'Manifest paths/order')
    gq.require({p.name for p in (directory / 'fixtures').iterdir()} == {f'{s}.json' for s in gq.SLUGS},
               'Unexpected/missing scenario files')
    fixtures = [gq.read(directory / e['fixture_path']) for e in manifest['scenarios']]
    validate_set(fixtures)
    for fixture, entry in zip(fixtures, manifest['scenarios']):
        gq.require(entry == manifest_entry(fixture, (directory / entry['fixture_path']).read_bytes()),
                   'Manifest hash/summary mismatch')
    gq.require(manifest['reserved_exclusions'] == reserved_exclusions(fixtures), 'Reserved exclusions')
    gq.require(manifest['coverage_summary'] == sorted({c for f in fixtures for c in f['reference']['coverage']}),
               'Coverage summary')
    check_separation(fixtures)
    return manifest, fixtures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path, default=DIRECTORY)
    args = parser.parse_args()
    validate_directory(args.directory)
    print('VALID: 12 calibration-only B0 scenarios; no naturalization or model call executed.')
    print('Manifest SHA-256:', gq.sha((args.directory / 'manifest.json').read_bytes()))


if __name__ == '__main__':
    main()
