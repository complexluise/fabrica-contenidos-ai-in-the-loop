#!/usr/bin/env node
"use strict";
/**
 * Conversor genérico Markdown -> .docx (D-030).
 *
 *   node convert.js <entrada.md> [salida.docx]
 *
 * La metadata sale del frontmatter (gray-matter): title, subtitle, eyebrow,
 * footer, accent (color hex de la marca; default = paleta Pacto Histórico).
 * Soporta: headings (#, ##, ###), párrafos (bold/italic/code/link), listas
 * (- y 1.), tablas GFM, blockquote (> -> nota), --- (-> divisor), code blocks.
 * Reutiliza el sistema de estilo; el contenido viene del markdown, no hardcodeado.
 */
const fs = require("fs");
const matter = require("gray-matter");
const { marked } = require("marked");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageNumber, Footer,
} = require("docx");

const DEFAULT = { primary: "7B2D8B", dark: "1E3A8A", accent: "D97706", body: "1F2937", soft: "FAF5FB" };
const NONE = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };

function hexOr(v, fallback) {
  return (typeof v === "string" && /^#?[0-9A-Fa-f]{6}$/.test(v)) ? v.replace("#", "") : fallback;
}

function build(md, data) {
  const PRIMARY = hexOr(data.accent, DEFAULT.primary);
  const ACCENT = DEFAULT.accent;
  const { dark, body, soft } = DEFAULT;
  const cell = { style: BorderStyle.SINGLE, size: 1, color: "D1D5DB" };
  const borders = { top: cell, bottom: cell, left: cell, right: cell };

  const mkRuns = (arr) => arr.map((r) => new TextRun({ font: "Arial", size: 20, color: body, ...r }));

  // tokens inline (marked) -> specs de run, propagando bold/italic anidados
  function inline(tokens, base = {}) {
    const out = [];
    for (const t of tokens || []) {
      if (t.type === "strong") out.push(...inline(t.tokens, { ...base, bold: true }));
      else if (t.type === "em") out.push(...inline(t.tokens, { ...base, italics: true }));
      else if (t.type === "codespan") out.push({ ...base, text: t.text, font: "Consolas" });
      else if (t.type === "link") out.push(...inline(t.tokens, { ...base, color: dark }));
      else if (t.type === "br") out.push({ ...base, break: 1 });
      else out.push({ ...base, text: t.text != null ? t.text : "" });
    }
    return out.length ? out : [{ ...base, text: "" }];
  }

  function heading(t) {
    const d = Math.min(t.depth, 3);
    const size = { 1: 30, 2: 24, 3: 21 }[d];
    const color = { 1: PRIMARY, 2: dark, 3: dark }[d];
    const level = { 1: HeadingLevel.HEADING_1, 2: HeadingLevel.HEADING_2, 3: HeadingLevel.HEADING_3 }[d];
    return new Paragraph({
      heading: level, spacing: { before: d === 1 ? 360 : 240, after: 120 },
      children: inline(t.tokens, { bold: true }).map((r) =>
        new TextRun({ font: "Arial", size, color, ...r })),
    });
  }

  const para = (t) => new Paragraph({ spacing: { before: 60, after: 100 }, children: mkRuns(inline(t.tokens)) });

  function itemInline(item) {
    const first = (item.tokens || [])[0];
    return first && first.tokens ? first.tokens : item.tokens || [];
  }

  function list(t) {
    const ref = t.ordered ? "numbers" : "bullets";
    return t.items.map((it) => new Paragraph({
      numbering: { reference: ref, level: 0 }, spacing: { before: 40, after: 40 },
      children: mkRuns(inline(itemInline(it))),
    }));
  }

  function table(t) {
    const n = t.header.length;
    const widths = Array(n).fill(Math.floor(9360 / n));
    const head = new TableRow({
      tableHeader: true,
      children: t.header.map((c, i) => new TableCell({
        borders, width: { size: widths[i], type: WidthType.DXA },
        shading: { fill: PRIMARY, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 140, right: 140 },
        children: [new Paragraph({ children: inline(c.tokens).map((r) =>
          new TextRun({ font: "Arial", size: 18, bold: true, color: "FFFFFF", ...r })) })],
      })),
    });
    const rows = t.rows.map((row, ri) => new TableRow({
      children: row.map((c, i) => new TableCell({
        borders, width: { size: widths[i], type: WidthType.DXA },
        shading: { fill: ri % 2 ? soft : "FFFFFF", type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 140, right: 140 },
        children: [new Paragraph({ children: inline(c.tokens).map((r) =>
          new TextRun({ font: "Arial", size: 18, color: body, ...r })) })],
      })),
    }));
    return new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: widths, rows: [head, ...rows] });
  }

  function nota(t) {
    const kids = [];
    for (const x of t.tokens || []) if (x.type === "paragraph") kids.push(...inline(x.tokens));
    return new Paragraph({
      spacing: { before: 100, after: 100 }, indent: { left: 360 },
      border: { left: { style: BorderStyle.SINGLE, size: 8, color: ACCENT, space: 8 } },
      children: kids.map((r) => new TextRun({ font: "Arial", size: 18, italics: true, color: "555555", ...r })),
    });
  }

  const divider = () => new Paragraph({
    spacing: { before: 200, after: 200 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 3, color: "E5E7EB", space: 1 } },
    children: [new TextRun("")],
  });

  const code = (t) => new Paragraph({
    spacing: { before: 60, after: 60 }, shading: { fill: "F3F4F6", type: ShadingType.CLEAR },
    children: [new TextRun({ text: t.text, font: "Consolas", size: 18, color: body })],
  });

  function cover() {
    if (!data.title) return [];
    const inner = [];
    if (data.eyebrow) inner.push(new Paragraph({ spacing: { after: 80 },
      children: [new TextRun({ text: String(data.eyebrow), font: "Arial", size: 16, bold: true, color: "D8B4F8" })] }));
    inner.push(new Paragraph({ spacing: { after: 120 },
      children: [new TextRun({ text: String(data.title), font: "Arial", size: 48, bold: true, color: "FFFFFF" })] }));
    if (data.subtitle) inner.push(new Paragraph({
      children: [new TextRun({ text: String(data.subtitle), font: "Arial", size: 22, color: "E9D5FF" })] }));
    return [
      new Table({
        width: { size: 9360, type: WidthType.DXA }, columnWidths: [9360],
        rows: [new TableRow({ children: [new TableCell({
          borders: { top: NONE, bottom: NONE, left: NONE, right: NONE },
          width: { size: 9360, type: WidthType.DXA },
          shading: { fill: PRIMARY, type: ShadingType.CLEAR },
          margins: { top: 520, bottom: 520, left: 520, right: 520 },
          children: inner,
        })] })],
      }),
      new Paragraph({ spacing: { after: 280 }, children: [new TextRun("")] }),
    ];
  }

  const els = [];
  for (const t of marked.lexer(md)) {
    if (t.type === "heading") els.push(heading(t));
    else if (t.type === "paragraph") els.push(para(t));
    else if (t.type === "list") els.push(...list(t));
    else if (t.type === "table") els.push(table(t));
    else if (t.type === "blockquote") els.push(nota(t));
    else if (t.type === "hr") els.push(divider());
    else if (t.type === "code") els.push(code(t));
  }

  const footerText = data.footer ? String(data.footer) + "   " : "";
  return new Document({
    numbering: { config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
        alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 560, hanging: 280 } } } }] },
      { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.",
        alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 560, hanging: 280 } } } }] },
    ] },
    styles: { default: { document: { run: { font: "Arial", size: 20, color: body } } } },
    sections: [{
      properties: { page: { size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
      footers: { default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.RIGHT, children: [
          new TextRun({ text: footerText, font: "Arial", size: 16, color: "9CA3AF" }),
          new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: "9CA3AF" }),
        ] })] }) },
      children: [...cover(), ...els],
    }],
  });
}

async function main() {
  const input = process.argv[2];
  if (!input || input === "--help" || input === "-h") {
    console.log("Uso: md-to-docs <entrada.md> [salida.docx]");
    console.log("");
    console.log("Frontmatter opcional: title, subtitle, eyebrow, footer, accent (#RRGGBB).");
    process.exit(0);
  }
  const output = process.argv[3] || input.replace(/\.md$/i, "") + ".docx";
  const { data, content } = matter(fs.readFileSync(input, "utf-8"));
  const buffer = await Packer.toBuffer(build(content, data || {}));
  fs.writeFileSync(output, buffer);
  console.log("OK " + output);
}

main().catch((e) => { console.error(e); process.exit(1); });
