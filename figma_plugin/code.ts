// Growth Creative Factory — Figma Plugin (TypeScript source)
// Compile with: npx tsc code.ts --outDir dist --target ES6 --lib ES6
// Or use the pre-built dist/code.js

figma.showUI(__html__, { width: 380, height: 520 });

interface VariationRow {
  H1: string;
  DESC: string;
  TAG: string;
}

const GENERATED_PREFIX = "AD_";

figma.ui.onmessage = async (msg: any) => {
  if (msg.type === "generate") {
    await handleGenerate(msg.templateName, msg.rows);
  }
  if (msg.type === "export-pngs") {
    await handleExportPngs();
  }
};

async function handleGenerate(templateName: string, rows: VariationRow[]) {
  // 1. Find the template frame
  const template = figma.currentPage.findOne(
    (n) => n.type === "FRAME" && n.name === templateName
  ) as FrameNode | null;

  if (!template) {
    figma.ui.postMessage({
      type: "status",
      text: `❌ Frame "${templateName}" not found on current page.`,
    });
    return;
  }

  // 2. Collect fonts used in text nodes
  const textNodes = template.findAll((n) => n.type === "TEXT") as TextNode[];
  const fontsToLoad = new Set<string>();

  for (const tn of textNodes) {
    const len = tn.characters.length;
    for (let i = 0; i < len; i++) {
      const font = tn.getRangeFontName(i, i + 1) as FontName;
      if (font && font.family) {
        fontsToLoad.add(JSON.stringify(font));
      }
    }
  }

  // Load all required fonts
  for (const fontStr of fontsToLoad) {
    try {
      await figma.loadFontAsync(JSON.parse(fontStr) as FontName);
    } catch (e) {
      console.warn("Could not load font:", fontStr, e);
    }
  }

  // 3. Grid layout config
  const gap = 40;
  const cols = 10;
  const fw = template.width + gap;
  const fh = template.height + gap;
  const startX = template.x + template.width + gap * 2;
  const startY = template.y;

  // 4. Clone and replace text
  let created = 0;

  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const clone = template.clone();
    const col = i % cols;
    const rowIdx = Math.floor(i / cols);

    clone.x = startX + col * fw;
    clone.y = startY + rowIdx * fh;
    clone.name = `${GENERATED_PREFIX}${String(i + 1).padStart(3, "0")}_${row.TAG}`;

    // Replace text nodes
    const cloneTextNodes = clone.findAll((n) => n.type === "TEXT") as TextNode[];
    for (const tn of cloneTextNodes) {
      const name = tn.name.toUpperCase().trim();
      if (name === "H1" && row.H1) {
        tn.characters = row.H1;
      } else if (name === "DESC" && row.DESC) {
        tn.characters = row.DESC;
      } else if (name === "H2" && row.H1) {
        // H2 gets same as H1 if no separate data
        tn.characters = row.H1;
      } else if (name === "CTA") {
        // Keep CTA as-is from template
      }
    }

    created++;

    // Progress update every 10 frames
    if (created % 10 === 0) {
      figma.ui.postMessage({
        type: "status",
        text: `⏳ Created ${created}/${rows.length} frames...`,
      });
    }
  }

  figma.ui.postMessage({
    type: "status",
    text: `✅ Done! Created ${created} ad variations from "${templateName}".`,
  });
}

async function handleExportPngs() {
  const generatedFrames = figma.currentPage.findAll(
    (n) => n.type === "FRAME" && n.name.startsWith(GENERATED_PREFIX)
  ) as FrameNode[];

  if (generatedFrames.length === 0) {
    figma.ui.postMessage({
      type: "status",
      text: "⚠️ No generated frames (AD_###) found. Generate variations first.",
    });
    return;
  }

  const files: Array<{ name: string; base64: string }> = [];

  for (let i = 0; i < generatedFrames.length; i++) {
    const frame = generatedFrames[i];
    try {
      const bytes = await frame.exportAsync({ format: "PNG", constraint: { type: "SCALE", value: 2 } });
      const base64 = figma.base64Encode(bytes);
      files.push({ name: `${frame.name}.png`, base64 });
    } catch (e) {
      console.warn("Export failed for", frame.name, e);
    }

    if ((i + 1) % 10 === 0) {
      figma.ui.postMessage({
        type: "status",
        text: `⏳ Exporting ${i + 1}/${generatedFrames.length}...`,
      });
    }
  }

  figma.ui.postMessage({ type: "export-done", files });
}
