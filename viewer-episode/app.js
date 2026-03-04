/**
 * Episode Simulation Viewer — load, parse, merge, render.
 * Supports: (1) single episode_bundle.json, (2) episode log JSONL + optional METHOD_TRACE, coord_decisions.
 */
(function (global) {
  'use strict';

  var BUNDLE_VERSION = '0.1';

  var DEFAULT_LAB_DESIGN = {
    zones: [
      'Z_SRA_RECEPTION', 'Z_ACCESSIONING', 'Z_SORTING_LANES', 'Z_PREANALYTICS',
      'Z_CENTRIFUGE_BAY', 'Z_ALIQUOT_LABEL', 'Z_ANALYZER_HALL_A', 'Z_ANALYZER_HALL_B',
      'Z_QC_SUPERVISOR', 'Z_RESTRICTED_BIOHAZARD'
    ],
    zone_labels: {
      Z_SRA_RECEPTION: 'Reception', Z_ACCESSIONING: 'Accessioning',
      Z_SORTING_LANES: 'Sorting', Z_PREANALYTICS: 'Preanalytics',
      Z_CENTRIFUGE_BAY: 'Centrifuge', Z_ALIQUOT_LABEL: 'Aliquot',
      Z_ANALYZER_HALL_A: 'Analyzer A', Z_ANALYZER_HALL_B: 'Analyzer B',
      Z_QC_SUPERVISOR: 'QC', Z_RESTRICTED_BIOHAZARD: 'Restricted'
    },
    devices: [
      'DEV_CENTRIFUGE_BANK_01', 'DEV_ALIQUOTER_01', 'DEV_CHEM_A_01',
      'DEV_CHEM_B_01', 'DEV_HAEM_01', 'DEV_COAG_01'
    ],
    specimen_status_order: [
      'arrived_at_reception', 'accessioning', 'accepted', 'held',
      'rejected', 'in_transit', 'separated', 'unknown'
    ],
    device_zone: {
      DEV_CENTRIFUGE_BANK_01: 'Z_CENTRIFUGE_BAY', DEV_ALIQUOTER_01: 'Z_ALIQUOT_LABEL',
      DEV_CHEM_A_01: 'Z_ANALYZER_HALL_A', DEV_CHEM_B_01: 'Z_ANALYZER_HALL_B',
      DEV_HAEM_01: 'Z_ANALYZER_HALL_A', DEV_COAG_01: 'Z_ANALYZER_HALL_B'
    }
  };

  function parseJsonl(text) {
    var lines = (text || '').trim().split('\n');
    var out = [];
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (!line) continue;
      try {
        out.push(JSON.parse(line));
      } catch (e) { /* skip bad lines */ }
    }
    return out;
  }

  function parseEpisodeLog(text) {
    return parseJsonl(text);
  }

  function mergeToBundle(episodeEntries, methodTraceLines, coordDecisionsLines) {
    var lab_design = DEFAULT_LAB_DESIGN;
    var byTs = {};
    var agentsSet = {};
    for (var i = 0; i < episodeEntries.length; i++) {
      var e = episodeEntries[i];
      var ts = parseInt(e.t_s, 10) || 0;
      if (!byTs[ts]) byTs[ts] = [];
      byTs[ts].push(e);
      var aid = e.agent_id;
      if (aid) agentsSet[aid] = true;
    }
    var sortedTs = Object.keys(byTs).map(Number).sort(function (a, b) { return a - b; });
    var agents = Object.keys(agentsSet).sort();

    var methodByStep = {};
    if (methodTraceLines && methodTraceLines.length) {
      for (var j = 0; j < methodTraceLines.length; j++) {
        var t = methodTraceLines[j].t_step;
        if (t !== undefined) methodByStep[parseInt(t, 10)] = methodTraceLines[j];
      }
    }
    var coordByStep = {};
    if (coordDecisionsLines && coordDecisionsLines.length) {
      for (var k = 0; k < coordDecisionsLines.length; k++) {
        var rec = coordDecisionsLines[k];
        var step = rec.t_step !== undefined ? parseInt(rec.t_step, 10) : k;
        coordByStep[step] = rec;
      }
    }

    var steps = [];
    for (var si = 0; si < sortedTs.length; si++) {
      var t_s = sortedTs[si];
      var stepObj = { stepIndex: si, t_s: t_s, entries: byTs[t_s] };
      if (methodByStep[si]) stepObj.method_trace = methodByStep[si];
      if (coordByStep[si]) stepObj.coord_decision = coordByStep[si];
      steps.push(stepObj);
    }

    return {
      version: BUNDLE_VERSION,
      lab_design: lab_design,
      agents: agents,
      steps: steps
    };
  }

  function byAgent(entries) {
    var out = {};
    for (var i = 0; i < entries.length; i++) {
      out[entries[i].agent_id] = entries[i];
    }
    return out;
  }

  function getEntryForAgent(step, agentId) {
    if (!step || !step.entries) return null;
    for (var i = 0; i < step.entries.length; i++) {
      if (step.entries[i].agent_id === agentId) return step.entries[i];
    }
    return null;
  }

  function actionClass(actionType, status) {
    if (status === 'BLOCKED') return 'blocked';
    var a = (actionType || '').toLowerCase().replace(/-/g, '_');
    return 'action-' + a;
  }

  function renderPipelineStrip(bundle, container) {
    if (!container || !bundle || !bundle.lab_design) return;
    var zones = bundle.lab_design.zones || [];
    var labels = bundle.lab_design.zone_labels || {};
    container.innerHTML = '';
    for (var i = 0; i < zones.length; i++) {
      var z = zones[i];
      var pill = document.createElement('span');
      pill.className = 'zone-pill';
      pill.setAttribute('aria-label', z);
      pill.textContent = labels[z] || z;
      container.appendChild(pill);
    }
  }

  function renderGrid(bundle, container, filters, onCellClick) {
    if (!container || !bundle) return;
    var steps = bundle.steps || [];
    var agents = bundle.agents || [];
    var filterAgent = filters && filters.agent;
    var filterAction = filters && filters.action_type;
    var filterStatus = filters && filters.status;

    var table = document.createElement('div');
    table.className = 'step-grid';
    table.setAttribute('role', 'grid');
    table.setAttribute('aria-label', 'Step x Agent');
    table.style.gridTemplateColumns = '5rem repeat(' + agents.length + ', minmax(5.5rem, 1fr))';

    var headerRow = document.createElement('div');
    headerRow.className = 'grid-row';
    headerRow.style.display = 'contents';
    var corner = document.createElement('div');
    corner.className = 'cell header step-col';
    corner.setAttribute('data-header', 'true');
    corner.textContent = 'Step';
    headerRow.appendChild(corner);
    for (var a = 0; a < agents.length; a++) {
      var th = document.createElement('div');
      th.className = 'cell header';
      th.setAttribute('data-header', 'true');
      th.textContent = agents[a];
      headerRow.appendChild(th);
    }
    table.appendChild(headerRow);

    for (var s = 0; s < steps.length; s++) {
      var step = steps[s];
      var row = document.createElement('div');
      row.className = 'grid-row';
      row.style.display = 'contents';
      var stepCell = document.createElement('div');
      stepCell.className = 'cell header step-col';
      stepCell.textContent = step.stepIndex + ' (' + step.t_s + 's)';
      row.appendChild(stepCell);
      for (var ai = 0; ai < agents.length; ai++) {
        var agentId = agents[ai];
        var entry = getEntryForAgent(step, agentId);
        var cell = document.createElement('div');
        cell.className = 'cell';
        cell.setAttribute('data-step', step.stepIndex);
        cell.setAttribute('data-agent', agentId);
        if (entry) {
          var at = entry.action_type || 'NOOP';
          var st = entry.status || '';
          if (filterAgent && filterAgent !== agentId) { cell.textContent = '—'; } else
          if (filterAction && filterAction !== at) { cell.textContent = '—'; } else
          if (filterStatus && filterStatus !== st) { cell.textContent = '—'; } else {
            cell.innerHTML = '<span class="action-label">' + at + '</span>' + (st ? '<span class="status-label">' + st + '</span>' : '');
            cell.className = 'cell ' + actionClass(at, st);
          }
          cell.addEventListener('click', function (ev) {
            var stepIndex = parseInt(ev.currentTarget.getAttribute('data-step'), 10);
            var ag = ev.currentTarget.getAttribute('data-agent');
            if (onCellClick) onCellClick(stepIndex, ag);
          });
        } else {
          cell.textContent = '—';
        }
        row.appendChild(cell);
      }
      table.appendChild(row);
    }
    container.innerHTML = '';
    container.appendChild(table);
  }

  function actionsTouchingZone(step, zoneId, labDesign) {
    var deviceZone = (labDesign && labDesign.device_zone) || {};
    var out = [];
    var entries = step.entries || [];
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      var args = e.args || {};
      if (args.from_zone === zoneId || args.to_zone === zoneId) {
        out.push({ agent_id: e.agent_id, action_type: e.action_type });
      }
      var dev = args.device_id;
      if (dev && deviceZone[dev] === zoneId) {
        out.push({ agent_id: e.agent_id, action_type: e.action_type });
      }
    }
    return out;
  }

  function renderZoneView(bundle, container) {
    if (!container || !bundle) return;
    var steps = bundle.steps || [];
    var labDesign = bundle.lab_design || DEFAULT_LAB_DESIGN;
    var zones = labDesign.zones || [];
    var labels = labDesign.zone_labels || {};

    var table = document.createElement('table');
    table.className = 'zone-table';
    table.setAttribute('aria-label', 'Zone-centric');
    var thead = document.createElement('thead');
    var headerRow = document.createElement('tr');
    headerRow.innerHTML = '<th>Zone</th><th>Step</th><th>Actions</th>';
    thead.appendChild(headerRow);
    table.appendChild(thead);
    var tbody = document.createElement('tbody');
    for (var z = 0; z < zones.length; z++) {
      var zoneId = zones[z];
      var zoneLabel = labels[zoneId] || zoneId;
      for (var s = 0; s < steps.length; s++) {
        var step = steps[s];
        var touches = actionsTouchingZone(step, zoneId, labDesign);
        if (touches.length === 0 && s > 0) continue;
        var tr = document.createElement('tr');
        tr.innerHTML = '<td>' + zoneLabel + '</td><td>' + step.stepIndex + ' (' + step.t_s + 's)</td><td></td>';
        var td = tr.cells[2];
        for (var t = 0; t < touches.length; t++) {
          td.textContent += (t ? '; ' : '') + touches[t].agent_id + ' ' + touches[t].action_type;
        }
        if (touches.length === 0) td.textContent = '-';
        tbody.appendChild(tr);
      }
    }
    table.appendChild(tbody);
    container.innerHTML = '';
    container.appendChild(table);
  }

  function renderDetailPanel(stepIndex, agentId, bundle, container) {
    if (!container || !bundle) return;
    var steps = bundle.steps || [];
    var step = steps[stepIndex];
    if (!step) {
      container.innerHTML = '<p class="empty-state">Select a cell in the grid to view step and action details.</p>';
      return;
    }
    var entry = getEntryForAgent(step, agentId);
    var html = '<h4>Step ' + stepIndex + ' (t_s=' + step.t_s + ')';
    if (agentId) html += ' — ' + agentId;
    html += '</h4>';
    if (entry) {
      html += '<pre>' + JSON.stringify(entry, null, 2) + '</pre>';
    }
    if (step.method_trace) {
      html += '<h4>Method trace</h4><pre>' + JSON.stringify(step.method_trace, null, 2) + '</pre>';
    }
    if (step.coord_decision) {
      html += '<h4>Coord decision</h4><pre>' + JSON.stringify(step.coord_decision, null, 2) + '</pre>';
    }
    container.innerHTML = html;
  }

  function run(bundle) {
    if (!bundle || !bundle.steps) return;
    var pipelineEl = document.getElementById('pipeline-strip');
    var gridEl = document.getElementById('grid-view');
    var zoneEl = document.getElementById('zone-view');
    var detailEl = document.getElementById('detail-panel');
    var filtersEl = document.getElementById('filters');

    renderPipelineStrip(bundle, pipelineEl);

    var filters = { agent: '', action_type: '', status: '' };
    function redraw() {
      renderGrid(bundle, gridEl, filters, function (stepIndex, agentId) {
        renderDetailPanel(stepIndex, agentId, bundle, detailEl);
      });
      renderZoneView(bundle, zoneEl);
    }

    var agents = bundle.agents || [];
    var actionTypes = ['', 'NOOP', 'TICK', 'QUEUE_RUN', 'MOVE', 'OPEN_DOOR', 'START_RUN'];
    var statuses = ['', 'ACCEPTED', 'BLOCKED'];
    filtersEl.innerHTML = '';
    var labelAgent = document.createElement('label');
    labelAgent.textContent = 'Agent ';
    var selectAgent = document.createElement('select');
    selectAgent.id = 'filter-agent';
    selectAgent.innerHTML = '<option value="">All</option>';
    for (var a = 0; a < agents.length; a++) {
      selectAgent.innerHTML += '<option value="' + agents[a] + '">' + agents[a] + '</option>';
    }
    selectAgent.onchange = function () { filters.agent = this.value; redraw(); };
    labelAgent.appendChild(selectAgent);
    filtersEl.appendChild(labelAgent);
    var labelAction = document.createElement('label');
    labelAction.textContent = ' Action ';
    var selectAction = document.createElement('select');
    selectAction.id = 'filter-action';
    for (var at = 0; at < actionTypes.length; at++) {
      selectAction.innerHTML += '<option value="' + actionTypes[at] + '">' + (actionTypes[at] || 'All') + '</option>';
    }
    selectAction.onchange = function () { filters.action_type = this.value; redraw(); };
    labelAction.appendChild(selectAction);
    filtersEl.appendChild(labelAction);
    var labelStatus = document.createElement('label');
    labelStatus.textContent = ' Status ';
    var selectStatus = document.createElement('select');
    selectStatus.id = 'filter-status';
    for (var st = 0; st < statuses.length; st++) {
      selectStatus.innerHTML += '<option value="' + statuses[st] + '">' + (statuses[st] || 'All') + '</option>';
    }
    selectStatus.onchange = function () { filters.status = this.value; redraw(); };
    labelStatus.appendChild(selectStatus);
    filtersEl.appendChild(labelStatus);

    redraw();
    renderDetailPanel(null, null, bundle, detailEl);

    var tabs = document.querySelectorAll('.view-tabs .tab');
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].addEventListener('click', function () {
        var view = this.getAttribute('data-view');
        document.querySelectorAll('.view-tabs .tab').forEach(function (t) { t.classList.remove('active'); });
        this.classList.add('active');
        document.getElementById('grid-view').style.display = view === 'grid' ? 'block' : 'none';
        document.getElementById('zone-view').style.display = view === 'zone' ? 'block' : 'none';
      });
    }
  }

  global.EpisodeViewer = {
    run: run,
    parseEpisodeLog: parseEpisodeLog,
    mergeToBundle: mergeToBundle,
    DEFAULT_LAB_DESIGN: DEFAULT_LAB_DESIGN
  };
})(typeof window !== 'undefined' ? window : this);
