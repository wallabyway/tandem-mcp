/**
 * Alpine.js component definitions for sidebar panels.
 * Loaded before main.js so Alpine stores are available when the DOM initialises.
 */

/* ---- Root shell: manages which panel is open and report overlay ---- */
window.appShell = () => ({
  activePanel: null,
  activeReport: null,
  toggle(name) {
    this.activePanel = this.activePanel === name ? null : name;
  },
  openReport(report) {
    this.activeReport = report;
    this.activePanel = null;
  },
  closeReport() {
    this.activeReport = null;
  },
});

/* ---- Tickets panel: demo ticket data ---- */
window.ticketsPanel = () => ({
  tickets: [
    { id: 1, title: "HVAC Unit #3 – abnormal vibration", priority: "High", location: "Level 2 – Mech Room", date: "2026-04-07" },
    { id: 2, title: "Lighting circuit B12 tripped", priority: "Medium", location: "Level 1 – Lobby", date: "2026-04-06" },
    { id: 3, title: "Fire damper inspection overdue", priority: "High", location: "Level 3 – Corridor", date: "2026-04-05" },
    { id: 4, title: "Chilled water valve leak", priority: "Medium", location: "Level B1 – Plant Room", date: "2026-04-04" },
    { id: 5, title: "Emergency exit sign dim", priority: "Low", location: "Level 1 – Stairwell A", date: "2026-04-03" },
    { id: 6, title: "AHU filter replacement due", priority: "Low", location: "Level 2 – Roof", date: "2026-04-01" },
  ],
});

/* ---- Chat panel: mock conversation ---- */
window.chatPanel = () => ({
  messages: [
    { id: 1, from: "system", text: "Welcome to Tandem Assistant. How can I help you today?" },
    { id: 2, from: "user", text: "What's the status of HVAC Unit #3?" },
    { id: 3, from: "system", text: "HVAC Unit #3 on Level 2 (Mech Room) has an open ticket for abnormal vibration. Last inspection was 2026-04-02. Current runtime: 4,218 hrs." },
    { id: 4, from: "user", text: "Can you show me its location?" },
    { id: 5, from: "system", text: "Isolating HVAC Unit #3 in the viewer now. The unit is located in the southeast corner of the Level 2 Mechanical Room." },
  ],
  draft: "",
  send() {
    if (!this.draft.trim()) return;
    this.messages.push({ id: Date.now(), from: "user", text: this.draft.trim() });
    const q = this.draft.trim();
    this.draft = "";
    setTimeout(() => {
      this.messages.push({ id: Date.now(), from: "system", text: `I'll look into "${q}" for you. This is a demo — live responses coming soon.` });
    }, 600);
  },
});

/* ---- Reports panel: list of available reports ---- */
window.reportsPanel = () => ({
  reports: [
    {
      id: "energy-q1",
      title: "Energy Consumption – Q1 2026",
      category: "Energy",
      date: "2026-04-01",
      icon: "bolt",
      sections: [
        { heading: "Executive Summary", body: "Total energy consumption for Q1 2026 was 1,247,000 kWh, a 4.2% decrease from Q4 2025. HVAC systems accounted for 58% of total usage, lighting 22%, and plug loads 20%." },
        { heading: "Monthly Breakdown", table: { headers: ["Month", "kWh", "Cost", "vs. Prior Year"], rows: [["January", "438,200", "$52,584", "-3.1%"], ["February", "396,100", "$47,532", "-5.8%"], ["March", "412,700", "$49,524", "-3.6%"]] } },
        { heading: "Recommendations", body: "1. Upgrade AHU-2 and AHU-4 VFDs to reduce HVAC consumption by an estimated 8%.\n2. Install occupancy-based lighting controls on Levels 2–3.\n3. Schedule chiller maintenance before summer peak season." },
      ],
    },
    {
      id: "maintenance-mar",
      title: "Maintenance Summary – March 2026",
      category: "Maintenance",
      date: "2026-03-31",
      icon: "wrench",
      sections: [
        { heading: "Overview", body: "32 work orders completed in March, 4 remain open. Average time-to-close: 2.3 days. Preventive maintenance compliance: 94%." },
        { heading: "Work Orders by Priority", table: { headers: ["Priority", "Opened", "Closed", "Avg Days"], rows: [["Critical", "3", "3", "0.5"], ["High", "8", "7", "1.8"], ["Medium", "14", "14", "2.6"], ["Low", "11", "8", "3.4"]] } },
        { heading: "Open Items", body: "1. HVAC Unit #3 abnormal vibration — awaiting parts (ETA Apr 10).\n2. Fire damper Level 3 corridor — scheduled for Apr 12.\n3. AHU filter replacement Level 2 — technician assigned.\n4. Emergency exit sign Stairwell A — on order." },
      ],
    },
    {
      id: "safety-q1",
      title: "Safety & Compliance – Q1 2026",
      category: "Safety",
      date: "2026-04-05",
      icon: "shield",
      sections: [
        { heading: "Summary", body: "Zero recordable incidents in Q1. All fire suppression systems passed quarterly inspection. Emergency lighting tested on all floors — 2 units flagged for replacement." },
        { heading: "Inspection Results", table: { headers: ["System", "Status", "Next Due", "Notes"], rows: [["Fire Alarm", "Pass", "Jul 2026", "—"], ["Sprinklers", "Pass", "Jul 2026", "Zone 4 head replaced"], ["Emergency Lighting", "2 Flags", "Jul 2026", "Stairwell A, B1 Corridor"], ["Fire Extinguishers", "Pass", "Oct 2026", "—"]] } },
        { heading: "Action Items", body: "1. Replace flagged emergency lighting units before Apr 30.\n2. Schedule mid-year fire drill for June.\n3. Update evacuation maps for Level 3 renovation." },
      ],
    },
    {
      id: "occupancy-mar",
      title: "Occupancy Analytics – March 2026",
      category: "Analytics",
      date: "2026-03-31",
      icon: "users",
      sections: [
        { heading: "Overview", body: "Average daily occupancy: 68% of capacity. Peak utilization on Tuesdays and Wednesdays. Level 2 open offices averaged 74% occupancy, Level 3 executive areas 41%." },
        { heading: "Floor-by-Floor", table: { headers: ["Floor", "Avg Occ%", "Peak Occ%", "Peak Day"], rows: [["Level 1", "82%", "95%", "Wednesday"], ["Level 2", "74%", "89%", "Tuesday"], ["Level 3", "41%", "62%", "Wednesday"], ["Level B1", "23%", "38%", "Thursday"]] } },
        { heading: "Recommendations", body: "1. Consider hot-desking policy for Level 3 to improve space utilization.\n2. Reduce HVAC scheduling for Level B1 on Mondays and Fridays.\n3. Evaluate converting Conference 202 to a shared workspace." },
      ],
    },
  ],
});

/* ---- Spatial panel: levels / rooms tree ---- */
window.spatialPanel = () => ({
  levels: [
    {
      name: "Level B1 – Basement",
      open: false,
      rooms: ["Plant Room", "Storage A", "Parking Garage", "Electrical Room"],
    },
    {
      name: "Level 1 – Ground Floor",
      open: true,
      rooms: ["Lobby", "Reception", "Stairwell A", "Stairwell B", "Restrooms"],
    },
    {
      name: "Level 2 – Offices",
      open: false,
      rooms: ["Open Office A", "Open Office B", "Mech Room", "Conference 201", "Conference 202"],
    },
    {
      name: "Level 3 – Executive",
      open: false,
      rooms: ["Board Room", "Corner Office A", "Corner Office B", "Corridor", "Kitchenette"],
    },
    {
      name: "Level 4 – Roof / Mechanical",
      open: false,
      rooms: ["Rooftop Terrace", "AHU Enclosure", "Elevator Machine Room"],
    },
  ],
});
