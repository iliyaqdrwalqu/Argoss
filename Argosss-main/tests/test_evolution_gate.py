import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.skills.evolution import ArgosEvolution
import src.skills.evolution.skill as evolution_module


class TestEvolutionGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="argos_evo_test_")
        self.skills_dir = os.path.join(self.tmp, "skills")
        self.tests_dir = os.path.join(self.tmp, "tests_generated")
        os.makedirs(self.skills_dir, exist_ok=True)
        os.makedirs(self.tests_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sample_skill_code(self) -> str:
        return (
            "class HelloSkill:\n"
            "    def handle(self, text):\n"
            "        return 'ok'\n"
        )

    def test_rejects_when_review_fails(self):
        evo = ArgosEvolution(ai_core=None)
        failing_test = (
            "import unittest\n"
            "import skill_under_test as s\n"
            "class T(unittest.TestCase):\n"
            "    def test_smoke(self):\n"
            "        self.assertTrue(True)\n"
        )

        with patch.object(evolution_module, "SKILLS_DIR", self.skills_dir), \
             patch.object(evolution_module, "TESTS_GEN_DIR", self.tests_dir), \
             patch.object(ArgosEvolution, "_review_patch", return_value=(False, "security issue")):
            result = evo.apply_patch("hello_skill", self._sample_skill_code(), test_code=failing_test)

        self.assertIn("Code Review не пройден", result)
        self.assertFalse(os.path.exists(os.path.join(self.skills_dir, "hello_skill.py")))

    def test_rejects_when_unit_test_fails(self):
        evo = ArgosEvolution(ai_core=None)
        failing_test = (
            "import unittest\n"
            "import skill_under_test as s\n"
            "class T(unittest.TestCase):\n"
            "    def test_fail(self):\n"
            "        self.assertEqual(1, 2)\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n"
        )

        with patch.object(evolution_module, "SKILLS_DIR", self.skills_dir), \
             patch.object(evolution_module, "TESTS_GEN_DIR", self.tests_dir), \
             patch.object(ArgosEvolution, "_review_patch", return_value=(True, "ok")):
            result = evo.apply_patch("hello_skill", self._sample_skill_code(), test_code=failing_test)

        self.assertIn("unit-тест не пройден", result)
        self.assertFalse(os.path.exists(os.path.join(self.skills_dir, "hello_skill.py")))

    def test_accepts_when_review_and_tests_pass(self):
        evo = ArgosEvolution(ai_core=None)
        passing_test = (
            "import unittest\n"
            "import skill_under_test as s\n"
            "class T(unittest.TestCase):\n"
            "    def test_handle(self):\n"
            "        inst = s.HelloSkill()\n"
            "        self.assertEqual(inst.handle('x'), 'ok')\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n"
        )

        with patch.object(evolution_module, "SKILLS_DIR", self.skills_dir), \
             patch.object(evolution_module, "TESTS_GEN_DIR", self.tests_dir), \
             patch.object(ArgosEvolution, "_review_patch", return_value=(True, "approved")):
            result = evo.apply_patch("hello_skill", self._sample_skill_code(), test_code=passing_test)

        self.assertIn("внедрён", result)
        self.assertTrue(os.path.exists(os.path.join(self.skills_dir, "hello_skill.py")))
        self.assertTrue(os.path.exists(os.path.join(self.tests_dir, "test_skill_hello_skill.py")))


if __name__ == "__main__":
    unittest.main()
