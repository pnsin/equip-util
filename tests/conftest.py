import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_session():
    """시험마다 새 화면(세션)처럼: 앞 시험에서 '본 값'이 남지 않게."""
    from core import db
    db.reset_seen()
    yield
    db.reset_seen()
