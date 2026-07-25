import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.logic_engine_mvp.logic_engine_mvp.cli import main
from tools.logic_engine_mvp.logic_engine_mvp.mutation_eval import (
    build_mutation_candidates,
    generate_mutation_pack,
    mutate_code,
)


class MutationEvalTests(unittest.TestCase):
    def test_builds_complex_angle_and_relation_candidates(self) -> None:
        code = "\n".join(
            [
                "from manim import *",
                "class MainScene(Scene):",
                "    def construct(self):",
                '        eq1 = MathTex(r"OA \\\\perp l \\\\Rightarrow \\\\angle OAl = 90^\\\\circ")',
                '        eq2 = MathTex(r"AD \\\\parallel BC")',
            ]
        )

        candidates = build_mutation_candidates(code)
        rule_ids = {candidate.rule_id for candidate in candidates}

        self.assertIn("undefined_angle_endpoint", rule_ids)
        self.assertIn("line_relation_swap", rule_ids)
        angle = next(candidate for candidate in candidates if candidate.rule_id == "undefined_angle_endpoint")
        self.assertIn("\\\\angle OAQ", angle.mutated_text)
        self.assertEqual(angle.difficulty, "medium")

    def test_builds_chinese_theorem_and_condition_candidates(self) -> None:
        code = "\n".join(
            [
                "from manim import *",
                "class MainScene(Scene):",
                "    def construct(self):",
                '        t1 = Text("因为 D 是 AB 的中点，所以 DE 平行 BC 且 DE 等于 BC 的一半")',
                '        t2 = Text("用 SAS 证明两个三角形全等")',
                '        t3 = Text("圆的切线垂直于过切点的半径")',
            ]
        )

        candidates = build_mutation_candidates(code)
        by_rule = {candidate.rule_id: candidate for candidate in candidates}

        self.assertIn("midpoint_condition_error", by_rule)
        self.assertIn("word_factor_error", by_rule)
        self.assertIn("theorem_concept_swap", by_rule)
        self.assertIn("circle_line_type_swap", by_rule)
        self.assertEqual(by_rule["circle_line_type_swap"].difficulty, "expert")

    def test_mutate_code_records_ground_truth(self) -> None:
        code = "\n".join(
            [
                "from manim import *",
                "class MainScene(Scene):",
                "    def construct(self):",
                '        eq = MathTex(r"\\\\angle lAB = \\\\frac{1}{2} \\\\angle AOB")',
            ]
        )

        result = mutate_code(code, seed=3, allowed_difficulties=("hard",))

        self.assertIn("\\\\frac{2}{1}", result.code)
        self.assertEqual(result.ground_truth["difficulty"], "hard")
        self.assertEqual(result.ground_truth["expected_fix"], result.ground_truth["original_text"])
        self.assertEqual(result.ground_truth["mutation_type"], "ratio_factor_error")

    def test_equality_mutation_does_not_break_python_assignment(self) -> None:
        code = "\n".join(
            [
                "from manim import *",
                "class MainScene(Scene):",
                "    def construct(self):",
                '        step3 = Tex(r"$$\\\\therefore PA = PB \\\\quad (\\\\text{切线长定理})$$")',
            ]
        )

        candidate = next(
            item
            for item in build_mutation_candidates(code)
            if item.rule_id == "equality_inequality_flip"
        )
        result = mutate_code(code, seed=0, allowed_difficulties=("medium",))

        self.assertIn("step3 = Tex", candidate.mutated_text)
        self.assertIn("PA \\ne PB", candidate.mutated_text)
        compile(result.code, "<mutation>", "exec")

    def test_builds_point_coordinate_shift_candidate(self) -> None:
        code = "\n".join(
            [
                "from manim import *",
                "import numpy as np",
                "class MainScene(Scene):",
                "    def construct(self):",
                "        A = np.array([0, -1.5, 0])",
                "        B = np.array([2, 0, 0])",
                "        radius = Line(ORIGIN, A)",
            ]
        )

        candidate = next(
            item
            for item in build_mutation_candidates(code)
            if item.rule_id == "point_coordinate_shift"
        )

        self.assertEqual(candidate.issue_type, "wrong_geometry_position")
        self.assertIn("A = np.array([0, -0.7, 0])", candidate.mutated_text)
        result = mutate_code(code, seed=0, allowed_difficulties=("expert",))
        compile(result.code, "<mutation>", "exec")

    def test_builds_wrong_line_endpoint_candidate(self) -> None:
        code = "\n".join(
            [
                "from manim import *",
                "import numpy as np",
                "class MainScene(Scene):",
                "    def construct(self):",
                "        A = np.array([-2, 0, 0])",
                "        B = np.array([2, 0, 0])",
                "        C = np.array([0, 1.5, 0])",
                "        side_ab = Line(A, B, color=BLUE)",
            ]
        )

        candidate = next(
            item
            for item in build_mutation_candidates(code)
            if item.rule_id == "line_endpoint_swap"
        )

        self.assertEqual(candidate.issue_type, "wrong_geometry_endpoint")
        self.assertIn("Line(A, C, color=BLUE)", candidate.mutated_text)
        result = mutate_code(code, seed=0, allowed_difficulties=("expert",))
        compile(result.code, "<mutation>", "exec")

    def test_builds_axes_point_shift_candidate(self) -> None:
        code = "\n".join(
            [
                "from manim import *",
                "class MainScene(Scene):",
                "    def construct(self):",
                "        axes = Axes()",
                "        p = Dot(point=axes.c2p(2, 0), color=RED)",
            ]
        )

        candidate = next(
            item
            for item in build_mutation_candidates(code)
            if item.rule_id == "axes_point_shift"
        )

        self.assertEqual(candidate.issue_type, "wrong_graph_coordinate")
        self.assertIn("axes.c2p(3, 0)", candidate.mutated_text)
        result = mutate_code(code, seed=0, allowed_difficulties=("expert",))
        compile(result.code, "<mutation>", "exec")

    def test_generate_mutation_pack_writes_short_samples_and_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "samples"
            sample = source / "long_chinese_name_that_should_not_be_reused"
            sample.mkdir(parents=True)
            (sample / "candidate.py").write_text(
                "\n".join(
                    [
                        "from manim import *",
                        "class MainScene(Scene):",
                        "    def construct(self):",
                        '        eq = MathTex(r"OA \\\\perp l \\\\Rightarrow \\\\angle OAl = 90^\\\\circ")',
                    ]
                ),
                encoding="utf-8",
            )
            (sample / "problem_text.txt").write_text("证明切线半径垂直。", encoding="utf-8")
            (sample / "sample_meta.json").write_text(
                json.dumps({"case_id": "original", "result_id": 123}, ensure_ascii=False),
                encoding="utf-8",
            )
            out = root / "mutation_pack"

            summary = generate_mutation_pack(source, out, limit=1, seed=0)

            self.assertEqual(summary["sample_count"], 1)
            mutated_sample = out / "samples" / "MUT001_medium_undefined_angle_endpoint"
            self.assertTrue((mutated_sample / "candidate.py").exists())
            truth = json.loads((mutated_sample / "mutation_ground_truth.json").read_text(encoding="utf-8"))
            self.assertEqual(truth["source_sample_id"], sample.name)
            self.assertIn("\\\\angle OAQ", truth["mutated_text"])
            self.assertEqual(len(str(mutated_sample)), len(str(mutated_sample)))
            self.assertLessEqual(len(mutated_sample.name), 64)

    def test_generate_mutation_pack_can_create_multiple_variants_per_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "samples"
            sample = source / "case001"
            sample.mkdir(parents=True)
            (sample / "candidate.py").write_text(
                "\n".join(
                    [
                        "from manim import *",
                        "class MainScene(Scene):",
                        "    def construct(self):",
                        '        eq1 = MathTex(r"AD \\\\parallel BC")',
                        '        eq2 = MathTex(r"\\\\angle lAB = \\\\frac{1}{2} \\\\angle AOB")',
                    ]
                ),
                encoding="utf-8",
            )

            summary = generate_mutation_pack(source, root / "out", limit=3, seed=0, variants_per_source=2)

            self.assertEqual(summary["sample_count"], 2)
            self.assertEqual(summary["samples"][0]["source_sample_id"], "case001")
            self.assertEqual(summary["samples"][1]["source_sample_id"], "case001")

    def test_generate_mutation_pack_balances_sources_before_repeating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "samples"
            for index in range(1, 4):
                sample = source / f"case{index:03d}"
                sample.mkdir(parents=True)
                (sample / "candidate.py").write_text(
                    "\n".join(
                        [
                            "from manim import *",
                            "import numpy as np",
                            "class MainScene(Scene):",
                            "    def construct(self):",
                            "        A = np.array([-2, 0, 0])",
                            "        B = np.array([2, 0, 0])",
                            "        C = np.array([0, 1.5, 0])",
                            "        side_ab = Line(A, B, color=BLUE)",
                            '        eq = MathTex(r"AD \\\\parallel BC")',
                        ]
                    ),
                    encoding="utf-8",
                )

            summary = generate_mutation_pack(source, root / "out", limit=3, seed=0, variants_per_source=6)

            self.assertEqual(summary["sample_count"], 3)
            self.assertEqual(
                {sample["source_sample_id"] for sample in summary["samples"]},
                {"case001", "case002", "case003"},
            )

    def test_cli_mutate_pack_creates_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "samples"
            sample = source / "case001"
            sample.mkdir(parents=True)
            (sample / "candidate.py").write_text(
                "\n".join(
                    [
                        "from manim import *",
                        "class MainScene(Scene):",
                        "    def construct(self):",
                        '        eq = MathTex(r"AD \\\\parallel BC")',
                    ]
                ),
                encoding="utf-8",
            )
            out = root / "out"

            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "mutate-pack",
                        "--samples-root",
                        str(source),
                        "--out",
                        str(out),
                        "--limit",
                        "1",
                        "--difficulty",
                        "medium",
                    ]
                )

            self.assertEqual(code, 0)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["sample_count"], 1)
            self.assertEqual(manifest["samples"][0]["mutation_type"], "line_relation_swap")


if __name__ == "__main__":
    unittest.main()
