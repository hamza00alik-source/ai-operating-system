import pytest

from ai_os.workflow_dag import (
    COMPANY_CYCLE_DEPENDENCIES,
    parallel_layers,
    ready_steps,
    validate_dependencies,
)


def test_company_cycle_has_parallel_department_branches():
    layers = parallel_layers(COMPANY_CYCLE_DEPENDENCIES)
    assert layers[:4] == [[1], [2], [3], [4, 5, 6]]
    assert layers[4] == [7]
    assert layers[5] == [8, 9, 10, 11]
    assert layers[6] == [12]


def test_step_waits_until_every_prerequisite_completes():
    assert ready_steps(COMPANY_CYCLE_DEPENDENCIES, {1, 2, 3, 4, 5}) == [6]
    assert ready_steps(COMPANY_CYCLE_DEPENDENCIES, {1, 2, 3, 4, 5, 6}) == [7]


def test_dag_rejects_cycles_and_missing_dependencies():
    with pytest.raises(ValueError, match="cycle"):
        validate_dependencies({1: (2,), 2: (1,)})
    with pytest.raises(ValueError, match="missing"):
        validate_dependencies({1: (), 2: (3,)})
