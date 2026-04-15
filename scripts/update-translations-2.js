const fs = require('fs');
const path = require('path');

const localesDir = path.join(__dirname, '..', 'apps', 'frontend', 'src', 'i18n', 'locales');

const newTranslations = {
  es: { common: { severityCritical: 'Crítico', severityHigh: 'Alto', severityMedium: 'Medio', severityLow: 'Bajo', supplierCount: '{{count}} proveedor(es)' } },
  fr: { common: { severityCritical: 'Critique', severityHigh: 'Élevé', severityMedium: 'Moyen', severityLow: 'Faible', supplierCount: '{{count}} fournisseur(s)' } },
  de: { common: { severityCritical: 'Kritisch', severityHigh: 'Hoch', severityMedium: 'Mittel', severityLow: 'Niedrig', supplierCount: '{{count}} Lieferant(en)' } },
  pt: { common: { severityCritical: 'Crítico', severityHigh: 'Alto', severityMedium: 'Médio', severityLow: 'Baixo', supplierCount: '{{count}} fornecedor(es)' } },
  zh: { common: { severityCritical: '严重', severityHigh: '高', severityMedium: '中等', severityLow: '低', supplierCount: '{{count}} 个供应商' } },
  ja: { common: { severityCritical: 'クリティカル', severityHigh: '高', severityMedium: '中', severityLow: '低', supplierCount: '{{count}} サプライヤー' } },
  ko: { common: { severityCritical: '심각', severityHigh: '높음', severityMedium: '중간', severityLow: '낮음', supplierCount: '{{count}} 공급업체' } },
  ar: { common: { severityCritical: 'حرج', severityHigh: 'مرتفع', severityMedium: 'متوسط', severityLow: 'منخفض', supplierCount: '{{count}} مورد(ين)' } },
  hi: { common: { severityCritical: 'गंभीर', severityHigh: 'उच्च', severityMedium: 'मध्यम', severityLow: 'कम', supplierCount: '{{count}} आपूर्तिकर्ता' } },
  it: { common: { severityCritical: 'Critico', severityHigh: 'Alto', severityMedium: 'Medio', severityLow: 'Basso', supplierCount: '{{count}} fornitore/i' } },
  nl: { common: { severityCritical: 'Kritiek', severityHigh: 'Hoog', severityMedium: 'Gemiddeld', severityLow: 'Laag', supplierCount: '{{count}} leverancier(s)' } },
};

for (const [lang, additions] of Object.entries(newTranslations)) {
  const filePath = path.join(localesDir, lang + '.json');
  const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));

  for (const [ns, keys] of Object.entries(additions)) {
    if (!data[ns]) data[ns] = {};
    Object.assign(data[ns], keys);
  }

  fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n');

  let total = 0;
  for (const ns of Object.keys(data)) total += Object.keys(data[ns]).length;
  console.log(`${lang}: ${total} keys`);
}

// Verify en.json
const en = JSON.parse(fs.readFileSync(path.join(localesDir, 'en.json'), 'utf8'));
let enTotal = 0;
for (const ns of Object.keys(en)) enTotal += Object.keys(en[ns]).length;
console.log(`en: ${enTotal} keys`);
