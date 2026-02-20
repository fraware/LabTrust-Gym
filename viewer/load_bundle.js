/**
 * Risk Register Bundle loader for the viewer (offline-first, dataset-agnostic).
 *
 * Loading sources: (1) local JSON file, (2) file inside a ui-export zip,
 * (3) remote URL, (4) "Load latest release" (viewer-data/latest/latest.json).
 * Default: local file. Bundle schema: policy/schemas/risk_register_bundle.v0.1.schema.json.
 */

(function (global) {
  'use strict';

  const BUNDLE_FILENAME = 'RISK_REGISTER_BUNDLE.v0.1.json';

  /**
   * Load a RiskRegisterBundle from a source.
   * @param {string|File|{url: string}} source - URL string, File (from input), or { url: string }
   * @returns {Promise<object>} Parsed bundle (bundle_version, risks, controls, evidence, links, reproduce)
   */
  function loadBundle(source) {
    if (typeof source === 'string') {
      return loadFromUrl(source);
    }
    if (source instanceof File) {
      if (source.name.toLowerCase().endsWith('.zip')) {
        return loadFromZip(source);
      }
      return loadFromFile(source);
    }
    if (source && typeof source.url === 'string') {
      return loadFromUrl(source.url);
    }
    return Promise.reject(new Error('Invalid source: expected URL string, File, or { url }'));
  }

  function loadFromUrl(url) {
    return fetch(url)
      .then(function (res) {
        if (!res.ok) throw new Error('Fetch failed: ' + res.status);
        return res.json();
      })
      .then(validateMinimal);
  }

  function loadFromFile(file) {
    return new Promise(function (resolve, reject) {
      const r = new FileReader();
      r.onload = function () {
        try {
          const bundle = JSON.parse(r.result);
          resolve(validateMinimal(bundle));
        } catch (e) {
          reject(e);
        }
      };
      r.onerror = function () { reject(new Error('File read failed')); };
      r.readAsText(file, 'utf-8');
    });
  }

  function loadFromZip(file) {
    if (typeof global.JSZip === 'undefined') {
      return Promise.reject(new Error('JSZip required for zip support. Include script: https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js'));
    }
    return global.JSZip.loadAsync(file)
      .then(function (zip) {
        const entry = zip.file(BUNDLE_FILENAME) || zip.file('risk_register_bundle.v0.1.json');
        if (!entry) return Promise.reject(new Error('Zip does not contain ' + BUNDLE_FILENAME));
        return entry.async('string');
      })
      .then(function (text) {
        return validateMinimal(JSON.parse(text));
      });
  }

  function validateMinimal(bundle) {
    if (!bundle || typeof bundle !== 'object') throw new Error('Invalid bundle: not an object');
    if (bundle.bundle_version !== '0.1') throw new Error('Unsupported bundle_version: ' + bundle.bundle_version);
    if (!Array.isArray(bundle.risks) || bundle.risks.length < 1) throw new Error('Bundle must have at least one risk');
    if (!Array.isArray(bundle.controls)) bundle.controls = [];
    if (!Array.isArray(bundle.evidence)) bundle.evidence = [];
    if (!Array.isArray(bundle.reproduce)) bundle.reproduce = [];
    return bundle;
  }

  global.loadRiskRegisterBundle = loadBundle;
  global.RISK_REGISTER_BUNDLE_FILENAME = BUNDLE_FILENAME;
})(typeof window !== 'undefined' ? window : typeof self !== 'undefined' ? self : this);
