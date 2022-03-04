from aurweb import defaults


def test_fallback_pp():
    assert defaults.fallback_pp(75) == defaults.PP
    assert defaults.fallback_pp(100) == 10


def test_pp():
    assert defaults.PP == 10


def test_o():
    assert defaults.O == 0  # noqa: E741
