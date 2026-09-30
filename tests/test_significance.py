"""Tests for the mass-significance rule."""


from src.preprocess import significance


def test_share_and_absolute_floor():
    # 50 g in a 1000 g recipe (5%) and >= 2 g -> significant
    assert significance.qualifies(50.0, 1000.0)
    # 1.5 g in 100 g (1.5%) -> below share threshold
    assert not significance.qualifies(1.5, 100.0)
    # 1 g in 20 g (5%) but below the 2 g absolute floor -> not significant
    assert not significance.qualifies(1.0, 20.0)
    # 5 g in 1000 g (0.5%) -> below share threshold
    assert not significance.qualifies(5.0, 1000.0)


def test_functional_bypasses_threshold():
    # a pinch of salt (1 g) is still kept because it is functional
    assert significance.qualifies(1.0, 1000.0, functional=True)


def test_invalid_mass():
    assert not significance.qualifies(None, 1000.0)
    assert not significance.qualifies(0.0, 1000.0)
    assert not significance.qualifies(10.0, 0.0)
