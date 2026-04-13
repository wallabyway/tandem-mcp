const accountSelect = document.getElementById("account-select");
const facilitySelect = document.getElementById("facility-select");
const viewerContainer = document.getElementById("viewer-container");
const loadingOverlay = document.getElementById("loading-overlay");
const statusEl = document.getElementById("status");

let viewer = null;
let dtApp = null;
let teams = [];
let accessToken = null;

function setStatus(msg) {
  statusEl.textContent = msg;
}

function showLoading(show) {
  loadingOverlay.classList.toggle("hidden", !show);
}

async function fetchToken() {
  const res = await fetch("/api/token");
  if (!res.ok) throw new Error(`Token fetch failed: ${res.status}`);
  const data = await res.json();
  return data.access_token;
}

function initLMV(token) {
  return new Promise((resolve, reject) => {
    Autodesk.Viewing.Initializer(
      {
        env: "DtProduction",
        api: "dt",
        useCookie: false,
        useCredentials: true,
        shouldInitializeAuth: false,
        opt_out_tracking_by_default: true,
        productId: "Digital Twins",
        corsWorker: true,
        config3d: {
          extensions: ["Autodesk.BoxSelection", "Autodesk.CompGeom"],
          screenModeDelegate: Autodesk.Viewing.NullScreenModeDelegate,
        },
      },
      () => {
        Autodesk.Viewing.endpoint.HTTP_REQUEST_HEADERS["Authorization"] =
          "Bearer " + token;
        resolve();
      }
    );
  });
}

function createViewer() {
  const el = document.createElement("div");
  el.style.width = "100%";
  el.style.height = "100%";
  viewerContainer.appendChild(el);

  viewer = new Autodesk.Viewing.GuiViewer3D(el, {
    extensions: ["Autodesk.BoxSelection"],
    screenModeDelegate: Autodesk.Viewing.NullScreenModeDelegate,
    theme: "dark-theme",
  });
  viewer.start();

  window.viewer = viewer;
  window.NOP_VIEWER = viewer;

  return viewer;
}

function getFacilityName(facility) {
  return (
    facility.settings?.props?.["Identity Data"]?.["Building Name"] ||
    facility.label?.() ||
    "Unnamed"
  );
}

async function populateAccounts() {
  accountSelect.innerHTML = '<option value="">Loading accounts...</option>';

  try {
    teams = await dtApp.getTeams();

    for (const team of teams) {
      await team.getFacilities();
    }

    const shared = await dtApp.getSharedFacilities();
    if (shared?.length) {
      teams.push({
        app: dtApp,
        name: "** SHARED **",
        facilities: shared,
      });
    }

    const sorted = [...teams]
      .filter((t) => t.facilities?.length)
      .sort((a, b) => {
        if (a.name === "** SHARED **") return 1;
        if (b.name === "** SHARED **") return -1;
        return a.name.localeCompare(b.name, undefined, {
          sensitivity: "base",
        });
      });

    if (!sorted.length) {
      accountSelect.innerHTML =
        '<option value="">No facilities available</option>';
      setStatus("No facilities found");
      return;
    }

    accountSelect.innerHTML = '<option value="">Select account...</option>';

    const lastTeam = localStorage.getItem("tandem-viewer-last-team");

    sorted.forEach((team) => {
      const opt = document.createElement("option");
      opt.value = team.name;
      opt.textContent = team.name;
      if (team.name === lastTeam) opt.selected = true;
      accountSelect.appendChild(opt);
    });

    accountSelect.disabled = false;

    const selected =
      lastTeam && sorted.find((t) => t.name === lastTeam)
        ? lastTeam
        : sorted[0]?.name;

    if (selected) {
      accountSelect.value = selected;
      await populateFacilities(selected);
    }
  } catch (err) {
    console.error("Error loading accounts:", err);
    accountSelect.innerHTML =
      '<option value="">Error loading accounts</option>';
    setStatus("Error: " + err.message);
  }
}

async function populateFacilities(teamName) {
  const team = teams.find((t) => t.name === teamName);
  if (!team?.facilities?.length) {
    facilitySelect.innerHTML = '<option value="">No facilities</option>';
    return;
  }

  await Promise.all(
    team.facilities.map((f) => f.load?.() || Promise.resolve())
  );

  const sorted = [...team.facilities].sort((a, b) =>
    getFacilityName(a).localeCompare(getFacilityName(b), undefined, {
      sensitivity: "base",
    })
  );

  facilitySelect.innerHTML = "";

  const lastFacility = localStorage.getItem("tandem-viewer-last-facility");

  sorted.forEach((f) => {
    const opt = document.createElement("option");
    opt.value = f.twinId;
    opt.textContent = getFacilityName(f);
    if (f.twinId === lastFacility) opt.selected = true;
    facilitySelect.appendChild(opt);
  });

  facilitySelect.disabled = false;

  const initial =
    sorted.find((f) => f.twinId === lastFacility) || sorted[0];
  if (initial) {
    await loadFacility(initial);
  }
}

async function loadFacility(facility) {
  showLoading(true);
  setStatus("Loading " + getFacilityName(facility) + "...");

  try {
    localStorage.setItem("tandem-viewer-last-facility", facility.twinId);
    await dtApp.displayFacility(facility, false, viewer);
    window._currentFacility = facility;

    setStatus(getFacilityName(facility));
    console.log("Facility loaded:", getFacilityName(facility));
  } catch (err) {
    console.error("Error loading facility:", err);
    setStatus("Error loading facility");
  } finally {
    showLoading(false);
  }
}

function findFacilityById(twinId) {
  for (const team of teams) {
    const f = team.facilities?.find((f) => f.twinId === twinId);
    if (f) return f;
  }
  return null;
}

accountSelect.addEventListener("change", async (e) => {
  if (e.target.value) {
    localStorage.setItem("tandem-viewer-last-team", e.target.value);
    await populateFacilities(e.target.value);
  }
});

facilitySelect.addEventListener("change", async (e) => {
  const facility = findFacilityById(e.target.value);
  if (facility) await loadFacility(facility);
});

function collectLeafNodes(model, max) {
  const tree = model.getInstanceTree();
  if (!tree) return [];
  const leaves = [];
  tree.enumNodeChildren(tree.getRootId(), (dbId) => {
    if (leaves.length >= max) return;
    if (tree.getChildCount(dbId) === 0) leaves.push(dbId);
  }, true);
  return leaves;
}

function doIsolateAndFit() {
  if (!viewer) return;

  const allModels = viewer.getVisibleModels();
  if (!allModels.length) {
    setStatus("No models loaded yet");
    return;
  }

  let targetModel = null;
  let targetDbIds = [];

  for (const model of allModels) {
    const leaves = collectLeafNodes(model, 5);
    if (leaves.length > 0) {
      targetModel = model;
      targetDbIds = leaves;
      break;
    }
  }

  if (!targetModel || targetDbIds.length === 0) {
    setStatus("No elements found in any model");
    return;
  }

  const tree = targetModel.getInstanceTree();
  const names = targetDbIds.map((id) => tree.getNodeName(id) || `dbId:${id}`);
  console.log("Isolating elements:", names, "from model", targetModel);

  for (const m of allModels) {
    if (m === targetModel) {
      viewer.isolate(targetDbIds, m);
    } else {
      viewer.isolate([0], m);
    }
  }

  viewer.fitToView(targetDbIds, targetModel, false);
  setStatus(`Isolated ${targetDbIds.length} elements: ${names.join(", ")}`);
}

function resetView() {
  if (!viewer) return;
  viewer.showAll();
  viewer.fitToView(undefined, undefined, false);
  setStatus("View reset");
}

window.doIsolateAndFit = doIsolateAndFit;
window.resetView = resetView;

window.addEventListener("unhandledrejection", (e) => {
  e.preventDefault();
  console.warn("Suppressed unhandled rejection:", e.reason);
});

async function init() {
  try {
    setStatus("Fetching token...");
    accessToken = await fetchToken();

    setStatus("Initializing viewer...");
    await initLMV(accessToken);
    createViewer();

    dtApp = new Autodesk.Tandem.DtApp();
    window.DT_APP = dtApp;

    setStatus("Loading accounts...");
    await populateAccounts();
  } catch (err) {
    console.error("Initialization failed:", err);
    setStatus("Error: " + err.message);
    showLoading(false);
  }
}

// --- TauriTerm postMessage listener ---
window.addEventListener("message", (event) => {
  if (event.data?.type !== "tauriterm") return;
  const { action, dbIds, modelIndex } = event.data;

  if (!viewer) {
    console.warn("TauriTerm command received but viewer not ready:", action);
    return;
  }

  const allModels = viewer.getVisibleModels();
  const model = modelIndex != null ? allModels[modelIndex] : allModels[0];

  switch (action) {
    case "isolate":
      if (model && dbIds) viewer.isolate(dbIds, model);
      break;
    case "fitToView":
      if (model && dbIds) viewer.fitToView(dbIds, model, false);
      break;
    case "select":
      if (model && dbIds) viewer.select(dbIds, model);
      break;
    case "showAll":
      viewer.showAll();
      viewer.fitToView(undefined, undefined, false);
      break;
    case "isolateAndFit":
      doIsolateAndFit();
      break;
    case "panel":
      // Toggle sidebar panels via Alpine
      const shell = document.querySelector("[x-data='appShell()']");
      if (shell && shell.__x) {
        shell.__x.$data.toggle(event.data.panel);
      }
      break;
    default:
      console.warn("Unknown TauriTerm action:", action);
  }
});

init();
