/**
 * Risk Register Viewer — dataset-agnostic UI for RiskRegisterBundle.v0.1.
 *
 * Loads a risk register bundle (from file, zip, or URL) and renders search,
 * filters, risk list, and risk detail. No hardcoded risks or evidence; swap
 * datasets (e.g. "Load latest release") without changing this code. Bundle
 * schema: policy/schemas/risk_register_bundle.v0.1.schema.json.
 */

(function (global) {
  'use strict';

  var bundle = null;
  var filteredRisks = [];
  var selectedRiskId = null;
  var filters = {
    risk_domain: '',
    applies_to: '',
    coverage_status: '',
    has_evidence: '',   // '' | 'yes' | 'no'
    failed_evidence: '' // '' | 'yes' | 'no'
  };

  function byId(id) { return document.getElementById(id); }

  function getEvidenceMap() {
    var map = {};
    (bundle.evidence || []).forEach(function (e) {
      map[e.evidence_id] = e;
    });
    return map;
  }

  function getReproduceByEvidence() {
    var map = {};
    (bundle.reproduce || []).forEach(function (r) {
      map[r.evidence_id] = r;
    });
    return map;
  }

  function getControlsMap() {
    var map = {};
    (bundle.controls || []).forEach(function (c) {
      map[c.control_id] = c;
    });
    return map;
  }

  function riskHasPresentEvidence(risk) {
    var evidenceMap = getEvidenceMap();
    return (risk.evidence_refs || []).some(function (eid) {
      var e = evidenceMap[eid];
      return e && e.status === 'present';
    });
  }

  function riskHasFailedOrMissingEvidence(risk) {
    var evidenceMap = getEvidenceMap();
    return (risk.evidence_refs || []).some(function (eid) {
      var e = evidenceMap[eid];
      if (!e) return false;
      if (e.status === 'missing') return true;
      var summary = e.summary || {};
      return Number(summary.failed) > 0;
    });
  }

  function applySearchAndFilters() {
    var q = (byId('search').value || '').toLowerCase().trim();
    var evidenceMap = getEvidenceMap();
    var controlsMap = getControlsMap();

    filteredRisks = (bundle.risks || []).filter(function (r) {
      if (filters.risk_domain && r.risk_domain !== filters.risk_domain) return false;
      if (filters.applies_to && !(r.applies_to || []).includes(filters.applies_to)) return false;
      if (filters.coverage_status && r.coverage_status !== filters.coverage_status) return false;
      if (filters.has_evidence === 'yes' && !riskHasPresentEvidence(r)) return false;
      if (filters.has_evidence === 'no' && riskHasPresentEvidence(r)) return false;
      if (filters.failed_evidence === 'yes' && !riskHasFailedOrMissingEvidence(r)) return false;
      if (filters.failed_evidence === 'no' && riskHasFailedOrMissingEvidence(r)) return false;

      if (q) {
        var text = [
          r.risk_id,
          r.name,
          (r.description || ''),
          (r.claimed_controls || []).map(function (cid) { return (controlsMap[cid] || {}).name || cid; }).join(' '),
          (r.evidence_refs || []).map(function (eid) {
            var e = evidenceMap[eid];
            return (e && e.label) ? e.label : eid;
          }).join(' ')
        ].join(' ').toLowerCase();
        if (text.indexOf(q) === -1) return false;
      }
      return true;
    });
  }

  function renderFilters() {
    var domains = {};
    var applies = {};
    var coverages = {};
    (bundle.risks || []).forEach(function (r) {
      if (r.risk_domain) domains[r.risk_domain] = true;
      (r.applies_to || []).forEach(function (a) { applies[a] = true; });
      if (r.coverage_status) coverages[r.coverage_status] = true;
    });

    var html = '<label>Risk domain <select id="filter_domain"><option value="">All</option>';
    Object.keys(domains).sort().forEach(function (d) {
      html += '<option value="' + escapeHtml(d) + '"' + (filters.risk_domain === d ? ' selected' : '') + '>' + escapeHtml(d) + '</option>';
    });
    html += '</select></label> ';

    html += '<label>Applies to <select id="filter_applies"><option value="">All</option>';
    Object.keys(applies).sort().forEach(function (a) {
      html += '<option value="' + escapeHtml(a) + '"' + (filters.applies_to === a ? ' selected' : '') + '>' + escapeHtml(a) + '</option>';
    });
    html += '</select></label> ';

    html += '<label>Coverage <select id="filter_coverage"><option value="">All</option>';
    Object.keys(coverages).sort().forEach(function (c) {
      html += '<option value="' + escapeHtml(c) + '"' + (filters.coverage_status === c ? ' selected' : '') + '>' + escapeHtml(c) + '</option>';
    });
    html += '</select></label> ';

    html += '<label>Has evidence <select id="filter_has_evidence"><option value="">All</option><option value="yes"' + (filters.has_evidence === 'yes' ? ' selected' : '') + '>Yes</option><option value="no"' + (filters.has_evidence === 'no' ? ' selected' : '') + '>No</option></select></label> ';
    html += '<label>Failed/missing evidence <select id="filter_failed"><option value="">All</option><option value="yes"' + (filters.failed_evidence === 'yes' ? ' selected' : '') + '>Yes</option><option value="no"' + (filters.failed_evidence === 'no' ? ' selected' : '') + '>No</option></select></label>';
    byId('filters').innerHTML = html;

    byId('filter_domain').onchange = function () { filters.risk_domain = this.value; applySearchAndFilters(); renderRiskList(); };
    byId('filter_applies').onchange = function () { filters.applies_to = this.value; applySearchAndFilters(); renderRiskList(); };
    byId('filter_coverage').onchange = function () { filters.coverage_status = this.value; applySearchAndFilters(); renderRiskList(); };
    byId('filter_has_evidence').onchange = function () { filters.has_evidence = this.value; applySearchAndFilters(); renderRiskList(); };
    byId('filter_failed').onchange = function () { filters.failed_evidence = this.value; applySearchAndFilters(); renderRiskList(); };
  }

  function escapeHtml(s) {
    if (s == null) return '';
    var div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function renderRiskList() {
    var html = '<ul class="risk-list">';
    filteredRisks.forEach(function (r) {
      var active = r.risk_id === selectedRiskId ? ' class="selected"' : '';
      html += '<li' + active + '><a href="#' + encodeURIComponent(r.risk_id) + '" data-risk-id="' + escapeHtml(r.risk_id) + '">' + escapeHtml(r.risk_id) + ': ' + escapeHtml(r.name) + '</a></li>';
    });
    html += '</ul>';
    byId('risk-list').innerHTML = html;
    byId('risk-list').querySelectorAll('a[data-risk-id]').forEach(function (a) {
      a.onclick = function (e) {
        e.preventDefault();
        selectedRiskId = a.getAttribute('data-risk-id');
        renderRiskList();
        renderRiskDetail();
      };
    });
  }

  function renderRiskDetail() {
    if (!selectedRiskId) {
      byId('risk-detail').innerHTML = '<p>Select a risk.</p>';
      return;
    }
    var risk = (bundle.risks || []).find(function (r) { return r.risk_id === selectedRiskId; });
    if (!risk) {
      byId('risk-detail').innerHTML = '<p>Risk not found.</p>';
      return;
    }
    var evidenceMap = getEvidenceMap();
    var reproduceMap = getReproduceByEvidence();
    var controlsMap = getControlsMap();

    var html = '<article class="risk-detail">';
    html += '<h2>' + escapeHtml(risk.risk_id) + ': ' + escapeHtml(risk.name) + '</h2>';
    html += '<p><strong>Domain</strong> ' + escapeHtml(risk.risk_domain) + ' &middot; <strong>Coverage</strong> ' + escapeHtml(risk.coverage_status) + ' &middot; <strong>Applies to</strong> ' + escapeHtml((risk.applies_to || []).join(', ')) + '</p>';
    if (risk.description) html += '<section><h3>Definition</h3><p>' + escapeHtml(risk.description) + '</p></section>';
    if (risk.typical_failure_mode) html += '<p><strong>Typical failure</strong> ' + escapeHtml(risk.typical_failure_mode) + '</p>';

    html += '<section><h3>Claimed controls</h3><ul>';
    (risk.claimed_controls || []).forEach(function (cid) {
      var c = controlsMap[cid];
      html += '<li>' + escapeHtml(c ? c.name : cid) + (c && c.description ? ' &mdash; ' + escapeHtml(c.description) : '') + '</li>';
    });
    html += '</ul></section>';

    html += '<section><h3>Evidence</h3>';
    (risk.evidence_refs || []).forEach(function (eid) {
      var e = evidenceMap[eid];
      var label = e ? (e.label || eid) : eid;
      var status = e ? (e.status || 'present') : 'unknown';
      var summary = e && e.summary ? ' (total: ' + (e.summary.total ?? '') + ', passed: ' + (e.summary.passed ?? '') + ', failed: ' + (e.summary.failed ?? '') + ')' : '';
      html += '<div class="evidence-block">';
      html += '<h4>' + escapeHtml(label) + ' <span class="status-' + escapeHtml(status) + '">' + escapeHtml(status) + '</span>' + escapeHtml(summary) + '</h4>';
      if (e && e.verification_summary) {
        var vs = e.verification_summary;
        html += '<p class="verification-summary"><strong>What was verified:</strong> ';
        var parts = [];
        parts.push('Manifest: ' + (vs.manifest_valid ? 'valid' : 'FAIL'));
        parts.push('Schema: ' + (vs.schema_valid ? 'valid' : 'FAIL'));
        parts.push('Hashchain: ' + (vs.hashchain_valid ? 'valid' : 'FAIL'));
        parts.push('Invariant trace: ' + (vs.invariant_trace_valid ? 'present' : 'missing'));
        var pf = vs.policy_fingerprints || {};
        parts.push('Policy fingerprints: rbac ' + (pf.rbac ? 'yes' : 'no') + ', coordination_identity ' + (pf.coordination_identity ? 'yes' : 'no') + ', memory ' + (pf.memory ? 'yes' : 'no') + ', tool_registry ' + (pf.tool_registry ? 'yes' : 'no'));
        html += escapeHtml(parts.join('; '));
        if ((vs.errors || []).length > 0) html += ' <span class="muted">Errors: ' + escapeHtml(vs.errors.slice(0, 2).join('; ')) + '</span>';
        html += '</p>';
      }
      if (e && e.reason_code_distribution && Object.keys(e.reason_code_distribution).length > 0) {
        html += '<p><strong>Why blocked (reason codes):</strong> ';
        var codes = Object.keys(e.reason_code_distribution).slice(0, 10);
        html += escapeHtml(codes.map(function (c) { return c + ' (' + e.reason_code_distribution[c] + ')'; }).join(', '));
        html += '</p>';
      }
      if (e && e.summary && e.summary.coord_metrics && e.summary.coord_metrics.length > 0) {
        var rows = e.summary.coord_metrics;
        var cols = ['sec.attack_success_rate', 'sec.stealth_success_rate', 'sec.time_to_attribution_steps', 'sec.blast_radius_proxy', 'robustness.resilience_score', 'perf.p95_tat', 'perf.throughput', 'safety.violations_total'];
        html += '<p><strong>Security + resilience (sample):</strong></p><table class="coord-metrics"><thead><tr>';
        cols.forEach(function (c) { html += '<th>' + escapeHtml(c) + '</th>'; });
        html += '</tr></thead><tbody>';
        rows.slice(0, 5).forEach(function (row) {
          html += '<tr>';
          cols.forEach(function (c) { html += '<td>' + (row[c] != null ? escapeHtml(String(row[c])) : '') + '</td>'; });
          html += '</tr>';
        });
        html += '</tbody></table>';
      }
      html += '</div>';
    });
    html += '</section>';

    html += '<section><h3>How to reproduce</h3>';
    (risk.evidence_refs || []).forEach(function (eid) {
      var repro = reproduceMap[eid];
      if (!repro) return;
      var label = repro.label || eid;
      html += '<h4>' + escapeHtml(label) + '</h4>';
      if ((repro.commands || []).length === 0) {
        html += '<p class="muted">No commands (evidence not yet collected or N/A).</p>';
      } else {
        html += '<pre class="commands">' + escapeHtml((repro.commands || []).join('\n')) + '</pre>';
      }
    });
    html += '</section></article>';
    byId('risk-detail').innerHTML = html;
  }

  function run(b) {
    bundle = b;
    global.currentBundle = b;
    applySearchAndFilters();
    byId('search').oninput = function () { applySearchAndFilters(); renderRiskList(); };
    byId('search').onkeyup = function () { applySearchAndFilters(); renderRiskList(); };
    renderFilters();
    renderRiskList();
    if (filteredRisks.length && !selectedRiskId) {
      selectedRiskId = filteredRisks[0].risk_id;
      renderRiskList();
    }
    renderRiskDetail();
  }

  function initFromHash() {
    var hash = (location.hash || '').slice(1);
    if (hash) selectedRiskId = decodeURIComponent(hash);
  }

  global.runRiskRegisterViewer = run;
  global.initRiskRegisterViewerHash = initFromHash;
  global.currentBundle = null;
})(typeof window !== 'undefined' ? window : this);
