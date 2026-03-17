# Review UI

This folder contains the browser UI for the run-based sales-tax review workflow.

The UI now matches the repo's current pipeline:

1. stage one workbook into an isolated run folder
2. generate lightweight helper context for that run
3. launch Claude CLI in the background for that run
4. automatically validate and apply the annotations when Claude finishes
5. download the reviewed workbook

The UI also shows recent run folders so workbooks do not cross-contaminate each other.

If Claude CLI is not installed or a run needs recovery, you can still upload `annotations.json` manually for that run and apply it from the browser.

Run it from here:

```bash
python3 server.py
```

Then open:

```text
http://127.0.0.1:8790
```
