#!/usr/bin/env node
'use strict';

/**
 * Headless voronoi-treemap computation engine.
 *
 * Reads a JSON payload from stdin:
 *   {
 *     "hierarchy": { "id": "...", "name": "...", "value": 1, "children": [...] },
 *     "shape": { "type": "circle" | "rectangle" | "polygon", ... },
 *     "options": { "width": 800, "height": 800, "seed": 42,
 *                  "convergenceRatio": 0.01, "maxIterationCount": 50 }
 *   }
 *
 * Writes computed geometry as JSON to stdout:
 *   { "meta": {...}, "nodes": [ { id, parentId, name, depth, height, value,
 *                                 polygon, centroid, area }, ... ] }
 */

const { voronoiTreemap } = require('d3-voronoi-treemap');

// ---------- seeded PRNG (mulberry32) ----------
function makePrng(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------- polygon helpers (shoelace formula) ----------
function polygonArea(points) {
  let sum = 0;
  const n = points.length;
  for (let i = 0; i < n; i++) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[(i + 1) % n];
    sum += x0 * y1 - x1 * y0;
  }
  return sum / 2;
}

function polygonCentroid(points) {
  let cx = 0;
  let cy = 0;
  const area = polygonArea(points);
  const n = points.length;
  if (area === 0) {
    // degenerate polygon; fall back to vertex average
    for (const [x, y] of points) {
      cx += x;
      cy += y;
    }
    return [cx / n, cy / n];
  }
  for (let i = 0; i < n; i++) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[(i + 1) % n];
    const cross = x0 * y1 - x1 * y0;
    cx += (x0 + x1) * cross;
    cy += (y0 + y1) * cross;
  }
  const factor = 1 / (6 * area);
  return [cx * factor, cy * factor];
}

// ---------- clip polygon builders ----------
function buildCircleClip(width, height, opts) {
  const cx = opts.cx != null ? opts.cx : width / 2;
  const cy = opts.cy != null ? opts.cy : height / 2;
  const r = opts.r != null ? opts.r : Math.min(width, height) / 2 * 0.95;
  const vertices = opts.vertices != null ? opts.vertices : 64;
  const points = [];
  for (let i = 0; i < vertices; i++) {
    const angle = (2 * Math.PI * i) / vertices;
    points.push([cx + r * Math.cos(angle), cy + r * Math.sin(angle)]);
  }
  return points;
}

const GOLDEN_RATIO = (1 + Math.sqrt(5)) / 2; // ~1.618

function buildRectangleClip(width, height, opts) {
  let w = opts.width;
  let h = opts.height;
  if (w == null && h == null) {
    // No explicit size (plain "rectangle"): use a golden-ratio rectangle
    // inscribed in the canvas, independent of the canvas's own aspect
    // ratio -- otherwise a square canvas would make "rectangle" degenerate
    // into a square, indistinguishable from shape "square".
    const margin = 0.95;
    const availW = width * margin;
    const availH = height * margin;
    if (availW / availH > GOLDEN_RATIO) {
      h = availH;
      w = h * GOLDEN_RATIO;
    } else {
      w = availW;
      h = w / GOLDEN_RATIO;
    }
  } else {
    w = w != null ? w : width;
    h = h != null ? h : height;
  }
  const x0 = opts.x != null ? opts.x : (width - w) / 2;
  const y0 = opts.y != null ? opts.y : (height - h) / 2;
  return [
    [x0, y0],
    [x0 + w, y0],
    [x0 + w, y0 + h],
    [x0, y0 + h],
  ];
}

function buildEllipseClip(width, height, opts) {
  const cx = opts.cx != null ? opts.cx : width / 2;
  const cy = opts.cy != null ? opts.cy : height / 2;
  const rx = opts.rx != null ? opts.rx : (width / 2) * 0.95;
  const ry = opts.ry != null ? opts.ry : (height / 2) * 0.95;
  const vertices = opts.vertices != null ? opts.vertices : 64;
  const points = [];
  for (let i = 0; i < vertices; i++) {
    const angle = (2 * Math.PI * i) / vertices;
    points.push([cx + rx * Math.cos(angle), cy + ry * Math.sin(angle)]);
  }
  return points;
}

function buildRegularPolygonClip(width, height, opts, sides) {
  if (!Number.isInteger(sides) || sides < 3) {
    throw new Error(`shape.sides must be an integer >= 3 (got: ${sides})`);
  }
  const cx = opts.cx != null ? opts.cx : width / 2;
  const cy = opts.cy != null ? opts.cy : height / 2;
  const r = opts.r != null ? opts.r : (Math.min(width, height) / 2) * 0.95;
  const startAngle = -Math.PI / 2; // first vertex points straight up
  const points = [];
  for (let i = 0; i < sides; i++) {
    const angle = startAngle + (2 * Math.PI * i) / sides;
    points.push([cx + r * Math.cos(angle), cy + r * Math.sin(angle)]);
  }
  return points;
}

function buildClipPolygon(shape, width, height) {
  const type = (shape && shape.type) || 'circle';
  switch (type) {
    case 'circle':
      return buildCircleClip(width, height, shape || {});
    case 'ellipse':
      return buildEllipseClip(width, height, shape || {});
    case 'rectangle':
      return buildRectangleClip(width, height, shape || {});
    case 'polygon':
      if (shape.sides != null) {
        return buildRegularPolygonClip(width, height, shape, shape.sides);
      }
      if (!Array.isArray(shape.points) || shape.points.length < 3) {
        throw new Error('shape.type "polygon" requires either "sides" (regular N-gon) or a "points" array with >= 3 [x, y] vertices');
      }
      return shape.points.map(([x, y]) => [x, y]);
    default:
      throw new Error(`Unknown shape.type "${type}" (expected "circle", "ellipse", "rectangle", or "polygon")`);
  }
}

// ---------- hierarchy builder (duck-typed d3.hierarchy replacement) ----------
// d3-voronoi-treemap only needs: node.children, node.value, node.height, node.data
function buildHierarchyNode(data, parent, depth) {
  const node = {
    data,
    parent: parent || null,
    depth,
    children: null,
    value: undefined,
    height: 0,
  };
  if (Array.isArray(data.children) && data.children.length > 0) {
    node.children = data.children.map((child) => buildHierarchyNode(child, node, depth + 1));
    node.height = 1 + Math.max(...node.children.map((c) => c.height));
  }
  return node;
}

// bottom-up sum: internal node value = sum of descendant leaf values
function sumValues(node) {
  if (!node.children) {
    node.value = typeof node.data.value === 'number' ? node.data.value : 0;
    return node.value;
  }
  node.value = node.children.reduce((acc, child) => acc + sumValues(child), 0);
  return node.value;
}

// ---------- serialize computed hierarchy to flat node list ----------
function serialize(node, out) {
  const [cx, cy] = polygonCentroid(node.polygon);
  out.push({
    id: node.data.id,
    parentId: node.parent ? node.parent.data.id : null,
    name: node.data.name,
    depth: node.depth,
    height: node.height,
    value: node.value,
    polygon: node.polygon,
    centroid: [cx, cy],
    area: Math.abs(polygonArea(node.polygon)),
  });
  if (node.children) {
    node.children.forEach((child) => serialize(child, out));
  }
}

// ---------- main ----------
function readStdin() {
  return new Promise((resolve, reject) => {
    const chunks = [];
    process.stdin.on('data', (chunk) => chunks.push(chunk));
    process.stdin.on('end', () => resolve(Buffer.concat(chunks).toString('utf-8')));
    process.stdin.on('error', reject);
  });
}

async function main() {
  const raw = await readStdin();
  let input;
  try {
    input = JSON.parse(raw);
  } catch (err) {
    throw new Error(`Invalid JSON on stdin: ${err.message}`);
  }

  if (!input.hierarchy) {
    throw new Error('Input JSON must have a "hierarchy" field');
  }

  const options = input.options || {};
  const width = options.width != null ? options.width : 800;
  const height = options.height != null ? options.height : 800;
  const seed = options.seed != null ? options.seed : 42;
  const convergenceRatio = options.convergenceRatio != null ? options.convergenceRatio : 0.01;
  const maxIterationCount = options.maxIterationCount != null ? options.maxIterationCount : 50;
  const minWeightRatio = options.minWeightRatio != null ? options.minWeightRatio : 0.01;

  const clipPolygon = buildClipPolygon(input.shape, width, height);

  const root = buildHierarchyNode(input.hierarchy, null, 0);
  sumValues(root);

  if (root.value <= 0) {
    throw new Error('Root hierarchy value must be > 0 (check that leaf "value" fields are numeric and positive)');
  }

  const layout = voronoiTreemap()
    .clip(clipPolygon)
    .convergenceRatio(convergenceRatio)
    .maxIterationCount(maxIterationCount)
    .minWeightRatio(minWeightRatio)
    .prng(makePrng(seed));

  layout(root);

  const nodes = [];
  serialize(root, nodes);

  const result = {
    meta: {
      shape: (input.shape && input.shape.type) || 'circle',
      width,
      height,
      seed,
      convergenceRatio,
      maxIterationCount,
      nodeCount: nodes.length,
    },
    nodes,
  };

  process.stdout.write(JSON.stringify(result));
}

main().catch((err) => {
  process.stderr.write(`compute_treemap.js error: ${err.message}\n`);
  process.exit(1);
});
