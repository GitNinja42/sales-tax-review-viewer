#!/usr/bin/env python3
"""Export a review run as a self-contained static site for GitHub Pages."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from run_utils import load_run_manifest  # noqa: E402
from viewer_payload import build_viewer_payload  # noqa: E402


def export_static(run_dir: Path, out_dir: Path) -> None:
    run_dir = run_dir.resolve()
    manifest = load_run_manifest(run_dir)
    payload = build_viewer_payload(BASE_DIR, run_dir, manifest)

    out_dir.mkdir(parents=True, exist_ok=True)

    # Copy CSS as-is.
    shutil.copy(BASE_DIR / "review_ui" / "styles.css", out_dir / "styles.css")

    # Read the original viewer.js and patch it for static mode.
    viewer_js = (BASE_DIR / "review_ui" / "viewer.js").read_text()

    # Replace the init() fetch with inline payload reading.
    static_init = """async function init() {
  const payload = window.__VIEWER_PAYLOAD__;
  if (!payload) {
    viewerTitle.textContent = "No data";
    viewerSubtitle.textContent = "Payload was not embedded.";
    return;
  }

  state.payload = payload;

  // Initialize row-level dismiss state from persisted data.
  payload.rows.forEach((row) => {
    if (!row.annotation) return;
    row.annotation._dismissed = row.annotation._dismissed || false;
  });

  searchInput.addEventListener("input", (event) => {
    state.query = event.target.value;
    render();
  });
  checklistFilter.addEventListener("change", (event) => {
    state.checklist = event.target.value;
    render();
  });
  flaggedOnlyToggle.addEventListener("change", (event) => {
    state.flaggedOnly = event.target.checked;
    if (!state.flaggedOnly) {
      state.activeStatuses.clear();
    }
    render();
  });
  clearFocusButton.addEventListener("click", clearFocus);
  clearAllFiltersButton.addEventListener("click", clearAllFilters);
  expandSpreadsheetButton.addEventListener("click", toggleSpreadsheetWidth);
  regenerateButton.addEventListener("click", regenerateWorkbook);

  // Editable annotation fields: save on blur (in-memory only for static).
  detailIssue.addEventListener("focus", () => {
    if (detailIssue.classList.contains("is-placeholder")) {
      detailIssue.textContent = "";
      detailIssue.classList.remove("is-placeholder");
    }
  });
  detailIssue.addEventListener("blur", () => {
    const row = selectedRow();
    if (!row?.annotation) return;
    const text = detailIssue.textContent.trim();
    if (text && text !== row.annotation.issueSummary) {
      saveAnnotationField(row, "issue_summary", text);
    }
  });
  detailIssue.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); detailIssue.blur(); }
    if (e.key === "Escape") { detailIssue.blur(); }
  });

  detailNextStep.addEventListener("focus", () => {
    if (detailNextStep.classList.contains("is-placeholder")) {
      detailNextStep.textContent = "";
      detailNextStep.classList.remove("is-placeholder");
    }
  });
  detailNextStep.addEventListener("blur", () => {
    const row = selectedRow();
    if (!row) return;
    const text = detailNextStep.textContent.trim();
    const original = row.annotation?.suggestedNextStep || "";
    if (text !== original) {
      if (row.annotation) {
        saveAnnotationField(row, "suggested_next_step", text);
      }
    }
    if (!text) {
      detailNextStep.textContent = "Add a suggested next step...";
      detailNextStep.classList.add("is-placeholder");
    }
  });
  detailNextStep.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); detailNextStep.blur(); }
    if (e.key === "Escape") { detailNextStep.blur(); }
  });

  feedbackUpButton.addEventListener("click", () => setFeedbackVote("up"));
  feedbackDownButton.addEventListener("click", () => setFeedbackVote("down"));
  feedbackComment.addEventListener("input", (event) => setFeedbackCommentValue(event.target.value));
  feedbackComment.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeFeedbackNote();
      return;
    }
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      submitFeedback({ keepNoteOpen: true });
    }
  });
  feedbackSubmitButton.addEventListener("click", () => submitFeedback({ keepNoteOpen: true }));
  feedbackDismissButton.addEventListener("click", closeFeedbackNote);
  document.addEventListener("pointerdown", handleFeedbackShellPointerDown);

  render();
}"""

    # Find the original init function and replace it.
    # The init function starts with "async function init() {" and ends before
    # "// --- Column resize ---"
    init_start = viewer_js.index("async function init() {")
    init_end = viewer_js.index("// --- Column resize ---")
    viewer_js = viewer_js[:init_start] + static_init + "\n\n" + viewer_js[init_end:]

    # Make all fetch-based functions into in-memory-only operations.
    # Replace dismissRow's fetch with a no-op.
    viewer_js = viewer_js.replace(
        """  const runId = getRunId();
  try {
    await fetch(`/api/runs/${runId}/dismiss`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rowNum: row.rowNum,
        dismissed: !isDismissed,
      }),
    });
  } catch (err) {
    console.error("Failed to save dismiss state:", err);
  }""",
        "  // Static mode: dismiss is in-memory only."
    )

    # Replace manualFlagRow's fetch.
    viewer_js = viewer_js.replace(
        """  const runId = getRunId();
  try {
    const response = await fetch(`/api/runs/${runId}/flag`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rowNum: row.rowNum }),
    });
    if (response.ok) {
      const result = await response.json();
      // Update local state with the new annotation.
      row.annotation = result.annotation;
      row.isFlagged = true;
      state.workbookStale = true;
      render();
    }
  } catch (err) {
    console.error("Failed to flag row:", err);
  }""",
        """  // Static mode: flag in-memory only.
  row.annotation = { status: "Review Needed", issueSummary: "", checklistRefs: [], checklistTitles: [] };
  row.isFlagged = true;
  state.workbookStale = true;
  render();"""
    )

    # Replace changeRowStatus fetch calls with no-ops.
    viewer_js = viewer_js.replace(
        """      try {
        await fetch(`/api/runs/${runId}/dismiss`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rowNum: row.rowNum, dismissed: true }),
        });
      } catch (err) {
        console.error("Failed to dismiss:", err);
      }""",
        "      // Static mode: dismiss in-memory only."
    )

    viewer_js = viewer_js.replace(
        """      try {
        await fetch(`/api/runs/${runId}/dismiss`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rowNum: row.rowNum, dismissed: false }),
        });
        await fetch(`/api/runs/${runId}/annotate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rowNum: row.rowNum, status: newStatus }),
        });
      } catch (err) {
        console.error("Failed to update status:", err);
      }""",
        "      // Static mode: status change in-memory only."
    )

    viewer_js = viewer_js.replace(
        """      try {
        await fetch(`/api/runs/${runId}/flag`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rowNum: row.rowNum, status: newStatus }),
        });
      } catch (err) {
        console.error("Failed to flag:", err);
      }""",
        "      // Static mode: flag in-memory only."
    )

    # Replace saveAnnotationField fetch.
    viewer_js = viewer_js.replace(
        """  const runId = getRunId();
  try {
    const resp = await fetch(`/api/runs/${runId}/annotate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rowNum: row.rowNum, [field]: value }),
    });
    if (resp.ok) {
      // Update in-memory annotation too.
      if (field === "issue_summary" && row.annotation) row.annotation.issueSummary = value;
      if (field === "suggested_next_step" && row.annotation) row.annotation.suggestedNextStep = value;
      state.workbookStale = true;
      render();
    }
  } catch (err) {
    console.error("Failed to save annotation field:", err);
  }""",
        """  // Static mode: save in-memory only.
  if (field === "issue_summary" && row.annotation) row.annotation.issueSummary = value;
  if (field === "suggested_next_step" && row.annotation) row.annotation.suggestedNextStep = value;
  state.workbookStale = true;
  render();"""
    )

    # Replace regenerateWorkbook fetch.
    viewer_js = viewer_js.replace(
        """  try {
    const response = await fetch(`/api/runs/${runId}/regenerate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const result = await response.json();
    if (response.ok) {
      state.workbookStale = false;
      regenerateButton.textContent = "Regenerate workbook";
      render();
    } else {
      regenerateButton.textContent = "Failed, retry";
      console.error("Regeneration failed:", result.error);
    }
  } catch (err) {
    regenerateButton.textContent = "Failed, retry";
    console.error("Regeneration error:", err);
  } finally {
    regenerateButton.disabled = false;
  }""",
        """  // Static mode: no workbook regeneration available.
  regenerateButton.textContent = "Not available in preview";
  regenerateButton.disabled = false;"""
    )

    # Replace submitFeedback fetch.
    viewer_js = viewer_js.replace(
        """  try {
    const response = await fetch(`/api/runs/${getRunId()}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rowNum: row.rowNum,
        vote: draft.vote,
        comment: draft.comment.trim(),
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Feedback could not be saved.");
    }
  } catch (error) {
    draft.error = error instanceof Error ? error.message : "Feedback could not be saved.";
  } finally {""",
        """  // Static mode: feedback saved in-memory only.
  try {
    // No-op in static mode.
  } catch (error) {
    draft.error = "Feedback not available in preview mode.";
  } finally {"""
    )

    # Write the patched JS.
    (out_dir / "viewer.js").write_text(viewer_js)

    # Build the HTML with inlined payload.
    run_id = manifest.get("run_id", "unknown")
    payload_json = json.dumps(payload)

    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Review Viewer</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap"
      rel="stylesheet"
    />
    <link rel="stylesheet" href="styles.css" />
  </head>
  <body class="viewer-body">
    <div class="viewer-shell">
      <header class="viewer-hero panel">
        <div class="viewer-hero-row">
          <div class="viewer-hero-left">
            <h1 class="viewer-hero-title" id="viewerTitle">Loading...</h1>
          </div>
          <div class="viewer-hero-actions">
            <span class="workbook-stale-badge is-hidden" id="workbookStaleBadge">Workbook out of date</span>
            <button class="button button-secondary button-sm is-hidden" id="regenerateButton" type="button">Regenerate workbook</button>
            <a class="button button-ghost button-sm is-hidden" id="viewerDownloadLink" href="#">Download workbook</a>
          </div>
        </div>
        <p class="viewer-hero-subtitle" id="viewerSubtitle">Preparing row-level review context.</p>
      </header>

      <details class="viewer-collapsible viewer-toolbar panel">
        <summary class="viewer-collapsible-summary">
          <div>
            <p class="viewer-kicker">Review controls</p>
            <h2>Search and filters</h2>
            <p id="filterSummary">Search all rows or tighten the review set.</p>
          </div>
          <span class="viewer-collapsible-toggle" aria-hidden="true"></span>
        </summary>
        <div class="viewer-collapsible-body">
          <div class="viewer-toolbar-main">
            <label class="viewer-search">
              <span>Search rows</span>
              <input id="searchInput" type="search" placeholder="Customer, account, memo, issue summary..." />
            </label>
            <label class="viewer-checklist-filter">
              <span>Checklist question</span>
              <select id="checklistFilter">
                <option value="all">All checklist questions</option>
              </select>
            </label>
          </div>
          <div class="viewer-toolbar-secondary">
            <div class="viewer-focus-pill is-hidden" id="focusPill">
              <span id="focusLabel">Focused set</span>
              <button class="pill-remove" id="clearFocusButton" type="button">Clear</button>
            </div>
          </div>
          <div class="viewer-status-chips" id="statusChips"></div>
        </div>
      </details>

      <div class="viewer-layout" id="viewerLayout">
        <section class="viewer-table-panel panel">
          <div class="viewer-section-head">
            <div>
              <h2>Transaction rows</h2>
              <p id="tableMeta">Loading rows...</p>
            </div>
            <div class="viewer-section-actions">
              <label class="viewer-toggle viewer-toggle-inline">
                <input id="flaggedOnlyToggle" type="checkbox" checked />
                <span>Flagged only</span>
              </label>
              <button class="button button-ghost button-sm is-hidden" id="clearAllFiltersButton" type="button">
                Clear filters
              </button>
              <button class="button button-ghost viewer-layout-button" id="expandSpreadsheetButton" type="button">
                Expand spreadsheet
              </button>
            </div>
          </div>
          <div class="viewer-table-wrap">
            <table class="viewer-table">
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Status</th>
                  <th>Name</th>
                  <th>Account</th>
                  <th>Tax code</th>
                  <th>Memo / description</th>
                  <th>Review note</th>
                </tr>
              </thead>
              <tbody id="viewerTableBody"></tbody>
            </table>
          </div>
        </section>

        <div class="panel-resize-handle" id="panelResizeHandle"></div>
        <aside class="viewer-detail-panel panel" id="detailPanel">
          <div class="viewer-empty-detail" id="emptyDetail">
            <h2>Select a row</h2>
            <p>Choose a row from the table to see the flag reason, highlighted evidence, and similar rows you can review together.</p>
          </div>
          <div class="viewer-detail is-hidden" id="detailContent">
            <div class="viewer-detail-head">
              <div>
                <p class="viewer-kicker" id="detailKicker">Row</p>
                <h2 id="detailTitle">Row detail</h2>
              </div>
              <span class="viewer-status-badge" id="detailStatus">Unflagged</span>
            </div>

            <div class="detail-meta-row">
              <div class="token-list detail-meta" id="detailMeta"></div>
              <div class="detail-inline-feedback" id="feedbackShell">
                <div class="feedback-votes" id="feedbackVotes">
                  <button class="feedback-vote feedback-vote-up" id="feedbackUpButton" type="button" aria-label="Helpful flag">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M7 10v10M14 10V5.5A2.5 2.5 0 0 0 11.5 3L7 10v10h9.2a2 2 0 0 0 1.96-1.62l1.2-6A2 2 0 0 0 17.4 10H14Z" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"/>
                      <path d="M4 10h3v10H4a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1Z" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"/>
                    </svg>
                    <span class="sr-only">Thumbs up</span>
                  </button>
                  <button class="feedback-vote feedback-vote-down" id="feedbackDownButton" type="button" aria-label="Unhelpful flag">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M7 14V4M14 14v4.5a2.5 2.5 0 0 1-2.5 2.5L7 14V4h9.2a2 2 0 0 1 1.96 1.62l1.2 6A2 2 0 0 1 17.4 14H14Z" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"/>
                      <path d="M4 4h3v10H4a1 1 0 0 0-1 1v0a1 1 0 0 0 1 1h3" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"/>
                    </svg>
                    <span class="sr-only">Thumbs down</span>
                  </button>
                </div>
                <div class="feedback-panel is-hidden" id="feedbackPanel">
                  <label class="feedback-comment">
                    <span>Optional note</span>
                    <textarea id="feedbackComment" rows="3" placeholder="What should we keep, change, or clarify here?"></textarea>
                  </label>
                  <div class="feedback-actions">
                    <button class="button button-ghost feedback-save-note" id="feedbackSubmitButton" type="button">Save note</button>
                    <button class="button button-ghost feedback-dismiss" id="feedbackDismissButton" type="button">Done</button>
                  </div>
                </div>
                <p class="feedback-status is-hidden" id="feedbackStatus"></p>
              </div>
            </div>

            <div class="detail-callout">
              <div class="detail-callout-section">
                <span class="detail-callout-label">What needs review</span>
                <p class="editable-field" id="detailIssue" tabindex="0">No formal issue was recorded for this row.</p>
              </div>
              <div class="detail-callout-section">
                <span class="detail-callout-label">Suggested next step</span>
                <p class="editable-field" id="detailNextStep" tabindex="0">No suggested next step was recorded.</p>
              </div>
              <button class="button button-ghost button-sm detail-dismiss-button is-hidden" id="detailDismissButton" type="button">
                Review not needed
              </button>
            </div>

            <div class="detail-block">
              <h3>Question behind the flag</h3>
              <div class="token-list" id="detailChecklist"></div>
            </div>

            <div class="detail-block">
              <h3>What in the row triggered this</h3>
              <div class="evidence-grid" id="detailEvidence"></div>
            </div>

            <div class="detail-block">
              <h3>Review together</h3>
              <div class="review-group-list" id="detailReviewGroups"></div>
            </div>

            <details class="detail-collapsible">
              <summary>More context needed</summary>
              <div class="detail-collapsible-body">
                <div class="token-list" id="detailMissingContext"></div>
              </div>
            </details>

            <details class="detail-collapsible">
              <summary>Full row details</summary>
              <div class="detail-collapsible-body">
                <div class="detail-table" id="detailTable"></div>
              </div>
            </details>
          </div>
        </aside>
      </div>

      <details class="viewer-collapsible viewer-patterns panel">
        <summary class="viewer-collapsible-summary">
          <div>
            <p class="viewer-kicker">Pattern review</p>
            <h2>Pattern flags</h2>
            <p id="patternSummary">Jump into row clusters that were flagged together.</p>
          </div>
          <span class="viewer-collapsible-toggle" aria-hidden="true"></span>
        </summary>
        <div class="viewer-collapsible-body">
          <div class="viewer-pattern-grid" id="patternGrid"></div>
        </div>
      </details>
    </div>

    <script>
      window.__VIEWER_PAYLOAD__ = {payload_json};
    </script>
    <script src="viewer.js" defer></script>
  </body>
</html>"""

    (out_dir / "index.html").write_text(html)

    # Also hide download link in static renderSummary by removing href.
    # The download link won't work without the server, so just hide it via JS.

    print(f"Static site exported to: {out_dir}")
    print(f"  index.html  ({(out_dir / 'index.html').stat().st_size:,} bytes)")
    print(f"  styles.css  ({(out_dir / 'styles.css').stat().st_size:,} bytes)")
    print(f"  viewer.js   ({(out_dir / 'viewer.js').stat().st_size:,} bytes)")


def main():
    parser = argparse.ArgumentParser(description="Export a review run as a static site")
    parser.add_argument("--run-dir", required=True, help="Path to the run directory")
    parser.add_argument("--out-dir", default=None, help="Output directory (default: <run-dir>/static)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else run_dir / "static"

    export_static(run_dir, out_dir)


if __name__ == "__main__":
    main()
