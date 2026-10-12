"""The new bounded inverse rejects both changed and newly added source mutations."""
from pathlib import Path
import sys
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dataset_photos_source_contract as contract


def test_exact_current_restores_fixed_parent():
    import json
    fixture=json.loads((contract.ROOT/'tests/backend_contract/dataset_photos_delta.json').read_bytes())
    for name,change in fixture['files'].items():
        assert contract.checkpoint_bytes(name,(contract.ROOT/name).read_bytes())==change['parent_source'].encode()
        with pytest.raises(AssertionError):contract.checkpoint_bytes(name,(contract.ROOT/name).read_bytes()+b'\nunknown_edit=True\n')


def test_added_source_and_fixture_tampering_rejected():
    real=Path.read_bytes
    for target in ('local_inspection_service/auth/dataset_photos.py','tests/backend_contract/dataset_photos_delta.json'):
        def read(path):
            value=real(path)
            return value+b'\nunknown_edit=True\n' if path==contract.ROOT/target else value
        with patch.object(Path,'read_bytes',read),pytest.raises(AssertionError):
            contract.checkpoint_bytes('local_inspection_service/auth/data_workbench.py',real(contract.ROOT/'local_inspection_service/auth/data_workbench.py'))
