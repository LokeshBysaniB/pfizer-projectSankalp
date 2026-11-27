// Calls the FastAPI backend. Same origin, so no CORS setup is needed.
const form = document.getElementById("ask");
const status = document.getElementById("status");

const DISCLAIMERS = {
  claims: "This is a recommendation only. The claims team and the credit note owners decide.",
  scheme: "This is a recommendation only. Sales, the Controller and the CFO decide.",
};
const HISTORY_KEY = "sankalp_history";
const MAX_HISTORY = 5;
let lastAuditQuestion = "";
let lastAuditData = null;

function splitNarrative(answer, topic) {
  const key = topic === "claims" ? "claims" : "scheme";
  const closing = DISCLAIMERS[key];
  let narrative = (answer || "").trim();
  if (narrative.endsWith(closing)) {
    narrative = narrative.slice(0, -closing.length).trim();
  } else if (narrative.includes(closing)) {
    narrative = narrative.replace(closing, "").trim();
  }
  return { narrative, disclaimer: closing };
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function fmtNum(v) {
  return v === undefined || v === null || v === "" ? "—" : String(v);
}

function fmtYesNo(v) {
  if (v === true) return "Yes";
  if (v === false) return "No";
  return "—";
}

function formatDateIso(iso) {
  if (!iso || typeof iso !== "string") return "—";
  const parts = iso.slice(0, 10).split("-");
  if (parts.length !== 3) return iso;
  return `${parts[2]}-${parts[1]}-${parts[0]}`;
}

function daysFromExpiryLabel(days) {
  if (days === undefined || days === null || days === "") return "—";
  const d = Number(days);
  if (Number.isNaN(d)) return String(days);
  if (d < 0) return `${-d} days before batch expiry`;
  if (d === 0) return "on the batch expiry date";
  return `${d} days after batch expiry`;
}

function allowedWindowText(result) {
  if (!result.expiry_date) return "—";
  const exp = formatDateIso(result.expiry_date);
  const vf = formatDateIso(result.valid_from);
  const vu = formatDateIso(result.valid_until);
  if (result.claim_type === "Near expiry") {
    return `${vf} through ${exp} (inclusive)`;
  }
  if (result.claim_type === "Expired") {
    return `from the day after ${exp} through ${vu}`;
  }
  return vf && vu ? `${vf} through ${vu}` : "—";
}

function renderClaimFacts(result) {
  const wrap = el("div", "claim-facts-inner");
  const dl = el("dl", "claim-facts-grid");
  const add = (label, value) => {
    dl.appendChild(el("dt", "", label));
    dl.appendChild(el("dd", "", value));
  };
  add("Batch", fmtNum(result.batch_no));
  add("Claim type", fmtNum(result.claim_type));
  add("Claim raised", formatDateIso(result.claim_date));
  add("Batch expiry (master)", formatDateIso(result.expiry_date));
  add("Timing", daysFromExpiryLabel(result.days_from_expiry));
  add("Allowed window", allowedWindowText(result));
  wrap.appendChild(dl);
  if (result.reason) {
    const p = el("p", "claim-facts-reason", result.reason);
    wrap.appendChild(p);
  }
  return wrap;
}

function metricCard(value, label, unit) {
  const card = el("div", "metric");
  card.appendChild(el("div", "metric-value", value));
  card.appendChild(el("div", "metric-label", label));
  if (unit) card.appendChild(el("div", "metric-unit", unit));
  return card;
}

function renderVerdict(result, host) {
  host.replaceChildren();
  if (!result?.found) {
    host.hidden = true;
    return;
  }
  let title = "";
  let sub = "";
  let extraClass = result.topic === "claims" ? "verdict-claims" : "verdict-scheme";

  if (result.route === "D" && result.verifiable_breaches) {
    const vb = result.verifiable_breaches;
    title = `${vb.claims} claims outside window`;
    sub = `INR ${vb.value_lakh} lakh total (credited)`;
  } else if (result.route === "C") {
    const oc = result.outcome;
    title = (oc || "—").toUpperCase();
    sub = `Batch ${result.batch_no || ""} · ${result.claim_type || ""}`;
    extraClass +=
      oc === "pass" ? " verdict-pass" : oc === "reject" ? " verdict-reject" : " verdict-escalate";
  } else if (result.route === "B") {
    const within = result.within_cap != null ? result.within_cap : !result.over_cap;
    title = within ? "Within cap" : "Over cap";
    const pct = result.total_free_pct ?? result.projected_free_pct;
    const ex = result.excess_cr ?? result.projected_excess_cr;
    sub = within ? `Projected ${pct}% free goods` : `Excess ${ex} cr · ${pct}% free goods`;
  } else if (result.route === "A" && result.quarter) {
    title = result.over_cap ? "Over cap" : "Within cap";
    sub = `${result.quarter} · ${result.free_pct}% free goods · excess ${result.excess_cr} cr`;
  } else if (result.route === "A" && result.total_excess_cr != null) {
    const n = Array.isArray(result.quarters_over_cap)
      ? result.quarters_over_cap.length
      : result.quarters_over_cap;
    title = `${n} quarters over cap`;
    sub = `${result.total_excess_cr} cr total excess (~${result.excess_per_year_cr} cr / yr)`;
  } else {
    host.hidden = true;
    return;
  }

  const box = el("div", `verdict ${extraClass}`);
  box.appendChild(el("p", "verdict-title", title));
  if (sub) box.appendChild(el("p", "verdict-sub", sub));
  host.appendChild(box);
  host.hidden = false;
}

function numbersTeaser(result) {
  if (!result?.found) return "";
  switch (result.route) {
    case "D": {
      const vb = result.verifiable_breaches;
      return vb ? `${vb.claims} claims · ${vb.value_lakh} lakh` : "";
    }
    case "C":
      return `${(result.outcome || "").toUpperCase()} · ${result.batch_no || ""}`;
    case "B": {
      const w = result.within_cap != null ? result.within_cap : !result.over_cap;
      const ex = result.excess_cr ?? result.projected_excess_cr;
      return w ? "Within cap" : `Over by ${ex} cr`;
    }
    case "A":
      if (result.quarter) return `${result.quarter} · ${result.free_pct}% · ${result.excess_cr} cr excess`;
      if (result.total_excess_cr != null)
        return `${result.total_excess_cr} cr excess · ~${result.excess_per_year_cr} cr / yr`;
      return "";
    default:
      return "";
  }
}

function loadHistory() {
  try {
    return JSON.parse(sessionStorage.getItem(HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}

function formatPerformance(data) {
  if (!data || data.model_calls == null) return "";
  const parts = [`${data.model_calls} model call(s)`];
  if (typeof data.elapsed_ms === "number") parts.push(`${data.elapsed_ms} ms`);
  const total = data.total_tokens;
  if (typeof total === "number" && total > 0) {
    parts.push(`${total.toLocaleString()} tokens`);
  } else if (data.model_calls > 0) {
    parts.push("tokens not reported by provider");
  }
  return parts.join(" · ");
}

function buildAuditPack(question, data) {
  const result = parseResult(data);
  const pack = {
    version: 1,
    generated_at: new Date().toISOString(),
    question,
    answer: data.answer,
    recommendation_only: true,
    performance: {
      elapsed_ms: data.elapsed_ms ?? null,
      model_calls: data.model_calls ?? 0,
      prompt_tokens: data.prompt_tokens ?? 0,
      completion_tokens: data.completion_tokens ?? 0,
      total_tokens: data.total_tokens ?? 0,
    },
    tool_result: result,
    evidence: data.evidence ?? [],
    show_table: data.show_table ?? false,
  };
  if (result?.rule) pack.policy_clause = policyClause(result.rule);
  if (result?.method) pack.method = result.method;
  if (result?.route === "D") pack.related_exports = { claims_window_check_csv: "/api/recovery-list.csv" };
  return pack;
}

function auditFilename(question) {
  const slug = question
    .slice(0, 48)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `sankalp-audit-${slug || "answer"}-${Date.now()}.json`;
}

function downloadAuditPack() {
  if (!lastAuditQuestion || !lastAuditData) return;
  const blob = new Blob([JSON.stringify(buildAuditPack(lastAuditQuestion, lastAuditData), null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = auditFilename(lastAuditQuestion);
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function performanceBlock(data) {
  return {
    elapsed_ms: data.elapsed_ms ?? null,
    model_calls: data.model_calls ?? 0,
    prompt_tokens: data.prompt_tokens ?? 0,
    completion_tokens: data.completion_tokens ?? 0,
    total_tokens: data.total_tokens ?? 0,
    summary: formatPerformance(data) || null,
  };
}

function buildRawEvidenceDocument(question, data) {
  const toolResult = parseResult(data);
  const doc = {
    performance: performanceBlock(data),
    tool_result: toolResult,
    show_table: data.show_table ?? false,
  };
  if (question) doc.question = question;
  if (!toolResult) doc.tool_result = null;
  return doc;
}

function renderRawEvidencePre(question, data) {
  const pre = document.getElementById("evidence");
  const dlBtn = document.getElementById("audit-download");
  pre.textContent = JSON.stringify(buildRawEvidenceDocument(question, data), null, 2);
  dlBtn.hidden = !data?.answer;
}

function saveHistory(question, data) {
  const entry = {
    question,
    answer: data.answer,
    result: data.result,
    evidence: data.evidence,
    show_table: data.show_table,
    model_calls: data.model_calls,
    elapsed_ms: data.elapsed_ms,
    prompt_tokens: data.prompt_tokens,
    completion_tokens: data.completion_tokens,
    total_tokens: data.total_tokens,
    at: Date.now(),
  };
  let items = loadHistory().filter((h) => h.question !== question);
  items.unshift(entry);
  sessionStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, MAX_HISTORY)));
  renderHistoryUI();
}

function truncateText(text, max) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function formatWhen(ts) {
  return new Date(ts).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

function renderHistoryUI() {
  const items = loadHistory();
  const panel = document.getElementById("history-panel");
  const list = document.getElementById("history-list");
  list.replaceChildren();
  if (!items.length) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  items.forEach((entry) => {
    const li = el("li", "history-item");
    const btn = el("button", "history-btn");
    btn.type = "button";
    btn.title = entry.question;
    btn.appendChild(document.createTextNode(truncateText(entry.question, 72)));
    btn.appendChild(el("span", "history-when", formatWhen(entry.at)));
    btn.addEventListener("click", () => {
      presentResult(
        {
          answer: entry.answer,
          result: entry.result,
          evidence: entry.evidence,
          show_table: entry.show_table,
          model_calls: entry.model_calls,
          elapsed_ms: entry.elapsed_ms,
          prompt_tokens: entry.prompt_tokens,
          completion_tokens: entry.completion_tokens,
          total_tokens: entry.total_tokens,
        },
        entry.question,
        { fromHistory: true }
      );
      status.textContent = "Restored from this session";
    });
    li.appendChild(btn);
    list.appendChild(li);
  });
}

function renderHighlights(result, host) {
  host.replaceChildren();
  if (!result?.found) {
    host.hidden = true;
    return;
  }
  const cards = [];
  if (result.route === "D" && result.verifiable_breaches) {
    const vb = result.verifiable_breaches;
    const firm = result.firm_more_than_90_days_after_expiry;
    cards.push(metricCard(vb.claims, "Outside 90-day window", "credited claims"));
    cards.push(metricCard(vb.value_lakh, "Total value", "INR lakh"));
    cards.push(metricCard(firm?.claims ?? "—", "Firm after expiry", "recovery candidates"));
    if (vb.value_lakh_per_year != null) {
      cards.push(metricCard(vb.value_lakh_per_year, "Per year (est.)", "INR lakh / yr"));
    }
  } else if (result.route === "A" && result.quarter) {
    cards.push(metricCard(`${result.free_pct}%`, result.quarter, "free goods vs sales"));
    cards.push(metricCard(fmtNum(result.excess_cr), "Excess", "INR cr"));
    cards.push(metricCard(fmtYesNo(result.over_cap), "Over 3% cap?", ""));
  } else if (result.route === "A" && result.total_excess_cr != null) {
    cards.push(metricCard(result.total_excess_cr, "Total excess", "INR cr"));
    cards.push(metricCard(result.excess_per_year_cr, "Per year", "INR cr"));
    cards.push(metricCard((result.quarters_over_cap || []).length, "Quarters over cap", ""));
  } else if (result.route === "B") {
    const within = result.within_cap != null ? result.within_cap : !result.over_cap;
    cards.push(metricCard(fmtYesNo(within), "Within cap?", "recommendation"));
    cards.push(
      metricCard(
        fmtNum(result.total_free_pct ?? result.projected_free_pct) + "%",
        "Projected free %",
        "of sales"
      )
    );
    cards.push(metricCard(fmtNum(result.excess_cr ?? result.projected_excess_cr), "Excess", "INR cr"));
  } else if (result.route === "C") {
    const oc = result.outcome;
    const cls =
      oc === "pass" ? "outcome-pass" : oc === "reject" ? "outcome-reject" : "outcome-escalate";
    const card = el("div", "metric");
    card.appendChild(el("div", "metric-value " + cls, (oc || "—").toUpperCase()));
    card.appendChild(el("div", "metric-label", `Batch ${result.batch_no || ""}`));
    card.appendChild(el("div", "metric-unit", result.claim_type || ""));
    cards.push(card);
  }
  if (!cards.length) {
    host.hidden = true;
    return;
  }
  cards.forEach((c) => host.appendChild(c));
  host.hidden = false;
}

/** Headers: string[]. Rows: string[][]. lastColNum: indexes (0-based) of numeric columns. */
function buildTable(headers, rows, lastColNum = [], rowClass = []) {
  const wrap = el("div", "facts-wrap");
  const table = el("table", "facts-table");
  const thead = document.createElement("thead");
  const hrow = document.createElement("tr");
  headers.forEach((h) => hrow.appendChild(el("th", null, h)));
  thead.appendChild(hrow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  rows.forEach((row, ri) => {
    const tr = document.createElement("tr");
    if (rowClass[ri]) tr.className = rowClass[ri];
    row.forEach((cell, i) => {
      const cls = lastColNum.includes(i) ? "num" : "";
      const td = el("td", cls, typeof cell === "string" ? cell : undefined);
      if (cell && typeof cell === "object" && cell.nodeType === 1) td.appendChild(cell);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

function badge(text, kind) {
  return el("span", `badge badge-${kind}`, text);
}

function buildKvTable(rows) {
  const wrap = el("div", "facts-wrap");
  const table = el("table", "facts-table facts-kv");
  const tbody = document.createElement("tbody");
  rows.forEach(([label, value, valueClass]) => {
    const tr = document.createElement("tr");
    tr.appendChild(el("td", "label", label));
    const vd = el("td", valueClass ? `num ${valueClass}` : "num", value);
    tr.appendChild(vd);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

function amtLakh(g, perYear) {
  let s = fmtNum(g?.value_lakh);
  if (perYear && g?.value_lakh_per_year != null) s += `  (~${g.value_lakh_per_year} / yr)`;
  return s;
}

function renderRouteD(result) {
  const vb = result.verifiable_breaches;
  const pending = result.pending_claims_outside_window_to_hold;
  const rows = [
    [el("strong", "", "Verifiable breaches (total)"), fmtNum(vb?.claims), amtLakh(vb, true), badge("Total", "total")],
    [
      "Firm (>90 days after expiry)",
      fmtNum(result.firm_more_than_90_days_after_expiry?.claims),
      amtLakh(result.firm_more_than_90_days_after_expiry, true),
      badge("Recovery", "firm"),
    ],
    [
      "Confirm with claims team",
      fmtNum(result.confirm_with_claims_team?.claims),
      amtLakh(result.confirm_with_claims_team, true),
      badge("Confirm first", "confirm"),
    ],
  ];
  const cb = result.confirm_breakdown;
  if (cb) {
    rows.push([
      "  Raised >90 days before expiry",
      fmtNum(cb.raised_more_than_90_days_before_expiry?.claims),
      amtLakh(cb.raised_more_than_90_days_before_expiry, false),
      badge("Confirm", "confirm"),
    ]);
    rows.push([
      "  Near expiry label, raised 1–90 days after",
      fmtNum(cb.near_expiry_label_but_raised_1_to_90_days_after_expiry?.claims),
      amtLakh(cb.near_expiry_label_but_raised_1_to_90_days_after_expiry, false),
      badge("Confirm", "confirm"),
    ]);
  }
  rows.push([
    "Cannot verify (batch not in master)",
    fmtNum(result.cannot_verify_batch_not_in_master?.claims),
    fmtNum(result.cannot_verify_batch_not_in_master?.value_lakh),
    badge("Escalate", "escalate"),
  ]);
  let holdNote = "Hold until verified";
  if (pending?.claims_without_a_stated_value) {
    holdNote += ` (${pending.claims_without_a_stated_value} no value)`;
  }
  rows.push([
    "Pending outside window",
    fmtNum(pending?.claims),
    fmtNum(pending?.value_lakh),
    badge("Hold", "hold"),
  ]);
  const rowClass = [];
  rowClass[0] = "row-total";
  return buildTable(["Category", "Claims", "INR (lakh)", "Status"], rows, [1, 2], rowClass);
}

function renderRouteA(result) {
  if (Array.isArray(result.quarters)) {
    const rows = result.quarters.map((q) => [
      q.quarter,
      fmtNum(q.free_pct) + "%",
      fmtYesNo(q.over_cap),
      fmtNum(q.excess_cr),
      fmtNum(q.sales_cr),
      fmtNum(q.free_goods_cr),
    ]);
    const wrap = buildTable(
      ["Quarter", "Free %", "Over cap?", "Excess (cr)", "Sales (cr)", "Free goods (cr)"],
      rows,
      [1, 3, 4, 5]
    );
    const table = wrap.querySelector("table");
    const tfoot = document.createElement("tfoot");
    const tr = document.createElement("tr");
    tr.className = "row-total";
    [`Total (${fmtNum(result.years_covered)} yr)`, "", "", fmtNum(result.total_excess_cr), "", `~${fmtNum(result.excess_per_year_cr)} / yr`].forEach(
      (cell, i) => {
        tr.appendChild(el("td", i > 0 ? "num" : "", cell));
      }
    );
    tfoot.appendChild(tr);
    table.appendChild(tfoot);
    return wrap;
  }
  if (result.quarter) {
    return buildKvTable([
      ["Quarter", result.quarter],
      ["Sales (INR cr)", fmtNum(result.sales_cr)],
      ["Free goods (INR cr)", fmtNum(result.free_goods_cr)],
      ["Free goods %", `${fmtNum(result.free_pct)}%`],
      ["Cap (3%)", `${fmtNum(result.allowed_free_cr)} cr allowed`],
      ["Over cap?", fmtYesNo(result.over_cap)],
      ["Excess (INR cr)", fmtNum(result.excess_cr)],
    ]);
  }
  return null;
}

function renderRouteB(result) {
  const fragment = document.createDocumentFragment();
  const within = result.within_cap != null ? result.within_cap : !result.over_cap;
  const main = [
    ["Requested for", fmtNum(result.requested_for || result.basis_quarter)],
    ["Basis quarter (orders)", fmtNum(result.basis_quarter)],
    ["Expected / basis sales (cr)", fmtNum(result.expected_sales_cr ?? result.sales_cr)],
    ["Total free goods (cr)", fmtNum(result.total_free_goods_cr ?? result.projected_free_goods_cr)],
    ["Free goods %", `${fmtNum(result.total_free_pct ?? result.projected_free_pct)}%`],
    ["Allowed at 3% (cr)", fmtNum(result.allowed_free_cr)],
    ["Within cap?", fmtYesNo(within), within ? "outcome-pass" : "outcome-reject"],
    ["Excess (cr)", fmtNum(result.excess_cr ?? result.projected_excess_cr)],
    ["Headroom (cr)", fmtNum(result.headroom_cr)],
  ];
  if (result.max_tier_a_free_per_10_within_cap != null) {
    main.push(["Max Tier A free /10 within cap", fmtNum(result.max_tier_a_free_per_10_within_cap)]);
  }
  if (result.offer_free_goods_cr != null) {
    main.splice(3, 0, ["From offer ratio (cr)", fmtNum(result.offer_free_goods_cr)]);
  }
  if (result.requested_amounts_cr != null && result.requested_amounts_cr !== 0) {
    main.splice(4, 0, ["Requested amounts (cr)", fmtNum(result.requested_amounts_cr)]);
  }
  if (result.planned_tier_a_free_per_10 != null) {
    main.unshift(["Planned Tier A +/10", fmtNum(result.planned_tier_a_free_per_10)]);
  }
  fragment.appendChild(buildKvTable(main));
  const hist = result.history;
  if (hist) {
    fragment.appendChild(
      buildKvTable([
        ["Quarters over cap (history)", fmtNum(hist.quarters_over_cap)],
        ["Historical total excess (cr)", fmtNum(hist.total_excess_cr)],
        ["Historical excess per year (cr)", fmtNum(hist.excess_per_year_cr)],
      ])
    );
  }
  if (Array.isArray(result.assumptions) && result.assumptions.length) {
    const ul = el("ul", "assumptions");
    result.assumptions.forEach((a) => ul.appendChild(el("li", null, a)));
    fragment.appendChild(ul);
  }
  return fragment;
}

function renderRouteC(result) {
  const oc = result.outcome;
  const ocClass =
    oc === "pass" ? "outcome-pass" : oc === "reject" ? "outcome-reject" : "outcome-escalate";
  const rows = [
    ["Batch", fmtNum(result.batch_no)],
    ["Claim type", fmtNum(result.claim_type)],
    ["Claim date", fmtNum(result.claim_date)],
    ["Expiry (batch master)", fmtNum(result.expiry_date)],
    ["Days from expiry", fmtNum(result.days_from_expiry)],
    ["Outcome", (oc || "—").toUpperCase(), ocClass],
    ["Code", fmtNum(result.code)],
  ];
  if (result.valid_from) rows.push(["Valid from (near expiry)", result.valid_from]);
  if (result.reason) rows.push(["Reason", result.reason]);
  return buildKvTable(rows);
}

function renderFactsTable(result) {
  if (!result?.found) return null;
  switch (result.route) {
    case "D":
      return renderRouteD(result);
    case "A":
      return renderRouteA(result);
    case "B":
      return renderRouteB(result);
    case "C":
      return renderRouteC(result);
    default:
      return null;
  }
}

function policyClause(rule) {
  if (!rule) return "—";
  if (rule.includes("CO-POL-014")) return "CO-POL-014 section 4.4 (3% scheme cap)";
  if (rule.includes("section 5.2")) return "Claims policy section 5.2 (90-day window)";
  return rule.slice(0, 120) + (rule.length > 120 ? "…" : "");
}

function evidenceSources(result) {
  if (!result?.found) return [];
  const q = result.basis_quarter || result.quarter;
  if (result.route === "D") {
    return [
      { file: "data/claims_window_check.csv", row: "All credited/pending rows (aggregate)" },
      { file: "data/batch_master.csv", row: "Per claim: expiry_date lookup" },
    ];
  }
  if (result.route === "C") {
    return [
      {
        file: "data/batch_master.csv",
        row: result.batch_no ? `batch_no = ${result.batch_no}` : "—",
      },
    ];
  }
  if (result.route === "B") {
    return [
      { file: "data/scheme_by_quarter.csv", row: q ? `quarter = ${q}` : "—" },
      { file: "data/scheme_by_tier.csv", row: q ? `quarter = ${q}, tiers A/B` : "—" },
    ];
  }
  if (result.route === "A" && result.quarters) {
    return [{ file: "data/scheme_by_quarter.csv", row: "All quarters in file" }];
  }
  if (result.route === "A" && result.quarter) {
    return [{ file: "data/scheme_by_quarter.csv", row: `quarter = ${result.quarter}` }];
  }
  return [];
}

function evidenceKeyValues(result) {
  if (!result?.found) return [];
  switch (result.route) {
    case "A":
      if (result.quarter) {
        return [
          ["Free goods %", `${result.free_pct}%`],
          ["Excess (INR cr)", fmtNum(result.excess_cr)],
          ["Over 3% cap?", fmtYesNo(result.over_cap)],
        ];
      }
      return [
        ["Quarters over cap", fmtNum((result.quarters_over_cap || []).length)],
        ["Total excess (INR cr)", fmtNum(result.total_excess_cr)],
      ];
    case "B":
      return [
        ["Basis quarter", fmtNum(result.basis_quarter)],
        ["Projected free %", fmtNum(result.total_free_pct ?? result.projected_free_pct) + "%"],
        ["Within cap?", fmtYesNo(result.within_cap ?? !result.over_cap)],
        ["Excess (INR cr)", fmtNum(result.excess_cr ?? result.projected_excess_cr)],
      ];
    case "C":
      return [
        ["Outcome", fmtNum(result.outcome)],
        ["Code", fmtNum(result.code)],
        ["Days from expiry", fmtNum(result.days_from_expiry)],
      ];
    case "D":
      return [
        ["Verifiable breaches", fmtNum(result.verifiable_breaches?.claims)],
        ["INR (lakh)", fmtNum(result.verifiable_breaches?.value_lakh)],
        ["Firm recoveries", fmtNum(result.firm_more_than_90_days_after_expiry?.claims)],
      ];
    default:
      return [];
  }
}

function renderEvidenceSummary(result) {
  const host = document.getElementById("evidence-summary");
  host.replaceChildren();
  if (!result?.found) {
    host.appendChild(el("p", "", "No tool result (declined or validation message)."));
    return;
  }
  const wrap = el("div", "evidence-summary-inner");
  const clause = el("dl", "");
  clause.appendChild(el("dt", "", "Policy"));
  clause.appendChild(el("dd", "", policyClause(result.rule)));
  clause.appendChild(el("dt", "", "Method"));
  clause.appendChild(el("dd", "", result.method || "—"));
  wrap.appendChild(clause);

  const srcTitle = el("p", "block-title", "Source files");
  wrap.appendChild(srcTitle);
  const ul = el("ul", "evidence-sources");
  evidenceSources(result).forEach((s) => {
    const li = el("li", "");
    const code = el("code", "", s.file);
    li.appendChild(code);
    if (s.row) {
      li.appendChild(document.createTextNode(" — "));
      li.appendChild(el("span", "", s.row));
    }
    ul.appendChild(li);
  });
  wrap.appendChild(ul);

  const vals = evidenceKeyValues(result);
  if (vals.length) {
    const valDl = el("dl", "");
    const vTitle = el("p", "block-title", "Values used");
    wrap.appendChild(vTitle);
    vals.forEach(([k, v]) => {
      valDl.appendChild(el("dt", "", k));
      valDl.appendChild(el("dd", "", v));
    });
    wrap.appendChild(valDl);
  }
  host.appendChild(wrap);
}

function wantsFactsTable(result) {
  if (!result?.found) return false;
  if (result.route === "D") return true;
  if (result.route === "A" && Array.isArray(result.quarters)) return true;
  return false;
}

function parseResult(data) {
  if (data.result && typeof data.result === "object") return data.result;
  const raw = data.evidence?.[0];
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function showAnswer(data) {
  const result = parseResult(data);
  const topic = result?.topic === "claims" ? "claims" : "scheme";
  const { narrative, disclaimer } = splitNarrative(data.answer, topic);

  renderVerdict(result, document.getElementById("result-verdict"));

  const claimFactsHost = document.getElementById("claim-facts");
  claimFactsHost.replaceChildren();
  if (result?.route === "C" && result.found) {
    claimFactsHost.appendChild(renderClaimFacts(result));
    claimFactsHost.hidden = false;
  } else {
    claimFactsHost.hidden = true;
  }

  const narrativeEl = document.getElementById("answer-narrative");
  const narrativeWrap = document.getElementById("narrative-wrap");
  const narrativeHeading = document.getElementById("narrative-heading");
  narrativeHeading.textContent =
    result?.route === "C" && result.found ? "What to do next" : "Plain-language summary";
  const text = narrative || data.answer || "";
  narrativeEl.textContent = text;
  narrativeWrap.hidden = !text;

  const showTable =
    data.show_table === true || (data.show_table === undefined && wantsFactsTable(result));

  const highlightsHost = document.getElementById("answer-highlights");
  const tableHost = document.getElementById("answer-table");
  const numbersWrap = document.getElementById("numbers-wrap");
  const teaserEl = document.getElementById("numbers-teaser");

  tableHost.replaceChildren();
  highlightsHost.replaceChildren();
  if (showTable && result) {
    teaserEl.textContent = numbersTeaser(result);
    renderHighlights(result, highlightsHost);
    const table = renderFactsTable(result);
    if (table) {
      tableHost.appendChild(table);
      numbersWrap.hidden = false;
      numbersWrap.open = false;
    } else {
      numbersWrap.hidden = true;
      teaserEl.textContent = "";
    }
  } else {
    numbersWrap.hidden = true;
    teaserEl.textContent = "";
    highlightsHost.hidden = true;
  }

  const disc = document.getElementById("answer-disclaimer");
  if (disclaimer && (data.answer || "").includes("recommendation only")) {
    disc.textContent = disclaimer;
    disc.hidden = false;
  } else {
    disc.textContent = "";
    disc.hidden = true;
  }
}

function presentResult(data, question, opts = {}) {
  showAnswer(data);
  const result = parseResult(data);
  renderEvidenceSummary(result);
  renderRawEvidencePre(question, data);
  document.getElementById("out").hidden = false;
  if (question) {
    lastAuditQuestion = question;
    lastAuditData = data;
  }
  if (question && opts.fromHistory) document.getElementById("q").value = question;
  document.getElementById("out").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = document.getElementById("q").value.trim();
  if (!question) return;
  status.textContent = "Thinking…";
  document.getElementById("out").hidden = true;
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Server returned ${res.status}`);
    presentResult(data, question);
    saveHistory(question, data);
    status.textContent = "Done — see Raw tool JSON for performance";
  } catch (err) {
    status.textContent = `Something went wrong: ${err.message}. Check /api/health and the logs.`;
  }
});

document.getElementById("audit-download")?.addEventListener("click", (e) => {
  e.preventDefault();
  downloadAuditPack();
});

document.querySelectorAll(".example-item").forEach((b) => {
  if (b.textContent.includes("Two December 2026")) {
    b.dataset.questionFull =
      "I have two requests for December 2026: 10 + 1.5 on Tier A, and INR 0.3 crore of extra free goods. Can I approve both?";
  }
  b.addEventListener("click", () => {
    document.getElementById("q").value = b.dataset.questionFull || b.textContent.trim();
    document.getElementById("q").focus();
  });
});

document.getElementById("history-clear").addEventListener("click", () => {
  sessionStorage.removeItem(HISTORY_KEY);
  renderHistoryUI();
  status.textContent = "Session history cleared";
});

renderHistoryUI();

(function initShellNav() {
  const shell = document.querySelector(".app-shell");
  const toggle = document.getElementById("sidebar-toggle");
  const backdrop = document.getElementById("sidebar-backdrop");
  const viewOverview = document.getElementById("view-overview");
  const viewAsk = document.getElementById("view-ask");
  if (!shell || !toggle || !viewOverview || !viewAsk) return;

  const setOpen = (open) => {
    shell.classList.toggle("sidebar-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (backdrop) backdrop.hidden = !open;
  };

  const setView = (name, opts = {}) => {
    const isOverview = name === "overview";
    viewOverview.hidden = !isOverview;
    viewAsk.hidden = isOverview;
    document.querySelectorAll(".nav-view").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.view === name);
    });
    const hash = isOverview ? "#overview" : "#ask";
    if (opts.replaceHash !== false) {
      history.replaceState(null, "", hash);
    }
    if (!isOverview && opts.scrollTo) {
      const target = document.getElementById(opts.scrollTo);
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      window.scrollTo({ top: 0, behavior: opts.scrollTo ? "smooth" : "auto" });
    }
    setOpen(false);
  };

  const initial = window.location.hash === "#overview" ? "overview" : "ask";
  setView(initial, { replaceHash: false });

  toggle.addEventListener("click", () => {
    setOpen(!shell.classList.contains("sidebar-open"));
  });

  backdrop?.addEventListener("click", () => setOpen(false));

  document.querySelectorAll(".nav-view").forEach((btn) => {
    btn.addEventListener("click", () => setView(btn.dataset.view || "ask"));
  });

  document.querySelectorAll(".nav-scroll").forEach((btn) => {
    btn.addEventListener("click", () => {
      setView("ask", { scrollTo: btn.dataset.scroll || "" });
    });
  });

  window.addEventListener("hashchange", () => {
    setView(window.location.hash === "#overview" ? "overview" : "ask", { replaceHash: false });
  });
})();