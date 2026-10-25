/* Browser-only visit history: stable IDs and content fingerprints, never source text. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PulseVisit = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const VERSION = 1;
  const MAX_IDS = 2000;
  const MAX_BYTES = 750000;
  const forbidden = new Set(['__proto__', 'prototype', 'constructor']);
  // Keep opaque namespaces (note:review), but never retain URLs as IDs or aliases.
  const urlId = /:\/\/|^(?:https?|ftp|file|data|javascript|blob|mailto|tel):/i;
  const validId = value => typeof value === 'string' && value.length <= 256 &&
    /^[A-Za-z0-9][A-Za-z0-9:_./~-]*$/.test(value) && !urlId.test(value) && !forbidden.has(value);

  function normalized(value) {
    if (typeof value === 'number') return Number.isFinite(value) ? String(value) : '';
    if (typeof value !== 'string') return '';
    return value.slice(0, 50000).normalize('NFKC').replace(/[\u2018\u2019]/g, "'")
      .replace(/[\u201c\u201d]/g, '"').replace(/[\u2010-\u2015\u2212]/g, '-')
      .replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function meaning(value) {
    return Array.isArray(value) ? value.slice(0, 100).map(normalized).filter(Boolean).sort() : normalized(value);
  }

  // A deterministic 64-bit attention fingerprint, not a cryptographic authenticator.
  function hash(value) {
    let a = 0x811c9dc5, b = 0x9e3779b9;
    for (let index = 0; index < value.length; index += 1) {
      const code = value.charCodeAt(index);
      a = Math.imul(a ^ code, 0x01000193);
      b = Math.imul(b ^ code, 0x85ebca6b);
    }
    return (a >>> 0).toString(16).padStart(8, '0') + (b >>> 0).toString(16).padStart(8, '0');
  }

  function fingerprint(item) {
    let title = normalized(item.title);
    const publisher = normalized(item.publisher_name || item.source_name);
    if (publisher && title.endsWith(' - ' + publisher)) title = title.slice(0, -(publisher.length + 3));
    const content = {title, summary: normalized(item.summary)};
    if (item.visitKind === 'curated' || item.inference_type === 'conditional_editorial_inference') {
      for (const field of ['observation', 'implication', 'beneficiaries', 'risks', 'counterevidence',
        'confirms', 'refutes', 'uncertainty', 'claim_type', 'event_date', 'event_start', 'event_end',
        'report_period', 'quote_as_of']) content[field] = meaning(item[field]);
      content.highlights = (Array.isArray(item.highlights) ? item.highlights : []).slice(0, 100)
        .filter(value => value && typeof value === 'object' && !Array.isArray(value))
        .map(value => JSON.stringify(['title', 'observation', 'implication', 'claim_type'].map(field => meaning(value[field]))))
        .sort();
    }
    return hash(JSON.stringify(content));
  }

  function records(items) {
    if (!Array.isArray(items)) return [];
    const result = [];
    const used = new Set();
    for (const item of items.slice(0, MAX_IDS)) {
      if (!item || typeof item !== 'object' || Array.isArray(item)) continue;
      try {
        if (!validId(item.id) || used.has(item.id)) continue;
        const aliases = [item.id];
        for (const field of ['article_ids', 'aliases']) {
          if (Array.isArray(item[field])) aliases.push(...item[field].slice(0, MAX_IDS).filter(validId));
        }
        used.add(item.id);
        result.push({id: item.id, aliases: [...new Set(aliases)], fingerprint: fingerprint(item)});
      } catch (_) { /* Malformed records never disable the rest of the page. */ }
    }
    return result;
  }

  function create(storage, key = 'pulse-visit-v1', now) {
    if (typeof key !== 'string' || !key || key.length > 256) key = 'pulse-visit-v1';
    const clock = () => {
      let value;
      try { value = typeof now === 'function' ? now() : now; } catch (_) { value = undefined; }
      const date = new Date(value === undefined ? Date.now() : value);
      return Number.isFinite(date.getTime()) ? date : new Date();
    };
    let available = Boolean(storage && typeof storage.getItem === 'function' && typeof storage.setItem === 'function');
    let baseline = new Map(), baselineAt = null;
    if (available) {
      let saved;
      try { saved = storage.getItem(key); }
      catch (_) { available = false; }
      try {
        if (available && saved !== null && saved !== undefined) {
          if (typeof saved !== 'string' || saved.length > MAX_BYTES) throw new Error('Invalid history size');
          const parsed = JSON.parse(saved);
          if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) ||
              Object.keys(parsed).some(field => !['version', 'at', 'entries'].includes(field)) ||
              parsed.version !== VERSION || typeof parsed.at !== 'string' ||
              !Number.isFinite(Date.parse(parsed.at)) || Date.parse(parsed.at) > clock().getTime() + 300000 ||
              !Array.isArray(parsed.entries) || parsed.entries.length > MAX_IDS) throw new Error('Invalid history');
          const checked = new Map();
          for (const entry of parsed.entries) {
            if (!Array.isArray(entry) || entry.length !== 2 || !validId(entry[0]) || checked.has(entry[0]) ||
                !(entry[1] === null || (typeof entry[1] === 'string' && /^[a-f0-9]{16}$/.test(entry[1])))) throw new Error('Invalid history entry');
            checked.set(entry[0], entry[1]);
          }
          baseline = checked;
          baselineAt = new Date(parsed.at).toISOString();
        }
      } catch (_) {
        // Corrupt values are replaceable without disabling a working storage API.
        baseline = new Map(); baselineAt = null;
      }
    }
    let pending = new Map(baseline);

    function compare(items) {
      const newIds = [], changedIds = [];
      if (baselineAt !== null) {
        for (const record of records(items)) {
          if (!record.aliases.some(id => baseline.has(id))) newIds.push(record.id);
          else if (baseline.has(record.id) && baseline.get(record.id) !== null && baseline.get(record.id) !== record.fingerprint) changedIds.push(record.id);
        }
      }
      return {firstVisit: baselineAt === null, storageAvailable: available, newIds, changedIds, baselineAt};
    }

    function commit(items) {
      const current = records(items);
      const touch = (id, value) => {
        pending.delete(id); pending.set(id, value);
        if (pending.size > MAX_IDS) pending.delete(pending.keys().next().value);
      };
      // An alias proves a related appearance was present, not what its unseen text said.
      for (const record of current) for (const id of record.aliases) {
        touch(id, pending.has(id) ? pending.get(id) : null);
      }
      // Prefer actual visible records over alias-only entries when enforcing the bound.
      for (const record of current) touch(record.id, record.fingerprint);
      while (pending.size > MAX_IDS) pending.delete(pending.keys().next().value);
      const at = clock().toISOString();
      const saved = JSON.stringify({version: VERSION, at, entries: [...pending]});
      let persisted = false;
      if (available) {
        try { storage.setItem(key, saved); persisted = true; }
        catch (_) { available = false; }
      }
      // The comparison baseline stays frozen for navigation and refresh within this visit.
      return {persisted, storageAvailable: available, baselineAt: at};
    }

    function clear() {
      baseline = new Map(); pending = new Map(); baselineAt = null;
      if (available) {
        try {
          if (typeof storage.removeItem !== 'function') throw new Error('Storage removal unavailable');
          storage.removeItem(key);
        } catch (_) { available = false; }
      }
      return {storageAvailable: available};
    }
    return {compare, commit, clear};
  }
  return {create, VERSION, MAX_IDS};
});
