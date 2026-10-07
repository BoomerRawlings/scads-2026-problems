"""Create the explicitly fictional portfolio discovery fixture; no source manuals."""
from pathlib import Path
import json
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from vopt.schema import seal_bundle, validate_bundle

documents, assertions = [], []
for doc_id, model, category, attribute, value, unit in [
    ('fixture-generator', 'DEMO-G30', 'generator', 'output_power', 30000, 'W'),
    ('fixture-drill', 'DEMO-D120', 'drill', 'input_voltage', 120, 'V'),
    ('fixture-pump', 'DEMO-P200', 'pump', 'pressure', 200, 'kPa'),
]:
    documents.append({'doc_id': doc_id, 'title': f'Fictional {model} demonstration manual',
        'manufacturer': 'Authored fixture', 'models': [model], 'category': category,
        'language': 'en', 'revision': 'synthetic-1', 'request_ref': f'fixture:{doc_id}',
        'processing_status': 'complete'})
    assertions.append({'assertion_id': f'{doc_id}-rating', 'doc_id': doc_id, 'model': model,
        'variant': None, 'attribute': attribute, 'qualifier': 'rated', 'status': 'reviewed',
        'value': value, 'value_max': None, 'unit': unit})
bundle = seal_bundle({'schema_version': 1, 'catalog_id': 'portfolio-synthetic', 'sequence': 1,
    'profile': 'values', 'policy': {'version': 1, 'revoked_doc_ids': [], 'revoked_assertion_ids': []},
    'documents': documents, 'assertions': assertions})
validate_bundle(bundle)
output = PROJECT / 'examples/catalog-synthetic.json'
output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Wrote examples/catalog-synthetic.json (authored fixture; no real specifications).')
