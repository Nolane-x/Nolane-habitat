from __future__ import annotations

from dataclasses import FrozenInstanceError
import math
import unittest

from habitat.benchmarking import (
    BENCHMARK_CLASSES,
    HeldOutSuite,
    HeldOutTask,
)


def make_task(index: int = 0, **overrides) -> HeldOutTask:
    values = {
        "task_id": f"heldout-{index:02d}",
        "benchmark_class": BENCHMARK_CLASSES[index % len(BENCHMARK_CLASSES)],
        "prompt": f"Solve held-out task {index} without evaluator-only information.",
        "fixture_id": f"fixture-{index:02d}",
        "task_fingerprint": f"task-sha256:{index:064x}",
        "repository_revision": f"fixture-revision:{index:064x}",
        "budget": {"tool_calls": 12, "wall_ms": 1500.0},
    }
    values.update(overrides)
    return HeldOutTask(**values)


class HeldOutTaskTests(unittest.TestCase):
    def test_task_is_frozen_and_budget_is_canonical_immutable_tuple(self):
        task = make_task(budget={"wall_ms": 1500.0, "tool_calls": 12})
        self.assertEqual(("tool_calls", 12), task.budget[0])
        self.assertEqual(("wall_ms", 1500.0), task.budget[1])
        self.assertIsInstance(task.budget, tuple)
        with self.assertRaises(FrozenInstanceError):
            task.prompt = "changed"

    def test_task_rejects_empty_identity_and_prompt_fields(self):
        for field in (
            "task_id",
            "prompt",
            "fixture_id",
            "task_fingerprint",
            "repository_revision",
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                make_task(**{field: "   "})

    def test_task_rejects_unknown_benchmark_class(self):
        with self.assertRaises(ValueError):
            make_task(benchmark_class="not-a-benchmark-class")

    def test_budget_rejects_invalid_entries(self):
        invalid = (
            ({"": 1}, ValueError),
            ({"steps": True}, TypeError),
            ({"steps": "3"}, TypeError),
            ({"steps": -1}, ValueError),
            ({"wall_ms": math.inf}, ValueError),
            ({"wall_ms": math.nan}, ValueError),
        )
        for budget, error_type in invalid:
            with self.subTest(budget=budget), self.assertRaises(error_type):
                make_task(budget=budget)

    def test_budget_rejects_duplicate_keys_in_pair_iterable(self):
        with self.assertRaises(ValueError):
            make_task(budget=(("steps", 3), ("steps", 4)))

    def test_budget_rejects_non_mapping_or_pair_iterable(self):
        for budget in ("wall_ms", 123, (("wall_ms",),)):
            with self.subTest(budget=budget), self.assertRaises((TypeError, ValueError)):
                make_task(budget=budget)


class HeldOutSuiteTests(unittest.TestCase):
    def test_suite_is_frozen_and_normalizes_tasks_to_tuple(self):
        suite = HeldOutSuite(suite_id="foundation-heldout-v1", tasks=[make_task(0)])
        self.assertIsInstance(suite.tasks, tuple)
        with self.assertRaises(FrozenInstanceError):
            suite.suite_id = "other"

    def test_suite_requires_non_empty_identity_and_at_least_one_task(self):
        with self.assertRaises(ValueError):
            HeldOutSuite(suite_id="   ", tasks=(make_task(0),))
        with self.assertRaises(ValueError):
            HeldOutSuite(suite_id="suite", tasks=())

    def test_suite_rejects_non_task_entries(self):
        with self.assertRaises(TypeError):
            HeldOutSuite(suite_id="suite", tasks=("not-a-task",))

    def test_suite_rejects_duplicate_task_ids_and_fingerprints(self):
        first = make_task(0)
        with self.assertRaisesRegex(ValueError, "duplicate task_id"):
            HeldOutSuite(
                suite_id="suite",
                tasks=(first, make_task(1, task_id=first.task_id)),
            )
        with self.assertRaisesRegex(ValueError, "duplicate task_fingerprint"):
            HeldOutSuite(
                suite_id="suite",
                tasks=(
                    first,
                    make_task(1, task_fingerprint=first.task_fingerprint),
                ),
            )

    def test_class_coverage_uses_canonical_benchmark_class_order(self):
        chosen = (BENCHMARK_CLASSES[8], BENCHMARK_CLASSES[2], BENCHMARK_CLASSES[8])
        tasks = tuple(
            make_task(i, benchmark_class=benchmark_class)
            for i, benchmark_class in enumerate(chosen)
        )
        suite = HeldOutSuite(suite_id="suite", tasks=tasks)
        self.assertEqual(
            (BENCHMARK_CLASSES[2], BENCHMARK_CLASSES[8]),
            suite.class_coverage,
        )

    def test_complete_taxonomy_requires_every_benchmark_class(self):
        complete = HeldOutSuite(
            suite_id="complete",
            tasks=tuple(
                make_task(index, benchmark_class=benchmark_class)
                for index, benchmark_class in enumerate(BENCHMARK_CLASSES)
            ),
        )
        self.assertEqual(BENCHMARK_CLASSES, complete.class_coverage)
        self.assertEqual((), complete.missing_classes)
        self.assertIs(complete, complete.require_complete_taxonomy())

        incomplete = HeldOutSuite(
            suite_id="incomplete",
            tasks=tuple(
                make_task(index, benchmark_class=benchmark_class)
                for index, benchmark_class in enumerate(BENCHMARK_CLASSES[:-2])
            ),
        )
        self.assertEqual(BENCHMARK_CLASSES[-2:], incomplete.missing_classes)
        with self.assertRaisesRegex(ValueError, "missing benchmark classes"):
            incomplete.require_complete_taxonomy()


if __name__ == "__main__":
    unittest.main()
