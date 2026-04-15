const fs = require('fs');
const path = require('path');

const localesDir = path.join(__dirname, '..', 'apps', 'frontend', 'src', 'i18n', 'locales');

const newTranslations = {
  es: {
    supplyChain: { legendSupplier: 'Proveedor', legendOrganization: 'Organización', legendRisk: 'Riesgo', legendLow: 'Riesgo Bajo', legendMedium: 'Medio', legendHigh: 'Alto', legendCritical: 'Crítico (más grueso = mayor riesgo)' },
    common: { searchPlaceholder: 'Buscar páginas, proveedores, componentes...', noResults: 'Sin resultados para "{{query}}"', settings: 'Configuración', signOut: 'Cerrar sesión', overview: 'Resumen', supplyChainGroup: 'Cadena de Suministro', intelligence: 'Inteligencia', operations: 'Operaciones', noHeatmapData: 'Sin datos de mapa de calor', noRiskData: 'Sin datos de riesgo disponibles' },
    dashboard: { newAssessmentBtn: 'Nueva Evaluación', simulatorBtn: 'Simulador', procurementAgent: 'Agente de Compras', intelFeed: 'Noticias Intel', riskEvents: 'Eventos de Riesgo', componentsBtn: 'Componentes' }
  },
  fr: {
    supplyChain: { legendSupplier: 'Fournisseur', legendOrganization: 'Organisation', legendRisk: 'Risque', legendLow: 'Risque Faible', legendMedium: 'Moyen', legendHigh: 'Élevé', legendCritical: 'Critique (plus épais = risque plus élevé)' },
    common: { searchPlaceholder: 'Rechercher des pages, fournisseurs, composants...', noResults: 'Aucun résultat pour "{{query}}"', settings: 'Paramètres', signOut: 'Déconnexion', overview: 'Aperçu', supplyChainGroup: "Chaîne d'Approvisionnement", intelligence: 'Renseignement', operations: 'Opérations', noHeatmapData: 'Aucune donnée de carte thermique', noRiskData: 'Aucune donnée de risque disponible' },
    dashboard: { newAssessmentBtn: 'Nouvelle Évaluation', simulatorBtn: 'Simulateur', procurementAgent: "Agent d'Approvisionnement", intelFeed: 'Flux Intel', riskEvents: 'Événements de Risque', componentsBtn: 'Composants' }
  },
  de: {
    supplyChain: { legendSupplier: 'Lieferant', legendOrganization: 'Organisation', legendRisk: 'Risiko', legendLow: 'Geringes Risiko', legendMedium: 'Mittel', legendHigh: 'Hoch', legendCritical: 'Kritisch (dicker = höheres Risiko)' },
    common: { searchPlaceholder: 'Seiten, Lieferanten, Komponenten suchen...', noResults: 'Keine Ergebnisse für "{{query}}"', settings: 'Einstellungen', signOut: 'Abmelden', overview: 'Übersicht', supplyChainGroup: 'Lieferkette', intelligence: 'Intelligence', operations: 'Betrieb', noHeatmapData: 'Keine Heatmap-Daten', noRiskData: 'Keine Risikodaten verfügbar' },
    dashboard: { newAssessmentBtn: 'Neue Bewertung', simulatorBtn: 'Simulator', procurementAgent: 'Beschaffungsagent', intelFeed: 'Intel-Feed', riskEvents: 'Risikoereignisse', componentsBtn: 'Komponenten' }
  },
  pt: {
    supplyChain: { legendSupplier: 'Fornecedor', legendOrganization: 'Organização', legendRisk: 'Risco', legendLow: 'Risco Baixo', legendMedium: 'Médio', legendHigh: 'Alto', legendCritical: 'Crítico (mais espesso = maior risco)' },
    common: { searchPlaceholder: 'Buscar páginas, fornecedores, componentes...', noResults: 'Nenhum resultado para "{{query}}"', settings: 'Configurações', signOut: 'Sair', overview: 'Visão Geral', supplyChainGroup: 'Cadeia de Suprimentos', intelligence: 'Inteligência', operations: 'Operações', noHeatmapData: 'Sem dados de mapa de calor', noRiskData: 'Sem dados de risco disponíveis' },
    dashboard: { newAssessmentBtn: 'Nova Avaliação', simulatorBtn: 'Simulador', procurementAgent: 'Agente de Compras', intelFeed: 'Feed Intel', riskEvents: 'Eventos de Risco', componentsBtn: 'Componentes' }
  },
  zh: {
    supplyChain: { legendSupplier: '供应商', legendOrganization: '组织', legendRisk: '风险', legendLow: '低风险', legendMedium: '中等', legendHigh: '高', legendCritical: '严重（越粗 = 风险越高）' },
    common: { searchPlaceholder: '搜索页面、供应商、组件...', noResults: '未找到 "{{query}}" 的结果', settings: '设置', signOut: '退出登录', overview: '概览', supplyChainGroup: '供应链', intelligence: '情报', operations: '运营', noHeatmapData: '暂无热力图数据', noRiskData: '暂无风险数据' },
    dashboard: { newAssessmentBtn: '新建评估', simulatorBtn: '模拟器', procurementAgent: '采购代理', intelFeed: '情报订阅', riskEvents: '风险事件', componentsBtn: '组件' }
  },
  ja: {
    supplyChain: { legendSupplier: 'サプライヤー', legendOrganization: '組織', legendRisk: 'リスク', legendLow: '低リスク', legendMedium: '中', legendHigh: '高', legendCritical: 'クリティカル（太い=高リスク）' },
    common: { searchPlaceholder: 'ページ、サプライヤー、コンポーネントを検索...', noResults: '「{{query}}」の結果はありません', settings: '設定', signOut: 'ログアウト', overview: '概要', supplyChainGroup: 'サプライチェーン', intelligence: 'インテリジェンス', operations: 'オペレーション', noHeatmapData: 'ヒートマップデータなし', noRiskData: 'リスクデータなし' },
    dashboard: { newAssessmentBtn: '新規評価', simulatorBtn: 'シミュレーター', procurementAgent: '調達エージェント', intelFeed: 'インテルフィード', riskEvents: 'リスクイベント', componentsBtn: 'コンポーネント' }
  },
  ko: {
    supplyChain: { legendSupplier: '공급업체', legendOrganization: '조직', legendRisk: '리스크', legendLow: '저위험', legendMedium: '중간', legendHigh: '높음', legendCritical: '심각 (굵을수록 = 높은 위험)' },
    common: { searchPlaceholder: '페이지, 공급업체, 구성요소 검색...', noResults: '"{{query}}"에 대한 결과 없음', settings: '설정', signOut: '로그아웃', overview: '개요', supplyChainGroup: '공급망', intelligence: '인텔리전스', operations: '운영', noHeatmapData: '히트맵 데이터 없음', noRiskData: '리스크 데이터 없음' },
    dashboard: { newAssessmentBtn: '신규 평가', simulatorBtn: '시뮬레이터', procurementAgent: '조달 에이전트', intelFeed: '인텔 피드', riskEvents: '리스크 이벤트', componentsBtn: '구성요소' }
  },
  ar: {
    supplyChain: { legendSupplier: 'مورد', legendOrganization: 'منظمة', legendRisk: 'مخاطر', legendLow: 'مخاطر منخفضة', legendMedium: 'متوسط', legendHigh: 'مرتفع', legendCritical: 'حرج (أسمك = مخاطر أعلى)' },
    common: { searchPlaceholder: 'البحث في الصفحات والموردين والمكونات...', noResults: 'لا توجد نتائج لـ "{{query}}"', settings: 'الإعدادات', signOut: 'تسجيل الخروج', overview: 'نظرة عامة', supplyChainGroup: 'سلسلة التوريد', intelligence: 'الاستخبارات', operations: 'العمليات', noHeatmapData: 'لا توجد بيانات خريطة حرارية', noRiskData: 'لا توجد بيانات مخاطر' },
    dashboard: { newAssessmentBtn: 'تقييم جديد', simulatorBtn: 'المحاكي', procurementAgent: 'وكيل المشتريات', intelFeed: 'موجز الاستخبارات', riskEvents: 'أحداث المخاطر', componentsBtn: 'المكونات' }
  },
  hi: {
    supplyChain: { legendSupplier: 'आपूर्तिकर्ता', legendOrganization: 'संगठन', legendRisk: 'जोखिम', legendLow: 'कम जोखिम', legendMedium: 'मध्यम', legendHigh: 'उच्च', legendCritical: 'गंभीर (मोटा = अधिक जोखिम)' },
    common: { searchPlaceholder: 'पृष्ठ, आपूर्तिकर्ता, घटक खोजें...', noResults: '"{{query}}" के लिए कोई परिणाम नहीं', settings: 'सेटिंग्स', signOut: 'साइन आउट', overview: 'अवलोकन', supplyChainGroup: 'आपूर्ति श्रृंखला', intelligence: 'खुफिया', operations: 'संचालन', noHeatmapData: 'कोई हीटमैप डेटा नहीं', noRiskData: 'कोई जोखिम डेटा उपलब्ध नहीं' },
    dashboard: { newAssessmentBtn: 'नया मूल्यांकन', simulatorBtn: 'सिम्युलेटर', procurementAgent: 'प्रोक्योरमेंट एजेंट', intelFeed: 'इंटेल फ़ीड', riskEvents: 'जोखिम घटनाएं', componentsBtn: 'घटक' }
  },
  it: {
    supplyChain: { legendSupplier: 'Fornitore', legendOrganization: 'Organizzazione', legendRisk: 'Rischio', legendLow: 'Rischio Basso', legendMedium: 'Medio', legendHigh: 'Alto', legendCritical: 'Critico (più spesso = rischio più alto)' },
    common: { searchPlaceholder: 'Cerca pagine, fornitori, componenti...', noResults: 'Nessun risultato per "{{query}}"', settings: 'Impostazioni', signOut: 'Esci', overview: 'Panoramica', supplyChainGroup: 'Catena di Fornitura', intelligence: 'Intelligence', operations: 'Operazioni', noHeatmapData: 'Nessun dato mappa di calore', noRiskData: 'Nessun dato di rischio disponibile' },
    dashboard: { newAssessmentBtn: 'Nuova Valutazione', simulatorBtn: 'Simulatore', procurementAgent: 'Agente Acquisti', intelFeed: 'Feed Intel', riskEvents: 'Eventi di Rischio', componentsBtn: 'Componenti' }
  },
  nl: {
    supplyChain: { legendSupplier: 'Leverancier', legendOrganization: 'Organisatie', legendRisk: 'Risico', legendLow: 'Laag Risico', legendMedium: 'Gemiddeld', legendHigh: 'Hoog', legendCritical: 'Kritiek (dikker = hoger risico)' },
    common: { searchPlaceholder: "Zoek pagina's, leveranciers, componenten...", noResults: 'Geen resultaten voor "{{query}}"', settings: 'Instellingen', signOut: 'Uitloggen', overview: 'Overzicht', supplyChainGroup: 'Toeleveringsketen', intelligence: 'Inlichtingen', operations: 'Operaties', noHeatmapData: 'Geen heatmap-gegevens', noRiskData: 'Geen risicogegevens beschikbaar' },
    dashboard: { newAssessmentBtn: 'Nieuwe Beoordeling', simulatorBtn: 'Simulator', procurementAgent: 'Inkoopagent', intelFeed: 'Intel Feed', riskEvents: 'Risicogebeurtenissen', componentsBtn: 'Componenten' }
  }
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
