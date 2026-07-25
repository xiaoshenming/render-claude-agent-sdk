from evals.workbench_e2e.workload import load_workload, round_slots


def test_frozen_workload_has_twenty_nontrivial_topics():
    workload = load_workload()

    assert len(workload) == 20
    assert len({item.task_id for item in workload}) == 20
    assert all(item.difficulty in {"medium_hard", "hard"} for item in workload)
    assert all(item.problem and item.expected_solution for item in workload)


def test_round_schedule_has_forty_five_deterministic_slots():
    workload = load_workload()
    slots = [
        slot for round_id in range(1, 4) for slot in round_slots(workload, round_id)
    ]

    assert len(slots) == 45
    assert all(len(round_slots(workload, round_id)) == 15 for round_id in range(1, 4))
    assert {slot.task.task_id for slot in slots} == {item.task_id for item in workload}
    assert [slot.slot_id for slot in slots] == [
        f"slot-{index:03d}" for index in range(1, 46)
    ]
