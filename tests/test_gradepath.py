import unittest

from gradepath import core, create_app
from gradepath.core import Task, at_risk, check_weights, comment, competency_profile, distribution, letter, mastery, mastery_label, rank, rubric_score, weighted_percent

W = {"Quiz": 40, "Project": 60}
TASKS = [Task(1, "Q1", "Quiz", 10), Task(2, "Q2", "Quiz", 20), Task(3, "P1", "Project", 100)]


class TestGrades(unittest.TestCase):
    def test_letters_at_each_cut(self):
        self.assertEqual(letter(80), ("A+", 5.0))
        self.assertEqual(letter(79.99), ("A", 4.75))
        self.assertEqual(letter(45), ("D", 2.0))
        self.assertEqual(letter(44.9), ("F", 0.0))

    def test_weighted(self):
        p, parts = weighted_percent(TASKS, {1: 10, 2: 10, 3: 50}, W)
        self.assertAlmostEqual(parts["Quiz"], 20 / 30 * 100)
        self.assertAlmostEqual(p, 0.4 * 20 / 30 * 100 + 0.6 * 50)

    def test_missing_counts_as_zero_or_is_excused(self):
        s = {1: 10, 2: None, 3: 100}
        self.assertLess(weighted_percent(TASKS, s, W)[0], weighted_percent(TASKS, s, W, missing="exclude")[0])
        self.assertEqual(weighted_percent(TASKS, s, W, missing="exclude")[0], 100)

    def test_empty_category_shares_its_weight(self):
        p, _ = weighted_percent(TASKS, {1: 5, 2: 10}, W, missing="exclude")
        self.assertEqual(p, 50)

    def test_nothing_entered(self):
        self.assertIsNone(weighted_percent(TASKS, {}, W, missing="exclude")[0])

    def test_drop_lowest(self):
        t = [Task(i, f"Q{i}", "Quiz", 10) for i in range(1, 5)]
        p, _ = weighted_percent(t, {1: 2, 2: 10, 3: 10, 4: 10}, {"Quiz": 100}, {"Quiz": 1})
        self.assertEqual(p, 100)

    def test_drop_lowest_keeps_one_task(self):
        p, _ = weighted_percent([Task(1, "Q", "Quiz", 10)], {1: 5}, {"Quiz": 100}, {"Quiz": 3})
        self.assertEqual(p, 50)

    def test_score_outside_range(self):
        with self.assertRaises(ValueError):
            weighted_percent(TASKS, {1: 11}, W)

    def test_weights_must_add_up(self):
        with self.assertRaises(ValueError):
            check_weights({"a": 30, "b": 30})

    def test_raising_one_mark_never_lowers_the_result(self):
        import random
        rng = random.Random(1)
        for _ in range(300):
            s = {1: rng.uniform(0, 9), 2: rng.uniform(0, 19), 3: rng.uniform(0, 99)}
            a = weighted_percent(TASKS, s, W)[0]
            k = rng.choice([1, 2, 3])
            s[k] += 0.5
            self.assertGreaterEqual(weighted_percent(TASKS, s, W)[0], a)


class TestCompetency(unittest.TestCase):
    def test_methods(self):
        e = [40, 60, 90]
        self.assertEqual(mastery(e, "latest"), 90)
        self.assertEqual(mastery(e, "highest"), 90)
        self.assertAlmostEqual(mastery(e, "mean"), 190 / 3)
        self.assertGreater(mastery(e, "decaying"), mastery(e, "mean"))
        self.assertIsNone(mastery([]))
        with self.assertRaises(ValueError):
            mastery(e, "nope")

    def test_improvement_counts_more_than_past_failure(self):
        self.assertGreater(mastery([30, 90, 90]), mastery([90, 90, 30]))

    def test_labels(self):
        self.assertEqual([mastery_label(v) for v in (85, 70, 50, 10, None)], ["Mastered", "Competent", "Developing", "Beginning", "No evidence"])

    def test_profile_follows_task_order(self):
        t = [Task(1, "a", "Q", 10, ("Excel",), 2), Task(2, "b", "Q", 10, ("Excel", "Typing"), 1)]
        p = competency_profile(t, {1: 10, 2: 5}, "latest")
        self.assertEqual(p["Excel"], (100, "Mastered", 2))
        self.assertEqual(p["Typing"][0], 50)

    def test_rubric(self):
        self.assertEqual(rubric_score([4, 4]), 100)
        self.assertEqual(rubric_score([2, 4], [3, 1]), 62.5)
        for bad in (([],), ([5],), ([2], [1, 1])):
            with self.assertRaises(ValueError):
                rubric_score(*bad)


class TestClass(unittest.TestCase):
    def test_rank_ties(self):
        self.assertEqual(rank({"a": 90, "b": 80, "c": 80, "d": 70}), {"a": 1, "b": 2, "c": 2, "d": 4})

    def test_distribution(self):
        d = distribution([90, 85, 10])
        self.assertEqual((d["A+"], d["F"], d["B"]), (2, 1, 0))

    def test_risk(self):
        r = at_risk({"low": [30, 40], "fall": [90, 90, 60, 60], "fine": [70, 72, 71, 73], "rise": [40, 40, 80, 80]})
        self.assertEqual(set(r), {"low", "fall"})
        self.assertIn("fell 30", r["fall"][0])

    def test_comment_is_specific(self):
        c = comment(82, {"Excel": (90, "", 1), "Email": (40, "", 1)})
        self.assertIn("Strong in Excel", c)
        self.assertIn("focus on Email", c)
        self.assertIn("Not enough", comment(None, {}))


class TestApp(unittest.TestCase):
    def setUp(self):
        self.a = create_app(":memory:")
        self.a.post("/learners", names="Rahima\nKarim\n\nRahima")
        self.a.post("/weights", category="Quiz", weight=40)
        self.a.post("/weights", category="Project", weight=60)
        self.a.post("/tasks", name="Quiz 1", category="Quiz", out_of=20, competencies="Excel, Typing")
        self.a.post("/tasks", name="Project", category="Project", out_of=100, competencies="Excel")

    def text(self, url):
        return self.a.get(url).body.decode()

    def enter(self, task, rahima, karim):
        r = self.a.post(f"/task/{task}", s1=rahima, s2=karim)
        self.assertEqual(r.status, 303)

    def test_duplicate_names_are_ignored(self):
        self.assertEqual(self.a.one("SELECT COUNT(*) FROM learners"), 2)

    def test_flow(self):
        self.enter(1, 18, 8)
        self.enter(2, 80, 40)
        home = self.text("/")
        self.assertIn("Rahima", home)
        self.assertIn("84.0", home)
        self.assertIn("A+", home)
        self.assertIn("average below the pass mark", home)
        page = self.text("/learner/1")
        self.assertIn("Excel", page)
        self.assertIn("Strong in", page)

    def test_blank_means_excused(self):
        self.enter(1, 10, "")
        self.enter(2, 100, 100)
        self.assertIn("100.0", self.text("/"))

    def test_mark_above_the_maximum_is_refused(self):
        self.assertEqual(self.a.post("/task/1", s1=21, s2=1).status, 400)
        self.assertEqual(self.a.one("SELECT COUNT(*) FROM scores"), 0)

    def test_wrong_weights_are_shown(self):
        self.a.post("/weights", category="Project", weight=10)
        self.assertIn("add up to 50", self.text("/"))

    def test_task_needs_a_real_category(self):
        self.assertEqual(self.a.post("/tasks", name="x", category="None", out_of=5).status, 400)

    def test_export(self):
        self.enter(1, 20, 10)
        csv = self.a.get("/export.csv")
        self.assertIn("text/csv", csv.kind)
        self.assertIn("Rahima,100.0,A+", csv.body.decode())

    def test_formula_in_a_name_is_defused_on_export(self):
        self.a.post("/learners", names="=HYPERLINK(1)")
        self.assertIn("'=HYPERLINK", self.a.get("/export.csv").body.decode())

    def test_missing_pages(self):
        self.assertEqual(self.a.get("/learner/99").status, 404)
        self.assertEqual(self.a.get("/task/99").status, 404)


if __name__ == "__main__":
    unittest.main()
