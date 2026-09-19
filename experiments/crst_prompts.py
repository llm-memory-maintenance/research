"""Frozen CRST Small Pilot prompts, request wrappers and response schemas (offline text only)."""
import hashlib
import json

ANSWER_PROMPT_VERSION = 'crst-pilot-answer/1.0.0'
ANSWER_SCHEMA_VERSION = 'crst-pilot-answer-schema/1.0.0'
# Wrapper of the final user request. 1.0.0 (Context and Question only) was never executed; 1.1.0 adds the answer
# format instruction to the final user request, because Q is outside the B0 historical token budget.
ANSWER_REQUEST_VERSION = 'crst-pilot-answer-request/1.1.0'
SUPERSEDED_ANSWER_REQUEST = {'version': 'crst-pilot-answer-request/1.0.0',
                             'sha256': '458e0a8e8a53ed92620386f4211606a2dac6735dd173782a966047e55cf54f2a'}
MAINTENANCE_PROMPT_VERSIONS = {'M2': 'crst-pilot-maintenance-m2/1.0.0', 'M3': 'crst-pilot-maintenance-m3/1.0.0'}
MAINTENANCE_SCHEMA_VERSIONS = {'M2': 'crst-pilot-maintenance-m2-schema/1.0.0',
                               'M3': 'crst-pilot-maintenance-m3-schema/1.0.0'}

# Identical for B0, M1, M2 and M3; frozen with B0 (configs/b0-calibration.yaml, system_prompt).
ANSWER_SYSTEM = ("You are a helpful assistant. Use only the information provided in the context to answer the "
                 "user's final question.\n\nReply with the answer only.")
ANSWER_SYSTEM_SHA256 = '8a6abc2b52c63340aa483023a823c6ff9d8142ab9749b3ae7d6d2f216da5e71e'

_MAINTENANCE_COMMON = (
    'You maintain a memory of facts. Each active memory entry is one line that begins with its memory_id. '
    'You are given the active memory and one candidate fact. Choose exactly one operation for the candidate.\n\n')
_MAINTENANCE_TAIL = (
    '\n\nReply with a JSON object that has exactly the keys "operation" and "target_id" and no other keys. '
    'For Update, target_id is the memory_id of the entry to replace. For every other operation, target_id is null.')
MAINTENANCE_SYSTEM = {
    'M2': (_MAINTENANCE_COMMON +
           'Available operations:\n'
           '- Update: an active entry already records the same entity and the same attribute as the candidate.\n'
           '- Add: no active entry records the same entity and the same attribute as the candidate.'
           + _MAINTENANCE_TAIL),
    'M3': (_MAINTENANCE_COMMON +
           'Available operations:\n'
           '- Add: no active entry records the same entity and the same attribute as the candidate.\n'
           '- Update: an active entry records the same entity and the same attribute as the candidate with a '
           'different value.\n'
           '- Noop: an active entry already records the same entity, the same attribute and the same value as '
           'the candidate.' + _MAINTENANCE_TAIL),
}
OPERATIONS = {'M2': ('Add', 'Update'), 'M3': ('Add', 'Update', 'Noop')}


def answer_schema():
    """Local semantic schema, enforced by crst_scoring.parse_answer; never sent to the provider."""
    return {'type': 'object', 'properties': {'answer': {'type': 'string', 'minLength': 1}},
            'required': ['answer'], 'additionalProperties': False}


def maintenance_schema(policy):
    """Local semantic schema, enforced by crst_policies.validate_decision; never sent to the provider.

    The conditional target invariant (Update needs a nonempty target_id, Add and Noop need null) is part of the
    local check.
    """
    return {'type': 'object',
            'properties': {'operation': {'type': 'string', 'enum': list(OPERATIONS[policy])},
                           'target_id': {'type': ['string', 'null']}},
            'required': ['operation', 'target_id'], 'additionalProperties': False}


PROVIDER_RESPONSE_MODE = 'json_object'


def response_format():
    """Provider response mode for every backbone call: the qualified json_object transport, never json_schema."""
    return {'type': PROVIDER_RESPONSE_MODE}


ANSWER_FORMAT_INSTRUCTION = (
    'Return exactly one JSON object with exactly one key named "answer".\n'
    'The value of "answer" must contain only the answer to the question, with no explanation or additional text.\n'
    'Do not return any other keys.')


def answer_user_text(context, question):
    """Final user request of M1, M2 and M3."""
    return f'Context:\n{context}\n\nQuestion:\n{question}\n\n{ANSWER_FORMAT_INSTRUCTION}'


def answer_final_user_text(question):
    """Final user message of B0, appended after the selected raw history and outside the historical budget."""
    return f'Question:\n{question}\n\n{ANSWER_FORMAT_INSTRUCTION}'


def maintenance_user_text(block, candidate):
    return f'Active memory:\n{block}\n\nCandidate:\n{candidate}'


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sha256_json(value):
    return sha256_text(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False))


def identities():
    """Version and SHA-256 of every frozen text and schema."""
    out = {'provider_response_mode': {'response_format': response_format()},
           'answer_system': {'version': ANSWER_PROMPT_VERSION, 'sha256': sha256_text(ANSWER_SYSTEM)},
           'answer_schema': {'version': ANSWER_SCHEMA_VERSION, 'sha256': sha256_json(answer_schema())},
           'answer_request': {
               'version': ANSWER_REQUEST_VERSION, 'superseded': SUPERSEDED_ANSWER_REQUEST,
               'memory_policies_sha256': sha256_text(answer_user_text('{context}', '{question}')),
               'b0_final_user_sha256': sha256_text(answer_final_user_text('{question}')),
               'format_instruction_sha256': sha256_text(ANSWER_FORMAT_INSTRUCTION)}}
    for policy in ('M2', 'M3'):
        out[f'maintenance_{policy.lower()}_system'] = {
            'version': MAINTENANCE_PROMPT_VERSIONS[policy], 'sha256': sha256_text(MAINTENANCE_SYSTEM[policy])}
        out[f'maintenance_{policy.lower()}_schema'] = {
            'version': MAINTENANCE_SCHEMA_VERSIONS[policy], 'sha256': sha256_json(maintenance_schema(policy))}
    out['maintenance_user_template'] = {'sha256': sha256_text(maintenance_user_text('{block}', '{candidate}'))}
    return out
