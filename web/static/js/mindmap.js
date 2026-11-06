/* 心智圖：歷史資料、手繪視覺與閱讀互動。 */
const MIND_MAP_HISTORY_LIMIT = 90;
const mindMapHistoryBySession = new Map();
const mindMapLatestBySession = new Map();
const mindMapPreviewIndexBySession = new Map();

function cloneJsonSafe(value) {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

function hasMindMapChildren(mind) {
  return getVisibleMindMapChildren(mind).length > 0;
}

function mindMapBranchLeaves(branch) {
  const leaves = Array.isArray(branch?.children) && branch.children.length
    ? branch.children.filter(Boolean)
    : (branch?.speaker || branch?.person_slug ? [branch] : []);
  return leaves.filter((leaf) => {
    const text = String(leaf.quote || leaf.quote_full || leaf.label || '').trim();
    const speaker = String(leaf.speaker || '').trim().toLowerCase();
    if (!text || ['系統', 'system'].includes(speaker)) return false;
    return !/暫無足夠觀點|待更多討論|等待更多觀點|討論開始後會更新|尚無重點|等待名人發言/.test(text);
  });
}

function getVisibleMindMapChildren(mind) {
  return (Array.isArray(mind?.children) ? mind.children : [])
    .filter((branch) => branch && mindMapBranchLeaves(branch).length > 0);
}

function cleanMindMap(mind) {
  return { ...(mind || {}), children: getVisibleMindMapChildren(mind) };
}

function mindMapLeafKey(leaf) {
  return `${leaf.person_slug || leaf.speaker || ''}|${String(leaf.quote || leaf.quote_full || leaf.label || '').trim()}`;
}

function mindMapBranchMap(mind) {
  return new Map(getVisibleMindMapChildren(mind).map((branch) => [
    String(branch.label || '延伸議題').trim(),
    new Set(mindMapBranchLeaves(branch).map(mindMapLeafKey)),
  ]));
}

function getMindMapHistory(sessionId) {
  if (!sessionId) return [];
  if (!mindMapHistoryBySession.has(sessionId)) {
    mindMapHistoryBySession.set(sessionId, []);
  }
  return mindMapHistoryBySession.get(sessionId);
}

function setMindMapPreviewIndex(sessionId, idx) {
  if (!sessionId) return;
  if (idx == null || idx < 0) {
    mindMapPreviewIndexBySession.delete(sessionId);
    return;
  }
  mindMapPreviewIndexBySession.set(sessionId, idx);
}

function getMindMapPreviewIndex(sessionId) {
  if (!sessionId) return null;
  const idx = mindMapPreviewIndexBySession.get(sessionId);
  return Number.isInteger(idx) ? idx : null;
}

function mindMapLeafCount(mind) {
  const branches = getVisibleMindMapChildren(mind);
  let leaves = 0;
  for (const b of branches) {
    leaves += mindMapBranchLeaves(b).length;
  }
  return leaves;
}

function upsertMindMapHistory(sessionId, mind, messageCount = 0) {
  if (!sessionId || !hasMindMapChildren(mind)) return;
  const history = getMindMapHistory(sessionId);
  const snapshot = {
    message_count: Number(messageCount) || 0,
    branch_count: Array.isArray(mind.children) ? mind.children.length : 0,
    leaf_count: mindMapLeafCount(mind),
    mind_map: cloneJsonSafe(mind),
  };

  const sameMsgIdx =
    snapshot.message_count > 0
      ? history.findIndex((h) => (h.message_count || 0) === snapshot.message_count)
      : -1;
  if (sameMsgIdx >= 0) {
    history[sameMsgIdx] = snapshot;
  } else {
    history.push(snapshot);
  }

  if (history.length > MIND_MAP_HISTORY_LIMIT) {
    history.splice(0, history.length - MIND_MAP_HISTORY_LIMIT);
  }
}

function getActiveMindMapForSession(sessionId, fallbackMind = {}) {
  const history = getMindMapHistory(sessionId);
  const previewIdx = getMindMapPreviewIndex(sessionId);
  if (
    previewIdx != null &&
    previewIdx >= 0 &&
    previewIdx < history.length &&
    hasMindMapChildren(history[previewIdx]?.mind_map)
  ) {
    return history[previewIdx].mind_map;
  }
  return mindMapLatestBySession.get(sessionId) || fallbackMind;
}


/* 手繪心智圖：DOM 卡片保留完整文字，SVG 只負責連線。 */
const MIND_MAP_BRANCH_THEMES = [
  { ink: '#456fae', soft: '#edf3ff', line: '#91addb' },
  { ink: '#3f806a', soft: '#edf6f1', line: '#91c0aa' },
  { ink: '#a66e2e', soft: '#fff5e7', line: '#dfb879' },
  { ink: '#a25f7a', soft: '#fbf0f4', line: '#d7a5b8' },
  { ink: '#765fa4', soft: '#f3effa', line: '#bba9d7' },
  { ink: '#397984', soft: '#edf6f7', line: '#91bdc3' },
];

const mindMapCanvases = new Set();
let mindMapLinkFrame = 0;
let mindMapZoomResizeListening = false;
const mindMapResizeObserver = typeof ResizeObserver === 'function'
  ? new ResizeObserver(entries => {
      for (const entry of entries) fitMindMapCardText(entry.target);
      scheduleMindMapLinks();
    }) : null;

function fitMindMapText(element, minSize = 9) {
  if (!element?.isConnected || !element.clientHeight) return;
  element.style.removeProperty('font-size');
  const baseSize = parseFloat(getComputedStyle(element).fontSize) || 13;
  let size = baseSize;
  while (size > minSize && element.scrollHeight > element.clientHeight + 1) {
    size = Math.max(minSize, size - 0.5);
    element.style.fontSize = `${size}px`;
  }
}

function fitMindMapCardText(canvas) {
  canvas.querySelectorAll('.mind-map-paper-title, .mind-map-paper-label, .mind-map-paper-quote').forEach(element => {
    fitMindMapText(element, element.classList.contains('mind-map-paper-quote') ? 8 : 9);
  });
}

function layoutMindMapRadial(canvas) {
  const grid = canvas?.querySelector('.mind-map-paper-grid');
  const rootWrap = grid?.querySelector('.mind-map-paper-root-wrap');
  const root = rootWrap?.querySelector('.mind-map-paper-root');
  if (!grid || !rootWrap || !root) return;

  const branches = [...grid.querySelectorAll(':scope > .mind-map-paper-branch')];
  const viewportWidth = canvas.parentElement?.clientWidth || 760;
  const baseWidth = Math.max(760, viewportWidth - 36);
  const leafCardWidth = Math.min(220, Math.max(170, (baseWidth - 320) / 2));
  const leafColumnGap = 14;
  canvas.style.width = `${baseWidth}px`;
  canvas.style.height = 'auto';
  canvas.style.minHeight = '0';
  grid.style.width = `${baseWidth}px`;
  grid.style.height = 'auto';

  branches.forEach((branch, index) => {
    const side = index % 2 === 0 ? 'left' : 'right';
    const leafCount = branch.querySelectorAll('.mind-map-paper-leaf').length;
    const leafColumns = Math.min(2, Math.max(1, leafCount));
    const branchWidth = leafColumns * leafCardWidth + (leafColumns - 1) * leafColumnGap;
    branch.dataset.flow = 'down';
    branch.dataset.contentsLayout = leafColumns > 1 ? 'spread' : 'stack';
    branch.dataset.leafColumns = String(leafColumns);
    branch.dataset.leafCount = String(leafCount);
    branch.dataset.centerLastLeaf = leafColumns > 1 && leafCount % 2 === 1 ? 'true' : 'false';
    branch.dataset.side = side;
    branch.style.setProperty('--branch-card-width', `${branchWidth}px`);
    branch.style.setProperty('--mind-map-leaf-columns', String(leafColumns));
    branch.style.width = `${branchWidth}px`;
    branch.style.left = '0px';
    branch.style.top = '0px';
  });
  const rootWidth = root.offsetWidth || 224;
  const rootHeight = root.offsetHeight || 94;
  rootWrap.style.width = `${rootWidth}px`;
  rootWrap.style.height = `${rootHeight}px`;

  if (!branches.length) {
    const mapHeight = 420;
    canvas.style.height = `${mapHeight}px`;
    grid.style.height = `${mapHeight}px`;
    rootWrap.style.left = `${baseWidth / 2}px`;
    rootWrap.style.top = `${mapHeight / 2}px`;
    return;
  }

  const branchHeights = branches.map(branch => branch.offsetHeight || 120);
  const gapX = 30;
  const gapY = 36;
  const padding = 26;
  let topIndices;
  let bottomIndices;
  if (branches.length <= 4) {
    const topCount = Math.ceil(branches.length / 2);
    topIndices = branches.map((_, index) => index).slice(0, topCount);
    bottomIndices = branches.map((_, index) => index).slice(topCount);
  } else {
    topIndices = [0, 4, 1].filter(index => index < branches.length);
    bottomIndices = [2, 5, 3].filter(index => index < branches.length);
    for (let index = 6; index < branches.length; index += 1) {
      (topIndices.length <= bottomIndices.length ? topIndices : bottomIndices).push(index);
    }
  }
  // 各組可能是單欄或雙欄，依整排實際寬度累加位置，避免寬度不同時互相覆蓋。
  const branchWidths = branches.map(branch => branch.offsetWidth || leafCardWidth);
  const rowCenters = new Map();
  for (const row of [topIndices, bottomIndices]) {
    const rowGap = row.length === 2 ? rootWidth + 2 * gapX : gapX;
    const rowWidth = row.reduce((sum, index) => sum + branchWidths[index], 0)
      + Math.max(0, row.length - 1) * rowGap;
    let cursor = -rowWidth / 2;
    for (const index of row) {
      rowCenters.set(index, cursor + branchWidths[index] / 2);
      cursor += branchWidths[index] + rowGap;
    }
  }
  const placements = branches.map((branch, index) => {
    const isTop = topIndices.includes(index);
    const vertical = isTop ? 'top' : 'bottom';
    const width = branchWidths[index];
    const height = branchHeights[index];
    const ySign = vertical === 'top' ? -1 : 1;
    const x = rowCenters.get(index);
    const y = ySign * (rootHeight / 2 + gapY + height / 2);
    const side = x < 0 ? 'left' : 'right';
    branch.dataset.positionRow = vertical;
    branch.dataset.flow = vertical === 'top' ? 'up' : 'down';
    return { branch, side, x, y, width, height };
  });

  const extentX = Math.max(rootWidth / 2, ...placements.map(rect => Math.abs(rect.x) + rect.width / 2));
  const extentY = Math.max(rootHeight / 2, ...placements.map(rect => Math.abs(rect.y) + rect.height / 2));
  const mapWidth = Math.max(baseWidth, Math.ceil(2 * (extentX + padding)));
  const mapHeight = Math.max(420, Math.ceil(2 * (extentY + padding)));
  const centerX = mapWidth / 2;
  const centerY = mapHeight / 2;

  canvas.style.width = `${mapWidth}px`;
  canvas.style.height = `${mapHeight}px`;
  grid.style.width = `${mapWidth}px`;
  grid.style.height = `${mapHeight}px`;
  rootWrap.style.left = `${centerX}px`;
  rootWrap.style.top = `${centerY}px`;

  placements.forEach(({ branch, side, x, y, width, height }) => {
    branch.dataset.side = side;
    branch.style.left = `${centerX + x - width / 2}px`;
    branch.style.top = `${centerY + y - height / 2}px`;
  });
}

function setMindMapZoom(viewport, scale, panX = 0, panY = 0, userInitiated = true) {
  const paper = viewport?.querySelector('.mind-map-paper');
  if (!paper) return;
  const nextScale = Math.max(0.18, Math.min(2.2, scale));
  viewport.dataset.mapScale = String(nextScale);
  viewport.dataset.mapPanX = String(panX);
  viewport.dataset.mapPanY = String(panY);
  if (userInitiated) viewport.dataset.mapUserZoomed = 'true';
  paper.style.setProperty('--mind-map-scale', String(nextScale));
  paper.style.setProperty('--mind-map-pan-x', `${panX}px`);
  paper.style.setProperty('--mind-map-pan-y', `${panY}px`);
  const container = viewport.closest('.mind-map-host') || viewport.closest('.mind-map-expanded-dialog');
  const label = container?.querySelector('.mind-map-zoom-level');
  const percentage = `${Math.round(nextScale * 100)}%`;
  if (label && label.textContent !== percentage) label.textContent = percentage;
}

function fitMindMapZoom(viewport) {
  const paper = viewport?.querySelector('.mind-map-paper');
  if (!paper || !viewport.clientWidth || !viewport.clientHeight) return;
  const width = paper.offsetWidth;
  const height = paper.offsetHeight;
  if (!width || !height) return;
  const scale = Math.min(
    1,
    Math.max(0.18, (viewport.clientWidth - 32) / width),
    Math.max(0.18, (viewport.clientHeight - 32) / height)
  );
  viewport.dataset.mapUserZoomed = 'false';
  setMindMapZoom(viewport, scale, 0, 0, false);
}

function zoomMindMapBy(viewport, factor) {
  const scale = Number(viewport?.dataset.mapScale) || 1;
  setMindMapZoom(
    viewport,
    scale * factor,
    Number(viewport.dataset.mapPanX) || 0,
    Number(viewport.dataset.mapPanY) || 0
  );
}

function appendMindMapZoomControls(parent, viewport, trailingButton = null) {
  const controls = mindMapElement('div', 'mind-map-zoom-controls');
  const makeButton = (label, title, action, className = '') => {
    const button = mindMapElement('button', `mind-map-zoom-button ${className}`.trim(), label);
    button.type = 'button';
    button.title = title;
    button.setAttribute('aria-label', title);
    button.addEventListener('click', action);
    controls.appendChild(button);
    return button;
  };
  makeButton('−', '縮小心智圖', () => zoomMindMapBy(viewport, 1 / 1.1));
  controls.appendChild(mindMapElement('span', 'mind-map-zoom-level', '100%'));
  makeButton('+', '放大心智圖', () => zoomMindMapBy(viewport, 1.1));
  makeButton('適合', '縮放至完整心智圖', () => fitMindMapZoom(viewport), 'mind-map-zoom-fit');
  if (trailingButton) controls.appendChild(trailingButton);
  parent.appendChild(controls);
}

function initMindMapZoomViewport(viewport) {
  if (!viewport || viewport.dataset.zoomReady === 'true') return;
  viewport.dataset.zoomReady = 'true';
  viewport.classList.add('mind-map-zoom-viewport');
  viewport.dataset.mapScale = '1';
  viewport.dataset.mapPanX = '0';
  viewport.dataset.mapPanY = '0';
  viewport.dataset.mapUserZoomed = 'false';
  viewport.addEventListener('wheel', event => {
    event.preventDefault();
    const delta = Math.max(-160, Math.min(160, event.deltaY));
    zoomMindMapBy(viewport, Math.exp(-delta * 0.00035));
  }, { passive: false });

  let drag = null;
  viewport.addEventListener('pointerdown', event => {
    if (event.button !== 0 || event.target.closest('button')) return;
    drag = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      panX: Number(viewport.dataset.mapPanX) || 0,
      panY: Number(viewport.dataset.mapPanY) || 0,
    };
    viewport.setPointerCapture(event.pointerId);
    viewport.classList.add('is-panning');
  });
  viewport.addEventListener('pointermove', event => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    setMindMapZoom(
      viewport,
      Number(viewport.dataset.mapScale) || 1,
      drag.panX + event.clientX - drag.x,
      drag.panY + event.clientY - drag.y
    );
  });
  const stopDrag = event => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    drag = null;
    viewport.classList.remove('is-panning');
  };
  viewport.addEventListener('pointerup', stopDrag);
  viewport.addEventListener('pointercancel', stopDrag);
  if (!mindMapZoomResizeListening) {
    window.addEventListener('resize', () => {
      document.querySelectorAll('.mind-map-zoom-viewport').forEach(node => {
        const canvas = node.querySelector('.mind-map-paper');
        if (canvas) layoutMindMapRadial(canvas);
        if (node.dataset.mapUserZoomed !== 'true') fitMindMapZoom(node);
      });
    });
    mindMapZoomResizeListening = true;
  }
}

function refreshMindMapZoom(viewport) {
  if (!viewport) return;
  if (viewport.dataset.mapUserZoomed !== 'true') {
    requestAnimationFrame(() => fitMindMapZoom(viewport));
    return;
  }
  const paper = viewport.querySelector('.mind-map-paper');
  if (paper) {
    paper.style.setProperty('--mind-map-scale', viewport.dataset.mapScale || '1');
    paper.style.setProperty('--mind-map-pan-x', `${viewport.dataset.mapPanX || 0}px`);
    paper.style.setProperty('--mind-map-pan-y', `${viewport.dataset.mapPanY || 0}px`);
  }
}

function scheduleMindMapLinks() {
  if (mindMapLinkFrame) return;
  mindMapLinkFrame = requestAnimationFrame(() => {
    mindMapLinkFrame = 0;
    for (const canvas of mindMapCanvases) {
      if (!canvas.isConnected) {
        mindMapResizeObserver?.unobserve(canvas);
        mindMapCanvases.delete(canvas);
        continue;
      }
      drawMindMapLinks(canvas);
    }
  });
}

function drawMindMapLinks(canvas) {
  const svg = canvas.querySelector('.mind-map-thread-layer');
  const root = canvas.querySelector('.mind-map-paper-root');
  if (!svg || !root || !canvas.clientWidth) return;
  const origin = canvas.getBoundingClientRect();
  const r = root.getBoundingClientRect();
  const scale = parseFloat(getComputedStyle(canvas).getPropertyValue('--mind-map-scale')) || 1;
  const rootX = (r.left + r.width / 2 - origin.left) / scale;
  const rootY = (r.top + r.height / 2 - origin.top) / scale;
  const height = canvas.scrollHeight;
  svg.setAttribute('viewBox', `0 0 ${canvas.clientWidth} ${height}`);
  svg.style.height = `${height}px`;
  const existingPaths = new Map(
    [...svg.querySelectorAll('path[data-link-key]')]
      .map(path => [path.dataset.linkKey, path])
  );
  svg.querySelectorAll('path:not([data-link-key])').forEach(path => path.remove());
  const wantedPaths = new Set();
  const upsertPath = (key, data, color, { shouldAnimate = false, delay = '0ms', kind = 'topic' } = {}) => {
    wantedPaths.add(key);
    const path = existingPaths.get(key) || document.createElementNS('http://www.w3.org/2000/svg', 'path');
    const isNewPath = !existingPaths.has(key);
    path.dataset.linkKey = key;
    path.dataset.linkKind = kind;
    path.setAttribute('d', data);
    path.setAttribute('stroke', color);
    if (isNewPath && shouldAnimate && typeof path.getTotalLength === 'function') {
      path.classList.add('mind-map-thread-drawing');
      path.style.setProperty('--path-length', path.getTotalLength());
      path.style.setProperty('--draw-delay', delay);
    }
    if (isNewPath) svg.appendChild(path);
  };
  canvas.querySelectorAll('.mind-map-paper-branch').forEach((branch, i) => {
    const branchKey = branch.dataset.branchKey || String(i);
    const color = MIND_MAP_BRANCH_THEMES[i % MIND_MAP_BRANCH_THEMES.length].line;
    const head = branch.querySelector('.mind-map-paper-heading').getBoundingClientRect();
    const targetX = (head.left + head.width / 2 - origin.left) / scale;
    const targetY = (head.top + head.height / 2 - origin.top) / scale;
    const dx = targetX - rootX;
    const dy = targetY - rootY;
    const distance = Math.max(1, Math.hypot(dx, dy));
    const rootEdge = 1 / Math.max(
      Math.abs(dx) / Math.max(1, r.width / scale / 2),
      Math.abs(dy) / Math.max(1, r.height / scale / 2)
    );
    const headingEdge = 1 / Math.max(
      Math.abs(dx) / Math.max(1, head.width / scale / 2),
      Math.abs(dy) / Math.max(1, head.height / scale / 2)
    );
    const sx = rootX + dx * rootEdge;
    const sy = rootY + dy * rootEdge;
    const ex = targetX - dx * headingEdge;
    const ey = targetY - dy * headingEdge;
    upsertPath(
      JSON.stringify(['topic', branchKey]),
      `M ${sx} ${sy} L ${ex} ${ey}`,
      color,
      { shouldAnimate: branch.dataset.drawNew === 'true', delay: branch.style.getPropertyValue('--branch-delay'), kind: 'topic' }
    );

    const leaves = [...branch.querySelectorAll('.mind-map-paper-leaf')];
    if (!leaves.length) return;
    const listRect = branch.querySelector('.mind-map-paper-leaves').getBoundingClientRect();
    const flow = branch.dataset.flow || 'down';
    const headingX = (flow === 'right'
      ? head.right
      : flow === 'left'
        ? head.left
        : head.left + head.width / 2) - origin.left;
    const headingY = (flow === 'up'
      ? head.top
      : flow === 'down'
        ? head.bottom
        : head.top + head.height / 2) - origin.top;
    const leafRects = leaves.map(leaf => leaf.getBoundingClientRect());
    const leafCenters = leafRects.map(rect => (rect.top + rect.height / 2 - origin.top) / scale);
    const localHeadingX = headingX / scale;
    const localHeadingY = headingY / scale;
    const listTop = (listRect.top - origin.top) / scale;
    const listBottom = (listRect.bottom - origin.top) / scale;
    const spineStartDelay = (parseFloat(branch.style.getPropertyValue('--branch-delay')) || 0) + 220;
    const listSideX = (flow === 'right'
      ? listRect.left
      : flow === 'left'
        ? listRect.right
        : listRect.left + listRect.width / 2) - origin.left;
    const leafTargetY = flow === 'up'
      ? listBottom
      : flow === 'down'
        ? listTop
        : leafCenters.reduce((closest, y) =>
            Math.abs(y - localHeadingY) < Math.abs(closest - localHeadingY) ? y : closest,
            leafCenters[0]
          );
    const spinePath = `M ${localHeadingX} ${localHeadingY} L ${listSideX / scale} ${leafTargetY}`;
    upsertPath(
      JSON.stringify(['spine', branchKey]),
      spinePath,
      color,
      { shouldAnimate: branch.dataset.drawNew === 'true', delay: `${spineStartDelay}ms`, kind: 'spine' }
    );
  });
  for (const [key, path] of existingPaths) {
    if (!wantedPaths.has(key)) path.remove();
  }
}

function mindMapElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  if (text != null) element.textContent = text;
  return element;
}

function buildMindMapCanvas(mind, { animate = false, previousMind = null } = {}) {
  const branches = getVisibleMindMapChildren(mind);
  if (!mind?.title && !branches.length) return null;
  const previousBranches = mindMapBranchMap(previousMind);
  const canvas = mindMapElement('div', 'mind-map-paper');
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'mind-map-thread-layer');
  svg.setAttribute('aria-hidden', 'true');
  canvas.appendChild(svg);

  const grid = mindMapElement('div', 'mind-map-paper-grid');
  const rowCount = Math.ceil(branches.length / 2) || 1;
  let drawStep = 0;
  const drawStepDelay = 220;
  if (!branches.length) grid.classList.add('mind-map-paper-grid--empty');
  grid.style.setProperty('--map-rows', rowCount);
  const rootWrap = mindMapElement('div', 'mind-map-paper-root-wrap');
  const root = mindMapElement('div', 'mind-map-paper-root');
  root.appendChild(mindMapElement('h4', 'mind-map-paper-title', mind.title || '討論主題'));
  rootWrap.appendChild(root);
  const doodle = mindMapElement('span', 'mind-map-paper-doodle', '✧');
  doodle.setAttribute('aria-hidden', 'true');
  rootWrap.appendChild(doodle);
  rootWrap.style.gridRow = `1 / span ${rowCount}`;
  grid.appendChild(rootWrap);
  branches.forEach((branch, i) => {
    const theme = MIND_MAP_BRANCH_THEMES[i % MIND_MAP_BRANCH_THEMES.length];
    const section = mindMapElement('section', 'mind-map-paper-branch');
    const branchLabel = String(branch.label || '延伸議題').trim();
    section.dataset.branchKey = branchLabel;
    const previousLeaves = previousBranches.get(branchLabel);
    const newBranch = animate && !previousBranches.has(branchLabel);
    section.dataset.drawNew = newBranch ? 'true' : 'false';
    const side = i % 2 === 0 ? 'left' : 'right';
    section.dataset.side = side;
    section.style.gridColumn = side === 'left' ? '1' : '3';
    section.style.gridRow = String(Math.floor(i / 2) + 1);
    section.style.setProperty('--map-ink', theme.ink);
    section.style.setProperty('--map-soft', theme.soft);
    section.style.setProperty('--map-line', theme.line);
    const heading = mindMapElement('div', 'mind-map-paper-heading');
    if (newBranch) {
      heading.classList.add('mind-map-draw-in');
      const delay = `${drawStep++ * drawStepDelay}ms`;
      heading.style.setProperty('--draw-delay', delay);
      section.style.setProperty('--branch-delay', delay);
    }
    heading.appendChild(mindMapElement('span', 'mind-map-paper-number', String(i + 1).padStart(2, '0')));
    heading.appendChild(mindMapElement('h5', 'mind-map-paper-label', branchLabel));
    section.appendChild(heading);
    const list = mindMapElement('ul', 'mind-map-paper-leaves');
    const leaves = mindMapBranchLeaves(branch);
    for (const leaf of leaves) {
      const item = mindMapElement('li', 'mind-map-paper-leaf');
      const leafKey = mindMapLeafKey(leaf);
      item.dataset.leafKey = leafKey;
      if (animate && (!previousLeaves || !previousLeaves.has(leafKey))) {
        item.classList.add('mind-map-draw-in');
        item.style.setProperty('--draw-delay', `${drawStep++ * drawStepDelay}ms`);
      }
      const byline = mindMapElement('div', 'mind-map-paper-byline');
      const meta = leaf.person_slug ? insightsPersonMeta(leaf.person_slug) : null;
      const speaker = leaf.speaker || meta?.name || '討論觀點';
      const avatar = avatarEl(speaker, 'avatar xs', leaf.person_slug || '', meta?.avatar || '');
      avatar.setAttribute('aria-hidden', 'true');
      byline.appendChild(avatar);
      byline.appendChild(mindMapElement('strong', 'mind-map-paper-speaker', speaker));
      item.appendChild(byline);
      let quote = String(leaf.quote || leaf.quote_full || leaf.label || '');
      if (quote.startsWith(`${speaker}：`)) quote = quote.slice(speaker.length + 1).trim();
      item.appendChild(mindMapElement('p', 'mind-map-paper-quote', quote));
      list.appendChild(item);
    }
    if (!leaves.length) list.appendChild(mindMapElement('li', 'mind-map-paper-pending', '這個方向，等待更多觀點…'));
    section.appendChild(list);
    grid.appendChild(section);
  });
  canvas.appendChild(grid);
  mindMapCanvases.add(canvas);
  mindMapResizeObserver?.observe(canvas);
  if (animate) {
    window.setTimeout(() => {
      canvas.querySelectorAll('.mind-map-paper-branch').forEach((branch) => {
        branch.dataset.drawNew = 'false';
      });
    }, drawStep * drawStepDelay + 450);
  }
  return canvas;
}

function reconcileMindMapLeafList(currentList, nextList) {
  const existing = new Map();
  for (const item of currentList.children) {
    existing.set(item.dataset.leafKey || '__pending__', item);
  }
  const desiredKeys = new Set();
  let cursor = currentList.firstElementChild;
  for (const nextItem of nextList.children) {
    const key = nextItem.dataset.leafKey || '__pending__';
    desiredKeys.add(key);
    const item = existing.get(key) || nextItem;
    if (item.parentElement !== currentList || item !== cursor) {
      currentList.insertBefore(item, cursor);
    }
    cursor = item.nextElementSibling;
  }
  for (const item of [...currentList.children]) {
    if (!desiredKeys.has(item.dataset.leafKey || '__pending__')) item.remove();
  }
}

function reconcileMindMapCanvas(currentCanvas, nextCanvas) {
  const currentGrid = currentCanvas.querySelector('.mind-map-paper-grid');
  const nextGrid = nextCanvas.querySelector('.mind-map-paper-grid');
  if (!currentGrid || !nextGrid) return false;

  currentGrid.classList.toggle(
    'mind-map-paper-grid--empty',
    nextGrid.classList.contains('mind-map-paper-grid--empty')
  );
  currentGrid.style.setProperty('--map-rows', nextGrid.style.getPropertyValue('--map-rows'));

  const currentRootWrap = currentGrid.querySelector('.mind-map-paper-root-wrap');
  const nextRootWrap = nextGrid.querySelector('.mind-map-paper-root-wrap');
  if (currentRootWrap && nextRootWrap) {
    currentRootWrap.style.gridRow = nextRootWrap.style.gridRow;
    const currentTitle = currentRootWrap.querySelector('.mind-map-paper-title');
    const nextTitle = nextRootWrap.querySelector('.mind-map-paper-title');
    if (currentTitle && nextTitle && currentTitle.textContent !== nextTitle.textContent) {
      currentTitle.textContent = nextTitle.textContent;
    }
  } else if (nextRootWrap && !currentRootWrap) {
    currentGrid.prepend(nextRootWrap);
  }

  const currentBranches = new Map(
    [...currentGrid.querySelectorAll(':scope > .mind-map-paper-branch')]
      .map(branch => [branch.dataset.branchKey, branch])
  );
  const wantedBranches = new Set();
  for (const nextBranch of nextGrid.querySelectorAll(':scope > .mind-map-paper-branch')) {
    const key = nextBranch.dataset.branchKey;
    wantedBranches.add(key);
    const branch = currentBranches.get(key);
    if (!branch) {
      currentGrid.appendChild(nextBranch);
      continue;
    }

    branch.dataset.side = nextBranch.dataset.side;
    branch.style.gridColumn = nextBranch.style.gridColumn;
    branch.style.gridRow = nextBranch.style.gridRow;
    for (const name of ['--map-ink', '--map-soft', '--map-line']) {
      branch.style.setProperty(name, nextBranch.style.getPropertyValue(name));
    }
    const currentList = branch.querySelector('.mind-map-paper-leaves');
    const nextList = nextBranch.querySelector('.mind-map-paper-leaves');
    if (currentList && nextList) reconcileMindMapLeafList(currentList, nextList);
  }

  for (const [key, branch] of currentBranches) {
    if (!wantedBranches.has(key)) branch.remove();
  }
  return true;
}

function openMindMapExpanded(mind, trigger) {
  document.querySelector('.mind-map-expanded-dialog')?.close();
  const dialog = mindMapElement('dialog', 'mind-map-expanded-dialog');
  document.body.classList.add('mind-map-expanded-open');
  dialog.setAttribute('aria-label', '心智圖完整檢視');
  const bar = mindMapElement('div', 'mind-map-expanded-bar');
  const title = mindMapElement('div', 'mind-map-expanded-title');
  title.appendChild(mindMapElement('strong', '', '討論的靈感地圖'));
  title.appendChild(mindMapElement('span', '', '從一個問題，長出不同的想法'));
  bar.appendChild(title);
  const scroll = mindMapElement('div', 'mind-map-expanded-scroll mind-map-zoom-viewport');
  appendMindMapZoomControls(bar, scroll);
  const close = mindMapElement('button', 'mind-map-tool', '關閉 ✕');
  close.type = 'button';
  close.addEventListener('click', () => dialog.close());
  bar.appendChild(close);
  dialog.appendChild(bar);
  const canvas = buildMindMapCanvas(mind);
  if (canvas) scroll.appendChild(canvas);
  dialog.appendChild(scroll);
  initMindMapZoomViewport(scroll);
  requestAnimationFrame(() => fitMindMapZoom(scroll));
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => {
    document.body.classList.remove('mind-map-expanded-open');
    dialog.remove();
    scheduleMindMapLinks();
    if (trigger?.isConnected) trigger.focus();
  }, { once: true });
  document.body.appendChild(dialog);
  dialog.showModal();
  requestAnimationFrame(() => {
    if (canvas) layoutMindMapRadial(canvas);
    fitMindMapZoom(scroll);
    scheduleMindMapLinks();
  });
}

function renderMindMap(mind, { animate = false, previousMind = null, emptyLabel = '' } = {}) {
  const host = document.getElementById('mindMapHost');
  if (!host) return;
  mind = cleanMindMap(mind);
  let toolbar = host.querySelector('.mind-map-paper-toolbar');
  let countElement = toolbar?.querySelector('.mind-map-paper-count');
  let expand = toolbar?.querySelector('.mind-map-expand-tool');
  let scroll = host.querySelector('.mind-map-paper-scroll');
  if (!toolbar) {
    toolbar = mindMapElement('div', 'mind-map-paper-toolbar');
    countElement = mindMapElement('span', 'mind-map-paper-count', '');
    expand = mindMapElement('button', 'mind-map-tool mind-map-expand-tool', '展開閱讀 ↗');
    expand.type = 'button';
    toolbar.append(countElement, expand);
    host.appendChild(toolbar);
  }
  if (!scroll) {
    scroll = mindMapElement('div', 'mind-map-paper-scroll mind-map-zoom-viewport');
    initMindMapZoomViewport(scroll);
    host.appendChild(scroll);
  }
  initMindMapZoomViewport(scroll);
  if (!toolbar.querySelector('.mind-map-zoom-controls')) {
    expand.remove();
    appendMindMapZoomControls(toolbar, scroll, expand);
  }
  const updateStatus = document.getElementById('mindMapUpdateStatus');
  if (updateStatus && updateStatus.parentElement !== toolbar) {
    const controls = toolbar.querySelector('.mind-map-zoom-controls');
    toolbar.insertBefore(updateStatus, controls || expand || null);
  }

  const oldScroll = scroll.scrollTop;
  const currentCanvas = scroll.querySelector('.mind-map-paper');
  const canvas = buildMindMapCanvas(mind, { animate, previousMind });
  if (!canvas) {
    const empty = mindMapElement('div', 'mind-map-paper-empty');
    empty.appendChild(mindMapElement('span', '', '✧'));
    empty.appendChild(mindMapElement('strong', '', '想法，正在發芽'));
    empty.appendChild(mindMapElement('p', '', '開始討論後，人物觀點會在這裡連成一張心智圖。'));
    scroll.replaceChildren(empty);
  } else {
    const labelText = mind.children.length
      ? `${mind.children.length} 個議題 · ${canvas.querySelectorAll('.mind-map-paper-leaf').length} 個觀點`
      : (emptyLabel || '討論主題 · 等待第一個觀點');
    toolbar.querySelector('.mind-map-paper-count').textContent = labelText;
    expand.onclick = () => openMindMapExpanded(mind, expand);

    let renderedCanvas = canvas;
    if (currentCanvas && reconcileMindMapCanvas(currentCanvas, canvas)) {
      renderedCanvas = currentCanvas;
      mindMapResizeObserver?.unobserve(canvas);
      mindMapCanvases.delete(canvas);
      const maximumDelay = [...renderedCanvas.querySelectorAll('.mind-map-draw-in')]
        .reduce((max, node) => Math.max(max, parseFloat(node.style.getPropertyValue('--draw-delay')) || 0), 0);
      window.setTimeout(() => {
        renderedCanvas.querySelectorAll('.mind-map-paper-branch').forEach(branch => {
          branch.dataset.drawNew = 'false';
        });
      }, maximumDelay + 450);
    } else if (currentCanvas) {
      currentCanvas.replaceWith(canvas);
    } else {
      scroll.replaceChildren(canvas);
    }
    scroll.scrollTop = oldScroll;
    layoutMindMapRadial(renderedCanvas);
    fitMindMapCardText(renderedCanvas);
    refreshMindMapZoom(scroll);
    scheduleMindMapLinks();
  }
  renderMindMapHistoryLauncher(host);
  renderMindMapHistoryModal(host);
  scheduleMindMapLinks();
}

let mindMapHistoryModalOpen = false;

function rerenderMindMapFromHistory() {
  if (!currentSessionId) return;
  const latest = mindMapLatestBySession.get(currentSessionId) || {};
  const activeMind = getActiveMindMapForSession(currentSessionId, latest);
  renderMindMap(activeMind || latest || {});
}

function renderMindMapHistoryLauncher(host) {
  const old = host.querySelector(".mind-map-history-launcher");
  if (old) old.remove();
  if (!currentSessionId) return;
  const history = getMindMapHistory(currentSessionId);
  if (!history || history.length < 2) return;

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "mind-map-history-launcher";
  btn.title = "預覽歷史紀錄";
  btn.setAttribute("aria-label", "預覽歷史紀錄");
  btn.textContent = "↶ 歷史版本";
  btn.addEventListener("click", () => {
    mindMapHistoryModalOpen = true;
    rerenderMindMapFromHistory();
  });
  host.appendChild(btn);
}

function renderMindMapHistoryModal(host) {
  const old = document.querySelector(".mind-map-history-overlay");
  if (old) old.remove();
  if (!mindMapHistoryModalOpen || !currentSessionId) return;
  const history = getMindMapHistory(currentSessionId);
  if (!history || history.length < 2) {
    mindMapHistoryModalOpen = false;
    return;
  }

  const activePreview = getMindMapPreviewIndex(currentSessionId);
  const activeIdx =
    activePreview != null && activePreview >= 0 && activePreview < history.length
      ? activePreview
      : history.length - 1;

  const overlay = document.createElement("div");
  overlay.className = "mind-map-history-overlay";
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      mindMapHistoryModalOpen = false;
      rerenderMindMapFromHistory();
    }
  });

  const modal = document.createElement("div");
  modal.className = "mind-map-history-modal";
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-label", "心智圖歷史");
  overlay.appendChild(modal);

  const close = document.createElement("button");
  close.type = "button";
  close.className = "mind-map-history-close";
  close.textContent = "×";
  close.setAttribute("aria-label", "關閉歷史預覽");
  close.addEventListener("click", () => {
    mindMapHistoryModalOpen = false;
    rerenderMindMapFromHistory();
  });
  modal.appendChild(close);

  const head = document.createElement("div");
  head.className = "mind-map-history-head";
  const title = document.createElement("strong");
  title.textContent = "心智圖歷史";
  head.appendChild(title);
  const step = document.createElement("span");
  step.className = "mind-map-history-step";
  step.textContent = `${activeIdx + 1}/${history.length}`;
  head.appendChild(step);
  modal.appendChild(head);

  const previewHost = document.createElement("div");
  previewHost.className = "mind-map-history-preview-host";
  const previewMind = history[activeIdx]?.mind_map || {};
  const previewSvg = buildMindMapCanvas(previewMind);
  if (previewSvg) {
    previewSvg.classList.add("mind-map-paper--history-preview");
    previewHost.appendChild(previewSvg);
  } else {
    previewHost.innerHTML = '<p class="insights-empty">此版本尚無心智圖</p>';
  }
  modal.appendChild(previewHost);

  const controls = document.createElement("div");
  controls.className = "mind-map-history-modal-controls";
  modal.appendChild(controls);

  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = "0";
  slider.max = String(history.length - 1);
  slider.value = String(activeIdx);
  slider.className = "mind-map-history-range";
  slider.setAttribute("aria-label", "選擇心智圖歷史版本");
  slider.addEventListener("input", (e) => {
    const idx = Number(e.target.value) || 0;
    if (idx >= history.length - 1) {
      setMindMapPreviewIndex(currentSessionId, null);
    } else {
      setMindMapPreviewIndex(currentSessionId, idx);
    }
    rerenderMindMapFromHistory();
  });
  controls.appendChild(slider);

  const footer = document.createElement("div");
  footer.className = "mind-map-history-controls";
  const btnPrev = document.createElement("button");
  btnPrev.type = "button";
  btnPrev.className = "mind-map-history-btn";
  btnPrev.textContent = "◀";
  btnPrev.setAttribute("aria-label", "上一個版本");
  btnPrev.disabled = activeIdx <= 0;
  btnPrev.addEventListener("click", () => {
    const idx = Math.max(0, activeIdx - 1);
    setMindMapPreviewIndex(currentSessionId, idx);
    rerenderMindMapFromHistory();
  });
  footer.appendChild(btnPrev);

  const btnLatest = document.createElement("button");
  btnLatest.type = "button";
  btnLatest.className = "mind-map-history-btn" + (activeIdx === history.length - 1 ? " is-active" : "");
  btnLatest.textContent = "最新";
  btnLatest.addEventListener("click", () => {
    setMindMapPreviewIndex(currentSessionId, null);
    rerenderMindMapFromHistory();
  });
  footer.appendChild(btnLatest);

  const btnNext = document.createElement("button");
  btnNext.type = "button";
  btnNext.className = "mind-map-history-btn";
  btnNext.textContent = "▶";
  btnNext.setAttribute("aria-label", "下一個版本");
  btnNext.disabled = activeIdx >= history.length - 1;
  btnNext.addEventListener("click", () => {
    const idx = Math.min(history.length - 1, activeIdx + 1);
    if (idx >= history.length - 1) {
      setMindMapPreviewIndex(currentSessionId, null);
    } else {
      setMindMapPreviewIndex(currentSessionId, idx);
    }
    rerenderMindMapFromHistory();
  });
  footer.appendChild(btnNext);
  controls.appendChild(footer);

  const meta = history[activeIdx] || {};
  const msgTag = document.createElement("div");
  msgTag.className = "mind-map-history-meta";
  msgTag.textContent = meta.message_count
    ? `第 ${meta.message_count} 則訊息`
    : `版本 ${activeIdx + 1}`;
  controls.appendChild(msgTag);

  document.body.appendChild(overlay);
  requestAnimationFrame(() => {
    if (!previewSvg?.isConnected) return;
    layoutMindMapRadial(previewSvg);
    fitMindMapZoom(previewHost);
    scheduleMindMapLinks();
  });
}

