const statusEl = document.getElementById("status");
const devThemeSwitcherEl = document.getElementById("devThemeSwitcher");
const themeSelectEl = document.getElementById("themeSelect");
const activeStylesheetEl = document.getElementById("activeStylesheet");
const inputTextEl = document.getElementById("inputText");
const outputTextEl = document.getElementById("outputText");
const fileInputEl = document.getElementById("fileInput");
const sampleSelectEl = document.getElementById("sampleSelect");
const modeEl = document.getElementById("mode");
const targetPresetEl = document.getElementById("targetPreset");
const customTargetEl = document.getElementById("customTarget");
const showOctaveEl = document.getElementById("showOctave");
const presetEl = document.getElementById("preset");
const strictnessEl = document.getElementById("strictness");
const preferAdjacentEl = document.getElementById("preferAdjacent");
const maxTargetFretEl = document.getElementById("maxTargetFret");
const stringHistoryWindowEl = document.getElementById("stringHistoryWindow");
const connectorJumpLimitEl = document.getElementById("connectorJumpLimit");
const runLockStrengthEl = document.getElementById("runLockStrength");
const openStringJumpScaleEl = document.getElementById("openStringJumpScale");
const reversalPenaltyEl = document.getElementById("reversalPenalty");
const translateBtnEl = document.getElementById("translateBtn");
const downloadBtnEl = document.getElementById("downloadBtn");

let pyodide = null;
let runRetab = null;
let latestOutput = "";

const PY_FILES = [
  "tuning.py",
  "note_sequence.py",
  "parser.py",
  "translator.py",
  "retab_web.py",
];

const THEME_STORAGE_KEY = "retab-theme";
const LEGACY_THEME_PATHS = {
  "themes/1-radio-terminal.css": "themes/radio.css",
  "themes/2-stein-um-stein.css": "themes/stein.css",
  "themes/3-zeit-dark-minimal.css": "themes/zeit.css",
  "themes/4-sonne-explosive.css": "themes/sonne.css",
  "themes/5-benzin-industrial.css": "themes/benzin.css",
  "themes/6-puppe-clinical.css": "themes/puppe.css",
  "themes/7-rosenrot-romantic.css": "themes/rosenrot.css",
  "themes/8-diamant-precision.css": "themes/diamant.css",
  "themes/9-engel-ethereal.css": "themes/engel.css",
};

function formatSampleLabel(samplePath) {
  const fileName = samplePath.split("/").pop() || "";
  const withoutExtension = fileName.replace(/\.[^.]+$/, "");
  return withoutExtension.replace(/_/g, " ").toUpperCase();
}

function getFallbackSamplePaths() {
  return [...sampleSelectEl.options]
    .map((option) => option.value)
    .filter((value) => value && value.endsWith(".txt"));
}

function setSampleOptions(samplePaths) {
  sampleSelectEl.innerHTML = "";

  const noneOption = document.createElement("option");
  noneOption.value = "";
  noneOption.textContent = "None";
  sampleSelectEl.append(noneOption);

  for (const samplePath of samplePaths) {
    const option = document.createElement("option");
    option.value = samplePath;
    option.textContent = formatSampleLabel(samplePath);
    sampleSelectEl.append(option);
  }
}

async function discoverSamplePaths() {
  const response = await fetch("samples/");
  if (!response.ok) {
    throw new Error("Cannot read samples directory");
  }

  const html = await response.text();
  const doc = new DOMParser().parseFromString(html, "text/html");
  const discovered = new Set();

  for (const link of doc.querySelectorAll("a[href]")) {
    const href = (link.getAttribute("href") || "").trim();
    if (!href || href.endsWith("/") || href.startsWith("?") || href.startsWith("#")) {
      continue;
    }

    const decoded = decodeURIComponent(href);
    if (!decoded.toLowerCase().endsWith(".txt")) {
      continue;
    }

    const fileName = decoded.split("/").pop();
    if (!fileName) {
      continue;
    }

    discovered.add(`samples/${fileName}`);
  }

  return [...discovered].sort((a, b) => a.localeCompare(b));
}

async function initSampleSelect() {
  const fallbackPaths = getFallbackSamplePaths();

  try {
    const discoveredPaths = await discoverSamplePaths();
    if (discoveredPaths.length > 0) {
      setSampleOptions(discoveredPaths);
      return;
    }
  } catch (_error) {
    // Ignore and use fallback list from markup when directory listing is unavailable.
  }

  setSampleOptions(fallbackPaths);
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.style.color = isError ? "#b42318" : "";
}

function applyThemeStylesheet(href) {
  activeStylesheetEl.setAttribute("href", href || "style.css");
}

function normalizeThemePath(themePath) {
  return LEGACY_THEME_PATHS[themePath] || themePath;
}

function initDevThemeSwitcher() {
  const rawSavedTheme = window.localStorage.getItem(THEME_STORAGE_KEY) || "";
  const savedTheme = normalizeThemePath(rawSavedTheme);
  if (savedTheme !== rawSavedTheme) {
    window.localStorage.setItem(THEME_STORAGE_KEY, savedTheme);
  }

  if ([...themeSelectEl.options].some((option) => option.value === savedTheme)) {
    themeSelectEl.value = savedTheme;
  }

  applyThemeStylesheet(themeSelectEl.value);

  themeSelectEl.addEventListener("change", () => {
    const nextTheme = normalizeThemePath(themeSelectEl.value);
    window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
    applyThemeStylesheet(nextTheme);
  });
}

function getNumberOrNull(value) {
  if (value === "" || value == null) {
    return null;
  }
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function updateModeState() {
  const targetMode = modeEl.value === "target";
  targetPresetEl.disabled = !targetMode;
  customTargetEl.disabled = !targetMode;

  [
    presetEl,
    strictnessEl,
    preferAdjacentEl,
    maxTargetFretEl,
    stringHistoryWindowEl,
    connectorJumpLimitEl,
    runLockStrengthEl,
    openStringJumpScaleEl,
    reversalPenaltyEl,
  ].forEach((el) => {
    el.disabled = !targetMode;
  });
}

async function installPythonFiles() {
  pyodide.FS.mkdirTree("/app");

  for (const fileName of PY_FILES) {
    const response = await fetch(`py/${fileName}`);
    if (!response.ok) {
      throw new Error(`Failed to load ${fileName}`);
    }

    const source = await response.text();
    pyodide.FS.writeFile(`/app/${fileName}`, source, { encoding: "utf8" });
  }
}

async function initPyodideRuntime() {
  try {
    pyodide = await loadPyodide();
    await installPythonFiles();

    await pyodide.runPythonAsync(`
import sys
sys.path.append('/app')
from retab_web import run_retab_from_json
`);

    runRetab = pyodide.globals.get("run_retab_from_json");
    setStatus("Ready.");
    translateBtnEl.disabled = false;
  } catch (error) {
    setStatus(`Runtime load failed: ${error.message}`, true);
  }
}

fileInputEl.addEventListener("change", async (event) => {
  const [file] = event.target.files;
  if (!file) {
    return;
  }

  inputTextEl.value = await file.text();
  setStatus(`Loaded ${file.name}.`);
});

sampleSelectEl.addEventListener("change", async () => {
  const value = sampleSelectEl.value;
  if (!value) {
    return;
  }

  try {
    const response = await fetch(value);
    if (!response.ok) {
      throw new Error("Sample not available");
    }

    inputTextEl.value = await response.text();
    setStatus(`Loaded sample ${value.split("/").pop()}.`);
  } catch (error) {
    setStatus(error.message, true);
  }
});

modeEl.addEventListener("change", updateModeState);

translateBtnEl.addEventListener("click", async () => {
  if (!runRetab) {
    setStatus("Python runtime is still loading.", true);
    return;
  }

  const effectiveTarget = (customTargetEl.value.trim() || targetPresetEl.value).trim();

  if (modeEl.value === "target" && !effectiveTarget) {
    setStatus("Target mode requires a target preset or custom tuning value.", true);
    return;
  }

  const payload = {
    input_text: inputTextEl.value,
    target: modeEl.value === "target" ? effectiveTarget : "",
    show_octave: showOctaveEl.checked,
    heuristic_preset: presetEl.value,
    strictness: strictnessEl.value,
    prefer_adjacent_strings: preferAdjacentEl.checked,
    max_target_fret: getNumberOrNull(maxTargetFretEl.value),
    string_history_window: getNumberOrNull(stringHistoryWindowEl.value),
    connector_jump_limit: getNumberOrNull(connectorJumpLimitEl.value),
    run_lock_strength: getNumberOrNull(runLockStrengthEl.value),
    open_string_jump_scale: getNumberOrNull(openStringJumpScaleEl.value),
    reversal_penalty: getNumberOrNull(reversalPenaltyEl.value),
  };

  try {
    setStatus("Translating...");
    const result = runRetab(JSON.stringify(payload));
    latestOutput = String(result ?? "");
    outputTextEl.textContent = latestOutput;
    downloadBtnEl.disabled = latestOutput.trim().length === 0;
    setStatus("Done.");
  } catch (error) {
    outputTextEl.textContent = "";
    latestOutput = "";
    downloadBtnEl.disabled = true;
    setStatus(error.message, true);
  }
});

downloadBtnEl.addEventListener("click", () => {
  if (!latestOutput) {
    return;
  }

  const blob = new Blob([latestOutput], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "retab-output.txt";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
});

updateModeState();
initSampleSelect();
initDevThemeSwitcher();
initPyodideRuntime();
