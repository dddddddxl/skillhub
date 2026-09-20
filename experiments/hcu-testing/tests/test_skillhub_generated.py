"""Generated from skillhub safe_relative_path contract; target is external checkout."""
import os
from pathlib import Path
import sys
import pytest

target = os.environ.get('TARGET_SKILLHUB_ROOT')
if not target:
    pytest.skip('Set TARGET_SKILLHUB_ROOT to the isolated source checkout', allow_module_level=True)
sys.path.insert(0, str(Path(target) / 'scripts'))
from skillhub import CatalogError, safe_relative_path


@pytest.mark.parametrize('value', ['skills/example/SKILL.md', 'skills/测试/SKILL.md', './skills/example'])
def test_preserve_valid_relative_path(value):
    assert safe_relative_path(value, 'path') == value


@pytest.mark.parametrize('value', ['', '  ', None, 3, '/etc/passwd', '../outside', 'skills/../../outside', 'skills\\example'])
def test_reject_invalid_or_escaping_path(value):
    with pytest.raises(CatalogError):
        safe_relative_path(value, 'path')
