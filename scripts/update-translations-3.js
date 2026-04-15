const fs = require('fs');
const path = require('path');

const localesDir = path.join(__dirname, '..', 'apps', 'frontend', 'src', 'i18n', 'locales');

const newTranslations = {
  es: { supplyChain: { colSuppliers: 'PROVEEDORES', colOrganization: 'ORGANIZACIÓN', colRiskCategories: 'CATEGORÍAS DE RIESGO', riskScore: 'Riesgo: {{score}}/100', risks: '{{count}} riesgos', worstSeverity: 'Peor severidad', noSupplyChainData: 'Sin datos de cadena de suministro' } },
  fr: { supplyChain: { colSuppliers: 'FOURNISSEURS', colOrganization: 'ORGANISATION', colRiskCategories: 'CATÉGORIES DE RISQUE', riskScore: 'Risque: {{score}}/100', risks: '{{count}} risques', worstSeverity: 'Pire sévérité', noSupplyChainData: 'Aucune donnée de chaîne logistique' } },
  de: { supplyChain: { colSuppliers: 'LIEFERANTEN', colOrganization: 'ORGANISATION', colRiskCategories: 'RISIKOKATEGORIEN', riskScore: 'Risiko: {{score}}/100', risks: '{{count}} Risiken', worstSeverity: 'Höchste Schwere', noSupplyChainData: 'Keine Lieferkettendaten' } },
  pt: { supplyChain: { colSuppliers: 'FORNECEDORES', colOrganization: 'ORGANIZAÇÃO', colRiskCategories: 'CATEGORIAS DE RISCO', riskScore: 'Risco: {{score}}/100', risks: '{{count}} riscos', worstSeverity: 'Pior severidade', noSupplyChainData: 'Sem dados da cadeia de suprimentos' } },
  zh: { supplyChain: { colSuppliers: '供应商', colOrganization: '组织', colRiskCategories: '风险类别', riskScore: '风险: {{score}}/100', risks: '{{count}} 个风险', worstSeverity: '最高严重程度', noSupplyChainData: '暂无供应链数据' } },
  ja: { supplyChain: { colSuppliers: 'サプライヤー', colOrganization: '組織', colRiskCategories: 'リスクカテゴリ', riskScore: 'リスク: {{score}}/100', risks: '{{count}} 件のリスク', worstSeverity: '最悪の重大度', noSupplyChainData: 'サプライチェーンデータなし' } },
  ko: { supplyChain: { colSuppliers: '공급업체', colOrganization: '조직', colRiskCategories: '리스크 카테고리', riskScore: '리스크: {{score}}/100', risks: '{{count}} 개 리스크', worstSeverity: '최악의 심각도', noSupplyChainData: '공급망 데이터 없음' } },
  ar: { supplyChain: { colSuppliers: 'الموردون', colOrganization: 'المنظمة', colRiskCategories: 'فئات المخاطر', riskScore: 'المخاطر: {{score}}/100', risks: '{{count}} مخاطر', worstSeverity: 'أسوأ شدة', noSupplyChainData: 'لا توجد بيانات سلسلة توريد' } },
  hi: { supplyChain: { colSuppliers: 'आपूर्तिकर्ता', colOrganization: 'संगठन', colRiskCategories: 'जोखिम श्रेणियां', riskScore: 'जोखिम: {{score}}/100', risks: '{{count}} जोखिम', worstSeverity: 'सबसे खराब गंभीरता', noSupplyChainData: 'कोई आपूर्ति श्रृंखला डेटा नहीं' } },
  it: { supplyChain: { colSuppliers: 'FORNITORI', colOrganization: 'ORGANIZZAZIONE', colRiskCategories: 'CATEGORIE DI RISCHIO', riskScore: 'Rischio: {{score}}/100', risks: '{{count}} rischi', worstSeverity: 'Peggiore gravità', noSupplyChainData: 'Nessun dato della catena di fornitura' } },
  nl: { supplyChain: { colSuppliers: 'LEVERANCIERS', colOrganization: 'ORGANISATIE', colRiskCategories: 'RISICOCATEGORIEËN', riskScore: 'Risico: {{score}}/100', risks: '{{count}} risico\'s', worstSeverity: 'Ergste ernst', noSupplyChainData: 'Geen toeleveringsketengegevens' } },
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

const en = JSON.parse(fs.readFileSync(path.join(localesDir, 'en.json'), 'utf8'));
let enTotal = 0;
for (const ns of Object.keys(en)) enTotal += Object.keys(en[ns]).length;
console.log(`en: ${enTotal} keys`);
