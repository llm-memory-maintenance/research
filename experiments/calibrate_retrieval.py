"""Official local-only calibration; execution requires explicit verified inputs.

Importing this module or requesting --help does not load models or datasets.
"""

import argparse
from decimal import Decimal
from fractions import Fraction
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile

import yaml

if __package__:
    from .retrieval_context import rank_entries, select_context, count_context_tokens
    from .validate_retrieval_calibration import load_dataset, validate_dataset
else:
    from retrieval_context import rank_entries, select_context, count_context_tokens
    from validate_retrieval_calibration import load_dataset, validate_dataset

ROOT = Path(__file__).resolve().parents[1]
# The configuration frozen by 4a88d9b, not the future runner source commit.
FROZEN_CONFIG_SHA256 = 'c00f6cf6fac8bf14f24bab6b16b7929c34a62369b9c2e8eee254faed919dbcf9'


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def require_checksum(path, expected):
    actual = file_sha256(path)
    if actual != expected:
        raise ValueError(f'Checksum mismatch: {path}')
    return actual


def load_config(path):
    require_checksum(path, FROZEN_CONFIG_SHA256)
    return yaml.safe_load(Path(path).read_text(encoding='utf-8'))


def verified_dataset(path, config):
    require_checksum(path, config['dataset']['sha256'])
    dataset = load_dataset(path)
    validate_dataset(dataset)
    if dataset['dataset_id'] != config['dataset']['id']:
        raise ValueError('Dataset identity mismatch')
    return dataset


def verify_artifacts(directory, expected):
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f'Local artifact directory absent: {directory}')
    return {name: require_checksum(directory / name, checksum)
            for name, checksum in expected.items()}


def clean_source_commit():
    def git(*args):
        return subprocess.run(['git', '-C', str(ROOT), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    if git('rev-parse', '--show-toplevel') != str(ROOT):
        raise ValueError('Runner must belong to the research Git repository')
    if git('status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Official calibration requires a clean working tree')
    git('ls-files', '--error-unmatch', 'experiments/calibrate_retrieval.py')
    return git('rev-parse', 'HEAD')


def verified_environment(config):
    actual = {'python': platform.python_version(),
              'platform': f'{platform.system().lower()}_{platform.machine()}'}
    for package in ('torch', 'transformers', 'huggingface_hub', 'tokenizers',
                    'numpy', 'safetensors'):
        actual[package] = version(package)
    for name, value in actual.items():
        if value != config['environment'][name]:
            raise ValueError(f'Frozen environment mismatch: {name} ({value})')
    # Also record the configuration/validation tooling actually used.
    for package in ('PyYAML', 'pydantic'):
        actual[package] = version(package)
    return actual


class ContrieverEncoder:
    """One explicit frozen embedding path; no retrieval-policy decisions."""

    def __init__(self, model, tokenizer):
        self.model = model
        self.tokenizer = tokenizer

    def encode(self, texts, batch_size):
        import torch

        if not texts or not 1 <= batch_size <= 32:
            raise ValueError('Expected nonempty texts and batch size in 1..32')
        vectors = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            lengths = self.tokenizer(batch, truncation=False, padding=False,
                                     add_special_tokens=True)['input_ids']
            if any(len(ids) > 512 for ids in lengths):
                raise ValueError('Embedding input exceeds 512 tokens before truncation')
            tokens = self.tokenizer(batch, padding=True, truncation=True,
                                    max_length=512, add_special_tokens=True,
                                    return_tensors='pt')
            mask = tokens['attention_mask']
            if (mask.sum(dim=1) == 0).any():
                raise ValueError('Empty attention mask')
            with torch.inference_mode():
                hidden = self.model(**tokens).last_hidden_state
                pooled = (hidden.masked_fill(~mask[..., None].bool(), 0.0).sum(dim=1)
                          / mask.sum(dim=1)[..., None])
            if (pooled.shape != (len(batch), 768) or pooled.dtype != torch.float32
                    or pooled.device.type != 'cpu' or not torch.isfinite(pooled).all()
                    or (pooled.norm(p=2, dim=-1) == 0).any()):
                raise ValueError('Invalid Contriever embedding vector')
            vectors.append(pooled)
        return torch.cat(vectors, dim=0)

    def scores(self, memory_texts, query):
        import torch

        memory = self.encode(memory_texts, batch_size=32)
        query_vector = self.encode([query], batch_size=1)
        memory_unit = torch.nn.functional.normalize(memory, p=2, dim=-1, eps=1e-12)
        query_unit = torch.nn.functional.normalize(query_vector, p=2, dim=-1, eps=1e-12)
        scores = query_unit @ memory_unit.T
        if not torch.isfinite(scores).all():
            raise ValueError('Nonfinite cosine similarity')
        return scores[0].tolist()


def load_local_models(contriever_dir, reader_dir):
    # No hub access is permitted, even if local loading encounters a missing file.
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    import torch
    from transformers import AutoModel, AutoTokenizer

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    local = {'local_files_only': True, 'trust_remote_code': False}
    tokenizer = AutoTokenizer.from_pretrained(str(contriever_dir), use_fast=True, **local)
    reader = AutoTokenizer.from_pretrained(str(reader_dir), use_fast=True, **local)
    model, info = AutoModel.from_pretrained(
        str(contriever_dir), attn_implementation='eager', torch_dtype=torch.float32,
        use_safetensors=False, output_loading_info=True, **local)
    if (type(model).__name__ != 'BertModel'
            or type(tokenizer).__name__ != 'BertTokenizerFast'
            or type(reader).__name__ != 'PreTrainedTokenizerFast'):
        raise ValueError('Unexpected frozen model/tokenizer class')
    if any(info.get(key) for key in ('missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs')):
        raise ValueError('Incomplete or incompatible Contriever weight loading')
    if (model.config.hidden_size != 768 or model.config.max_position_embeddings != 512
            or model.config._attn_implementation != 'eager'
            or tokenizer.model_max_length != 512):
        raise ValueError('Unexpected Contriever configuration')
    model.to(device='cpu', dtype=torch.float32).eval()
    if any(p.device.type != 'cpu' or p.dtype != torch.float32 for p in model.parameters()):
        raise ValueError('Model device/dtype mismatch')
    return ContrieverEncoder(model, tokenizer), reader


def threshold_passes(successes, denominator, threshold):
    if denominator <= 0 or not 0 <= successes <= denominator:
        raise ValueError('Invalid success count or denominator')
    gate = Fraction(Decimal(str(threshold)))
    if not 0 < gate <= 1:
        raise ValueError('Invalid success threshold')
    return Fraction(successes, denominator) >= gate


def prepare_case(case, encoder):
    # Only atomic text enters the encoder. Hidden annotations never enter ranking.
    entries = [{key: entry[key] for key in
                ('entry_id', 'text', 'created_time', 'last_updated_time')}
               for entry in case['active_memory']]
    query = case['candidate']['text'] if case['task'] == 'maintenance' else case['question']
    scores = encoder.scores([entry['text'] for entry in entries], query)
    ranked = rank_entries(entries, scores)
    # Oracle lookup is separate from scoring and selection.
    oracle = (case['oracle_target_entry_id'] if case['task'] == 'maintenance'
              else case['oracle_entry_ids'][0])
    return {'case_id': case['case_id'], 'ranked': ranked, 'oracle_id': oracle}


def case_outcome(prepared, k, budget, tokenizer):
    admitted, context = select_context(prepared['ranked'], k, budget, tokenizer)
    ids = [entry['entry_id'] for entry in admitted]
    result = {'case_id': prepared['case_id'],
              'ranked_top_k_ids': [entry['entry_id'] for entry in prepared['ranked'][:k]],
              'admitted_ids': ids,
              'context_token_count': count_context_tokens(context, tokenizer)}
    if prepared['oracle_id'] is not None:
        result.update(oracle_id=prepared['oracle_id'],
                      success=prepared['oracle_id'] in ids)
    return result


def evaluate(cases, k, budget, tokenizer, threshold):
    outcomes = [case_outcome(case, k, budget, tokenizer) for case in cases]
    successes = sum(item['success'] for item in outcomes)
    denominator = len(outcomes)
    return {'k': k, 'budget': budget, 'success_count': successes,
            'denominator': denominator, 'success_proportion': successes / denominator,
            'exact_success_proportion': f'{successes}/{denominator}',
            'threshold_pass': threshold_passes(successes, denominator, threshold),
            'cases': outcomes}


def minimum_k(results):
    return next((result['k'] for result in results if result['threshold_pass']), None)


def calibrate(dataset, config, encoder, tokenizer):
    """Evaluate predeclared grids. Official input validation belongs to run()."""
    design = config['retrieval']
    threshold = design['success_threshold']
    budgets = design['context_token_candidates']
    maintenance, answer, new_key = [], [], []
    for case in dataset['cases']:
        if case['task'] == 'maintenance' and case['maintenance_case_type'] == 'new_key':
            new_key.append(case)
        else:
            prepared = prepare_case(case, encoder)
            (maintenance if case['task'] == 'maintenance' else answer).append(prepared)
    maintenance_results = [evaluate(maintenance, k, max(budgets), tokenizer, threshold)
                           for k in design['maintenance_k_candidates']]
    answer_results = [evaluate(answer, k, max(budgets), tokenizer, threshold)
                      for k in design['answer_k_candidates']]
    km, ka = minimum_k(maintenance_results), minimum_k(answer_results)
    shared_results, selected_budget = [], None
    if km is not None and ka is not None:
        for budget in budgets:
            m = evaluate(maintenance, km, budget, tokenizer, threshold)
            a = evaluate(answer, ka, budget, tokenizer, threshold)
            passed = m['threshold_pass'] and a['threshold_pass']
            shared_results.append({'budget': budget, 'maintenance': m, 'answer': a,
                                   'threshold_pass': passed})
            if passed and selected_budget is None:
                selected_budget = budget
    qualified = selected_budget is not None
    diagnostics = {'status': 'not_applicable', 'cases': []}
    if qualified:
        diagnostics = {'status': 'evaluated', 'cases': [
            case_outcome(prepare_case(case, encoder), km, selected_budget, tokenizer)
            for case in new_key]}
    return {'maintenance_k_results': maintenance_results, 'answer_k_results': answer_results,
            'selected': {'K_MAINT': km, 'K_ANSWER': ka,
                         'LME_RETRIEVAL_CONTEXT_TOKENS': selected_budget},
            'shared_budget_results': shared_results, 'new_key_diagnostics': diagnostics,
            'embedding_qualified': qualified,
            'status': 'QUALIFIED' if qualified else 'NOT_QUALIFIED'}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def require_new_output(path):
    if os.path.lexists(path):
        raise FileExistsError(f'Refusing to overwrite output: {path}')


def write_result(path, result):
    """Publish a complete file atomically without replacing even a racing writer."""
    path = Path(path)
    require_new_output(path)
    payload = json_bytes(result)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.calibration-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # Atomic no-clobber publication on the same filesystem.
    finally:
        if temporary is not None:
            temporary.unlink()
    return file_sha256(path)


def run(args):
    require_new_output(args.output)
    source_commit = clean_source_commit()
    config = load_config(args.config)
    dataset = verified_dataset(args.dataset, config)
    checksums = {
        'embedding': verify_artifacts(args.contriever_dir, config['embedding']['artifact_sha256']),
        'reader_tokenizer': verify_artifacts(args.reader_tokenizer_dir,
                                           config['reader_tokenizer']['artifact_sha256'])}
    packages = verified_environment(config)
    encoder, tokenizer = load_local_models(args.contriever_dir, args.reader_tokenizer_dir)
    provenance = {'source_commit': source_commit, 'config_path': str(args.config),
                  'config_sha256': file_sha256(args.config), 'dataset_path': str(args.dataset),
                  'dataset_id': dataset['dataset_id'], 'dataset_sha256': config['dataset']['sha256'],
                  'protocol_checkpoint': config['protocol_checkpoint'],
                  'corpus_checkpoint': config['corpus_checkpoint'],
                  'verified_artifact_checksums': checksums, 'package_versions': packages,
                  'device': config['embedding']['device'], 'dtype': config['embedding']['dtype']}
    for section in ('embedding', 'reader_tokenizer'):
        provenance[section] = {key: config[section][key] for key in ('repository_id', 'revision')}
    provenance['embedding'].update({key: config['embedding'][key] for key in
                                    ('tokenizer_repository_id', 'tokenizer_revision')})
    result = {'provenance': provenance, 'frozen_calibration_design': config['retrieval'],
              'results': calibrate(dataset, config, encoder, tokenizer)}
    if clean_source_commit() != source_commit:
        raise ValueError('Source commit changed during calibration')
    require_checksum(args.config, provenance['config_sha256'])
    require_checksum(args.dataset, provenance['dataset_sha256'])
    checksum = write_result(args.output, result)
    print(f"{result['results']['status']}\nResult SHA-256: {checksum}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'config', 'contriever-dir', 'reader-tokenizer-dir', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    run(args)


if __name__ == '__main__':
    main()
