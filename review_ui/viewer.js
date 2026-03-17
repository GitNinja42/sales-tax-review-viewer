const state = {
  payload: null,
  selectedRowNum: null,
  query: "",
  checklist: "all",
  flaggedOnly: true,
  activeStatuses: new Set(),
  focusRows: null,
  focusLabel: "",
  fullWidthTable: true,
  workbookStale: false,
  customGridColumns: null,
};

const viewerTitle = document.querySelector("#viewerTitle");
const viewerSubtitle = document.querySelector("#viewerSubtitle");
const viewerDownloadLink = document.querySelector("#viewerDownloadLink");
const searchInput = document.querySelector("#searchInput");
const checklistFilter = document.querySelector("#checklistFilter");
const flaggedOnlyToggle = document.querySelector("#flaggedOnlyToggle");
const filterSummary = document.querySelector("#filterSummary");
const patternSummary = document.querySelector("#patternSummary");
const statusChips = document.querySelector("#statusChips");
const patternGrid = document.querySelector("#patternGrid");
const viewerLayout = document.querySelector("#viewerLayout");
const expandSpreadsheetButton = document.querySelector("#expandSpreadsheetButton");
const viewerTableBody = document.querySelector("#viewerTableBody");
const tableMeta = document.querySelector("#tableMeta");
const focusPill = document.querySelector("#focusPill");
const focusLabel = document.querySelector("#focusLabel");
const clearFocusButton = document.querySelector("#clearFocusButton");
const clearAllFiltersButton = document.querySelector("#clearAllFiltersButton");
const emptyDetail = document.querySelector("#emptyDetail");
const detailContent = document.querySelector("#detailContent");
const detailKicker = document.querySelector("#detailKicker");
const detailTitle = document.querySelector("#detailTitle");
const detailStatus = document.querySelector("#detailStatus");
const detailMeta = document.querySelector("#detailMeta");
const detailIssue = document.querySelector("#detailIssue");
const detailChecklist = document.querySelector("#detailChecklist");
const detailEvidence = document.querySelector("#detailEvidence");
const detailReviewGroups = document.querySelector("#detailReviewGroups");
const detailMissingContext = document.querySelector("#detailMissingContext");
const detailNextStep = document.querySelector("#detailNextStep");
const detailTable = document.querySelector("#detailTable");
const feedbackShell = document.querySelector("#feedbackShell");
const feedbackUpButton = document.querySelector("#feedbackUpButton");
const feedbackDownButton = document.querySelector("#feedbackDownButton");
const feedbackPanel = document.querySelector("#feedbackPanel");
const feedbackComment = document.querySelector("#feedbackComment");
const feedbackSubmitButton = document.querySelector("#feedbackSubmitButton");
const feedbackDismissButton = document.querySelector("#feedbackDismissButton");
const feedbackStatus = document.querySelector("#feedbackStatus");
const workbookStaleBadge = document.querySelector("#workbookStaleBadge");
const regenerateButton = document.querySelector("#regenerateButton");

function getRunId() {
  const params = new URLSearchParams(window.location.search);
  return params.get("run");
}

function formatNumber(value) {
  if (typeof value !== "number") return value ?? "—";
  return new Intl.NumberFormat("en-CA", { maximumFractionDigits: 2 }).format(value);
}

function formatMoney(value) {
  if (typeof value !== "number") return value ?? "—";
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(value);
}

function formatValue(label, value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    if (label?.toLowerCase().includes("amount")) return formatMoney(value);
    return formatNumber(value);
  }
  return String(value);
}

function effectiveStatus(row) {
  const annotation = row.annotation;
  if (!annotation) return "Unflagged";
  if (annotation._dismissed) return "Dismissed";
  return annotation.status || "Unflagged";
}

function statusTone(status) {
  if (status === "Likely Incorrect") return "status-warning";
  if (status === "Needs More Context") return "status-muted";
  if (status === "Review Needed") return "status-warning";
  if (status === "Dismissed") return "status-neutral";
  return "status-neutral";
}

function token(label, tone = "") {
  const span = document.createElement("span");
  span.className = `token ${tone}`.trim();
  span.textContent = label;
  return span;
}

function feedbackDraft(rowNum) {
  state.feedbackDrafts ||= {};
  if (!state.feedbackDrafts[rowNum]) {
    state.feedbackDrafts[rowNum] = {
      vote: "",
      comment: "",
      error: "",
      submitting: false,
      noteOpen: false,
    };
  }
  return state.feedbackDrafts[rowNum];
}

function selectedRow() {
  if (!state.payload || state.selectedRowNum === null) return null;
  return state.payload.rows.find((row) => row.rowNum === state.selectedRowNum) || null;
}

function checklistTitle(ref) {
  return state.payload.summary.checklistCounts.find((item) => item.checklistRef === ref)?.title || ref;
}

function compactMoney(value) {
  if (typeof value !== "number") return value ?? "—";
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
    maximumFractionDigits: 0,
  }).format(value);
}

function getFilteredRows() {
  if (!state.payload) return [];
  const query = state.query.trim().toLowerCase();

  return state.payload.rows.filter((row) => {
    // 1. Focus group: if active, only rows in the group pass. Bypasses flaggedOnly.
    if (state.focusRows) {
      if (!state.focusRows.has(row.rowNum)) return false;
    }
    // 2. Flagged-only gate (skipped when a focus group is active).
    else if (state.flaggedOnly) {
      if (!row.isFlagged || row.annotation?._dismissed) return false;
    }
    // 3. Status chip refinement.
    if (state.activeStatuses.size > 0) {
      const status = row.annotation?.status || "Unflagged";
      if (!state.activeStatuses.has(status)) return false;
    }
    // 4. Checklist filter.
    if (state.checklist !== "all") {
      const refs = row.annotation?.checklistRefs || [];
      if (!refs.includes(state.checklist)) return false;
    }
    if (!query) return true;

    const haystack = [
      row.rowNum,
      row.name,
      row.account,
      row.taxCode,
      row.memoDescription,
      row.annotation?.issueSummary,
      row.annotation?.suggestedNextStep,
      ...(row.annotation?.checklistTitles || []),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    return haystack.includes(query);
  });
}

function ensureSelectedRow(rows) {
  if (!rows.length) {
    state.selectedRowNum = null;
    return;
  }
  if (rows.some((row) => row.rowNum === state.selectedRowNum)) return;
  state.selectedRowNum = rows[0].rowNum;
}

function liveFlaggedCount() {
  if (!state.payload) return 0;
  return state.payload.rows.filter((r) => r.isFlagged && !r.annotation?._dismissed).length;
}

function liveStatusCounts() {
  const counts = { "Review Needed": 0, "Needs More Context": 0 };
  if (!state.payload) return counts;
  for (const row of state.payload.rows) {
    if (!row.annotation || row.annotation._dismissed) continue;
    const s = row.annotation.status;
    if (s in counts) counts[s]++;
  }
  return counts;
}

function renderSummary() {
  const { run, summary } = state.payload;
  const flagged = liveFlaggedCount();
  viewerTitle.textContent = run.runLabel || run.runId;
  viewerSubtitle.textContent = `${run.viewerWorkbook} · ${run.sheetName} · ${flagged} flagged rows across ${summary.transactionRows} transactions.`;
  viewerDownloadLink.href = run.downloadUrl || "#";
}

function renderChecklistFilter() {
  checklistFilter.innerHTML = '<option value="all">All checklist questions</option>';
  state.payload.summary.checklistCounts.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.checklistRef;
    option.textContent = `${item.checklistRef} · ${item.title} (${item.count})`;
    checklistFilter.appendChild(option);
  });
  checklistFilter.value = state.checklist;
}

function renderStatusChips() {
  const live = liveStatusCounts();
  const flagged = liveFlaggedCount();
  const counts = {
    "Review Needed": live["Review Needed"],
    "Needs More Context": live["Needs More Context"],
    Unflagged: state.payload.summary.transactionRows - flagged,
  };

  statusChips.textContent = "";
  Object.entries(counts).forEach(([label, count]) => {
    if (count <= 0 && label !== "Unflagged") return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = `status-chip ${statusTone(label)} ${state.activeStatuses.has(label) ? "is-active" : ""}`.trim();
    button.textContent = `${label} (${count})`;
    button.addEventListener("click", () => {
      if (state.activeStatuses.has(label)) {
        state.activeStatuses.delete(label);
      } else {
        state.activeStatuses.add(label);
      }
      render();
    });
    statusChips.appendChild(button);
  });
}

function setFocus(rowNums, label) {
  state.focusRows = new Set(rowNums);
  state.focusLabel = label;
  state.query = "";
  state.checklist = "all";
  state.activeStatuses.clear();
  searchInput.value = "";
  checklistFilter.value = "all";
  render();
}

function clearFocus() {
  state.focusRows = null;
  state.focusLabel = "";
  render();
}

function hasActiveFilters() {
  return (
    state.query.trim() !== "" ||
    state.checklist !== "all" ||
    state.activeStatuses.size > 0 ||
    state.focusRows !== null ||
    !state.flaggedOnly
  );
}

function clearAllFilters() {
  state.query = "";
  state.checklist = "all";
  state.activeStatuses.clear();
  state.focusRows = null;
  state.focusLabel = "";
  state.flaggedOnly = true;
  searchInput.value = "";
  checklistFilter.value = "all";
  flaggedOnlyToggle.checked = true;
  render();
}

function toggleSpreadsheetWidth() {
  state.fullWidthTable = !state.fullWidthTable;
  render();
}

function renderPatterns() {
  const count = state.payload.patterns.length;
  patternSummary.textContent = count
    ? `${count} pattern ${count === 1 ? "cluster" : "clusters"} are available for grouped review at the end of the page.`
    : "No pattern clusters were recorded for this run.";
  patternGrid.textContent = "";
  if (!state.payload.patterns.length) {
    const empty = document.createElement("p");
    empty.className = "viewer-empty-copy";
    empty.textContent = "No pattern flags were recorded for this run.";
    patternGrid.appendChild(empty);
    return;
  }

  state.payload.patterns.forEach((pattern) => {
    const card = document.createElement("article");
    card.className = "pattern-card";
    const checklist = pattern.checklistRefs
      .map((ref, index) => `${ref} · ${pattern.checklistTitles[index] || ref}`)
      .join(" / ");
    card.innerHTML = `
      <p class="pattern-card-id">${pattern.patternId}</p>
      <h3>${pattern.issueSummary}</h3>
      <p class="pattern-card-meta">${checklist}</p>
      <p class="pattern-card-meta">${pattern.rowRefs.length} related rows</p>
    `;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button-ghost pattern-card-action";
    button.textContent = "Focus these rows";
    button.addEventListener("click", () => setFocus(pattern.rowRefs, `Pattern: ${pattern.patternId}`));
    card.appendChild(button);
    patternGrid.appendChild(card);
  });
}

function renderFilterSummary(rows) {
  const parts = [`${rows.length} rows shown`];

  if (state.flaggedOnly) {
    parts.push("flagged only");
  } else {
    parts.push("including unflagged rows");
  }

  if (state.query.trim()) {
    parts.push(`search: "${state.query.trim()}"`);
  }

  if (state.checklist !== "all") {
    parts.push(checklistTitle(state.checklist));
  }

  if (state.activeStatuses.size) {
    parts.push(`${state.activeStatuses.size} status filter${state.activeStatuses.size === 1 ? "" : "s"}`);
  }

  if (state.focusRows) {
    parts.push(state.focusLabel);
  }

  filterSummary.textContent = parts.join(" · ");
}

function renderLayoutMode() {
  viewerLayout.classList.toggle("is-expanded", state.fullWidthTable);
  if (state.fullWidthTable) {
    // Expanded mode: clear inline grid so CSS 1fr takes over.
    viewerLayout.style.gridTemplateColumns = "";
  } else if (state.customGridColumns) {
    // Split mode with user-resized panels: restore their widths.
    viewerLayout.style.gridTemplateColumns = state.customGridColumns;
  } else {
    // Split mode default: let CSS handle it.
    viewerLayout.style.gridTemplateColumns = "";
  }
  expandSpreadsheetButton.textContent = state.fullWidthTable ? "Split view" : "Expand spreadsheet";
}

function renderTable() {
  const rows = getFilteredRows();
  ensureSelectedRow(rows);
  viewerTableBody.textContent = "";
  tableMeta.textContent = `${rows.length} shown of ${state.payload.summary.transactionRows} transaction rows`;
  renderFilterSummary(rows);

  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="7" class="viewer-empty-cell">No rows match the current filters.</td>';
    viewerTableBody.appendChild(tr);
    renderDetail(null);
    return;
  }

  rows.forEach((row) => {
    const status = effectiveStatus(row);
    const tr = document.createElement("tr");
    tr.className = row.rowNum === state.selectedRowNum ? "is-selected" : "";
    tr.innerHTML = `
      <td class="table-col-row">${row.rowNum}</td>
      <td class="table-col-status"><span class="viewer-status-badge ${statusTone(status)}">${status}</span></td>
      <td class="table-col-name">${row.name || "—"}</td>
      <td class="table-col-account">${row.account || "—"}</td>
      <td class="table-col-tax">${row.taxCode || "—"}</td>
      <td class="table-col-memo">${row.memoDescription || "—"}</td>
      <td class="table-col-issue">${row.annotation?.issueSummary || "No formal issue recorded."}</td>
    `;
    // Status badge click opens picker.
    const badge = tr.querySelector(".table-col-status .viewer-status-badge");
    if (badge) {
      badge.addEventListener("click", (e) => {
        e.stopPropagation();
        showStatusPicker(badge, row);
      });
    }

    tr.addEventListener("click", () => {
      state.selectedRowNum = row.rowNum;
      render();
    });
    tr.addEventListener("dblclick", () => {
      state.selectedRowNum = row.rowNum;
      state.fullWidthTable = !state.fullWidthTable;
      render();
    });
    viewerTableBody.appendChild(tr);
  });

  renderDetail(rows.find((row) => row.rowNum === state.selectedRowNum) || rows[0]);
}

function reviewQuestionLabel(annotation) {
  const titles = annotation?.checklistTitles || [];
  const text = titles.join(" ").toLowerCase();

  if (text.includes("inconsistent sales tax treatment")) return "Similar mixed-tax question";
  if (text.includes("exempt purchase")) return "Similar exempt-coding question";
  if (text.includes("reimbursement")) return "Similar reimbursement question";
  if (text.includes("freelancer") || text.includes("subcontractor")) return "Similar contractor question";
  if (text.includes("out-of-scope")) return "Similar coding question";
  return "Similar review question";
}

function metaPills(row) {
  const items = [];
  if (row.values["Transaction Type"]) items.push(`Type: ${row.values["Transaction Type"]}`);
  if (row.values["Date"]) items.push(`Date: ${row.values["Date"]}`);
  if (typeof row.values["Gross Total"] === "number") items.push(`Gross: ${compactMoney(row.values["Gross Total"])}`);
  if (typeof row.values["Tax Amount"] === "number") items.push(`Tax: ${formatMoney(row.values["Tax Amount"])}`);
  return items;
}

function relatedGroups(row) {
  const groups = [];
  const annotation = row.annotation;
  const rows = state.payload.rows;

  if (annotation) {
    const sameFinding = rows
      .filter((candidate) => {
        const other = candidate.annotation;
        if (!other || candidate.rowNum === row.rowNum) return false;
        return (
          other.issueSummary === annotation.issueSummary &&
          JSON.stringify(other.checklistRefs) === JSON.stringify(annotation.checklistRefs)
        );
      })
      .map((candidate) => candidate.rowNum);
    if (sameFinding.length) {
      groups.push({ label: "Matching finding", rowNums: [row.rowNum, ...sameFinding] });
    }

    const sameChecklist = rows
      .filter((candidate) => {
        const other = candidate.annotation;
        if (!other || candidate.rowNum === row.rowNum) return false;
        return other.checklistRefs.some((ref) => annotation.checklistRefs.includes(ref));
      })
      .map((candidate) => candidate.rowNum);
    if (sameChecklist.length) {
      groups.push({ label: reviewQuestionLabel(annotation), rowNums: [row.rowNum, ...sameChecklist] });
    }
  }

  if (row.patternIds?.length) {
    const patternRows = new Set([row.rowNum]);
    state.payload.patterns
      .filter((pattern) => row.patternIds.includes(pattern.patternId))
      .forEach((pattern) => pattern.rowRefs.forEach((value) => patternRows.add(value)));
    groups.push({ label: "Same pattern flag", rowNums: Array.from(patternRows) });
  }

  if (row.normalizedName) {
    const sameName = rows
      .filter((candidate) => candidate.rowNum !== row.rowNum && candidate.normalizedName === row.normalizedName)
      .map((candidate) => candidate.rowNum);
    if (sameName.length) {
      groups.push({ label: "Same customer or vendor", rowNums: [row.rowNum, ...sameName] });
    }
  }

  if (row.account) {
    const sameAccount = rows
      .filter((candidate) => candidate.rowNum !== row.rowNum && candidate.account === row.account)
      .map((candidate) => candidate.rowNum);
    if (sameAccount.length) {
      groups.push({ label: "Same account", rowNums: [row.rowNum, ...sameAccount] });
    }
  }

  // Deduplicate groups that resolve to the same set of rows.
  // Earlier groups are more specific (pattern > checklist > mechanical),
  // so when two groups have identical row sets, keep the earlier one.
  const seen = new Map();
  const deduped = [];
  for (const group of groups) {
    const key = group.rowNums.slice().sort((a, b) => a - b).join(",");
    if (!seen.has(key)) {
      seen.set(key, true);
      deduped.push(group);
    }
  }
  return deduped;
}

async function dismissRow(row) {
  if (!row.annotation) return;
  const isDismissed = row.annotation._dismissed;
  const willHide = !isDismissed && state.flaggedOnly;

  // If the row will disappear from the list, pre-select the next visible row.
  if (willHide) {
    const currentRows = getFilteredRows();
    const idx = currentRows.findIndex((r) => r.rowNum === row.rowNum);
    if (idx !== -1) {
      const nextRow = currentRows[idx + 1] || currentRows[idx - 1];
      state.selectedRowNum = nextRow ? nextRow.rowNum : null;
    }
  }

  row.annotation._dismissed = !isDismissed;

  const runId = getRunId();
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
  }

  state.workbookStale = true;
  render();
}

async function manualFlagRow(row) {
  const runId = getRunId();
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
  }
}

const STATUS_OPTIONS = ["Review Needed", "Needs More Context", "No Issues Found", "Unflagged"];

function showStatusPicker(badge, row) {
  // Remove any existing picker.
  document.querySelector(".status-picker")?.remove();

  const picker = document.createElement("div");
  picker.className = "status-picker";

  const currentStatus = effectiveStatus(row);
  STATUS_OPTIONS.forEach((option) => {
    if (option === currentStatus) return;
    const btn = document.createElement("button");
    btn.className = "status-picker-option";
    btn.innerHTML = `<span class="viewer-status-badge ${statusTone(option)}">${option}</span>`;
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      changeRowStatus(row, option);
      picker.remove();
    });
    picker.appendChild(btn);
  });

  // Position below the badge.
  const rect = badge.getBoundingClientRect();
  picker.style.top = `${rect.bottom + window.scrollY + 4}px`;
  picker.style.left = `${rect.left + window.scrollX}px`;
  document.body.appendChild(picker);

  // Close on outside click.
  function closePicker(e) {
    if (!picker.contains(e.target)) {
      picker.remove();
      document.removeEventListener("click", closePicker, true);
    }
  }
  setTimeout(() => document.addEventListener("click", closePicker, true), 0);
}

async function changeRowStatus(row, newStatus) {
  const runId = getRunId();

  if (newStatus === "Unflagged") {
    // Remove the annotation entirely: dismiss it.
    if (row.annotation) {
      row.annotation._dismissed = true;
      try {
        await fetch(`/api/runs/${runId}/dismiss`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rowNum: row.rowNum, dismissed: true }),
        });
      } catch (err) {
        console.error("Failed to dismiss:", err);
      }
    }
  } else {
    if (row.annotation) {
      // Update existing annotation status.
      row.annotation._dismissed = false;
      row.annotation.status = newStatus;
      try {
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
      }
    } else {
      // Flag an unflagged row.
      row.annotation = { status: newStatus, issueSummary: "", checklistRefs: [] };
      try {
        await fetch(`/api/runs/${runId}/flag`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rowNum: row.rowNum, status: newStatus }),
        });
      } catch (err) {
        console.error("Failed to flag:", err);
      }
    }
  }
  state.workbookStale = true;
  render();
}

async function saveAnnotationField(row, field, value) {
  const runId = getRunId();
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
  }
}

async function regenerateWorkbook() {
  if (!state.workbookStale) return;
  const runId = getRunId();
  regenerateButton.disabled = true;
  regenerateButton.textContent = "Regenerating...";

  try {
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
  }
}

function renderDetail(row) {
  if (!row) {
    emptyDetail.classList.remove("is-hidden");
    detailContent.classList.add("is-hidden");
    return;
  }

  emptyDetail.classList.add("is-hidden");
  detailContent.classList.remove("is-hidden");

  const annotation = row.annotation;
  const status = effectiveStatus(row);

  detailKicker.textContent = row.section ? `${row.section} · Row ${row.rowNum}` : `Row ${row.rowNum}`;
  detailTitle.textContent = row.name || row.account || `Row ${row.rowNum}`;
  detailStatus.className = `viewer-status-badge ${statusTone(status)}`.trim();
  detailStatus.textContent = status;
  const hasAnnotation = !!annotation;
  detailIssue.textContent = annotation?.issueSummary || "No formal issue was recorded for this row.";
  detailIssue.contentEditable = hasAnnotation ? "true" : "false";
  detailNextStep.textContent = annotation?.suggestedNextStep || "";
  detailNextStep.contentEditable = "true";
  detailNextStep.dataset.placeholder = "Add a suggested next step...";
  if (!detailNextStep.textContent) {
    detailNextStep.textContent = "Add a suggested next step...";
    detailNextStep.classList.add("is-placeholder");
  } else {
    detailNextStep.classList.remove("is-placeholder");
  }

  const dismissBtn = document.querySelector("#detailDismissButton");
  if (dismissBtn) {
    if (annotation && annotation.status) {
      dismissBtn.classList.remove("is-hidden");
      dismissBtn.className = "button button-ghost button-sm";
      dismissBtn.textContent = annotation._dismissed ? "Restore flag" : "Review not needed";
      dismissBtn.onclick = () => dismissRow(row);
    } else {
      // Unflagged row: show a "Flag for review" button.
      dismissBtn.classList.remove("is-hidden");
      dismissBtn.className = "button button-secondary button-sm";
      dismissBtn.textContent = "Flag for review";
      dismissBtn.onclick = () => manualFlagRow(row);
    }
  }

  detailMeta.textContent = "";
  metaPills(row).forEach((item) => detailMeta.appendChild(token(item)));

  detailChecklist.textContent = "";
  if (annotation?.checklistRefs?.length) {
    annotation.checklistRefs.forEach((ref, index) => {
      detailChecklist.appendChild(token(`${ref} · ${annotation.checklistTitles[index] || ref}`));
    });
  } else {
    detailChecklist.appendChild(token("No checklist mapping"));
  }

  detailEvidence.textContent = "";
  const evidenceColumns = annotation?.highlightColumns?.length ? annotation.highlightColumns : ["Name", "Account", "Tax Code", "Memo/Description"];
  evidenceColumns.forEach((label) => {
    const card = document.createElement("article");
    card.className = "evidence-card";
    card.innerHTML = `<span>${label}</span><strong>${formatValue(label, row.values[label])}</strong>`;
    detailEvidence.appendChild(card);
  });

  detailMissingContext.textContent = "";
  if (annotation?.missingContext?.length) {
    annotation.missingContext.forEach((item) => detailMissingContext.appendChild(token(item)));
  } else {
    detailMissingContext.appendChild(token("None recorded"));
  }

  detailReviewGroups.textContent = "";
  const groups = relatedGroups(row);
  if (!groups.length) {
    const p = document.createElement("p");
    p.className = "viewer-empty-copy";
    p.textContent = "No grouped review suggestions were generated for this row.";
    detailReviewGroups.appendChild(p);
  } else {
    groups.forEach((group) => {
      const focusKey = `${group.label} · row ${row.rowNum}`;
      const isActive = state.focusLabel === focusKey;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `review-group-button ${isActive ? "is-active" : ""}`;
      button.innerHTML = `<strong>${group.label}</strong><span>${group.rowNums.length} rows</span>`;
      button.addEventListener("click", () => {
        if (state.focusLabel === focusKey) {
          clearFocus();
        } else {
          setFocus(group.rowNums, focusKey);
        }
      });
      detailReviewGroups.appendChild(button);
    });
  }

  detailTable.textContent = "";
  Object.entries(row.values).forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "detail-table-row";
    item.innerHTML = `<span>${label}</span><strong>${formatValue(label, value)}</strong>`;
    detailTable.appendChild(item);
  });

  renderFeedback(row);
}

function renderFeedback(row) {
  const draft = feedbackDraft(row.rowNum);
  const trimmedComment = draft.comment.trim();

  feedbackShell.classList.toggle("is-open", draft.noteOpen);
  feedbackUpButton.classList.toggle("is-active", draft.vote === "up");
  feedbackDownButton.classList.toggle("is-active", draft.vote === "down");
  feedbackUpButton.setAttribute("aria-pressed", draft.vote === "up" ? "true" : "false");
  feedbackDownButton.setAttribute("aria-pressed", draft.vote === "down" ? "true" : "false");
  feedbackUpButton.disabled = draft.submitting;
  feedbackDownButton.disabled = draft.submitting;
  feedbackPanel.classList.toggle("is-hidden", !draft.noteOpen);
  feedbackComment.value = draft.comment;
  feedbackSubmitButton.disabled = draft.submitting || !draft.vote || !trimmedComment;
  feedbackDismissButton.disabled = draft.submitting;
  feedbackSubmitButton.textContent = draft.submitting ? "Saving..." : "Save note";

  if (draft.error) {
    feedbackStatus.textContent = draft.error;
    feedbackStatus.className = "feedback-status is-error";
    return;
  }

  feedbackStatus.textContent = "";
  feedbackStatus.className = "feedback-status is-hidden";
}

async function setFeedbackVote(vote) {
  const row = selectedRow();
  if (!row) return;
  const draft = feedbackDraft(row.rowNum);
  draft.vote = vote;
  draft.noteOpen = true;
  draft.error = "";
  renderFeedback(row);
  await submitFeedback({ row, keepNoteOpen: true });
}

function setFeedbackCommentValue(value) {
  const row = selectedRow();
  if (!row) return;
  const draft = feedbackDraft(row.rowNum);
  draft.comment = value;
  draft.error = "";
  renderFeedback(row);
}

function closeFeedbackNote() {
  const row = selectedRow();
  if (!row) return;
  const draft = feedbackDraft(row.rowNum);
  draft.noteOpen = false;
  draft.error = "";
  renderFeedback(row);
}

async function submitFeedback(options = {}) {
  const row = options.row || selectedRow();
  if (!row) return;

  const draft = feedbackDraft(row.rowNum);
  draft.comment = feedbackComment.value;
  if (!draft.vote) {
    draft.error = "Choose thumbs up or thumbs down before saving feedback.";
    renderFeedback(row);
    return;
  }

  draft.submitting = true;
  draft.error = "";
  renderFeedback(row);

  try {
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
  } finally {
    draft.submitting = false;
    if (options.keepNoteOpen === false) {
      draft.noteOpen = false;
    }
    renderFeedback(row);
  }
}

function handleFeedbackShellPointerDown(event) {
  const row = selectedRow();
  if (!row) return;
  const draft = feedbackDraft(row.rowNum);
  if (!draft.noteOpen) return;
  if (draft.submitting) return;
  if (feedbackShell.contains(event.target)) return;
  draft.noteOpen = false;
  draft.error = "";
  renderFeedback(row);
}

function renderFocus() {
  if (!state.focusRows) {
    focusPill.classList.add("is-hidden");
    return;
  }
  focusPill.classList.remove("is-hidden");
  focusLabel.textContent = state.focusLabel;
}

function render() {
  renderLayoutMode();
  renderSummary();
  renderChecklistFilter();
  renderStatusChips();
  renderFocus();
  renderTable();
  renderPatterns();
  clearAllFiltersButton.classList.toggle("is-hidden", !hasActiveFilters());
  workbookStaleBadge.classList.toggle("is-hidden", !state.workbookStale);
  regenerateButton.classList.toggle("is-hidden", !state.workbookStale);
}

async function init() {
  const runId = getRunId();
  if (!runId) {
    viewerTitle.textContent = "Missing run id";
    viewerSubtitle.textContent = "Open this page from a finished review run.";
    return;
  }

  const response = await fetch(`/api/runs/${runId}/viewer`);
  const payload = await response.json();
  if (!response.ok) {
    viewerTitle.textContent = "Could not load viewer";
    viewerSubtitle.textContent = payload.error || "The review viewer payload is unavailable.";
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
    // Unchecking "flagged only" means "show me everything", so clear refinement filters.
    if (!state.flaggedOnly) {
      state.activeStatuses.clear();
    }
    render();
  });
  clearFocusButton.addEventListener("click", clearFocus);
  clearAllFiltersButton.addEventListener("click", clearAllFilters);
  expandSpreadsheetButton.addEventListener("click", toggleSpreadsheetWidth);
  regenerateButton.addEventListener("click", regenerateWorkbook);

  // Editable annotation fields: save on blur.
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
      // If there's no annotation yet (unflagged row), we still save next step.
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
}

// --- Column resize ---

const COL_KEYS = ["row", "status", "name", "account", "tax", "memo", "issue"];
const COL_STORAGE_KEY = "viewer-col-widths";

// Clear any cached column widths from previous fixed-layout so auto-layout sizes by content.
try { localStorage.removeItem(COL_STORAGE_KEY); } catch { /* ignore */ }

function loadColumnWidths() {
  try {
    const raw = localStorage.getItem(COL_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveColumnWidths(widths) {
  try {
    localStorage.setItem(COL_STORAGE_KEY, JSON.stringify(widths));
  } catch {
    // ignore
  }
}

function applyColumnWidths() {
  const table = document.querySelector(".viewer-table");
  if (!table) return;
  const widths = loadColumnWidths();
  const ths = table.querySelectorAll("thead th");
  ths.forEach((th, i) => {
    const key = COL_KEYS[i];
    if (key && widths[key]) {
      th.style.width = widths[key] + "px";
    }
  });
}

function setupColumnResize() {
  const table = document.querySelector(".viewer-table");
  if (!table) return;
  const ths = table.querySelectorAll("thead th");

  ths.forEach((th, i) => {
    if (th.querySelector(".col-resize-handle")) return;
    const key = COL_KEYS[i];
    if (!key) return;

    const handle = document.createElement("div");
    handle.className = "col-resize-handle";
    th.appendChild(handle);

    let startX = 0;
    let startW = 0;

    function onMouseMove(e) {
      const newW = Math.max(36, startW + (e.clientX - startX));
      th.style.width = newW + "px";
    }

    function onMouseUp(e) {
      handle.classList.remove("is-dragging");
      table.classList.remove("is-resizing");
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);

      const finalW = Math.max(36, startW + (e.clientX - startX));
      const widths = loadColumnWidths();
      widths[key] = Math.round(finalW);
      saveColumnWidths(widths);
    }

    handle.addEventListener("mousedown", (e) => {
      e.preventDefault();
      startX = e.clientX;
      startW = th.getBoundingClientRect().width;
      handle.classList.add("is-dragging");
      table.classList.add("is-resizing");
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });
  });

  applyColumnWidths();
}

// Patch render to set up resize handles after table is built.
const _originalRender = render;
function patchedRender() {
  _originalRender();
  setupColumnResize();
}
// Replace all render() calls by reassigning.
// We hook via MutationObserver on the table body instead for simplicity.
const resizeObserver = new MutationObserver(() => {
  setupColumnResize();
});

// --- Panel resize (table vs detail) ---
function setupPanelResize() {
  const handle = document.getElementById("panelResizeHandle");
  const layout = document.getElementById("viewerLayout");
  if (!handle || !layout) return;

  let startX = 0;
  let startTableW = 0;
  let layoutW = 0;

  function onMove(e) {
    const dx = e.clientX - startX;
    const newTableW = Math.max(300, startTableW + dx);
    const detailW = Math.max(300, layoutW - newTableW - 6);
    const value = `${newTableW}px 6px ${detailW}px`;
    layout.style.gridTemplateColumns = value;
    state.customGridColumns = value;
  }

  function onUp() {
    handle.classList.remove("is-dragging");
    layout.classList.remove("is-panel-resizing");
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
  }

  handle.addEventListener("mousedown", (e) => {
    e.preventDefault();
    const tablePanel = layout.querySelector(".viewer-table-panel");
    startX = e.clientX;
    startTableW = tablePanel.getBoundingClientRect().width;
    layoutW = layout.getBoundingClientRect().width;
    handle.classList.add("is-dragging");
    layout.classList.add("is-panel-resizing");
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  });
}

init();
setupPanelResize();

// Wire up resize handles after each render via MutationObserver on the table body.
requestAnimationFrame(() => {
  const tbody = document.querySelector("#viewerTableBody");
  if (tbody) {
    resizeObserver.observe(tbody, { childList: true });
    setupColumnResize();
  }
});
