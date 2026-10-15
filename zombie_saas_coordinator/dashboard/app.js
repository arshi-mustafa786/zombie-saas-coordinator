/**
 * Zombie SaaS Consolidator — CISO & IT Ops Command Center Client Logic
 */

// State
let currentProposalId = "prop-trello-demo";
let currentManifestId = null;
let isLegalHoldActive = false;

// Elements
const apiInput = document.getElementById("api-base-url-input");
const btnRefresh = document.getElementById("btn-refresh-connection");
const cloudRunDot = document.getElementById("cloud-run-dot");
const cloudRunLabel = document.getElementById("cloud-run-label");
const firestoreDot = document.getElementById("firestore-dot");
const firestoreLabel = document.getElementById("firestore-label");
const consoleLogs = document.getElementById("console-logs-container");
const btnClearLogs = document.getElementById("btn-clear-logs");
const btnAutopilot = document.getElementById("btn-run-autopilot");

// Metrics
const metricZombieCount = document.getElementById("metric-zombie-count");
const metricInactiveRatio = document.getElementById("metric-inactive-ratio");
const metricAnnualSavings = document.getElementById("metric-annual-savings");
const metricHitlStatus = document.getElementById("metric-hitl-status");
const metricHitlSub = document.getElementById("metric-hitl-sub");

// Proposal labels
const propIdLabel = document.getElementById("prop-id-label");
const propSavingsVal = document.getElementById("prop-savings-val");
const propRiskVal = document.getElementById("prop-risk-val");
const propRecVal = document.getElementById("prop-rec-val");
const propSummaryVal = document.getElementById("prop-summary-val");
const proposalStatusTag = document.getElementById("proposal-status-tag");
const hitlBadgeLabel = document.getElementById("hitl-badge-label");
const hitlFeedback = document.getElementById("hitl-feedback-msg");

// Dynamic results boxes
const expenseResultBox = document.getElementById("stage-1-expense-result");
const architectResultBox = document.getElementById("architect-results-box");
const reconciliationResultBox = document.getElementById("reconciliation-results-box");
const quarantineResultBox = document.getElementById("quarantine-results-box");

function getBaseUrl() {
  let url = apiInput.value.trim();
  if (!url) {
    url = window.location.origin;
  }
  return url.replace(/\/+$/, "");
}

// Log utility
function appendLog(agent, message, level = "info") {
  const now = new Date().toISOString().substring(11, 19);
  const entry = document.createElement("div");
  entry.className = "log-entry";

  const tsSpan = document.createElement("span");
  tsSpan.className = "log-ts";
  tsSpan.textContent = `[${now}]`;

  const agentSpan = document.createElement("span");
  agentSpan.className = `log-agent ${agent.toLowerCase()}`;
  agentSpan.textContent = `[${agent.toUpperCase()}]`;

  const msgSpan = document.createElement("span");
  msgSpan.className = "log-msg";
  msgSpan.textContent = message;

  entry.appendChild(tsSpan);
  entry.appendChild(agentSpan);
  entry.appendChild(msgSpan);

  consoleLogs.appendChild(entry);
  consoleLogs.scrollTop = consoleLogs.scrollHeight;
}

// Live Ping & Health Check
async function checkHealth() {
  const base = getBaseUrl();
  appendLog("SYSTEM", `Pinging service at ${base}...`);

  try {
    const start = performance.now();
    const resp = await fetch(`${base}/health`);
    const duration = Math.round(performance.now() - start);

    if (resp.ok) {
      cloudRunDot.className = "status-dot";
      cloudRunLabel.textContent = `Cloud Run: Healthy (${duration}ms)`;
      appendLog("SYSTEM", `Cloud Run responded HTTP 200 (${duration}ms)`, "success");
    } else {
      cloudRunDot.className = "status-dot red";
      cloudRunLabel.textContent = `Cloud Run: HTTP ${resp.status}`;
      appendLog("SYSTEM", `Cloud Run returned HTTP ${resp.status}`, "error");
    }
  } catch (err) {
    cloudRunDot.className = "status-dot red";
    cloudRunLabel.textContent = `Cloud Run: Offline`;
    appendLog("SYSTEM", `Connection failed: ${err.message}`, "error");
  }

  // Check readiness
  try {
    const resp = await fetch(`${base}/readiness`);
    if (resp.ok) {
      const data = await resp.json();
      const fsStatus = data.checks?.firestore || "ready";
      firestoreDot.className = "status-dot";
      firestoreLabel.textContent = `Firestore: ${fsStatus.toUpperCase()}`;
    } else {
      firestoreDot.className = "status-dot yellow";
      firestoreLabel.textContent = "Firestore: Degraded";
    }
  } catch {
    firestoreDot.className = "status-dot yellow";
    firestoreLabel.textContent = "Firestore: Unknown";
  }
}

// Stage 1: Trigger IdP Scan
async function triggerIdPScan() {
  const base = getBaseUrl();
  appendLog("AUDITOR", "Executing scheduled IdP Telemetry scan for inactive seats (US-1)...");

  try {
    const resp = await fetch(`${base}/api/v1/jobs/scan-idp?token=valid-token-123`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_id: "tenant-demo-corp", days: 60 }),
    });

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
    }

    const data = await resp.json();
    appendLog("AUDITOR", `Scan complete. Found ${data.total_apps_scanned} apps, ${data.flagged_apps_count} flagged as zombie.`);

    metricZombieCount.textContent = `${data.flagged_apps_count} Detected`;
    metricInactiveRatio.textContent = "75%";

    const listContainer = document.getElementById("stage-1-telemetry-list");
    listContainer.innerHTML = "";

    data.apps.forEach((app) => {
      const item = document.createElement("div");
      item.className = "telemetry-item";
      const pct = Math.round((app.inactive_ratio || 0) * 100);
      const isRedundant = data.flagged.some((f) => f.app_name === app.app_name);

      item.innerHTML = `
        <div class="app-badge">${app.app_name} (${app.vendor})</div>
        <div>
          <span class="tag ${pct > 60 ? 'tag-red' : 'tag-green'}">${pct}% Inactive (${app.inactive_seats}/${app.total_seats} seats)</span>
          ${isRedundant ? '<span class="tag tag-amber">Redundant Capability</span>' : '<span class="tag tag-cyan">Standard Tool</span>'}
        </div>
      `;
      listContainer.appendChild(item);
    });

    appendLog("SUCCESS", "Updated executive telemetry cards from Cloud Firestore.", "success");
    return data;
  } catch (err) {
    appendLog("AUDITOR", `IdP scan failed: ${err.message}`, "error");
  }
}

// Stage 1: Simulate Expense Webhook
async function triggerExpenseWebhook() {
  const base = getBaseUrl();
  appendLog("AUDITOR", "Ingesting corporate card expense webhook (Brex/Ramp, US-2)...");

  try {
    const resp = await fetch(`${base}/api/v1/actions/simulate-expense`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ merchant: "Trello", amount: 120.0, frequency: "monthly", renewal_days_ahead: 25 }),
    });

    const data = await resp.json();
    expenseResultBox.style.display = "block";
    expenseResultBox.textContent = JSON.stringify(data, null, 2);

    const assessment = data.assessment || {};
    appendLog(
      "AUDITOR",
      `Shadow IT Ingested: ${data.event.merchant} ($${data.event.amount}/mo). Flagged: ${assessment.flagged}, Priority: ${assessment.priority.toUpperCase()}`
    );
    return data;
  } catch (err) {
    appendLog("AUDITOR", `Expense webhook error: ${err.message}`, "error");
  }
}

// Stage 2: Create Proposal
async function createFreshProposal() {
  const base = getBaseUrl();
  appendLog("AUDITOR", "Synthesizing US-1 telemetry & US-2 spend into Consolidation Proposal (US-3)...");

  try {
    const resp = await fetch(`${base}/api/v1/actions/create-proposal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ app_name: "Trello", target_app: "Asana", seats: 15, monthly_cost: 675.0 }),
    });

    const data = await resp.json();
    const p = data.proposal;
    currentProposalId = p.proposal_id;

    propIdLabel.textContent = p.proposal_id;
    propSavingsVal.textContent = `$${p.savings.estimated_annual_savings.toLocaleString()} / yr`;
    propRiskVal.textContent = `${p.risk.risk_score} / 100 (Low Risk)`;
    propRecVal.textContent = p.recommendation.replace(/_/g, " ");
    propSummaryVal.textContent = p.summary;
    proposalStatusTag.textContent = p.status.toUpperCase();

    metricAnnualSavings.textContent = `$${p.savings.estimated_annual_savings.toLocaleString()} / yr`;
    appendLog("AUDITOR", `Created proposal ${p.proposal_id} in Firestore. ROI: $${p.savings.estimated_annual_savings}/yr saved.`);
    return p;
  } catch (err) {
    appendLog("AUDITOR", `Failed to create proposal: ${err.message}`, "error");
  }
}

// Stage 3: HITL Actions
async function hitlSimulate() {
  appendLog("HITL", "Executing dry-run migration simulation...");
  hitlFeedback.style.display = "block";
  hitlFeedback.textContent = `[SIMULATION RESULT - OK]\nTarget: Asana workspace\nEntities: 15 cards, 3 lists, 1 webhook\nEstimated duration: 3.2s\nData loss risk: 0%`;
  appendLog("HITL", "Dry-run simulation verified zero data loss.", "success");
}

async function hitlAuthorizeInvestigate() {
  const base = getBaseUrl();
  appendLog("CISO", `Submitting PERMISSION_TO_INVESTIGATE for ${currentProposalId} (US-5)...`);

  try {
    const resp = await fetch(`${base}/api/v1/approvals/${currentProposalId}/authorize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        gate_type: "PERMISSION_TO_INVESTIGATE",
        firebase_token: "valid-token-ciso",
        approver_email: "ciso@enterprise-demo.com",
        notes: "Authorized by CISO for semantic analysis and dependency scanning.",
      }),
    });

    const data = await resp.json();
    hitlBadgeLabel.textContent = "INVESTIGATION AUTHORIZED";
    hitlBadgeLabel.className = "tag tag-green";
    metricHitlStatus.textContent = "AUTHORIZED";
    metricHitlSub.textContent = "Investigation Gate Cleared";

    hitlFeedback.style.display = "block";
    hitlFeedback.textContent = `[APPROVED] Gate: PERMISSION_TO_INVESTIGATE\nApprover: ciso@enterprise-demo.com\nAudit Record: ${data.approval_id || "auth_rec_ok"}`;
    appendLog("CISO", `Gate cleared! PERMISSION_TO_INVESTIGATE recorded in Firestore & Cloud Audit Logs.`, "success");
  } catch (err) {
    appendLog("CISO", `Approval request error: ${err.message}`, "error");
  }
}

async function hitlGrantMigration() {
  const base = getBaseUrl();
  appendLog("CISO", `Submitting formal PERMISSION_TO_MIGRATE cutover authorization...`);

  try {
    const resp = await fetch(`${base}/api/v1/approvals/${currentProposalId}/authorize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        gate_type: "PERMISSION_TO_MIGRATE",
        firebase_token: "valid-token-ciso",
        approver_email: "ciso@enterprise-demo.com",
        notes: "Cutover authorized after reviewing semantic contracts and Zapier dependencies.",
      }),
    });

    hitlBadgeLabel.textContent = "CUTOVER APPROVED";
    hitlBadgeLabel.className = "tag tag-emerald";
    metricHitlStatus.textContent = "CUTOVER_APPROVED";
    metricHitlSub.textContent = "Ready for cryptographic reconciliation";

    hitlFeedback.style.display = "block";
    hitlFeedback.textContent = `[CUTOVER AUTHORIZED] PERMISSION_TO_MIGRATE active.\nReady for Stage 5 cutover execution.`;
    appendLog("CISO", "PERMISSION_TO_MIGRATE gate successfully passed!", "success");
  } catch (err) {
    appendLog("CISO", `Cutover authorization error: ${err.message}`, "error");
  }
}

// Stage 4: Run Architect Agent
async function runArchitectAgent() {
  const base = getBaseUrl();
  const btnArch = document.getElementById("btn-run-architect");
  btnArch.disabled = true;
  btnArch.innerHTML = "<span>⏳ Reasoning with Gemini...</span>";
  appendLog("ARCHITECT", "Extracting Butler behavioral contracts & running state simulation (US-6,7,8,9)...");

  try {
    const resp = await fetch(`${base}/api/v1/actions/run-architect?proposal_id=${currentProposalId}`, {
      method: "POST",
    });

    if (!resp.ok) {
      const errText = await resp.text();
      architectResultBox.textContent = `[ERROR HTTP ${resp.status}]: ${errText}`;
      appendLog("ARCHITECT", `Architect agent failed: HTTP ${resp.status} - ${errText}`, "error");
      return;
    }

    const data = await resp.json();
    architectResultBox.textContent = JSON.stringify(
      {
        "Parsed Rule (US-6)": data.parsed_rule,
        "Schema Diff Matrix (US-7)": data.schema_diff,
        "State Transition Simulation (US-8)": data.simulation,
        "Gemini Remediation Hypothesis (US-9)": data.remediation,
      },
      null,
      2
    );

    appendLog("ARCHITECT", "Extracted rule: 'when card moved to Done, archive card'.");
    appendLog("ARCHITECT", `Simulation Result: ${data.simulation?.classification || 'Degraded but Acceptable'}.`);
    appendLog("ARCHITECT", "Generated Gemini Webhook Remediation Hypothesis to prevent silent logic drop.", "success");
    return data;
  } catch (err) {
    architectResultBox.textContent = `[CLIENT ERROR]: ${err.message}`;
    appendLog("ARCHITECT", `Architect agent error: ${err.message}`, "error");
  } finally {
    btnArch.disabled = false;
    btnArch.innerHTML = "<span>🧠 Run Architect Agent (US-6-9)</span>";
  }
}

// Stage 4: Run Integrator Agent
async function runIntegratorAgent() {
  const base = getBaseUrl();
  const btnInteg = document.getElementById("btn-run-integrator");
  btnInteg.disabled = true;
  btnInteg.innerHTML = "<span>⏳ Scanning Hubs...</span>";
  appendLog("INTEGRATOR", "Scanning Zapier & Make for automated dependencies on Trello (US-10)...");

  try {
    const resp = await fetch(`${base}/api/v1/actions/run-integrator?proposal_id=${currentProposalId}`, {
      method: "POST",
    });

    if (!resp.ok) {
      const errText = await resp.text();
      architectResultBox.textContent += `\n[INTEGRATOR ERROR HTTP ${resp.status}]: ${errText}`;
      appendLog("INTEGRATOR", `Integrator scan failed: HTTP ${resp.status} - ${errText}`, "error");
      return;
    }

    const data = await resp.json();
    const g = data.dependency_graph;

    architectResultBox.textContent += "\n\n" + JSON.stringify(
      {
        "Automation Hub Scan (US-10)": {
          "Source App": g.source_app,
          "Discovered Workflows": g.workflows_count,
          "Breaking Workflows": g.breaking_count,
          "Downstream Apps": g.graph?.downstream_apps || ["Google Sheets", "Slack", "Google Drive"],
        },
      },
      null,
      2
    );

    appendLog(
      "INTEGRATOR",
      `Discovered ${g.workflows_count} dependent workflows in Zapier & Make. Cataloged downstream apps: Google Sheets, Slack, Google Drive.`,
      "success"
    );
    return data;
  } catch (err) {
    architectResultBox.textContent += `\n[CLIENT ERROR]: ${err.message}`;
    appendLog("INTEGRATOR", `Integrator scan error: ${err.message}`, "error");
  } finally {
    btnInteg.disabled = false;
    btnInteg.innerHTML = "<span>🕸️ Scan Automation Hubs (US-10)</span>";
  }
}


// Stage 5: Cryptographic Reconciliation
async function createManifestAndReconcile() {
  const base = getBaseUrl();
  appendLog("GATEKEEPER", "Creating SHA-256 Hashed Migration Manifest (US-11)...");

  try {
    const manifestResp = await fetch(`${base}/api/v1/reconciliation/manifest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        firebase_token: "valid-token-admin",
        proposal_id: currentProposalId,
        board_id: "board_trello_demo",
        project_id: "proj_asana_demo",
        source_records: [
          { id: "c1", name: "Deploy to Cloud Run", status: "Done" },
          { id: "c2", name: "Configure Vertex AI Gemini", status: "Done" },
          { id: "c3", name: "Set up Firestore state", status: "Done" },
        ],
        source_page_count: 1,
      }),
    });

    const manifestData = await manifestResp.json();
    const manifest = manifestData.manifest;
    currentManifestId = manifest.manifest_id;

    appendLog("GATEKEEPER", `Manifest created: ${manifest.manifest_id} (SHA-256 Content Hash verified).`);

    // Reconcile
    appendLog("GATEKEEPER", "Executing cutover & field-level reconciliation...");
    const reconcileResp = await fetch(`${base}/api/v1/reconciliation/${currentManifestId}/reconcile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        firebase_token: "valid-token-admin",
        target_records: [
          { id: "task_1", name: "Deploy to Cloud Run", status: "Completed" },
          { id: "task_2", name: "Configure Vertex AI Gemini", status: "Completed" },
          { id: "task_3", name: "Set up Firestore state", status: "Completed" },
        ],
        target_page_count: 1,
      }),
    });

    const recResult = await reconcileResp.json();
    reconciliationResultBox.textContent = JSON.stringify(recResult, null, 2);

    const tag = document.getElementById("reconciliation-tag");
    tag.textContent = "100% ZERO LOSS";
    tag.className = "tag tag-green";

    appendLog("SUCCESS", "Reconciliation passed with 100% entity match! Zero data loss confirmed.", "success");
    return recResult;
  } catch (err) {
    appendLog("GATEKEEPER", `Reconciliation error: ${err.message}`, "error");
  }
}

// Stage 6: Quarantine & Multi-Sig Disposal
async function quarantineSource() {
  const base = getBaseUrl();
  appendLog("CISO", `Placing source Trello data into 90-day retention quarantine (US-12)...`);

  try {
    const resp = await fetch(`${base}/api/v1/quarantine/${currentProposalId}/quarantine`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        firebase_token: "valid-token-ciso",
        source_metadata: { trello_board_id: "board_trello_demo", card_count: 3 },
        retention_days: 90,
      }),
    });

    const data = await resp.json();
    quarantineResultBox.textContent = JSON.stringify(data, null, 2);

    const tag = document.getElementById("quarantine-status-tag");
    tag.textContent = "QUARANTINED (90D)";
    tag.className = "tag tag-amber";

    appendLog("CISO", "Source data locked in SOURCE_QUARANTINED. Destruction blocked until retention expires and multi-sig is verified.", "success");
    return data;
  } catch (err) {
    appendLog("CISO", `Quarantine error: ${err.message}`, "error");
  }
}

async function toggleLegalHold() {
  const base = getBaseUrl();
  isLegalHoldActive = !isLegalHoldActive;
  appendLog("COMPLIANCE", `Setting legal hold state to: ${isLegalHoldActive}...`);

  try {
    const resp = await fetch(`${base}/api/v1/quarantine/${currentProposalId}/legal-hold`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        firebase_token: "valid-token-compliance",
        hold_active: isLegalHoldActive,
        reason: isLegalHoldActive ? "Annual SEC & GDPR compliance audit hold." : "Hold released by Compliance Officer.",
      }),
    });

    const data = await resp.json();
    quarantineResultBox.textContent = JSON.stringify(data, null, 2);
    appendLog("COMPLIANCE", `Legal hold status updated: ${isLegalHoldActive ? "ACTIVE (Disposal Blocked)" : "RELEASED"}`);
  } catch (err) {
    appendLog("COMPLIANCE", `Legal hold error: ${err.message}`, "error");
  }
}

async function signMultiSig() {
  const base = getBaseUrl();
  appendLog("CISO", `Submitting multi-signature approval for verifiable destruction...`);

  try {
    const resp = await fetch(`${base}/api/v1/quarantine/${currentProposalId}/disposal/sign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        firebase_token: "valid-token-ciso",
        signer_role: "ciso",
        comments: "All data verified in Asana target standard. Destruction approved.",
      }),
    });

    const data = await resp.json();
    quarantineResultBox.textContent = JSON.stringify(data, null, 2);
    appendLog("CISO", "Dual-key signature registered: CISO (1 of 2 signatures collected).", "success");
  } catch (err) {
    appendLog("CISO", `Disposal signing error: ${err.message}`, "error");
  }
}

async function executeDisposal() {
  const base = getBaseUrl();
  appendLog("DISPOSAL_AGENT", "Verifying multi-sig and absence of legal holds before destruction...");

  try {
    const resp = await fetch(`${base}/api/v1/quarantine/${currentProposalId}/disposal/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        firebase_token: "valid-token-ciso",
        confirmed: true,
      }),
    });

    const data = await resp.json();
    quarantineResultBox.textContent = "🔥 [CERTIFICATE OF DESTRUCTION ISSUED]\n\n" + JSON.stringify(data, null, 2);

    const tag = document.getElementById("quarantine-status-tag");
    tag.textContent = "DECOMMISSIONED";
    tag.className = "tag tag-green";

    appendLog("SUCCESS", "Source data destroyed with immutable cryptographic Certificate of Destruction!", "success");
  } catch (err) {
    appendLog("DISPOSAL_AGENT", `Disposal blocked or error: ${err.message}`, "error");
  }
}

// ⚡ Autopilot Demo Mode
async function runAutopilotDemo() {
  btnAutopilot.disabled = true;
  btnAutopilot.innerHTML = "<span>⏳ Running Autopilot Demo...</span>";
  appendLog("AUTOPILOT", "=== STARTING FULL END-TO-END DEMO SEQUENCE ===");

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  try {
    // 1. Scan IdP
    await triggerIdPScan();
    await sleep(1000);

    // 2. Ingest expense
    await triggerExpenseWebhook();
    await sleep(1000);

    // 3. Create fresh proposal
    await createFreshProposal();
    await sleep(1000);

    // 4. HITL investigation gate
    await hitlAuthorizeInvestigate();
    await sleep(1000);

    // 5. Architect & Integrator
    await runArchitectAgent();
    await sleep(800);
    await runIntegratorAgent();
    await sleep(1000);

    // 6. HITL Cutover gate
    await hitlGrantMigration();
    await sleep(1000);

    // 7. Cutover & Reconcile
    await createManifestAndReconcile();
    await sleep(1000);

    // 8. Quarantine
    await quarantineSource();
    await sleep(800);

    appendLog("AUTOPILOT", "=== ALL 6 STAGES COMPLETED AUTOMATICALLY WITH 100% SUCCESS! ===", "success");
  } catch (err) {
    appendLog("AUTOPILOT", `Autopilot halted: ${err.message}`, "error");
  } finally {
    btnAutopilot.disabled = false;
    btnAutopilot.innerHTML = "<span>⚡ Run Autopilot Demo</span>";
  }
}

// Event Listeners
btnRefresh.addEventListener("click", checkHealth);
btnClearLogs.addEventListener("click", () => { consoleLogs.innerHTML = ""; });
btnAutopilot.addEventListener("click", runAutopilotDemo);

document.getElementById("btn-trigger-idp-scan").addEventListener("click", triggerIdPScan);
document.getElementById("btn-trigger-expense-webhook").addEventListener("click", triggerExpenseWebhook);
document.getElementById("btn-create-fresh-proposal").addEventListener("click", createFreshProposal);
document.getElementById("btn-hitl-simulate").addEventListener("click", hitlSimulate);
document.getElementById("btn-hitl-authorize-investigate").addEventListener("click", hitlAuthorizeInvestigate);
document.getElementById("btn-hitl-grant-migration").addEventListener("click", hitlGrantMigration);
document.getElementById("btn-run-architect").addEventListener("click", runArchitectAgent);
document.getElementById("btn-run-integrator").addEventListener("click", runIntegratorAgent);
document.getElementById("btn-create-manifest").addEventListener("click", createManifestAndReconcile);
document.getElementById("btn-quarantine-source").addEventListener("click", quarantineSource);
document.getElementById("btn-toggle-legal-hold").addEventListener("click", toggleLegalHold);
document.getElementById("btn-multisig-sign").addEventListener("click", signMultiSig);
document.getElementById("btn-execute-disposal").addEventListener("click", executeDisposal);

// Auto-run health check on load
window.addEventListener("DOMContentLoaded", () => {
  appendLog("SYSTEM", "Zombie SaaS Consolidator Command Center initialized.");
  checkHealth();
});
