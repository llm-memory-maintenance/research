"""Build synthetic calibration data with fixed templates, without a model or external data.

Protocol checkpoint: 24eb542. The lexicon below was authored independently of
LongMemEval-S and the Model Qualification content, and the builder reads
neither. Its source provenance rests on this construction, not on an
external-corpus similarity audit. No reader, embedding, retrieval or
naturalization service is involved.
"""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/retrieval-calibration/calibration.json'
SEED = 20260917
BASELINE = datetime(2020, 1, 1, tzinfo=timezone.utc)
SIZES = (16, 64, 128)

# Each family has distinct but meaningfully related state keys. These are
# semantic relationships for validating distractors, not retrieval features.
# Tuple fields: family, values, fact templates, direct questions, paraphrases.
ATTRIBUTES = {
    'residence_city': (
        'city', ('Velin', 'Orava', 'Delsin', 'Torven', 'Selvik', 'Pevora'),
        ('{entity} lives in {value}.', '{entity}\'s home city is {value}.', 'The city where {entity} resides is {value}.'),
        ('Which city does {entity} live in?', 'What is {entity}\'s home city?'),
        ('Where does {entity} make a home now?', 'Which city is home for {entity} these days?')),
    'workplace_city': (
        'city', ('Torven', 'Velin', 'Pevora', 'Selvik', 'Delsin', 'Orava'),
        ('{entity} works in {value}.', '{entity}\'s workplace city is {value}.', 'The city hosting {entity}\'s workplace is {value}.'),
        ('In which city does {entity} work?', 'What is {entity}\'s workplace city?'),
        ('Which city hosts {entity}\'s place of employment?', 'Where is {entity}\'s job based, by city?')),
    'preferred_beverage': (
        'dining', ('oolong tea', 'pear juice', 'sparkling water', 'filter coffee', 'mint tea', 'oat milk'),
        ('{entity}\'s preferred beverage is {value}.', '{entity} prefers {value} as a beverage.', 'For a drink, {entity} favors {value}.'),
        ('What is {entity}\'s preferred beverage?', 'Which beverage does {entity} prefer?'),
        ('What would {entity} choose to drink?', 'Which drink is {entity}\'s first choice?')),
    'preferred_cuisine': (
        'dining', ('Greek', 'Korean', 'Ethiopian', 'Peruvian', 'Turkish', 'Vietnamese'),
        ('{entity}\'s preferred cuisine is {value}.', '{entity} prefers {value} cuisine.', 'For cuisine, {entity} favors {value}.'),
        ('Which cuisine does {entity} prefer?', 'What is {entity}\'s preferred cuisine?'),
        ('Which style of cooking is {entity}\'s first choice?', 'What culinary tradition does {entity} favor?')),
    'commute_method': (
        'transport', ('tram', 'bicycle', 'bus', 'train', 'walking', 'ferry'),
        ('{entity}\'s commute method is {value}.', '{entity} uses {value} for commuting.', 'For the commute, {entity} chooses {value}.'),
        ('What commute method does {entity} use?', 'How does {entity} commute?'),
        ('What means of transport gets {entity} to work?', 'What is {entity}\'s way of traveling to the job?')),
    'leisure_transport': (
        'transport', ('bicycle', 'ferry', 'walking', 'tram', 'train', 'bus'),
        ('{entity}\'s leisure transport is {value}.', '{entity} uses {value} for leisure trips.', 'For leisure journeys, {entity} chooses {value}.'),
        ('What transport does {entity} use for leisure trips?', 'What is {entity}\'s leisure transport?'),
        ('How does {entity} travel on recreational outings?', 'What means of getting around does {entity} choose for recreation?')),
    'exercise_day': (
        'weekly_schedule', ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'),
        ('{entity} exercises on {value}.', '{entity}\'s exercise day is {value}.', 'The day assigned to {entity}\'s exercise is {value}.'),
        ('On which day does {entity} exercise?', 'What is {entity}\'s exercise day?'),
        ('Which weekday is reserved for {entity}\'s workout?', 'When in the week is {entity}\'s fitness session?')),
    'meeting_day': (
        'weekly_schedule', ('Saturday', 'Friday', 'Thursday', 'Wednesday', 'Tuesday', 'Monday'),
        ('{entity}\'s meeting day is {value}.', '{entity} attends the weekly meeting on {value}.', 'The day assigned to {entity}\'s weekly meeting is {value}.'),
        ('What is {entity}\'s meeting day?', 'On which day is {entity}\'s weekly meeting?'),
        ('Which weekday is reserved for {entity}\'s meeting?', 'When in the week does {entity}\'s meeting take place?')),
    'study_location': (
        'venue', ('the east library', 'the riverside cafe', 'the south reading room', 'the garden pavilion', 'the north studio', 'the west learning center'),
        ('{entity} studies at {value}.', '{entity}\'s study location is {value}.', 'For studying, {entity} uses {value}.'),
        ('Where does {entity} study?', 'What is {entity}\'s study location?'),
        ('Which place does {entity} use for learning sessions?', 'Where does {entity} go to do coursework?')),
    'meeting_location': (
        'venue', ('the north studio', 'the garden pavilion', 'the east library', 'the west learning center', 'the riverside cafe', 'the south reading room'),
        ('{entity}\'s meeting location is {value}.', '{entity} attends the meeting at {value}.', 'For the meeting, {entity} uses {value}.'),
        ('Where is {entity}\'s meeting held?', 'What is {entity}\'s meeting location?'),
        ('Which venue hosts {entity}\'s meeting?', 'Where does {entity} go for the scheduled gathering?')),
    'reading_device': (
        'device', ('a tablet', 'an e-reader', 'a laptop', 'a desktop computer', 'a smartphone', 'a convertible notebook'),
        ('{entity}\'s reading device is {value}.', '{entity} uses {value} for reading.', 'For reading, {entity} chooses {value}.'),
        ('Which device does {entity} use for reading?', 'What is {entity}\'s reading device?'),
        ('On what hardware does {entity} read digital books?', 'What device serves {entity}\'s digital reading needs?')),
    'work_device': (
        'device', ('a laptop', 'a tablet', 'a desktop computer', 'a convertible notebook', 'a smartphone', 'a workstation'),
        ('{entity}\'s work device is {value}.', '{entity} uses {value} for work.', 'For work, {entity} chooses {value}.'),
        ('What is {entity}\'s work device?', 'Which device does {entity} use for work?'),
        ('What hardware does {entity} do the job on?', 'Which device handles {entity}\'s professional tasks?')),
    'jacket_color_preference': (
        'clothing_color', ('scarlet', 'ivory', 'violet', 'charcoal', 'teal', 'olive'),
        ('{entity}\'s preferred jacket color is {value}.', '{entity} prefers {value} jackets.', 'For jackets, {entity} favors {value}.'),
        ('What jacket color does {entity} prefer?', 'What is {entity}\'s preferred jacket color?'),
        ('Which shade would {entity} choose for a jacket?', 'What color is {entity}\'s first choice when selecting a jacket?')),
    'scarf_color_preference': (
        'clothing_color', ('teal', 'olive', 'scarlet', 'violet', 'ivory', 'charcoal'),
        ('{entity}\'s preferred scarf color is {value}.', '{entity} prefers {value} scarves.', 'For scarves, {entity} favors {value}.'),
        ('What scarf color does {entity} prefer?', 'What is {entity}\'s preferred scarf color?'),
        ('Which shade would {entity} choose for a scarf?', 'What color is {entity}\'s first choice when selecting a scarf?')),
    'music_subscription': (
        'subscription', ('Basic', 'Plus', 'Premium', 'Family', 'Student', 'Annual'),
        ('{entity}\'s music subscription plan is {value}.', '{entity} uses the {value} plan for music.', 'For music streaming, {entity}\'s plan is {value}.'),
        ('What is {entity}\'s music subscription plan?', 'Which music plan does {entity} use?'),
        ('Which subscription tier covers {entity}\'s music streaming?', 'What plan gives {entity} access to streamed music?')),
    'video_subscription': (
        'subscription', ('Premium', 'Basic', 'Annual', 'Student', 'Plus', 'Family'),
        ('{entity}\'s video subscription plan is {value}.', '{entity} uses the {value} plan for video.', 'For video streaming, {entity}\'s plan is {value}.'),
        ('What is {entity}\'s video subscription plan?', 'Which video plan does {entity} use?'),
        ('Which subscription tier covers {entity}\'s video streaming?', 'What plan gives {entity} access to streamed video?')),
}
ATTRIBUTE_NAMES = tuple(ATTRIBUTES)
# Fictional combinations authored here, without consulting external datasets.
ENTITIES = tuple(f'{first} {last}' for first in (
    'Zevan', 'Ruvik', 'Teyla', 'Osvin', 'Kelvo', 'Nerith', 'Pevin', 'Dovra',
    'Yelna', 'Vesko', 'Talvi', 'Wenro', 'Quelis', 'Feyra', 'Sovek', 'Lurvi',
) for last in ('Qev', 'Toril', 'Vesk', 'Nul', 'Perov', 'Zeth', 'Falun', 'Drel',
               'Kovin', 'Weral', 'Besun', 'Havor', 'Jorin', 'Solven', 'Reth', 'Yul'))


def fact_forms(entity, attribute, value):
    return tuple(t.format(entity=entity, value=value) for t in ATTRIBUTES[attribute][2])


def question_forms(entity, attribute, wording):
    index = {'direct': 3, 'paraphrased': 4}[wording]
    return tuple(t.format(entity=entity) for t in ATTRIBUTES[attribute][index])


def fact(entity, attribute, value, variant=0, tags=()):
    return {'text': fact_forms(entity, attribute, value)[variant % 3],
            'annotation': {'entity': entity, 'attribute': attribute, 'value': value,
                           'diagnostic_tags': list(tags)}}


def timestamp(minutes):
    return (BASELINE + timedelta(minutes=minutes)).isoformat().replace('+00:00', 'Z')


def build_case(case_id, serial, size, rng, *, kind=None, wording=None, stale=False):
    entity = ENTITIES[serial]
    attribute = ATTRIBUTE_NAMES[serial % len(ATTRIBUTE_NAMES)]
    related = next(a for a in ATTRIBUTE_NAMES if a != attribute and ATTRIBUTES[a][0] == ATTRIBUTES[attribute][0])
    values = ATTRIBUTES[attribute][1]
    current = values[(serial // len(ATTRIBUTE_NAMES)) % len(values)]
    previous = values[(values.index(current) + 1) % len(values)]
    records = []

    def add(subject, attr, value, tag):
        item = fact(subject, attr, value, rng.randrange(3), (tag,))
        index = len(records) + 1
        item = {'entry_id': f'{case_id}-entry-{index:03d}', **item,
                'created_time': timestamp(serial * 1000 + index * 2),
                'last_updated_time': timestamp(serial * 1000 + index * 2 + 1)}
        records.append(item)
        return item

    target = None
    if kind != 'new_key':
        target = add(entity, attribute, previous if kind == 'changed_state' else current,
                     'oracle_existing_target' if kind else 'oracle_current')
    if stale:
        # Stale version of the target key, as retained by Add-only (M1); not a model of the entries that
        # M2 and M3 replace.
        old = add(entity, attribute, previous, 'stale_competing_version')
        old['created_time'] = timestamp(serial * 1000)
        old['last_updated_time'] = timestamp(serial * 1000 + 1)
    add(entity, related, ATTRIBUTES[related][1][serial % 6], 'same_entity_different_attribute')
    add(ENTITIES[(serial + 1) % len(ENTITIES)], attribute, previous, 'different_entity_similar_attribute')
    add(ENTITIES[(serial + 2) % len(ENTITIES)], related, ATTRIBUTES[related][1][(serial + 1) % 6],
        'semantically_related_different_key')
    # A mix of other attributes of the subject, competing subjects, and unrelated
    # state families. Sampling order and surface variation use a private fixed RNG.
    occupied = {(r['annotation']['entity'], r['annotation']['attribute']) for r in records}
    occupied.add((entity, attribute))  # Also protects the absent new-key target.
    pool = [(ENTITIES[(serial + offset) % len(ENTITIES)], a)
            for offset in range(16) for a in ATTRIBUTE_NAMES
            if (ENTITIES[(serial + offset) % len(ENTITIES)], a) not in occupied]
    rng.shuffle(pool)
    for subject, attr in pool[:size - len(records)]:
        add(subject, attr, rng.choice(ATTRIBUTES[attr][1]), 'other')
    rng.shuffle(records)
    case = {'case_id': case_id, 'task': 'maintenance' if kind else 'answer',
            'active_memory': records, 'active_memory_size': size}
    if kind:
        candidate = fact(entity, attribute, current, rng.randrange(3))
        if kind == 'same_state' and candidate['text'] == target['text']:
            # Advance within the existing family without another RNG draw, so
            # this correction cannot perturb any other case or field.
            forms = fact_forms(entity, attribute, current)
            candidate['text'] = forms[(forms.index(candidate['text']) + 1) % len(forms)]
        case.update(maintenance_case_type=kind,
                    candidate=candidate,
                    oracle_target_entry_id=target['entry_id'] if target else None)
    else:
        case.update(query_wording=wording, stale_competing_version=stale,
                    question=rng.choice(question_forms(entity, attribute, wording)),
                    oracle_entry_ids=[target['entry_id']])
    return case


def build_dataset(seed=SEED):
    if type(seed) is not int or seed != SEED:
        raise ValueError(f'Only the frozen seed {SEED} is supported')
    rng = random.Random(seed)  # Private seeded RNG; no global RNG state, wall-clock time or filesystem order.
    cases = []
    for kind, prefix in (('changed_state', 'changed'), ('same_state', 'same')):
        for size in SIZES:
            for _ in range(10):
                number = sum(c.get('maintenance_case_type') == kind for c in cases) + 1
                cases.append(build_case(f'maint-{prefix}-{number:03d}', len(cases), size, rng, kind=kind))
    for number, size in enumerate((16,) * 7 + (64,) * 7 + (128,) * 6, 1):
        cases.append(build_case(f'maint-new-{number:03d}', len(cases), size, rng, kind='new_key'))
    number = 0
    for wording in ('direct', 'paraphrased'):
        for size in SIZES:
            for stale in (False, True):
                for _ in range(5):
                    number += 1
                    cases.append(build_case(f'answer-{number:03d}', len(cases), size, rng,
                                            wording=wording, stale=stale))
    return {'schema_version': '1.0', 'dataset_id': 'retrieval-calibration-v1',
            'source': 'synthetic_retrieval_calibration', 'cases': cases}


def dataset_bytes(dataset):
    return (json.dumps(dataset, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def summary(dataset, payload):
    cases = dataset['cases']
    counts = Counter(c.get('maintenance_case_type', 'answer') for c in cases)
    cells = Counter((c['query_wording'], c['active_memory_size'], c['stale_competing_version'])
                    for c in cases if c['task'] == 'answer')
    print(f'Total: {len(cases)}; maintenance: changed={counts["changed_state"]}, '
          f'same={counts["same_state"]}, new={counts["new_key"]}; answer={counts["answer"]}')
    print('Answer cells (wording/size/stale): ' + ', '.join(
        f'{w}/{s}/{str(t).lower()}={n}' for (w, s, t), n in sorted(cells.items())))
    print('SHA-256: ' + hashlib.sha256(payload).hexdigest())


def main(argv=None):
    if __package__:
        from .validate_retrieval_calibration import validate_dataset
    else:
        from validate_retrieval_calibration import validate_dataset
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate and compare without writing')
    args = parser.parse_args(argv)
    dataset = build_dataset()
    validate_dataset(dataset)
    payload = dataset_bytes(dataset)
    if payload != dataset_bytes(build_dataset()):
        raise ValueError('Nondeterministic generation detected; refusing output')
    if args.check:
        actual = OUTPUT.read_bytes()
        validate_dataset(json.loads(actual))
        if actual != payload:
            raise ValueError('Existing calibration.json differs from deterministic generation')
        print('CHECK PASSED')
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=OUTPUT.parent, prefix='.calibration-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, OUTPUT)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        print('WROTE calibration.json')
    summary(dataset, payload)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
