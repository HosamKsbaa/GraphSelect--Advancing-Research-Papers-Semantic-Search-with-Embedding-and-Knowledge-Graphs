/**
 * Frontend unit & state-machine tests for code/frontend/index.html.
 *
 * Uses Node.js built-in test runner (`node --test`) and `node:vm` to execute the
 * inline script from `index.html` against a lightweight DOM harness with zero
 * external npm dependencies.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const INDEX_HTML_PATH = path.resolve(__dirname, '..', 'index.html');
const HTML_SOURCE = fs.readFileSync(INDEX_HTML_PATH, 'utf8');

function extractInlineScript(html) {
  const match = html.match(/<script>([\s\S]*?)<\/script>/);
  assert.ok(match, 'Expected inline <script> block in frontend/index.html');
  return `${match[1]}\n;globalThis.__getState = () => JSON.parse(JSON.stringify({ paperNodes, treeStructure, isSearching }));`;
}

class FakeClassList {
  constructor(initial = []) {
    this._set = new Set(initial);
  }
  add(...names) {
    for (const n of names) this._set.add(n);
  }
  remove(...names) {
    for (const n of names) this._set.delete(n);
  }
  contains(name) {
    return this._set.has(name);
  }
  toggle(name, force) {
    if (force !== undefined) {
      if (force) this._set.add(name);
      else this._set.delete(name);
      return Boolean(force);
    }
    if (this._set.has(name)) {
      this._set.delete(name);
      return false;
    }
    this._set.add(name);
    return true;
  }
}

class FakeElement {
  constructor(tagName = 'div', id = '', doc = null) {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.ownerDocument = doc;
    this.className = '';
    this.value = '';
    this.disabled = false;
    this.style = { display: '', width: '', background: '', borderColor: '', color: '' };
    this.classList = new FakeClassList();
    this.attributes = new Map();
    this.children = [];
    this.parentElement = null;
    this._innerHTML = '';
    this._textContent = '';
  }

  get innerHTML() {
    return this._innerHTML;
  }

  set innerHTML(val) {
    this._innerHTML = String(val ?? '');
    if (this._innerHTML === '') {
      this.children = [];
    }
  }

  get textContent() {
    return this._textContent;
  }

  set textContent(val) {
    const raw = String(val ?? '');
    this._textContent = raw;
    this._innerHTML = raw
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  setAttribute(k, v) {
    this.attributes.set(k, String(v));
  }

  getAttribute(k) {
    return this.attributes.get(k) ?? null;
  }

  appendChild(child) {
    child.parentElement = this;
    child.ownerDocument = this.ownerDocument;
    if (!this.children.includes(child)) {
      this.children.push(child);
    }
    if (child.id && this.ownerDocument) {
      this.ownerDocument.registerElement(child);
    }
    return child;
  }

  remove() {
    if (this.parentElement) {
      this.parentElement.children = this.parentElement.children.filter(c => c !== this);
    }
  }

  closest(selector) {
    if (selector === '.q-row') {
      let cur = this;
      while (cur) {
        if (cur.className === 'q-row') return cur;
        cur = cur.parentElement;
      }
    }
    return null;
  }

  querySelector(selector) {
    if (selector === ':scope > ul') {
      return this.children.find(c => c.tagName === 'UL') ?? null;
    }
    if (selector === 'input') {
      let input = this.children.find(c => c.tagName === 'INPUT');
      if (!input) {
        input = new FakeElement('input', '', this.ownerDocument);
        input.className = 'q-input';
        this.appendChild(input);
      }
      return input;
    }
    return new FakeElement('span', '', this.ownerDocument);
  }

  focus() {}
  scrollIntoView() {}
}

function createFrontendRuntime({ fetchImpl } = {}) {
  const elementsById = new Map();
  const phaseIconEl = new FakeElement('span');

  const doc = {
    cookie: '',
    registerElement(el) {
      if (el.id) elementsById.set(el.id, el);
    },
    getElementById(id) {
      if (!elementsById.has(id)) {
        // Elements created dynamically by upsertNode ('tree-W...') must only exist after appendChild
        if (id.startsWith('tree-') || id.startsWith('detail-')) {
          return null;
        }
        const el = new FakeElement('div', id, doc);
        elementsById.set(id, el);
      }
      return elementsById.get(id);
    },
    createElement(tag) {
      return new FakeElement(tag, '', doc);
    },
    querySelector(selector) {
      if (selector === '.progress-status .phase-icon') return phaseIconEl;
      return new FakeElement('div', '', doc);
    },
    querySelectorAll(selector) {
      if (selector === '.q-input') {
        const list = doc.getElementById('questionsList');
        return list.children.map(row => row.querySelector('input'));
      }
      return [];
    },
  };

  // Seed initial question input row matching index.html
  const questionsList = doc.getElementById('questionsList');
  const initialRow = new FakeElement('div', '', doc);
  initialRow.className = 'q-row';
  const initialInput = new FakeElement('input', '', doc);
  initialInput.className = 'q-input';
  initialInput.value = 'How does self-attention replace recurrence?';
  initialRow.appendChild(initialInput);
  questionsList.appendChild(initialRow);

  // Default form inputs
  doc.getElementById('seedDoi').value = '10.48550/arXiv.1706.03762';
  doc.getElementById('threshold').value = '0.3';
  doc.getElementById('maxDepth').value = '3';
  doc.getElementById('maxNeighbors').value = '25';
  doc.getElementById('guideModal').style.display = 'none';

  const defaultFetch = async url => {
    if (url === '/api/health') {
      return { ok: true, status: 200, json: async () => ({ status: 'healthy' }) };
    }
    throw new Error(`Unexpected fetch URL: ${url}`);
  };

  const context = vm.createContext({
    document: doc,
    window: { location: { reload() {} } },
    navigator: { clipboard: { writeText: async () => {} } },
    fetch: fetchImpl || defaultFetch,
    TextDecoder,
    console: { log() {}, warn() {}, error() {} },
    setInterval: () => 1,
    clearInterval: () => {},
    setTimeout: () => 1,
    Date,
    Math,
    JSON,
     parseFloat,
    parseInt,
    encodeURIComponent,
    decodeURIComponent,
  });

  vm.runInContext(extractInlineScript(HTML_SOURCE), context);
  return { context, doc, phaseIconEl };
}

test('index.html contains all required DOM ids and API endpoints', () => {
  const requiredIds = [
    'statusBadge',
    'statusText',
    'geminiApiKey',
    'openalexEmail',
    'seedDoi',
    'questionsList',
    'btnAddQ',
    'threshold',
    'maxDepth',
    'maxNeighbors',
    'btnSearch',
    'btnStop',
    'errorBox',
    'progressPanel',
    'progressBar',
    'progressMessage',
    'progressStats',
    'resultsCard',
    'resultsStats',
    'treeRoot',
  ];

  for (const id of requiredIds) {
    assert.match(
      HTML_SOURCE,
      new RegExp(`id=["']${id}["']`),
      `Missing required DOM element id="${id}" in frontend/index.html`,
    );
  }
  assert.match(HTML_SOURCE, /\/api\/health/);
  assert.match(HTML_SOURCE, /\/api\/search\/stream/);
});

test('question list enforces minimum 1 and maximum 6 questions', () => {
  const { context, doc } = createFrontendRuntime();
  const list = doc.getElementById('questionsList');
  const addBtn = doc.getElementById('btnAddQ');

  assert.equal(list.children.length, 1);

  // Cannot remove the last remaining question
  const removeBtn = new FakeElement('button', '', doc);
  list.children[0].appendChild(removeBtn);
  context.removeQuestion(removeBtn);
  assert.equal(list.children.length, 1);

  // Can add up to 6 questions total
  for (let i = 0; i < 8; i++) {
    context.addQuestion();
  }
  assert.equal(list.children.length, 6);
  assert.equal(addBtn.style.display, 'none');

  // Removing one question restores the Add button
  const secondRowBtn = new FakeElement('button', '', doc);
  list.children[1].appendChild(secondRowBtn);
  context.removeQuestion(secondRowBtn);
  assert.equal(list.children.length, 5);
  assert.equal(addBtn.style.display, 'inline-flex');
});

test('utilities escape HTML XSS payloads, format percentages, and extract OpenAlex IDs', () => {
  const { context } = createFrontendRuntime();

  assert.equal(
    context.esc('<img src=x onerror="alert(1)"> & more'),
    '&lt;img src=x onerror="alert(1)"&gt; &amp; more',
  );
  assert.equal(context.esc(''), '');
  assert.equal(context.pct(0.8426), '84.3%');
  assert.equal(context.extractId('https://openalex.org/W2626778328'), 'W2626778328');
  assert.equal(context.extractId('W12345'), 'W12345');
});

test('SSE events build the citation tree state machine from seed to ranked results', () => {
  const { context, doc, phaseIconEl } = createFrontendRuntime();

  // 1. Progress event
  context.handleSSEEvent(
    'progress',
    JSON.stringify({
      status: 'exploring_level',
      message: 'Exploring citation depth 1',
      current_depth: 1,
      max_depth: 2,
      current_level_progress: 2,
      current_level_total: 4,
      relevant_papers_found: 1,
    }),
  );
  assert.equal(doc.getElementById('progressMessage').textContent, 'Exploring citation depth 1');
  assert.equal(phaseIconEl.textContent, '🔍');
  assert.equal(doc.getElementById('progressBar').style.width, '50%');

  // 2. Seed paper found at depth 0
  context.handleSSEEvent(
    'paper_found',
    JSON.stringify({
      id: 'W2626778328',
      title: 'Attention Is All You Need',
      depth: 0,
      similarity: 0.91,
      doi: '10.48550/arXiv.1706.03762',
    }),
  );

  // 3. Child paper found at depth 1 and skipped paper at depth 1
  context.handleSSEEvent(
    'paper_found',
    JSON.stringify({
      id: 'W2963403868',
      title: 'BERT: Pre-training of Deep Bidirectional Transformers',
      depth: 1,
      parent_id: 'W2626778328',
      similarity: 0.78,
    }),
  );
  context.handleSSEEvent(
    'paper_skipped',
    JSON.stringify({
      id: 'W1111111111',
      title: 'Unrelated Chemistry Paper',
      depth: 1,
      parent_id: 'W2626778328',
      reason: 'Below similarity threshold',
    }),
  );

  // 4. Final ranked results event updates ranks and stats
  context.handleSSEEvent(
    'results',
    JSON.stringify({
      total_results: 2,
      total_papers_processed: 3,
      total_api_calls: 4,
      results: [
        {
          work: {
            id: 'https://openalex.org/W2626778328',
            display_name: 'Attention Is All You Need',
            publication_year: 2017,
            doi: 'https://doi.org/10.48550/arXiv.1706.03762',
            authorships: [{ author: { display_name: 'Ashish Vaswani' } }],
          },
          depth: 0,
          max_similarity_score: 0.91,
          pagerank_score: 0.65,
          combined_score: 0.832,
          abstract_text: 'The dominant sequence transduction models...',
        },
        {
          work: {
            id: 'https://openalex.org/W2963403868',
            display_name: 'BERT: Pre-training of Deep Bidirectional Transformers',
            publication_year: 2019,
            doi: '10.18653/v1/N19-1423',
            authorships: [{ author: { display_name: 'Jacob Devlin' } }],
          },
          depth: 1,
          max_similarity_score: 0.78,
          pagerank_score: 0.35,
          combined_score: 0.651,
          abstract_text: 'We introduce a new language representation model...',
        },
      ],
    }),
  );

  const state = context.__getState();
  assert.equal(state.paperNodes.W2626778328.rank, 1);
  assert.equal(state.paperNodes.W2626778328.status, 'ranked');
  assert.equal(state.paperNodes.W2963403868.rank, 2);
  assert.equal(state.paperNodes.W1111111111.status, 'skipped');
  assert.deepEqual(state.treeStructure[0], ['W2626778328']);
  assert.deepEqual(state.treeStructure[1], ['W2963403868', 'W1111111111']);
  assert.match(doc.getElementById('resultsStats').innerHTML, /2<\/strong>&nbsp;papers found/);

  // Malformed SSE payload does not throw or corrupt state
  context.handleSSEEvent('progress', '{not-valid-json');
  assert.equal(context.__getState().paperNodes.W2626778328.rank, 1);
});

test('runSearch validates missing seed DOI and empty questions before calling fetch', async () => {
  let fetchCalled = false;
  const { context, doc } = createFrontendRuntime({
    fetchImpl: async url => {
      if (url === '/api/health') return { ok: true, status: 200 };
      fetchCalled = true;
      throw new Error('Should not call /api/search/stream when inputs are invalid');
    },
  });

  // Missing seed DOI
  doc.getElementById('seedDoi').value = '   ';
  await context.runSearch();
  assert.equal(fetchCalled, false);
  assert.equal(doc.getElementById('errorBox').textContent, 'Please enter a seed DOI.');
  assert.equal(doc.getElementById('errorBox').style.display, 'block');

  // Seed DOI present, but all research questions blank
  doc.getElementById('seedDoi').value = '10.48550/arXiv.1706.03762';
  doc.querySelectorAll('.q-input')[0].value = '   ';
  await context.runSearch();
  assert.equal(fetchCalled, false);
  assert.equal(
    doc.getElementById('errorBox').textContent,
    'Add at least one research question.',
  );
});
