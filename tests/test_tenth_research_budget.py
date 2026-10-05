import importlib.util
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from run_tenth_research import assert_budget, frozen_config, repaired_baselines, FROZEN


def test_frozen_card_and_failed_attempts_cannot_bypass_budget(tmp_path):
    path=tmp_path/'card.json'
    modified=dict(FROZEN,confidence_quantile=.9)
    path.write_text(json.dumps(modified),encoding='utf-8')
    with pytest.raises(ValueError,match='frozen'):
        frozen_config(path)
    records=[dict(type='tenth_evaluation',cost='base',status='failed') for _ in range(9)]
    with pytest.raises(ValueError,match='budget'):
        assert_budget(records,'tenth_evaluation','base')
    assert_budget(records,'tenth_evaluation','strict')


def test_phase_a_is_required_even_if_some_results_exist(tmp_path):
    folder=tmp_path/'artifacts/experiments/EXP-174'
    folder.mkdir(parents=True)
    (folder/'run_manifest.json').write_text(json.dumps(dict(status='failed',holdout_read=False)),encoding='utf-8')
    with pytest.raises(ValueError,match='Phase A'):
        repaired_baselines(tmp_path)
