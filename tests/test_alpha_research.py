"""第九轮 CLI 命令与研究流程针对性测试。"""

from pathlib import Path
import pytest

from cryptoquant.cli import main
from cryptoquant.models.alpha_workflow import _audit_alpha_budget
from cryptoquant.models.research_config import load_research_config


def test_alpha_cli_help(capsys):
    for sub in ('alpha-evaluate', 'alpha-select', 'alpha-compare'):
        with pytest.raises(SystemExit) as exc:
            main([sub, '--help'])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert 'usage:' in captured.out.lower()


def test_alpha_budget_audit():
    root = Path.cwd()
    cfg = load_research_config('configs/ninth_experiment.toml', root)
    budget = _audit_alpha_budget(root, cfg)
    
    assert budget['total_limit'] == 17
    assert budget['base_accounts_limit'] == 9
    assert budget['pressure_accounts_limit'] == 6
    assert budget['accounts_limit'] == 15
    assert 0 <= budget['accounts_used'] <= budget['accounts_limit']


def test_cli_rejects_invalid_alpha_variant(capsys):
    with pytest.raises(SystemExit) as exc:
        main([
            'alpha-evaluate',
            '--research-config', 'configs/ninth_experiment.toml',
            '--state-experiment-id', 'EXP-122',
            '--variant', 'R99',
            '--window', 'W1',
            '--experiment-id', 'EXP-999',
        ])
    assert exc.value.code != 0
