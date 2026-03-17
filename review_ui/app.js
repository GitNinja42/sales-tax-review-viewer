const state = {
  phase: "submit", // submit | processing | complete | error
  workbook: null,
  supportFiles: [],
  annotationsFile: null,
  activeRun: null,
  submittedAt: null,
  error: null,
  submitError: null,
  runs: [],
  loading: false,
  pollTimer: null,
  elapsedTimer: null,
};

// --- DOM refs ---

const phaseSubmit = document.querySelector("#phaseSubmit");
const phaseProcessing = document.querySelector("#phaseProcessing");
const phaseComplete = document.querySelector("#phaseComplete");
const phaseError = document.querySelector("#phaseError");

const workbookInput = document.querySelector("#workbookInput");
const supportInput = document.querySelector("#supportInput");
const annotationsInput = document.querySelector("#annotationsInput");
const runLabelInput = document.querySelector("#runLabelInput");
const notesInput = document.querySelector("#notesInput");
const submitError = document.querySelector("#submitError");

const workbookDropzone = document.querySelector("#workbookDropzone");
const supportDropzone = document.querySelector("#supportDropzone");
const annotationsDropzone = document.querySelector("#annotationsDropzone");

const workbookFileList = document.querySelector("#workbookFileList");
const supportFileList = document.querySelector("#supportFileList");
const annotationsFileList = document.querySelector("#annotationsFileList");

const submitButton = document.querySelector("#submitButton");
const manualApplyButton = document.querySelector("#manualApplyButton");
const newDuringProcessing = document.querySelector("#newDuringProcessing");
const startNewButton = document.querySelector("#startNewButton");
const retryButton = document.querySelector("#retryButton");
const errorNewButton = document.querySelector("#errorNewButton");
const downloadButton = document.querySelector("#downloadButton");
const viewerButton = document.querySelector("#viewerButton");

const elapsedText = document.querySelector("#elapsedText");
const errorText = document.querySelector("#errorText");
const processingStatusLine = document.querySelector("#processingStatusLine");
const processingHeartbeatLine = document.querySelector("#processingHeartbeatLine");
const statAnnotations = document.querySelector("#statAnnotations");
const statFlags = document.querySelector("#statFlags");
const statRows = document.querySelector("#statRows");
const completeSummary = document.querySelector("#completeSummary");

const runList = document.querySelector("#runList");
const filePillTemplate = document.querySelector("#filePillTemplate");
const runItemTemplate = document.querySelector("#runItemTemplate");

// --- Helpers ---

function classifySupportFile(file) {
  const name = file.name.toLowerCase();
  if (name.includes("checklist")) return "Checklist";
  if (name.includes("matrix")) return "Client matrix";
  if (name.includes("alias")) return "Aliases";
  if (name.includes("tax")) return "Tax dictionary";
  if (name.endsWith(".pdf")) return "PDF support";
  if (name.endsWith(".csv")) return "CSV support";
  if (name.endsWith(".xlsx") || name.endsWith(".xls")) return "Spreadsheet";
  return "Support file";
}

function createPill(label, fileName, onRemove) {
  const pill = filePillTemplate.content.firstElementChild.cloneNode(true);
  pill.querySelector(".file-pill-label").textContent = label;
  pill.querySelector(".file-pill-name").textContent = fileName;
  pill.querySelector(".pill-remove").addEventListener("click", onRemove);
  return pill;
}

function statusClass(status) {
  if (status === "Reviewed") return "run-status-complete";
  if (status === "Review failed") return "run-status-error";
  if (status === "Ready to apply" || status === "Finalizing") return "run-status-ready";
  return "run-status-processing";
}

function formatElapsed(ms) {
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return "Started just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes === 1) return "Started 1 minute ago";
  return `Started ${minutes} minutes ago`;
}

function relativeAge(value) {
  if (!value) return null;
  const diffSeconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (diffSeconds < 5) return "just now";
  if (diffSeconds < 60) return `${diffSeconds} seconds ago`;
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes === 1) return "1 minute ago";
  return `${diffMinutes} minutes ago`;
}

function parseDateValue(value) {
  if (!value) return null;
  const parsed = new Date(value).getTime();
  if (Number.isNaN(parsed)) return null;
  return parsed;
}

function runDurationMs(run) {
  if (!run) return null;
  const startedAt = parseDateValue(run.reviewStartedAt || run.createdAt);
  if (!startedAt) return null;
  const finishedAt = parseDateValue(run.reviewFinishedAt);
  return Math.max(0, (finishedAt || Date.now()) - startedAt);
}

function formatDuration(ms) {
  if (!ms && ms !== 0) return null;
  const seconds = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  const remainingSeconds = seconds % 60;
  if (hours) return `${hours}h ${String(remainingMinutes).padStart(2, "0")}m`;
  if (minutes) return `${minutes}m ${String(remainingSeconds).padStart(2, "0")}s`;
  return `${remainingSeconds}s`;
}

function formatUsd(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return null;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: amount < 10 ? 2 : 0,
    maximumFractionDigits: amount < 10 ? 2 : 0,
  }).format(amount);
}

function formatTokenCount(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount <= 0) return null;
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: amount >= 1000000 ? 2 : 1,
  }).format(amount);
}

function runMetricParts(run) {
  if (!run) return [];
  const parts = [];
  const duration = formatDuration(runDurationMs(run));
  const cost = formatUsd(run.usageEstimatedCostUsd);
  const tokens = formatTokenCount(run.usageTotalTokens);

  if (duration) parts.push(`Runtime ${duration}`);
  if (cost) parts.push(`Est. cost ${cost}`);
  if (tokens) parts.push(`${tokens} tokens`);

  return parts;
}

function expectedRunWindowMs(run) {
  const rowCount = Number(run?.transactionRows || 0);
  if (!rowCount) return 4 * 60 * 1000;
  if (rowCount <= 100) return 4 * 60 * 1000;
  if (rowCount <= 500) return 8 * 60 * 1000;
  return 12 * 60 * 1000;
}

function progressMetaLabel(run) {
  if (!run) return "Progress updates will appear here.";

  if (run.hasReviewedWorkbook || run.reviewStatus === "reviewed") {
    return "The reviewed workbook is ready to download.";
  }

  if (run.hasAnnotations || run.status === "Ready to apply" || run.status === "Finalizing") {
    return "The review file is ready and the workbook is being finalized.";
  }

  if (run.reviewStatus === "failed") {
    return "The automatic review stopped before the workbook was finished.";
  }

  const parts = ["The automatic review is still running."];
  const startedAge = relativeAge(run.reviewStartedAt || run.createdAt);
  const checkInAge = relativeAge(run.reviewHeartbeatAt);

  if (startedAge) {
    parts.push(`It started ${startedAge}.`);
  }

  if (checkInAge) {
    parts.push(`Latest check-in was ${checkInAge}.`);
  } else {
    parts.push("Waiting for the first check-in from the review process.");
  }

  const startedAtValue = run.reviewStartedAt || run.createdAt;
  const startedAtMs = startedAtValue ? new Date(startedAtValue).getTime() : null;
  if (startedAtMs && !Number.isNaN(startedAtMs)) {
    const elapsedMs = Date.now() - startedAtMs;
    if (!run.hasAnnotations && elapsedMs > expectedRunWindowMs(run)) {
      parts.push("This is taking longer than expected for a workbook of this size, so the run may be stalled.");
    }
  }

  return parts.join(" ");
}

function fallbackStepLabel(run) {
  if (!run) return "Preparing the workbook review.";
  if (run.hasReviewedWorkbook || run.reviewStatus === "reviewed") {
    return "The reviewed workbook is ready.";
  }
  if (run.hasAnnotations || run.status === "Ready to apply" || run.status === "Finalizing") {
    return "Checking the review file and finalizing the workbook.";
  }
  if (run.reviewStatus === "failed") {
    return run.reviewError || "The automatic review stopped before the workbook was finished.";
  }
  return "Checking workbook rows and drafting annotations.";
}

function activeStepLabel(run) {
  if (!run) return "Preparing the workbook review.";
  if (run.reviewDetail) return run.reviewDetail;
  if (run.nextStep && !run.nextStep.includes("Codex CLI")) return run.nextStep;
  return fallbackStepLabel(run);
}

function renderProcessingStatus() {
  if (state.phase === "processing") {
    processingStatusLine.textContent = activeStepLabel(state.activeRun);
    processingHeartbeatLine.textContent = progressMetaLabel(state.activeRun);
  } else {
    processingStatusLine.textContent = "Preparing the workbook review.";
    processingHeartbeatLine.textContent = "Progress updates will appear here.";
  }
}

function attachDropzone(dropzone, onFiles) {
  ["dragenter", "dragover"].forEach((e) => {
    dropzone.addEventListener(e, (ev) => {
      ev.preventDefault();
      dropzone.classList.add("is-dragover");
    });
  });
  ["dragleave", "drop"].forEach((e) => {
    dropzone.addEventListener(e, (ev) => {
      ev.preventDefault();
      dropzone.classList.remove("is-dragover");
    });
  });
  dropzone.addEventListener("drop", (ev) => {
    const files = ev.dataTransfer?.files;
    if (files?.length) onFiles(files);
  });
}

// --- Render ---

function render() {
  // Phase switching
  phaseSubmit.classList.toggle("is-active", state.phase === "submit");
  phaseProcessing.classList.toggle("is-active", state.phase === "processing");
  phaseComplete.classList.toggle("is-active", state.phase === "complete");
  phaseError.classList.toggle("is-active", state.phase === "error");

  // Submit phase
  submitButton.disabled = !state.workbook || state.loading;
  submitButton.textContent = state.loading && state.phase === "submit" ? "Submitting..." : "Submit for review";
  submitError.hidden = !state.submitError;
  submitError.textContent = state.submitError || "";
  renderFileList(workbookFileList, state.workbook ? [state.workbook] : [], "Workbook", (i) => {
    state.workbook = null;
    state.submitError = null;
    workbookInput.value = "";
    render();
  });
  renderFileList(supportFileList, state.supportFiles, null, (i) => {
    state.supportFiles.splice(i, 1);
    render();
  });

  // Processing phase
  renderFileList(annotationsFileList, state.annotationsFile ? [state.annotationsFile] : [], "Review file", (i) => {
    state.annotationsFile = null;
    annotationsInput.value = "";
    render();
  });
  manualApplyButton.disabled = !state.annotationsFile || state.loading;
  renderProcessingStatus();

  // Complete phase
  if (state.activeRun && state.phase === "complete") {
    statAnnotations.textContent = String(state.activeRun.rowAnnotations ?? 0);
    statFlags.textContent = String(state.activeRun.patternFlags ?? 0);
    statRows.textContent = String(state.activeRun.transactionRows ?? 0);
    completeSummary.textContent = runMetricParts(state.activeRun).join(" \u2022 ");
    if (state.activeRun.downloadUrl) {
      downloadButton.href = state.activeRun.downloadUrl;
    }
    if (state.activeRun.viewerUrl) {
      viewerButton.href = state.activeRun.viewerUrl;
    }
  } else {
    completeSummary.textContent = "";
  }

  // Error phase
  if (state.error) {
    errorText.textContent = state.error;
  }

  // History
  renderRunList();
}

function renderFileList(container, files, labelOverride, onRemove) {
  container.textContent = "";
  files.forEach((file, index) => {
    const label = labelOverride || classifySupportFile(file);
    container.appendChild(createPill(label, file.name, () => onRemove(index)));
  });
}

function renderRunList() {
  runList.textContent = "";
  if (!state.runs.length) {
    const empty = document.createElement("p");
    empty.className = "empty-copy";
    empty.textContent = "No reviews yet.";
    runList.appendChild(empty);
    return;
  }

  state.runs.forEach((run) => {
    const item = runItemTemplate.content.firstElementChild.cloneNode(true);
    item.querySelector(".run-item-label").textContent = run.runLabel || run.runId;

    const statusEl = item.querySelector(".run-status");
    const isComplete = run.hasReviewedWorkbook;
    const isRecoverable = !isComplete && run.runId;
    statusEl.textContent = run.status || (isComplete ? "Reviewed" : "Reviewing");
    statusEl.classList.add(statusClass(statusEl.textContent));

    item.querySelector(".run-item-meta").textContent = run.workbook || "";
    item.querySelector(".run-item-submeta").textContent = runMetricParts(run).join(" \u2022 ");

    const actionsEl = item.querySelector(".run-item-actions");
    if (isComplete && run.downloadUrl) {
      if (run.viewerUrl) {
        const viewerLink = document.createElement("a");
        viewerLink.className = "run-viewer";
        viewerLink.href = run.viewerUrl;
        viewerLink.textContent = "Open viewer";
        actionsEl.appendChild(viewerLink);
      }
      const link = document.createElement("a");
      link.className = "run-download";
      link.href = run.downloadUrl;
      link.textContent = "Download";
      actionsEl.appendChild(link);
    } else if (isRecoverable) {
      const btn = document.createElement("button");
      btn.className = "button button-ghost";
      btn.textContent = "View";
      btn.style.fontSize = "0.82rem";
      btn.style.minHeight = "34px";
      btn.style.padding = "0 10px";
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        state.activeRun = run;
        state.submittedAt = run.createdAt ? new Date(run.createdAt).getTime() : Date.now();
        setPhase("processing");
      });
      actionsEl.appendChild(btn);
    }

    runList.appendChild(item);
  });
}

// --- Phase management ---

function setPhase(phase) {
  state.phase = phase;

  // Start/stop polling
  if (phase === "processing") {
    startPolling();
    startElapsedTimer();
  } else {
    stopPolling();
    stopElapsedTimer();
  }

  render();
}

function startPolling() {
  stopPolling();
  state.pollTimer = setInterval(pollForCompletion, 5000);
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function startElapsedTimer() {
  stopElapsedTimer();
  state.elapsedTimer = setInterval(() => {
    if (state.submittedAt) {
      elapsedText.textContent = formatElapsed(Date.now() - state.submittedAt);
    }
    renderProcessingStatus();
  }, 1000);
}

function stopElapsedTimer() {
  if (state.elapsedTimer) {
    clearInterval(state.elapsedTimer);
    state.elapsedTimer = null;
  }
}

// --- API calls ---

async function readResponsePayload(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      return await response.json();
    } catch {
      return {};
    }
  }

  const text = await response.text();
  return text ? { error: text } : {};
}

async function fetchRuns() {
  const response = await fetch("/api/runs");
  const payload = await response.json();
  state.runs = payload.runs || [];
}

async function pollForCompletion() {
  try {
    await fetchRuns();

    if (!state.activeRun?.runId) return;

    const active = state.runs.find((r) => r.runId === state.activeRun.runId);
    if (!active) return;

    state.activeRun = active;

    if (active.hasReviewedWorkbook) {
      setPhase("complete");
      return;
    }

    if (active.hasAnnotations) {
      stopPolling();
      await autoApply();
      return;
    }

    if (active.reviewStatus === "failed") {
      state.error = active.reviewError || "The automatic review could not finish this workbook.";
      setPhase("error");
      return;
    }

    render();
  } catch {
    // Silently retry on next poll
  }
}

async function autoApply() {
  try {
    const response = await fetch(`/api/runs/${state.activeRun.runId}/apply`, { method: "POST" });
    const payload = await readResponsePayload(response);
    if (!response.ok) {
      throw new Error(payload.details || payload.error || "Could not finalize the review.");
    }
    state.activeRun = payload;
    await fetchRuns();
    setPhase("complete");
  } catch (err) {
    state.error = err.message || "We had trouble finalizing your review.";
    setPhase("error");
  }
}

async function submitForReview() {
  if (!state.workbook || state.loading) return;

  state.submitError = null;
  state.loading = true;
  render();

  const formData = new FormData();
  formData.append("workbook", state.workbook);
  state.supportFiles.forEach((file) => formData.append("support_files", file));
  formData.append("notes", notesInput.value.trim());
  formData.append("run_label", runLabelInput.value.trim());

  try {
    const response = await fetch("/api/review", { method: "POST", body: formData });
    const payload = await readResponsePayload(response);
    if (!response.ok) {
      throw new Error(payload.details || payload.error || "Could not start the review.");
    }
    state.activeRun = payload;
    state.submittedAt = Date.now();
    await fetchRuns();
    state.submitError = null;
    state.loading = false;
    setPhase("processing");
  } catch (err) {
    state.loading = false;
    state.submitError = err.message || "Could not start the review.";
    render();
  }
}

async function manualApply() {
  if (!state.annotationsFile || !state.activeRun?.runId || state.loading) return;

  state.loading = true;
  render();

  const formData = new FormData();
  formData.append("annotations", state.annotationsFile);

  try {
    const response = await fetch(`/api/runs/${state.activeRun.runId}/apply`, { method: "POST", body: formData });
    const payload = await readResponsePayload(response);
    if (!response.ok) {
      throw new Error(payload.details || payload.error || "Could not apply the review file.");
    }
    state.activeRun = payload;
    state.annotationsFile = null;
    annotationsInput.value = "";
    await fetchRuns();
    state.loading = false;
    setPhase("complete");
  } catch (err) {
    state.loading = false;
    state.error = err.message || "Could not apply the review file.";
    setPhase("error");
  }
}

function resetToSubmit() {
  state.workbook = null;
  state.supportFiles = [];
  state.annotationsFile = null;
  state.activeRun = null;
  state.submittedAt = null;
  state.error = null;
  state.submitError = null;
  state.loading = false;
  workbookInput.value = "";
  supportInput.value = "";
  annotationsInput.value = "";
  runLabelInput.value = "";
  notesInput.value = "";
  setPhase("submit");
}

// --- File handlers ---

function setWorkbook(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".xlsx")) {
    state.submitError = "Please upload an .xlsx workbook.";
    render();
    return;
  }
  state.workbook = file;
  state.submitError = null;
  render();
}

function addSupportFiles(files) {
  const deduped = new Map(state.supportFiles.map((f) => [`${f.name}-${f.size}`, f]));
  Array.from(files).forEach((f) => deduped.set(`${f.name}-${f.size}`, f));
  state.supportFiles = Array.from(deduped.values());
  render();
}

function setAnnotationsFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".json")) {
    window.alert("Please upload a .json file.");
    return;
  }
  state.annotationsFile = file;
  render();
}

// --- Event listeners ---

workbookInput.addEventListener("change", (e) => setWorkbook(e.target.files?.[0]));
supportInput.addEventListener("change", (e) => addSupportFiles(e.target.files || []));
annotationsInput.addEventListener("change", (e) => setAnnotationsFile(e.target.files?.[0]));
submitButton.addEventListener("click", submitForReview);
manualApplyButton.addEventListener("click", manualApply);
newDuringProcessing.addEventListener("click", resetToSubmit);
startNewButton.addEventListener("click", resetToSubmit);
retryButton.addEventListener("click", () => {
  if (state.activeRun?.runId) {
    setPhase("processing");
  }
});
errorNewButton.addEventListener("click", resetToSubmit);

attachDropzone(workbookDropzone, (files) => setWorkbook(files[0]));
attachDropzone(supportDropzone, (files) => addSupportFiles(files));
attachDropzone(annotationsDropzone, (files) => setAnnotationsFile(files[0]));

// --- Init ---

async function init() {
  try {
    await fetchRuns();

    // Find if there's an active (non-complete) run to resume
    const activeRun = state.runs.find((r) => !r.hasReviewedWorkbook);
    if (activeRun) {
      state.activeRun = activeRun;
      state.submittedAt = activeRun.createdAt ? new Date(activeRun.createdAt).getTime() : Date.now();
      setPhase("processing");
      return;
    }
  } catch {
    // API unavailable, just show submit
  }

  setPhase("submit");
}

init();
