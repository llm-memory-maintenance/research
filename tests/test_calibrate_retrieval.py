"""Runner regression tests: invented facts, fake scores, no calibration corpus I/O."""

import argparse
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments'))
import calibrate_retrieval as runner


@pytest.fixture(autouse=True)
def no_network_or_frozen_corpus(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Network access forbidden')
    for name in ('connect', 'connect_ex'):
        monkeypatch.setattr(socket.socket, name, forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    original = Path.open

    def guarded(path, *args, **kwargs):
        if path.resolve() == ROOT / 'data/retrieval-calibration/calibration.json':
            raise AssertionError('Frozen corpus must not be read by runner tests')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)


@pytest.fixture
def config():
    return yaml.safe_load((ROOT / 'configs/retrieval.yaml').read_text())


class EntryTokenizer:
    """Ten invented tokens per complete serialized entry, no model loading."""
    def encode(self, text, *, add_special_tokens):
        assert add_special_tokens is False
        return [0] * (10 * text.count('[memory_id='))


class FakeEncoder:
    def __init__(self):
        self.calls = []

    def scores(self, memory_texts, query):
        assert all(type(text) is str for text in memory_texts)
        self.calls.append((list(memory_texts), query))
        return [1.0 - index / 10 for index in range(len(memory_texts))]


def invented_case(identity, task, oracle_rank=2, kind='changed_state'):
    entries = [{'entry_id': f'{identity}-{i}', 'text': f'The toy satellite has panel code T{i}.',
                'created_time': '2024-02-01T00:00:00Z',
                'last_updated_time': '2024-02-02T00:00:00Z',
                'annotation': {'private': f'not embedding input {i}'}}
               for i in range(1, 5)]
    case = {'case_id': identity, 'task': task, 'active_memory': entries}
    if task == 'maintenance':
        case.update(maintenance_case_type=kind,
                    candidate={'text': 'The toy satellite has panel code T9.',
                               'annotation': {'private': 'candidate evaluator data'}},
                    oracle_target_entry_id=None if kind == 'new_key' else entries[oracle_rank - 1]['entry_id'])
    else:
        case.update(question='What is the panel code of the toy satellite?',
                    oracle_entry_ids=[entries[oracle_rank - 1]['entry_id']],
                    stale_competing_version=True)
        entries[0]['annotation']['diagnostic_tags'] = ['stale_competing_version']
    return case


def invented_dataset(m_rank=2, a_rank=2):
    return {'dataset_id': 'unit-test-only', 'cases': [
        invented_case('toy-m', 'maintenance', m_rank),
        invented_case('toy-a', 'answer', a_rank),
        invented_case('toy-new', 'maintenance', kind='new_key')]}


@pytest.mark.parametrize('count,denominator,threshold,expected', [
    (57, 60, 0.95, True), (56, 60, 0.95, False), (1, 3, '0.33333333333333333334', False),
    (1, 3, '0.33333333333333333333', True), (19, 20, '0.95', True), (0, 60, 0.95, False)])
def test_exact_threshold(count, denominator, threshold, expected):
    assert runner.threshold_passes(count, denominator, threshold) is expected


@pytest.mark.parametrize('count,denominator,threshold', [(0, 0, .95), (2, 1, .95), (-1, 1, .95), (1, 1, 1.1)])
def test_invalid_threshold_inputs(count, denominator, threshold):
    with pytest.raises(ValueError):
        runner.threshold_passes(count, denominator, threshold)


def test_frozen_config_load_and_checksum(tmp_path):
    assert runner.load_config(ROOT / 'configs/retrieval.yaml')['dataset']['cases'] == 140
    bad = tmp_path / 'config.yaml'
    bad.write_text('changed: true\n')
    with pytest.raises(ValueError, match='Checksum'):
        runner.load_config(bad)


def test_minimum_k_not_larger_higher_score():
    results = [{'k': 1, 'threshold_pass': False, 'success_count': 56},
               {'k': 3, 'threshold_pass': True, 'success_count': 57},
               {'k': 5, 'threshold_pass': True, 'success_count': 60}]
    assert runner.minimum_k(results) == 3


def test_full_grids_smallest_k_denominators_and_reuse(config):
    encoder = FakeEncoder()
    dataset = invented_dataset()
    result = runner.calibrate(dataset, config, encoder, EntryTokenizer())
    assert result['status'] == 'QUALIFIED'
    assert result['selected'] == {'K_MAINT': 3, 'K_ANSWER': 3, 'LME_RETRIEVAL_CONTEXT_TOKENS': 512}
    assert [r['k'] for r in result['maintenance_k_results']] == [1, 3, 5, 10]
    assert [r['k'] for r in result['answer_k_results']] == [1, 3, 5, 10, 20]
    assert [r['budget'] for r in result['shared_budget_results']] == [512, 1024, 2048, 3072]
    for group in ('maintenance_k_results', 'answer_k_results'):
        assert all(r['denominator'] == 1 for r in result[group])
    assert len(encoder.calls) == 3  # One score/embedding computation per case, not per grid cell.
    for case, (texts, query) in zip(dataset['cases'], encoder.calls):
        assert texts == [entry['text'] for entry in case['active_memory']]
        assert query == (case['question'] if case['task'] == 'answer' else case['candidate']['text'])
    diagnostic = result['new_key_diagnostics']['cases'][0]
    assert set(diagnostic) == {'case_id', 'ranked_top_k_ids', 'admitted_ids', 'context_token_count'}
    assert diagnostic['ranked_top_k_ids'] == ['toy-new-1', 'toy-new-2', 'toy-new-3']
    assert 'success' not in diagnostic and 'oracle_id' not in diagnostic


def test_sixty_case_denominators_exclude_new_keys(config):
    dataset = {'cases': [invented_case(f'toy-m-{i}', 'maintenance') for i in range(60)]
               + [invented_case(f'toy-a-{i}', 'answer') for i in range(60)]
               + [invented_case(f'toy-n-{i}', 'maintenance', kind='new_key') for i in range(20)]}
    result = runner.calibrate(dataset, config, FakeEncoder(), EntryTokenizer())
    assert all(row['denominator'] == 60 for name in ('maintenance_k_results', 'answer_k_results')
               for row in result[name])
    assert len(result['new_key_diagnostics']['cases']) == 20


@pytest.mark.parametrize('task', ['maintenance', 'answer'])
def test_no_qualifying_k_stops_before_budgets(config, task):
    config['retrieval'][f'{task}_k_candidates'] = [1]
    encoder = FakeEncoder()
    result = runner.calibrate(invented_dataset(), config, encoder, EntryTokenizer())
    assert result['status'] == 'NOT_QUALIFIED' and result['embedding_qualified'] is False
    failed_key = 'K_MAINT' if task == 'maintenance' else 'K_ANSWER'
    assert result['selected'][failed_key] is None
    assert result['selected']['LME_RETRIEVAL_CONTEXT_TOKENS'] is None
    assert result['shared_budget_results'] == []
    assert result['new_key_diagnostics'] == {'status': 'not_applicable', 'cases': []}
    assert len(encoder.calls) == 2
    assert json.loads(runner.json_bytes(result))['selected'][failed_key] is None


def test_budget_selection_fixed_ks_smallest_shared(config):
    config['retrieval']['context_token_candidates'] = [10, 20, 30, 40]
    result = runner.calibrate(invented_dataset(a_rank=3), config, FakeEncoder(), EntryTokenizer())
    assert result['selected'] == {'K_MAINT': 3, 'K_ANSWER': 3, 'LME_RETRIEVAL_CONTEXT_TOKENS': 30}
    assert [r['threshold_pass'] for r in result['shared_budget_results']] == [False, False, True, True]
    assert all(r[task]['k'] == 3 for r in result['shared_budget_results'] for task in ('maintenance', 'answer'))
    evidence = result['shared_budget_results'][0]['maintenance']['cases'][0]
    assert evidence['oracle_id'] in evidence['ranked_top_k_ids']
    assert evidence['oracle_id'] not in evidence['admitted_ids']
    assert evidence['success'] is False and evidence['context_token_count'] == 10


def test_no_shared_budget_fails_closed_even_if_k_grid_passed(config, monkeypatch):
    original = runner.evaluate
    calls = 0

    def simulate_no_shared_configuration(*args):
        nonlocal calls
        result = original(*args)
        calls += 1
        if calls > 9:  # Simulate an unexpected failure during the shared-budget sweep.
            result['threshold_pass'] = False
        return result
    monkeypatch.setattr(runner, 'evaluate', simulate_no_shared_configuration)
    result = runner.calibrate(invented_dataset(), config, FakeEncoder(), EntryTokenizer())
    assert result['status'] == 'NOT_QUALIFIED'
    assert result['embedding_qualified'] is False
    assert result['selected']['LME_RETRIEVAL_CONTEXT_TOKENS'] is None
    assert len(result['shared_budget_results']) == 4
    assert result['new_key_diagnostics']['status'] == 'not_applicable'


def test_stale_annotation_has_no_scoring_effect():
    case = invented_case('toy-a', 'answer')
    first = runner.prepare_case(case, FakeEncoder())
    case['stale_competing_version'] = False
    for entry in case['active_memory']:
        entry['annotation'] = {'anything': 'changed hidden metadata'}
    second = runner.prepare_case(case, FakeEncoder())
    assert first == second
    assert first['ranked'][0]['entry_id'] == 'toy-a-1'  # The stale entry receives the highest fake score.
    assert not runner.case_outcome(first, 1, 100, EntryTokenizer())['success']


def test_dataset_checksum_before_loading(tmp_path, config, monkeypatch):
    path = tmp_path / 'invented.json'
    path.write_text('{"dataset_id":"unit-test-only","cases":[]}')
    monkeypatch.setattr(runner, 'load_dataset', lambda p: pytest.fail('Must check checksum first'))
    with pytest.raises(ValueError, match='Checksum'):
        runner.verified_dataset(path, config)


def test_verified_dataset_calls_validator(tmp_path, config, monkeypatch):
    path = tmp_path / 'invented.json'
    path.write_bytes(runner.json_bytes(invented_dataset()))
    config['dataset'].update(id='unit-test-only', sha256=runner.file_sha256(path))
    seen = []
    monkeypatch.setattr(runner, 'validate_dataset', lambda dataset: seen.append(dataset))
    assert runner.verified_dataset(path, config) == seen[0]
    config['dataset']['id'] = 'wrong'
    with pytest.raises(ValueError, match='identity'):
        runner.verified_dataset(path, config)


def test_verify_every_artifact_checksum(tmp_path):
    files = {'first.json': b'one', 'second.bin': b'two'}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    assert runner.verify_artifacts(tmp_path, hashes) == hashes
    (tmp_path / 'second.bin').write_bytes(b'changed')
    with pytest.raises(ValueError, match='Checksum'):
        runner.verify_artifacts(tmp_path, hashes)
    (tmp_path / 'second.bin').unlink()
    with pytest.raises(FileNotFoundError):
        runner.verify_artifacts(tmp_path, hashes)


@pytest.mark.parametrize('dirty', [True, False])
def test_git_clean_and_exact_head(monkeypatch, dirty):
    commands = []
    def git(command, **kwargs):
        commands.append(command)
        args = command[3:]
        output = str(ROOT) if args == ['rev-parse', '--show-toplevel'] else ''
        if args[0] == 'status':
            output = '?? untracked.py' if dirty else ''
        if args == ['rev-parse', 'HEAD']:
            output = 'a' * 40
        return SimpleNamespace(stdout=output)
    monkeypatch.setattr(runner.subprocess, 'run', git)
    if dirty:
        with pytest.raises(ValueError, match='clean working tree'):
            runner.clean_source_commit()
    else:
        assert runner.clean_source_commit() == 'a' * 40
        assert any('ls-files' in cmd and '--error-unmatch' in cmd for cmd in commands)


def test_not_git_repository_rejected(monkeypatch):
    def absent(*args, **kwargs):
        raise subprocess.CalledProcessError(128, 'git')
    monkeypatch.setattr(runner.subprocess, 'run', absent)
    with pytest.raises(subprocess.CalledProcessError):
        runner.clean_source_commit()


def test_immutable_deterministic_json(tmp_path):
    value = {'text': 'Invented café fixture', 'selected': None, 'items': [True, 3]}
    payload = runner.json_bytes(value)
    assert payload == runner.json_bytes(copy.deepcopy(value))
    assert payload.endswith(b'\n') and b'  "text"' in payload
    path = tmp_path / 'result.json'
    checksum = runner.write_result(path, value)
    assert path.read_bytes() == payload
    assert checksum == hashlib.sha256(payload).hexdigest()
    with pytest.raises(FileExistsError):
        runner.write_result(path, {'changed': True})
    assert path.read_bytes() == payload
    with pytest.raises(ValueError):
        runner.write_result(tmp_path / 'invalid.json', {'score': float('nan')})
    assert not (tmp_path / 'invalid.json').exists()


def test_atomic_publication_race_does_not_overwrite(tmp_path, monkeypatch):
    target = tmp_path / 'result.json'
    original_link = runner.os.link
    def racing_link(source, destination):
        Path(destination).write_text('another writer')
        original_link(source, destination)
    monkeypatch.setattr(runner.os, 'link', racing_link)
    with pytest.raises(FileExistsError):
        runner.write_result(target, {'complete': True})
    assert target.read_text() == 'another writer'
    assert list(tmp_path.iterdir()) == [target]


@pytest.fixture
def official_harness(tmp_path, config, monkeypatch):
    """Invented inputs only; replace official data/config validation at this boundary."""
    args = argparse.Namespace(dataset=tmp_path / 'invented.json', config=tmp_path / 'config.yaml',
                              contriever_dir=tmp_path / 'embedding', reader_tokenizer_dir=tmp_path / 'reader',
                              output=tmp_path / 'result.json')
    args.dataset.write_bytes(runner.json_bytes(invented_dataset()))
    args.config.write_text(yaml.safe_dump(config))
    config['dataset']['sha256'] = runner.file_sha256(args.dataset)
    monkeypatch.setattr(runner, 'clean_source_commit', lambda: 'b' * 40)
    monkeypatch.setattr(runner, 'load_config', lambda path: config)
    monkeypatch.setattr(runner, 'verified_dataset', lambda path, cfg: invented_dataset())
    monkeypatch.setattr(runner, 'verify_artifacts', lambda directory, checksums: checksums)
    monkeypatch.setattr(runner, 'verified_environment', lambda cfg: {'python': 'test-only'})
    monkeypatch.setattr(runner, 'load_local_models', lambda *args: (FakeEncoder(), EntryTokenizer()))
    return args


def test_official_provenance_and_result_write(official_harness):
    args = official_harness
    result = runner.run(args)
    provenance = result['provenance']
    assert provenance['source_commit'] == 'b' * 40
    assert provenance['config_sha256'] == runner.file_sha256(args.config)
    assert provenance['config_path'] == str(args.config)
    assert provenance['dataset_sha256'] == runner.file_sha256(args.dataset)
    assert provenance['protocol_checkpoint'] == '24eb542'
    assert provenance['corpus_checkpoint'] == '5b0d6fe'
    assert provenance['verified_artifact_checksums']['embedding']['pytorch_model.bin']
    assert 'tokenizer_revision' in provenance['embedding']
    assert json.loads(args.output.read_bytes()) == result
    assert 'timestamp' not in result and 'embeddings' not in result


@pytest.mark.parametrize('failure_point', ['load_local_models', 'calibrate'])
def test_infrastructure_failure_no_partial_artifact(official_harness, monkeypatch, failure_point):
    def fail(*args, **kwargs):
        raise RuntimeError('invented infrastructure failure')
    monkeypatch.setattr(runner, failure_point, fail)
    with pytest.raises(RuntimeError):
        runner.run(official_harness)
    assert not official_harness.output.exists()


def test_existing_output_rejected_before_model_load(official_harness, monkeypatch):
    official_harness.output.write_text('preserved')
    monkeypatch.setattr(runner, 'load_local_models', lambda *args: pytest.fail('Must not load'))
    with pytest.raises(FileExistsError):
        runner.run(official_harness)
    assert official_harness.output.read_text() == 'preserved'


def test_environment_mismatch_rejected(config, monkeypatch):
    monkeypatch.setattr(runner.platform, 'python_version', lambda: '0.0.0')
    with pytest.raises(ValueError, match='environment mismatch'):
        runner.verified_environment(config)


class TinyInputTokenizer:
    def __init__(self, length=3, empty=False):
        self.length = length
        self.empty = empty
        self.calls = []

    def __call__(self, texts, **kwargs):
        import torch
        self.calls.append((list(texts), kwargs))
        if 'return_tensors' not in kwargs:
            assert kwargs == {'truncation': False, 'padding': False, 'add_special_tokens': True}
            return {'input_ids': [[1] * self.length for _ in texts]}
        assert kwargs == {'padding': True, 'truncation': True, 'max_length': 512,
                          'add_special_tokens': True, 'return_tensors': 'pt'}
        return {'input_ids': torch.ones((len(texts), 3), dtype=torch.int64),
                'attention_mask': torch.tensor([[0, 0, 0] if self.empty else [1, 1, 0]] * len(texts))}


class TinyHiddenModel:
    def __init__(self, value=None):
        self.value = value
        self.calls = 0

    def __call__(self, input_ids, attention_mask):
        import torch
        assert torch.is_inference_mode_enabled()
        self.calls += 1
        hidden = torch.empty((len(input_ids), 3, 768), dtype=torch.float32)
        hidden[:, 0] = 2.0
        hidden[:, 1] = 4.0
        hidden[:, 2] = 1000.0  # Must not contribute through padding.
        if self.value is not None:
            hidden.fill_(self.value)
        return SimpleNamespace(last_hidden_state=hidden)


def test_embedding_masked_mean_batching_dtype_and_cosine():
    import torch
    model, tokenizer = TinyHiddenModel(), TinyInputTokenizer()
    encoder = runner.ContrieverEncoder(model, tokenizer)
    vectors = encoder.encode([f'Toy prism fixture {i}.' for i in range(33)], 32)
    assert vectors.shape == (33, 768) and vectors.dtype == torch.float32
    assert torch.equal(vectors, torch.full((33, 768), 3.0))
    assert [len(texts) for texts, kw in tokenizer.calls if 'return_tensors' in kw] == [32, 1]
    scores = encoder.scores(['Toy prism fixture.'], 'What shape is the toy?')
    assert scores == pytest.approx([1.0], abs=1e-6)
    assert tokenizer.calls[-1][0] == ['What shape is the toy?']


@pytest.mark.parametrize('mode', ['overlength', 'empty_mask', 'zero_vector', 'nan_vector'])
def test_embedding_fails_closed(mode):
    tokenizer = TinyInputTokenizer(length=513 if mode == 'overlength' else 3, empty=mode == 'empty_mask')
    value = {'zero_vector': 0.0, 'nan_vector': float('nan')}.get(mode)
    model = TinyHiddenModel(value)
    with pytest.raises(ValueError):
        runner.ContrieverEncoder(model, tokenizer).encode(['A tiny glass prism.'], 1)
    if mode in ('overlength', 'empty_mask'):
        assert model.calls == 0


@pytest.mark.parametrize('problem', [None, 'class', 'weights', 'attention', 'length'])
def test_local_model_loading_controls(monkeypatch, problem):
    import torch
    import transformers

    calls = []
    controls = []
    for name in ('set_num_threads', 'set_num_interop_threads', 'use_deterministic_algorithms',
                 'set_float32_matmul_precision'):
        monkeypatch.setattr(torch, name, lambda value, name=name: controls.append((name, value)))
    # Register these variables with monkeypatch so the loader's offline settings are restored after the test.
    monkeypatch.setenv('HF_HUB_OFFLINE', '1')
    monkeypatch.setenv('TRANSFORMERS_OFFLINE', '1')

    class BertModel:
        config = SimpleNamespace(hidden_size=768, max_position_embeddings=512,
                                 _attn_implementation='sdpa' if problem == 'attention' else 'eager')

        def to(self, **kwargs):
            assert kwargs == {'device': 'cpu', 'dtype': torch.float32}
            return self

        def eval(self):
            self.evaluation_mode = True
            return self

        def parameters(self):
            return [torch.ones(1, dtype=torch.float32)]

    class BertTokenizerFast:
        model_max_length = 1024 if problem == 'length' else 512

    class PreTrainedTokenizerFast:
        pass

    def tokenizer_loader(path, **kwargs):
        assert kwargs == {'use_fast': True, 'local_files_only': True, 'trust_remote_code': False}
        calls.append(path)
        return BertTokenizerFast() if path == 'invented-embedding-dir' else PreTrainedTokenizerFast()

    def model_loader(path, **kwargs):
        assert path == 'invented-embedding-dir'
        assert kwargs == {'attn_implementation': 'eager', 'torch_dtype': torch.float32,
                          'use_safetensors': False, 'output_loading_info': True,
                          'local_files_only': True, 'trust_remote_code': False}
        model = SimpleNamespace() if problem == 'class' else BertModel()
        return model, {'missing_keys': ['missing'] if problem == 'weights' else []}

    monkeypatch.setattr(transformers.AutoTokenizer, 'from_pretrained', tokenizer_loader)
    monkeypatch.setattr(transformers.AutoModel, 'from_pretrained', model_loader)
    if problem:
        with pytest.raises(ValueError):
            runner.load_local_models('invented-embedding-dir', 'invented-reader-dir')
    else:
        encoder, reader = runner.load_local_models('invented-embedding-dir', 'invented-reader-dir')
        assert encoder.model.evaluation_mode is True
        assert type(reader).__name__ == 'PreTrainedTokenizerFast'
    assert calls == ['invented-embedding-dir', 'invented-reader-dir']
    assert controls == [('set_num_threads', 1), ('set_num_interop_threads', 1),
                        ('use_deterministic_algorithms', True), ('set_float32_matmul_precision', 'highest')]


def test_maximum_length_is_accepted_without_repair():
    model = TinyHiddenModel()
    tokenizer = TinyInputTokenizer(length=512)
    assert runner.ContrieverEncoder(model, tokenizer).encode(['Toy crystal fixture.'], 1).shape == (1, 768)
    assert model.calls == 1


def test_complete_failed_qualification_is_written(official_harness, monkeypatch):
    original = runner.load_config
    def fail_k_config(path):
        config = copy.deepcopy(original(path))
        config['retrieval']['maintenance_k_candidates'] = [1]
        return config
    monkeypatch.setattr(runner, 'load_config', fail_k_config)
    result = runner.run(official_harness)
    assert result['results']['status'] == 'NOT_QUALIFIED'
    assert json.loads(official_harness.output.read_bytes())['results']['selected']['K_MAINT'] is None


def test_changed_worktree_before_publication_aborts(official_harness, monkeypatch):
    commits = iter(['b' * 40, 'c' * 40])
    monkeypatch.setattr(runner, 'clean_source_commit', lambda: next(commits))
    with pytest.raises(ValueError, match='Source commit changed'):
        runner.run(official_harness)
    assert not official_harness.output.exists()


def test_dangling_output_symlink_rejected(tmp_path):
    output = tmp_path / 'output.json'
    output.symlink_to(tmp_path / 'absent.json')
    with pytest.raises(FileExistsError):
        runner.write_result(output, {'complete': True})
