// @ts-nocheck
// Growth Creative Factory — Figma Plugin (TypeScript source)
// Compile with: npx tsc code.ts --outDir dist --target ES6 --lib ES6

figma.showUI(__html__, { width: 460, height: 760 });

interface VariationRow {
  H1?: string;
  DESC?: string;
  CTA?: string;
  H2?: string;
  TAG: string;
  [key: string]: string | undefined;
}

interface LayerMapping {
  h1Node: string;
  descNode: string;
  ctaNode?: string;
  h2Node?: string;
}

interface GeneratePayload {
  templateName: string;
  rows: VariationRow[];
  mapping: LayerMapping;
  grid: {
    columns: number;
    gapX: number;
    gapY: number;
  };
}

const GENERATED_PREFIX = "AD_";

figma.ui.onmessage = async (msg: any) => {
  if (msg.type === "generate") {
    await handleGenerate(msg as GeneratePayload);
  }
  if (msg.type === "export-pngs") {
    await handleExportPngs();
  }
};

function postStatus(text: string) {
  figma.ui.postMessage({ type: "status", text });
}

async function loadFontSafe(font: FontName, context: string): Promise<boolean> {
  try {
    await figma.loadFontAsync(font);
    return true;
  } catch (err) {
    postStatus(`⚠️ Font load failed for ${context}: ${font.family} ${font.style}. Node skipped.`);
    console.warn("Font load failed", context, font, err);
    return false;
  }
}

async function preflightTemplateFonts(template: FrameNode): Promise<{ ok: boolean; failedNodes: string[] }> {
  const textNodes = template.findAll((n) => n.type === "TEXT") as TextNode[];
  const failedNodes: string[] = [];

  for (const tn of textNodes) {
    const nodeLabel = `template node "${tn.name}"`;

    try {
      if (tn.fontName !== figma.mixed) {
        const ok = await loadFontSafe(tn.fontName as FontName, nodeLabel);
        if (!ok) failedNodes.push(tn.name);
      } else {
        const len = tn.characters.length;
        let nodeOk = true;
        for (let i = 0; i < len; i++) {
          const font = tn.getRangeFontName(i, i + 1) as FontName;
          const ok = await loadFontSafe(font, `${nodeLabel} (range ${i})`);
          if (!ok) {
            nodeOk = false;
            break;
          }
        }
        if (!nodeOk) failedNodes.push(tn.name);
      }
    } catch (err) {
      postStatus(`⚠️ Font preflight failed for node "${tn.name}". Node may be skipped.`);
      console.warn("Preflight node scan failed", tn.name, err);
      failedNodes.push(tn.name);
    }
  }

  return { ok: failedNodes.length === 0, failedNodes };
}

function getMappedValue(row: VariationRow, nodeName: string, mapping: LayerMapping): string | undefined {
  const key = nodeName.trim().toUpperCase();
  const h1 = mapping.h1Node.trim().toUpperCase();
  const desc = mapping.descNode.trim().toUpperCase();
  const cta = (mapping.ctaNode || "").trim().toUpperCase();
  const h2 = (mapping.h2Node || "").trim().toUpperCase();

  if (key === h1) return row.H1;
  if (key === desc) return row.DESC;
  if (cta && key === cta) return row.CTA;
  if (h2 && key === h2) return row.H2;
  return undefined;
}

async function setTextIfMapped(tn: TextNode, value: string, nodeLabel: string) {
  try {
    if (tn.fontName !== figma.mixed) {
      const ok = await loadFontSafe(tn.fontName as FontName, nodeLabel);
      if (!ok) return;
      tn.characters = value;
      return;
    }

    // Mixed font: load every range to avoid hard failures.
    const len = Math.max(tn.characters.length, 1);
    for (let i = 0; i < len; i++) {
      const font = tn.getRangeFontName(i, Math.min(i + 1, tn.characters.length)) as FontName;
      const ok = await loadFontSafe(font, `${nodeLabel} (range ${i})`);
      if (!ok) return;
    }
    tn.characters = value;
  } catch (err) {
    postStatus(`⚠️ Failed to write node "${tn.name}". Node skipped.`);
    console.warn("Text write failed", tn.name, err);
  }
}

async function handleGenerate(payload: GeneratePayload) {
  const { templateName, rows, mapping, grid } = payload;

  const template = figma.currentPage.findOne(
    (n) => n.type === "FRAME" && n.name === templateName
  ) as FrameNode | null;

  if (!template) {
    postStatus(`❌ Frame "${templateName}" not found on current page.`);
    return;
  }

  const preflight = await preflightTemplateFonts(template);
  if (!preflight.ok) {
    postStatus(
      `⚠️ Preflight font issues on ${preflight.failedNodes.length} node(s): ${preflight.failedNodes.join(", ")}. Continuing with skip-on-failure.`
    );
  }

  const cols = Math.max(1, grid.columns || 1);
  const gapX = Math.max(0, grid.gapX || 0);
  const gapY = Math.max(0, grid.gapY || 0);

  const fw = template.width + gapX;
  const fh = template.height + gapY;
  const startX = template.x + template.width + gapX * 2;
  const startY = template.y;

  let created = 0;

  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const clone = template.clone();
    const col = i % cols;
    const rowIdx = Math.floor(i / cols);

    clone.x = startX + col * fw;
    clone.y = startY + rowIdx * fh;
    clone.name = `${GENERATED_PREFIX}${String(i + 1).padStart(3, "0")}_${row.TAG || "UNTAGGED"}`;

    const cloneTextNodes = clone.findAll((n) => n.type === "TEXT") as TextNode[];
    for (const tn of cloneTextNodes) {
      const value = getMappedValue(row, tn.name, mapping);
      if (typeof value === "string") {
        await setTextIfMapped(tn, value, `clone ${clone.name} node "${tn.name}"`);
      }
    }

    created++;

    if (created % 10 === 0) {
      postStatus(`⏳ Created ${created}/${rows.length} frames...`);
    }
  }

  postStatus(`✅ Done! Created ${created} ad variations from "${templateName}".`);
}

async function handleExportPngs() {
  const generatedFrames = figma.currentPage.findAll(
    (n) => n.type === "FRAME" && n.name.startsWith(GENERATED_PREFIX)
  ) as FrameNode[];

  if (generatedFrames.length === 0) {
    postStatus("⚠️ No generated frames (AD_###) found. Generate variations first.");
    return;
  }

  const files: Array<{ name: string; base64: string }> = [];

  for (let i = 0; i < generatedFrames.length; i++) {
    const frame = generatedFrames[i];
    try {
      const bytes = await frame.exportAsync({
        format: "PNG",
        constraint: { type: "SCALE", value: 2 },
      });
      files.push({
        name: `${frame.name}.png`,
        base64: figma.base64Encode(bytes),
      });
    } catch (e) {
      postStatus(`⚠️ Export failed for ${frame.name}; skipped.`);
      console.warn("Export failed for", frame.name, e);
    }

    if ((i + 1) % 10 === 0) {
      postStatus(`⏳ Exporting ${i + 1}/${generatedFrames.length}...`);
    }
  }

  figma.ui.postMessage({ type: "export-done", files });
}
