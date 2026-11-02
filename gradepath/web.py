"""The offline web app."""
import json

from . import core
from .fieldkit import App, Fail, Raw, bar_chart, card, download, form, h, link, redirect, stats, table

SCHEMA = """
CREATE TABLE IF NOT EXISTS learners (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS weights (category TEXT PRIMARY KEY, weight REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL REFERENCES weights(category), out_of REAL NOT NULL, competencies TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS scores (learner INTEGER NOT NULL REFERENCES learners(id), task INTEGER NOT NULL REFERENCES tasks(id), value REAL, PRIMARY KEY (learner, task));
"""


def create_app(db="gradepath.db"):
    a = App("GradePath", db, SCHEMA, [("Class", "/"), ("Learners", "/learners"), ("Tasks", "/tasks"), ("Weights", "/weights"), ("Export", "/export.csv")])

    def tasks():
        return [core.Task(t["id"], t["name"], t["category"], t["out_of"], tuple(json.loads(t["competencies"])), t["id"]) for t in a.rows("SELECT * FROM tasks ORDER BY id")]

    def scores_of(lid):
        return {r["task"]: r["value"] for r in a.rows("SELECT task, value FROM scores WHERE learner = ?", lid)}

    def weights():
        return {r["category"]: r["weight"] for r in a.rows("SELECT * FROM weights")}

    def final(lid):
        w = weights()
        if abs(sum(w.values()) - 100) > 1e-9:
            return None, {}
        return core.weighted_percent(tasks(), scores_of(lid), w, missing="exclude")

    @a.route("/")
    def home(req):
        learners = a.rows("SELECT * FROM learners ORDER BY name")
        w = weights()
        problem = "" if not w or abs(sum(w.values()) - 100) < 1e-9 else f'<div class="flash bad">Category weights add up to {sum(w.values()):g}, not 100. <a href="/weights">Fix them</a>.</div>'
        results = {l["id"]: final(l["id"])[0] for l in learners}
        done = {k: v for k, v in results.items() if v is not None}
        ranks = core.rank(done)
        history = {}
        for l in learners:
            sc = scores_of(l["id"])
            history[l["name"]] = [sc[t.id] / t.out_of * 100 for t in tasks() if sc.get(t.id) is not None]
        risk = core.at_risk(history)
        rows = [{"id": l["id"], "name": l["name"], "pct": results[l["id"]], "rank": ranks.get(l["id"], ""), "risk": "; ".join(risk.get(l["name"], []))} for l in learners]
        rows.sort(key=lambda r: (r["pct"] is None, -(r["pct"] or 0)))
        dist = core.distribution(done.values())
        body = problem + stats([("Learners", len(learners)), ("Tasks", len(tasks())), ("Class mean", f"{sum(done.values()) / len(done):.1f}%" if done else "n/a"), ("At risk", len(risk))])
        body += card("Class", table(rows, [("Rank", "rank"), ("Learner", lambda r: link(f"/learner/{r['id']}", r["name"])), ("Percent", lambda r: "" if r["pct"] is None else f"{r['pct']:.1f}"), ("Grade", lambda r: "" if r["pct"] is None else core.letter(r["pct"])[0]), ("Watch", lambda r: Raw(f'<span class="warn">{h(r["risk"])}</span>'))], "Add learners to begin."))
        body += card("Grade spread", bar_chart(list(dist.items())))
        return a.page("Class overview", body)

    @a.route("/learners", ("GET", "POST"))
    def learners(req):
        if req.method == "POST":
            for name in req.text("names", limit=100000).splitlines():
                if name.strip():
                    a.run("INSERT OR IGNORE INTO learners (name) VALUES (?)", name.strip())
            return redirect("/learners")
        return a.page("Learners", card("Add learners, one name per line", form(a, "/learners", [("names", "Names", "textarea")], "Add")) + card("All learners", table(a.rows("SELECT * FROM learners ORDER BY name"), [("Name", lambda r: link(f"/learner/{r['id']}", r["name"]))])))

    @a.route("/weights", ("GET", "POST"))
    def weight_page(req):
        if req.method == "POST":
            a.run("INSERT INTO weights (category, weight) VALUES (?, ?) ON CONFLICT(category) DO UPDATE SET weight = excluded.weight", req.text("category"), req.number("weight", low=0, high=100))
            return redirect("/weights")
        w = weights()
        return a.page("Weights", card("Category weights must add up to 100", table(a.rows("SELECT * FROM weights ORDER BY category"), [("Category", "category"), ("Weight", "weight")]) + f"<p>Total: {sum(w.values()):g}</p>" + form(a, "/weights", [("category", "Category"), ("weight", "Weight", "number")], "Save")))

    @a.route("/tasks", ("GET", "POST"))
    def task_page(req):
        if req.method == "POST":
            comps = [c.strip() for c in req.text("competencies", required=False).split(",") if c.strip()]
            cat = req.text("category")
            if not a.row("SELECT 1 FROM weights WHERE category = ?", cat):
                raise Fail("Create that category on the Weights page first")
            a.run("INSERT INTO tasks (name, category, out_of, competencies) VALUES (?, ?, ?, ?)", req.text("name"), cat, req.number("out_of", low=0.01), json.dumps(comps, ensure_ascii=False))
            return redirect("/tasks")
        cats = [(r["category"], r["category"]) for r in a.rows("SELECT category FROM weights ORDER BY category")]
        return a.page("Tasks", card("Add a task", form(a, "/tasks", [("name", "Task"), ("category", "Category", "select", cats), ("out_of", "Out of", "number", 100), ("competencies", "Competencies, separated by commas")], "Add")) + card("Tasks", table(tasks(), [("Task", lambda t: link(f"/task/{t.id}", t.name)), ("Category", lambda t: t.category), ("Out of", lambda t: t.out_of), ("Competencies", lambda t: ", ".join(t.competencies))])))

    @a.route("/task/<id>", ("GET", "POST"))
    def task(req, id):
        t = a.row("SELECT * FROM tasks WHERE id = ?", id)
        if t is None:
            raise Fail("No such task", 404)
        learners = a.rows("SELECT * FROM learners ORDER BY name")
        if req.method == "POST":
            for l in learners:
                text = str(req.form.get(f"s{l['id']}", "")).strip()
                value = None
                if text:
                    value = req.number(f"s{l['id']}", low=0, high=t["out_of"])
                a.run("INSERT INTO scores (learner, task, value) VALUES (?, ?, ?) ON CONFLICT(learner, task) DO UPDATE SET value = excluded.value", l["id"], id, value)
            a.log("enter scores", t["name"])
            return redirect(f"/task/{id}")
        have = {r["learner"]: r["value"] for r in a.rows("SELECT learner, value FROM scores WHERE task = ?", id)}
        fields = [(f"s{l['id']}", l["name"], "number", have.get(l["id"]) if have.get(l["id"]) is not None else "") for l in learners]
        return a.page(t["name"], card(f"Scores out of {t['out_of']:g}. Leave a box empty for an excused absence.", form(a, f"/task/{id}", fields, "Save scores")))

    @a.route("/learner/<id>")
    def learner(req, id):
        l = a.row("SELECT * FROM learners WHERE id = ?", id)
        if l is None:
            raise Fail("No such learner", 404)
        pct, parts = final(id)
        profile = core.competency_profile(tasks(), scores_of(id))
        body = stats([("Percent", "n/a" if pct is None else f"{pct:.1f}"), ("Grade", "n/a" if pct is None else core.letter(pct)[0])])
        body += card("Report comment (a draft to edit)", f"<p>{h(core.comment(pct, profile))}</p>")
        body += card("By category", bar_chart(sorted(parts.items()), unit="%"))
        body += card("Competencies", table([{"c": c, "v": v} for c, v in sorted(profile.items())], [("Competency", "c"), ("Level", lambda r: f"{r['v'][0]:.0f}%"), ("Status", lambda r: r["v"][1]), ("Evidence", lambda r: r["v"][2])], "No competency evidence yet."))
        return a.page(l["name"], body)

    @a.route("/export.csv")
    def export(req):
        rows = []
        for l in a.rows("SELECT * FROM learners ORDER BY name"):
            pct, _ = final(l["id"])
            rows.append([l["name"], "" if pct is None else round(pct, 2), "" if pct is None else core.letter(pct)[0]])
        return download(rows, ["learner", "percent", "grade"], "grades.csv")

    return a
