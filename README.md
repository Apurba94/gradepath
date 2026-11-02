# GradePath

An offline gradebook for competency-based teaching. It answers two questions: "what is this learner's mark?" and "what can this learner actually do?" It runs on your own computer with no internet.

```
python -m gradepath
```

Then open http://127.0.0.1:8022. It needs Python 3.10 or newer, and nothing else.

## What it does

- **Weighted grades:** categories such as quizzes and projects, with weights that must add up to 100, and a clear warning if they do not
- **Fair handling of gaps:** an empty box means an excused absence. A category with no work yet shares its weight, so mid-term figures make sense
- **Competency mastery:** each task can link to competencies, and mastery weighs recent evidence more, so a learner who improved gets credit for it
- **Rubrics:** criteria with weights give a percentage
- **Early warnings:** learners below the pass mark, or falling sharply through the term
- **Report comments:** a specific draft for each learner, to edit
- **CSV export**

The default grade scale is the common Bangladeshi A+ to F. You can pass your own to the functions in `core.py`.

## How mastery works

Evidence is combined with a decaying average, so later results count more. A learner scoring 30, 90, 90 ends far above one scoring 90, 90, 30. You can also choose the latest result, the highest, or the plain mean.

## How it is tested

Logic is tested on hand examples, grade boundaries and edge cases, such as dropping a learner's only task. A random test confirms that raising any one mark can never lower a final grade. App tests run the whole flow and check that marks above the maximum are refused, and that a name such as `=HYPERLINK(...)` cannot become a formula in the exported file.

## Limits

It is built for one teacher and one class in a file, with no logins. Keep a copy of the data file, because it is the only copy. Comments are drafts, and a teacher should read each one before it reaches a family.

MIT licence.
