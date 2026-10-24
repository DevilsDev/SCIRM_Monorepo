// Text from an uploaded export. SAP spreadsheet and text exports are often UTF-16
// (with a byte-order mark) or Windows-1252 rather than UTF-8.
export function decodeExport(bytes: Uint8Array): string {
  if (bytes[0] === 0xff && bytes[1] === 0xfe) return new TextDecoder('utf-16le').decode(bytes.subarray(2));
  if (bytes[0] === 0xfe && bytes[1] === 0xff) return new TextDecoder('utf-16be').decode(bytes.subarray(2));
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    return new TextDecoder('windows-1252').decode(bytes);
  }
}

/** The header cells of the first line, for mapping columns. */
export function headerCells(text: string): string[] {
  const first = text.replace(/^﻿/, '').split(/\r?\n/, 1)[0] || '';
  const sep = first.includes('\t') ? '\t' : first.includes(';') ? ';' : first.includes('|') ? '|' : ',';
  return first.split(sep).map((h) => h.trim().replace(/^"|"$/g, '')).filter(Boolean);
}
