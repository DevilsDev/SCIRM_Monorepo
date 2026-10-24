import { describe, expect, it } from 'vitest';
import { decodeExport, headerCells } from './fileText';

describe('decoding exports', () => {
  it('reads UTF-8', () => {
    expect(decodeExport(new TextEncoder().encode('LIFNR\tNAME1\n1\tMüller GmbH'))).toContain('Müller GmbH');
  });

  it('reads UTF-16 with a byte-order mark', () => {
    const text = 'LIFNR\tNAME1\n1\tMüller GmbH';
    const bytes = new Uint8Array(2 + text.length * 2);
    bytes.set([0xff, 0xfe]);
    for (let i = 0; i < text.length; i++) {
      bytes[2 + i * 2] = text.charCodeAt(i) & 0xff;
      bytes[3 + i * 2] = text.charCodeAt(i) >> 8;
    }
    expect(decodeExport(bytes)).toBe(text);
  });

  it('falls back to Windows-1252 when the bytes are not UTF-8', () => {
    // "Müller" with ü as the single byte 0xFC
    expect(decodeExport(new Uint8Array([0x4d, 0xfc, 0x6c, 0x6c, 0x65, 0x72]))).toBe('Müller');
  });
});

describe('header cells', () => {
  it('splits on the delimiter the first line uses', () => {
    expect(headerCells('﻿LIFNR\tNAME1\tLAND1\n1\tA\tDE')).toEqual(['LIFNR', 'NAME1', 'LAND1']);
    expect(headerCells('"Supplier";"Name 1"\r\n1;A')).toEqual(['Supplier', 'Name 1']);
  });
});
