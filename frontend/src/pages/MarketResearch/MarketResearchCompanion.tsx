import { useState, useMemo, useEffect } from 'react';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend, ComposedChart, Area
} from 'recharts';
import {
  Download, FileText, Edit3, Plus, Trash2, X, Search, Building2, Globe, TrendingUp, DollarSign, Target, MessageCircle, Send
} from 'lucide-react';
import { BLUE, TEAL, RED, GREEN, YELLOW, TEXT, BORDER, BG, CHART_COLORS } from '../../constants/theme';
import { ChartCard } from '../../components/ui/ChartCard';
import type { CustomerTableData, CompanyProfile } from '../../types';
import { MarketResearchService } from '../../services/marketResearch.service';
import { StatusBanner } from '../../components/common/StatusBanner';

const card = {
  background: 'white',
  border: `1px solid ${BORDER}`,
  borderRadius: 12,
  boxShadow: '0 2px 8px rgba(31,95,168,0.06)',
};

export function MarketResearchCompanion() {
  const [geography, setGeography] = useState<Record<string, string[]>>({});
  const [showGeographyEditor, setShowGeographyEditor] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState<string | null>(null);
  const [selectedCompanyData, setSelectedCompanyData] = useState<any | null>(null);

  // Filters
  const [selectedRegion, setSelectedRegion] = useState<string>('All');
  const [selectedCountry, setSelectedCountry] = useState<string>('All');
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [selectedProduct, setSelectedProduct] = useState<string>('All');
  const [selectedApplication, setSelectedApplication] = useState<string>('All');
  const [selectedYear, setSelectedYear] = useState<string>('2026');
  const [selectedUnit, setSelectedUnit] = useState<string>('MT');

  const [searchTerm, setSearchTerm] = useState('');
  const [sortColumn, setSortColumn] = useState<string>('');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');

  // Editable cells
  const [editingCell, setEditingCell] = useState<{ rowIndex: number; column: string } | null>(null);
  const [editValue, setEditValue] = useState('');
  const [tableData, setTableData] = useState<any[]>([]);

  // Customer Intelligence Database table data
  const [customerTableData, setCustomerTableData] = useState<CustomerTableData[]>([]);

  // Chatbot states
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const [chatInput, setChatInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('');

  // Phase 1: Market Research APIs not available — auto-load empty datasets
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Loaded metadata structures
  const [categoriesMap, setCategoriesMap] = useState<Record<string, string[]>>({});
  const [applicationsMap, setApplicationsMap] = useState<Record<string, string[]>>({});
  const [companyProfiles, setCompanyProfiles] = useState<Record<string, CompanyProfile>>({});
  const [referenceSources, setReferenceSources] = useState<string[]>([]);
  const [supplierLocations, setSupplierLocations] = useState<Record<string, string>>({});
  const [competitors, setCompetitors] = useState<string[]>([]);
  const [regionCompetitors, setRegionCompetitors] = useState<Record<string, string[]>>({});
  const [priceTrendData, setPriceTrendData] = useState<any[]>([]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [
        geo,
        cats,
        apps,
        profs,
        refs,
        sups,
        comps,
        regComps,
        pTrend,
      ] = await Promise.all([
        MarketResearchService.getGeography(),
        MarketResearchService.getCategories(),
        MarketResearchService.getApplications(),
        MarketResearchService.getCompanyProfiles(),
        MarketResearchService.getReferenceSources(),
        MarketResearchService.getSupplierLocations(),
        MarketResearchService.getCompetitors(),
        MarketResearchService.getRegionCompetitors(),
        MarketResearchService.getPriceTrendData(),
      ]);

      setGeography(geo);
      setCategoriesMap(cats);
      setApplicationsMap(apps);
      setCompanyProfiles(profs);
      setReferenceSources(refs);
      setSupplierLocations(sups);
      setCompetitors(comps);
      setRegionCompetitors(regComps);
      setPriceTrendData(pTrend);

      setLoaded(true);
      setError('Market Research APIs are not available in Phase 1. This page will connect when backend endpoints are added.');
    } catch (err) {
      setLoaded(false);
      setError(err instanceof Error ? err.message : 'Failed to load market research companion data');
    } finally {
      setLoading(false);
    }
  };

  // Auto-load data on component mount
  useEffect(() => {
    loadData();
  }, []);

  // Generate table data based on filters
  useEffect(() => {
    if (!loaded) return;

    const runFilter = async () => {
      const allCustomers = await MarketResearchService.getComprehensiveCustomers();
      let filteredCustomers = [...allCustomers];

      if (selectedRegion !== 'All') {
        filteredCustomers = filteredCustomers.filter(c => c.region === selectedRegion);
      }
      if (selectedCountry !== 'All') {
        filteredCustomers = filteredCustomers.filter(c => c.country === selectedCountry);
      }
      if (selectedCategory !== 'All') {
        filteredCustomers = filteredCustomers.filter(c => c.category === selectedCategory);
      }
      if (selectedProduct !== 'All') {
        filteredCustomers = filteredCustomers.filter(c => c.product === selectedProduct);
      }
      if (selectedApplication !== 'All') {
        filteredCustomers = filteredCustomers.filter(c => c.application === selectedApplication);
      }

      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        filteredCustomers = filteredCustomers.filter(
          c =>
            c.name.toLowerCase().includes(term) ||
            c.product.toLowerCase().includes(term) ||
            c.application.toLowerCase().includes(term) ||
            c.country.toLowerCase().includes(term)
        );
      }

      let data = filteredCustomers.map((customer) => ({
        ...customer,
        annualDemand: 0,
        currentSupplier: '—',
        supplierLocation: '—',
        competitorShare: 0,
        price: 0,
        currentGrade: '—',
        suggestedGrade: '—',
        fitScore: 0,
        referenceNames: '—',
        entryPotential: 'Low',
      }));

      // Sorting
      if (sortColumn) {
        data.sort((a, b) => {
          let aVal = a[sortColumn as keyof typeof a];
          let bVal = b[sortColumn as keyof typeof b];

          if (typeof aVal === 'string') aVal = aVal.toLowerCase();
          if (typeof bVal === 'string') bVal = bVal.toLowerCase();

          if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
          if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
          return 0;
        });
      }

      setTableData(data);
    };

    runFilter();
  }, [loaded, selectedRegion, selectedCountry, selectedCategory, selectedProduct, selectedApplication, searchTerm, sortColumn, sortDirection, competitors, supplierLocations, referenceSources]);

  // Update Customer Intelligence Database table data
  useEffect(() => {
    if (!loaded) return;
    const compsList = regionCompetitors[selectedRegion] || [];
    const runFilterCustInt = async () => {
      const allCustomers = await MarketResearchService.getComprehensiveCustomers();
      const customers = allCustomers.filter(
        c =>
          (selectedRegion === 'All' || c.region === selectedRegion) &&
          (selectedProduct === 'All' || c.product === selectedProduct) &&
          (selectedApplication === 'All' || c.application === selectedApplication)
      );

      const generated = customers.slice(0, 8).map((customer, index) => {
        const competitorSales: { [key: string]: number } = {};
        compsList.forEach(comp => {
          competitorSales[comp] = 0;
        });
        return {
          srNo: index + 1,
          customerName: customer.name,
          product: customer.product,
          application: customer.application,
          apcotexSale: 0,
          competitorSales,
          totalConsumption: 0,
          remark: '—',
          confidenceScore: 0,
          referenceName: '—',
          entryPotential: 'Low' as const,
        };
      });

      setCustomerTableData(generated);
    };

    runFilterCustInt();
  }, [loaded, selectedRegion, selectedProduct, selectedApplication, regionCompetitors]);

  const availableCountries = useMemo(() => {
    if (!loaded) return [];
    return selectedRegion === 'All'
      ? Object.values(geography).flat()
      : geography[selectedRegion] || [];
  }, [loaded, selectedRegion, geography]);

  const availableProducts = useMemo(() => {
    if (!loaded) return [];
    return selectedCategory === 'All'
      ? Object.values(categoriesMap).flat()
      : categoriesMap[selectedCategory] || [];
  }, [loaded, selectedCategory, categoriesMap]);

  const availableApplications = useMemo(() => {
    if (!loaded) return [];
    return selectedProduct === 'All'
      ? Object.values(applicationsMap).flat()
      : applicationsMap[selectedProduct] || [];
  }, [loaded, selectedProduct, applicationsMap]);

  // Get current competitors based on selected region
  const currentCompetitors = useMemo(() => {
    if (!loaded) return [];
    return regionCompetitors[selectedRegion] || [];
  }, [loaded, selectedRegion, regionCompetitors]);

  // Calculate totals for Customer Intelligence Database
  const customerTotals = useMemo(() => {
    return customerTableData.reduce(
      (acc, row) => {
        acc.apcotexSale += row.apcotexSale;
        acc.totalConsumption += row.totalConsumption;

        currentCompetitors.forEach(competitor => {
          acc.competitorSales[competitor] = (acc.competitorSales[competitor] || 0) + (row.competitorSales[competitor] || 0);
        });

        return acc;
      },
      {
        apcotexSale: 0,
        totalConsumption: 0,
        competitorSales: {} as { [key: string]: number },
      }
    );
  }, [customerTableData, currentCompetitors]);

  // Chart data based on filtered results
  const demandTrendData = useMemo(() => {
    const sumDemand = tableData.reduce((sum, r) => sum + r.annualDemand, 0);
    return [
      { year: '2022', demand: Math.floor(sumDemand * 0.75) },
      { year: '2023', demand: Math.floor(sumDemand * 0.85) },
      { year: '2024', demand: Math.floor(sumDemand * 0.92) },
      { year: '2025', demand: Math.floor(sumDemand * 0.97) },
      { year: '2026', demand: sumDemand },
    ];
  }, [tableData]);

  const competitorShareData = useMemo(() => {
    return competitors.slice(0, 6).map(name => ({
      name,
      share: 0,
    }));
  }, [competitors]);

  const topCustomersData = useMemo(() => {
    return [...tableData]
      .sort((a, b) => b.annualDemand - a.annualDemand)
      .slice(0, 8)
      .map(c => ({ name: c.name.substring(0, 18), demand: c.annualDemand }));
  }, [tableData]);

  const countryHeatmapData = useMemo(() => {
    return Array.from(new Set(tableData.map(r => r.country)))
      .slice(0, 10)
      .map(country => ({
        country,
        demand: tableData.filter(r => r.country === country).reduce((sum, r) => sum + r.annualDemand, 0),
      }));
  }, [tableData]);

  const opportunityFunnelData = useMemo(() => {
    return [
      { stage: 'Total Prospects', value: tableData.length },
      { stage: 'High Fit Score', value: tableData.filter(r => r.fitScore >= 80).length },
      { stage: 'High Entry Potential', value: tableData.filter(r => r.entryPotential === 'High').length },
      { stage: 'Immediate Targets', value: tableData.filter(r => r.entryPotential === 'High' && r.fitScore >= 85).length },
    ];
  }, [tableData]);

  const downloadExcel = () => {
    const headers = [
      'Customer/Distributor',
      'Region',
      'Country',
      'Category',
      'Product',
      'Application Segment',
      `Annual Demand (${selectedUnit})`,
      'Current Supplier',
      'Supplier Location',
      'Competitor Share %',
      'Price USD/MT',
      'Current Grade',
      'Suggested Grade',
      'Confidence Score',
      'Reference Names',
      'Entry Potential',
    ];

    const csvContent = [
      headers.join(','),
      ...tableData.map(row =>
        [
          `"${row.name}"`,
          row.region,
          row.country,
          `"${row.category}"`,
          row.product,
          `"${row.application}"`,
          row.annualDemand,
          row.currentSupplier,
          row.supplierLocation,
          row.competitorShare,
          row.price,
          row.currentGrade,
          row.suggestedGrade,
          row.fitScore,
          `"${row.referenceNames}"`,
          row.entryPotential,
        ].join(',')
      ),
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `Market_Research_Data_${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const downloadReport = () => {
    const reportContent = `Market Research Companion Report
Generated: ${new Date().toLocaleDateString()}

Filters Applied:
- Region: ${selectedRegion}
- Country: ${selectedCountry}
- Category: ${selectedCategory}
- Product: ${selectedProduct}
- Application: ${selectedApplication}
- Year: ${selectedYear}
- Unit: ${selectedUnit}

Total Records: ${tableData.length}

Customer Intelligence Database:
${tableData
  .map(
    (row, i) => `
${i + 1}. ${row.name}
   Region: ${row.region} | Country: ${row.country}
   Category: ${row.category} | Product: ${row.product}
   Application: ${row.application}
   Annual Demand: ${row.annualDemand} ${selectedUnit}
   Current Supplier: ${row.currentSupplier}
   Competitor Share: ${row.competitorShare}%
   Price: $${row.price}/MT
   Current Grade: ${row.currentGrade}
   Suggested Grade: ${row.suggestedGrade}
   Fit Score: ${row.fitScore}%
   Entry Potential: ${row.entryPotential}
`
  )
  .join('\n')}`;

    const blob = new Blob([reportContent], { type: 'text/plain;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `Market_Research_Report_${new Date().toISOString().split('T')[0]}.txt`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleChatSubmit = (question: string) => {
    if (!question.trim()) return;

    setChatMessages([...chatMessages, { role: 'user', content: question }]);
    setChatInput('');
    setIsLoading(true);

    const loadingMessages = [
      'Agent searching market data...',
      'Analyzing filtered records...',
      'Comparing suppliers...',
      'Ranking opportunities...',
      'Building summary...',
    ];
    setLoadingMessage(loadingMessages[0] || 'Thinking…');

    setTimeout(() => {
      const response = generateChatResponse(question.toLowerCase());
      setChatMessages(prev => [...prev, { role: 'assistant', content: response }]);
      setIsLoading(false);
    }, 2000);
  };

  const generateChatResponse = (question: string): string => {
    if (question.includes('top') && (question.includes('customer') || question.includes('5')) && question.includes('demand')) {
      const topCustomers = [...tableData].sort((a, b) => b.annualDemand - a.annualDemand).slice(0, 5);
      return topCustomers.map((c, i) => `${i + 1}. ${c.name} – ${c.annualDemand.toLocaleString()} MT`).join('\n');
    }

    if (question.includes('best') && (question.includes('entry') || question.includes('opportunit'))) {
      const highOpportunities = tableData.filter(c => c.entryPotential === 'High').slice(0, 4);
      return `Top opportunities based on fit score and pricing:\n${highOpportunities.map((c, i) => `${i + 1}. ${c.name} – ${c.entryPotential}`).join('\n')}`;
    }

    if (question.includes('basf') && question.includes('share')) {
      return 'BASF currently leads selected dataset with estimated 34% share, followed by Synthomer at 22% and Trinseo at 17%.';
    }

    if (question.includes('summar')) {
      return 'The selected market shows strong demand in paper coating and industrial rubber segments. Import dependency remains high, creating entry potential for alternative suppliers. Average pricing remains stable with moderate growth outlook.';
    }

    if (question.includes('highest') && question.includes('price')) {
      const highestPrice = [...tableData].sort((a, b) => b.price - a.price).slice(0, 3);
      return highestPrice.map((c, i) => `${i + 1}. ${c.name} – $${c.price}/MT`).join('\n');
    }

    if (question.includes('compare') && question.includes('supplier')) {
      return 'BASF leads in premium grades and pricing. Synthomer is strong in latex volume segments. Trinseo is competitive in rubber applications. Local suppliers compete on price.';
    }

    if (question.includes('customer') && question.includes('apx')) {
      const highFit = tableData.filter(c => c.fitScore >= 80).slice(0, 3);
      return `Best matches for APX series grades:\n${highFit.map((c, i) => `${i + 1}. ${c.name} – Fit Score ${c.fitScore}%`).join('\n')}`;
    }

    if (question.includes('low') && question.includes('competition')) {
      const lowCompetition = tableData.filter(c => c.competitorShare < 40).slice(0, 4);
      return `Low competition opportunities:\n${lowCompetition.map((c, i) => `${i + 1}. ${c.name} – ${c.competitorShare}% competitor share`).join('\n')}`;
    }

    return 'Based on current filtered data, I recommend narrowing by region, product, or application for sharper insights.';
  };

  const handleCellDoubleClick = (rowIndex: number, column: string, currentValue: any) => {
    setEditingCell({ rowIndex, column });
    setEditValue(String(currentValue));
  };

  const handleCellEdit = (rowIndex: number, column: string) => {
    const updatedData = [...tableData];
    updatedData[rowIndex][column] =
      column === 'annualDemand' || column === 'competitorShare' || column === 'price' || column === 'fitScore'
        ? parseInt(editValue) || 0
        : editValue;

    if (column === 'fitScore') {
      const fitScore = parseInt(editValue) || 0;
      if (fitScore >= 80) updatedData[rowIndex].entryPotential = 'High';
      else if (fitScore >= 61) updatedData[rowIndex].entryPotential = 'Medium';
      else updatedData[rowIndex].entryPotential = 'Low';
    }

    setTableData(updatedData);
    setEditingCell(null);
  };

  const renderEditableCell = (rowIndex: number, column: string, value: any, style: any) => {
    const isEditing = editingCell?.rowIndex === rowIndex && editingCell?.column === column;

    if (isEditing) {
      return (
        <input
          autoFocus
          type="text"
          value={editValue}
          onChange={e => setEditValue(e.target.value)}
          onBlur={() => handleCellEdit(rowIndex, column)}
          onKeyDown={e => {
            if (e.key === 'Enter') handleCellEdit(rowIndex, column);
            if (e.key === 'Escape') setEditingCell(null);
          }}
          style={{
            width: '100%',
            padding: '6px 8px',
            fontSize: '0.8125rem',
            border: `2px solid ${TEAL}`,
            borderRadius: 4,
            outline: 'none',
            background: 'white',
          }}
        />
      );
    }

    return (
      <span onDoubleClick={() => handleCellDoubleClick(rowIndex, column, value)} style={{ cursor: 'text', ...style }}>
        {value}
      </span>
    );
  };

  return (
    <div style={{ padding: '28px 32px 32px', background: BG, minHeight: '100vh' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: TEXT, marginBottom: 6 }}>Market Research Companion</h1>
        <p style={{ fontSize: '0.875rem', color: '#6B7280' }}>View, analyze, and download market intelligence reports</p>
      </div>

      <StatusBanner loading={loading} error={error} onRetry={loadData} loadingText="Loading companion…" />

      {loaded && (
        <>
          {/* Filter Bar */}
          <div style={{ ...card, padding: '20px 24px', marginBottom: 20 }}>
            <div className="grid grid-cols-7 gap-3 mb-3">
              <FilterDropdown label="Region" value={selectedRegion} onChange={setSelectedRegion} options={['All', ...Object.keys(geography)]} />
              <FilterDropdown label="Country" value={selectedCountry} onChange={setSelectedCountry} options={['All', ...availableCountries]} />
              <FilterDropdown label="Category" value={selectedCategory} onChange={setSelectedCategory} options={['All', ...Object.keys(categoriesMap)]} />
              <FilterDropdown label="Product" value={selectedProduct} onChange={setSelectedProduct} options={['All', ...availableProducts]} />
              <FilterDropdown label="Application" value={selectedApplication} onChange={setSelectedApplication} options={['All', ...availableApplications]} />
              <FilterDropdown label="Year" value={selectedYear} onChange={setSelectedYear} options={['2024', '2025', '2026']} />
              <FilterDropdown label="Unit" value={selectedUnit} onChange={setSelectedUnit} options={['MT', 'KT', 'USD Mn']} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setShowGeographyEditor(true)}
                style={{
                  padding: '7px 14px',
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  color: BLUE,
                  background: 'white',
                  border: `1px solid ${BORDER}`,
                  borderRadius: 6,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                <Edit3 size={14} />
                Edit Geography
              </button>
            </div>
          </div>

          {/* Search and Actions */}
          <div style={{ ...card, padding: '16px 20px', marginBottom: 20, display: 'flex', gap: 14, alignItems: 'center' }}>
            <div style={{ flex: 1, position: 'relative' }}>
              <Search size={15} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#9CA3AF' }} />
              <input
                type="text"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                placeholder="Search Customer / Product / Segment / Competitor / Country"
                style={{
                  width: '100%',
                  height: 38,
                  paddingLeft: 38,
                  paddingRight: 14,
                  border: `1px solid ${BORDER}`,
                  borderRadius: 6,
                  fontSize: '0.8125rem',
                  color: TEXT,
                  background: '#F9FAFB',
                  outline: 'none',
                }}
              />
            </div>
            <ActionButton icon={<Download size={15} />} label="Download" onClick={downloadReport} />
            <ActionButton icon={<FileText size={15} />} label="Export Excel" onClick={downloadExcel} />
          </div>

          {/* Main Table */}
          <div style={{ ...card, marginBottom: 24, overflow: 'hidden' }}>
            <div style={{ padding: '18px 22px', borderBottom: `1px solid ${BORDER}` }}>
              <h2 style={{ fontSize: '1.0625rem', fontWeight: 600, color: TEXT }}>Customer Intelligence Database</h2>
              <p style={{ fontSize: '0.875rem', color: '#6B7280', marginTop: 4 }}>
                {customerTableData.length} customers matching your criteria • Dynamic competitor columns based on {selectedRegion} region
              </p>
            </div>
            <div style={{ overflowX: 'auto', maxHeight: 600, overflowY: 'auto' }}>
              <table
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: '0.8125rem',
                  minWidth: '1200px',
                  tableLayout: 'auto',
                }}
              >
                <thead style={{ position: 'sticky', top: 0, background: BG, zIndex: 10 }}>
                  <tr style={{ background: BG }}>
                    <th
                      style={{
                        padding: '12px 8px',
                        textAlign: 'center',
                        border: `1px solid ${BORDER}`,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: BLUE,
                        minWidth: '80px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Sr. No.
                    </th>
                    <th
                      style={{
                        padding: '12px 8px',
                        textAlign: 'left',
                        border: `1px solid ${BORDER}`,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: BLUE,
                        minWidth: '150px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Customer Name
                    </th>
                    <th
                      style={{
                        padding: '12px 8px',
                        textAlign: 'left',
                        border: `1px solid ${BORDER}`,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: BLUE,
                        minWidth: '120px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Product
                    </th>
                    <th
                      style={{
                        padding: '12px 8px',
                        textAlign: 'left',
                        border: `1px solid ${BORDER}`,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: BLUE,
                        minWidth: '140px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Application
                    </th>
                    <th
                      style={{
                        padding: '12px 8px',
                        textAlign: 'center',
                        border: `1px solid ${BORDER}`,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: BLUE,
                        minWidth: '140px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Apcotex Sale ({selectedUnit}) FY24-25
                    </th>

                    <th
                      colSpan={currentCompetitors.length}
                      style={{
                        padding: '12px 8px',
                        textAlign: 'center',
                        border: `1px solid ${BORDER}`,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: BLUE,
                        background: '#F0F9FF',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Competitor's Sale ({selectedUnit}) FY24-25
                    </th>

                    <th
                      style={{
                        padding: '12px 8px',
                        textAlign: 'center',
                        border: `1px solid ${BORDER}`,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: BLUE,
                        minWidth: '140px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Total Consumption ({selectedUnit}) FY24-25
                    </th>
                    <th
                      style={{
                        padding: '12px 8px',
                        textAlign: 'left',
                        border: `1px solid ${BORDER}`,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: BLUE,
                        minWidth: '120px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Remark
                    </th>
                    <th
                      style={{
                        padding: '12px 8px',
                        textAlign: 'center',
                        border: `1px solid ${BORDER}`,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: BLUE,
                        minWidth: '120px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Confidence Score
                    </th>
                    <th
                      style={{
                        padding: '12px 8px',
                        textAlign: 'left',
                        border: `1px solid ${BORDER}`,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: BLUE,
                        minWidth: '120px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Reference Name
                    </th>
                    <th
                      style={{
                        padding: '12px 8px',
                        textAlign: 'center',
                        border: `1px solid ${BORDER}`,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: BLUE,
                        minWidth: '100px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Entry Potential
                    </th>
                  </tr>

                  <tr style={{ background: BG }}>
                    <td style={{ padding: '8px', border: `1px solid ${BORDER}`, background: '#F9FAFB' }}></td>
                    <td style={{ padding: '8px', border: `1px solid ${BORDER}`, background: '#F9FAFB' }}></td>
                    <td style={{ padding: '8px', border: `1px solid ${BORDER}`, background: '#F9FAFB' }}></td>
                    <td style={{ padding: '8px', border: `1px solid ${BORDER}`, background: '#F9FAFB' }}></td>
                    <td style={{ padding: '8px', border: `1px solid ${BORDER}`, background: '#F9FAFB' }}></td>

                    {currentCompetitors.map(competitor => (
                      <th
                        key={competitor}
                        style={{
                          padding: '8px 6px',
                          textAlign: 'center',
                          border: `1px solid ${BORDER}`,
                          fontSize: '0.7rem',
                          fontWeight: 600,
                          color: BLUE,
                          minWidth: '140px',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {competitor}
                      </th>
                    ))}

                    <td style={{ padding: '8px', border: `1px solid ${BORDER}`, background: '#F9FAFB' }}></td>
                    <td style={{ padding: '8px', border: `1px solid ${BORDER}`, background: '#F9FAFB' }}></td>
                    <td style={{ padding: '8px', border: `1px solid ${BORDER}`, background: '#F9FAFB' }}></td>
                    <td style={{ padding: '8px', border: `1px solid ${BORDER}`, background: '#F9FAFB' }}></td>
                  </tr>
                </thead>

                <tbody>
                  {customerTableData.map((row, index) => (
                    <tr key={row.srNo} style={{ background: index % 2 === 0 ? 'white' : '#F9FAFB' }}>
                      <td style={{ padding: '10px 8px', textAlign: 'center', border: `1px solid ${BORDER}`, color: TEXT, fontWeight: 500, whiteSpace: 'nowrap' }}>
                        {row.srNo}
                      </td>
                      <td
                        onClick={() => {
                          setSelectedCompany(row.customerName);
                          setSelectedCompanyData(row);
                        }}
                        style={{ padding: '10px 8px', border: `1px solid ${BORDER}`, color: BLUE, cursor: 'pointer', fontWeight: 600, whiteSpace: 'nowrap' }}
                      >
                        {row.customerName}
                      </td>
                      <td style={{ padding: '10px 8px', border: `1px solid ${BORDER}`, color: TEXT, whiteSpace: 'nowrap' }}>{row.product}</td>
                      <td style={{ padding: '10px 8px', border: `1px solid ${BORDER}`, color: TEXT, whiteSpace: 'nowrap' }}>{row.application}</td>
                      <td style={{ padding: '10px 8px', textAlign: 'center', border: `1px solid ${BORDER}`, color: TEXT, fontWeight: 600, whiteSpace: 'nowrap' }}>
                        {row.apcotexSale.toLocaleString()}
                      </td>

                      {currentCompetitors.map(competitor => (
                        <td key={competitor} style={{ padding: '10px 6px', textAlign: 'center', border: `1px solid ${BORDER}`, color: TEXT, whiteSpace: 'nowrap' }}>
                          {row.competitorSales[competitor]?.toLocaleString() || 0}
                        </td>
                      ))}

                      <td
                        style={{
                          padding: '10px 8px',
                          textAlign: 'center',
                          border: `1px solid ${BORDER}`,
                          color: TEXT,
                          fontWeight: 600,
                          background: '#FFF9E6',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {row.totalConsumption.toLocaleString()}
                      </td>
                      <td style={{ padding: '10px 8px', border: `1px solid ${BORDER}`, color: TEXT, fontSize: '0.75rem', whiteSpace: 'nowrap' }}>{row.remark}</td>
                      <td style={{ padding: '10px 8px', textAlign: 'center', border: `1px solid ${BORDER}`, color: TEXT, fontWeight: 600, whiteSpace: 'nowrap' }}>
                        {row.confidenceScore}%
                      </td>
                      <td style={{ padding: '10px 8px', border: `1px solid ${BORDER}`, color: TEXT, fontSize: '0.75rem', whiteSpace: 'nowrap' }}>{row.referenceName}</td>
                      <td style={{ padding: '10px 8px', border: `1px solid ${BORDER}`, textAlign: 'center' }}>
                        <span
                          style={{
                            padding: '4px 10px',
                            borderRadius: 12,
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            background:
                              row.entryPotential === 'High'
                                ? 'rgba(16,185,129,0.1)'
                                : row.entryPotential === 'Medium'
                                ? 'rgba(245,158,11,0.1)'
                                : 'rgba(217,58,47,0.1)',
                            color: row.entryPotential === 'High' ? GREEN : row.entryPotential === 'Medium' ? YELLOW : RED,
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {row.entryPotential}
                        </span>
                      </td>
                    </tr>
                  ))}

                  <tr style={{ background: '#F0F9FF', fontWeight: 700 }}>
                    <td style={{ padding: '10px 8px', textAlign: 'center', border: `1px solid ${BORDER}`, color: TEXT, whiteSpace: 'nowrap' }}>TOTAL</td>
                    <td style={{ padding: '10px 8px', border: `1px solid ${BORDER}`, color: TEXT }}></td>
                    <td style={{ padding: '10px 8px', border: `1px solid ${BORDER}`, color: TEXT }}></td>
                    <td style={{ padding: '10px 8px', border: `1px solid ${BORDER}`, color: TEXT }}></td>
                    <td style={{ padding: '10px 8px', textAlign: 'center', border: `1px solid ${BORDER}`, color: TEXT, whiteSpace: 'nowrap' }}>
                      {customerTotals.apcotexSale.toLocaleString()}
                    </td>

                    {currentCompetitors.map(competitor => (
                      <td key={competitor} style={{ padding: '10px 6px', textAlign: 'center', border: `1px solid ${BORDER}`, color: TEXT, whiteSpace: 'nowrap' }}>
                        {customerTotals.competitorSales[competitor]?.toLocaleString() || 0}
                      </td>
                    ))}

                    <td
                      style={{
                        padding: '10px 8px',
                        textAlign: 'center',
                        border: `1px solid ${BORDER}`,
                        color: TEXT,
                        background: '#FFF3CD',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {customerTotals.totalConsumption.toLocaleString()}
                    </td>
                    <td style={{ padding: '10px 8px', border: `1px solid ${BORDER}`, color: TEXT }}></td>
                    <td style={{ padding: '10px 8px', border: `1px solid ${BORDER}`, color: TEXT }}></td>
                    <td style={{ padding: '10px 8px', border: `1px solid ${BORDER}`, color: TEXT }}></td>
                    <td style={{ padding: '10px 8px', border: `1px solid ${BORDER}`, color: TEXT }}></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Charts Section */}
          <div className="grid grid-cols-2 gap-5 mb-5">
            <ChartCard title="Demand Trend by Year" subtitle={`Historical and projected demand in ${selectedUnit}`}>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={demandTrendData}>
                  <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={value => `${value} ${selectedUnit}`} />
                  <Line type="monotone" dataKey="demand" stroke={BLUE} strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Competitor Market Share" subtitle="Distribution across suppliers">
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={competitorShareData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={entry => `${entry.name} ${entry.share}%`}
                    outerRadius={85}
                    fill="#8884d8"
                    dataKey="share"
                    nameKey="name"
                  >
                    {competitorShareData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={[BLUE, TEAL, '#60A5FA', '#34D399', '#A78BFA', '#E5E7EB'][index]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          <div className="grid grid-cols-2 gap-5 mb-5">
            <ChartCard title="Top Customers by Demand" subtitle={`Annual consumption in ${selectedUnit}`}>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={topCustomersData} layout="vertical">
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="name" type="category" tick={{ fontSize: 10 }} width={120} />
                  <Tooltip formatter={value => `${value} ${selectedUnit}`} />
                  <Bar dataKey="demand" fill={TEAL} radius={[0, 6, 6, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Price Movement Trend" subtitle="Monthly price range (USD/MT)">
              <ResponsiveContainer width="100%" height={280}>
                <ComposedChart data={priceTrendData}>
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Area type="monotone" dataKey="high" fill={BLUE} fillOpacity={0.1} stroke="none" />
                  <Area type="monotone" dataKey="low" fill={BLUE} fillOpacity={0.1} stroke="none" />
                  <Line type="monotone" dataKey="open" stroke={BLUE} strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="close" stroke={TEAL} strokeWidth={2} dot={{ r: 3 }} />
                  <Legend />
                </ComposedChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          <div className="grid grid-cols-2 gap-5">
            <ChartCard title="Country Demand Heatmap" subtitle={`Top markets by ${selectedUnit}`}>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={countryHeatmapData}>
                  <XAxis dataKey="country" tick={{ fontSize: 10 }} angle={-15} textAnchor="end" height={80} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={value => `${value} ${selectedUnit}`} />
                  <Bar dataKey="demand" fill={GREEN} radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Market Opportunity Funnel" subtitle="Customer segmentation by potential">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={opportunityFunnelData} layout="vertical">
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="stage" type="category" tick={{ fontSize: 10 }} width={140} />
                  <Tooltip />
                  <Bar dataKey="value" fill={BLUE} radius={[0, 6, 6, 0]}>
                    {opportunityFunnelData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={[BLUE, TEAL, GREEN, RED][index]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          {/* Company Profile Panel */}
          {selectedCompany && (
            <CompanyProfilePanel
              company={selectedCompany}
              profile={companyProfiles[selectedCompany]}
              companyData={selectedCompanyData}
              onClose={() => {
                setSelectedCompany(null);
                setSelectedCompanyData(null);
              }}
            />
          )}

          {/* Geography Editor Modal */}
          {showGeographyEditor && (
            <GeographyEditorModal
              geography={geography}
              onSave={(newGeography: typeof geography) => {
                setGeography(newGeography);
                setShowGeographyEditor(false);
              }}
              onClose={() => setShowGeographyEditor(false)}
            />
          )}

          {/* Floating Chat Button */}
          {!isChatOpen && (
            <button
              onClick={() => setIsChatOpen(true)}
              style={{
                position: 'fixed',
                bottom: 32,
                right: 32,
                width: 64,
                height: 64,
                borderRadius: '50%',
                background: `linear-gradient(135deg, ${TEAL} 0%, ${BLUE} 100%)`,
                border: 'none',
                boxShadow: '0 8px 24px rgba(31,183,181,0.3)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 999,
                transition: 'transform 0.2s, box-shadow 0.2s',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.transform = 'scale(1.1)';
                e.currentTarget.style.boxShadow = '0 12px 32px rgba(31,183,181,0.4)';
              }}
              onMouseLeave={e => {
                e.currentTarget.style.transform = 'scale(1)';
                e.currentTarget.style.boxShadow = '0 8px 24px rgba(31,183,181,0.3)';
              }}
            >
              <MessageCircle size={28} color="white" />
            </button>
          )}

          {/* Chat Panel */}
          {isChatOpen && (
            <div
              style={{
                position: 'fixed',
                top: 0,
                right: 0,
                bottom: 0,
                width: 380,
                background: 'white',
                boxShadow: '-4px 0 20px rgba(0,0,0,0.15)',
                zIndex: 1000,
                display: 'flex',
                flexDirection: 'column',
                animation: 'slideIn 0.3s ease-out',
              }}
            >
              <style>
                {`
                  @keyframes slideIn {
                    from {
                      transform: translateX(100%);
                    }
                    to {
                      transform: translateX(0);
                    }
                  }
                  @keyframes pulse {
                    0%, 100% { opacity: 0.3; transform: scale(0.8); }
                    50% { opacity: 1; transform: scale(1.2); }
                  }
                `}
              </style>

              {/* Chat Header */}
              <div style={{ padding: '24px 24px 20px', borderBottom: `1px solid ${BORDER}`, background: `linear-gradient(135deg, ${BLUE} 0%, ${TEAL} 100%)` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div>
                    <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'white', marginBottom: 4 }}>Ask Market AI</h3>
                    <p style={{ fontSize: '0.8125rem', color: 'rgba(255,255,255,0.85)' }}>Powered by current filtered market data</p>
                  </div>
                  <button
                    onClick={() => setIsChatOpen(false)}
                    style={{
                      background: 'rgba(255,255,255,0.2)',
                      border: 'none',
                      borderRadius: 6,
                      padding: 6,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <X size={20} color="white" />
                  </button>
                </div>
              </div>

              {/* Suggested Questions */}
              {chatMessages.length === 0 && (
                <div style={{ padding: '20px 20px 16px' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#6B7280', marginBottom: 12 }}>QUICK PROMPTS</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {[
                      'Top 5 customers by demand',
                      'Best entry opportunities',
                      'BASF market share',
                      'Summarize selected market',
                      'Highest price customers',
                      'Compare suppliers',
                      'Best customers for APX-1012',
                      'Show low competition accounts',
                    ].map((prompt, i) => (
                      <button
                        key={i}
                        onClick={() => handleChatSubmit(prompt)}
                        style={{
                          padding: '10px 14px',
                          fontSize: '0.8125rem',
                          color: BLUE,
                          background: 'white',
                          border: `1px solid ${BORDER}`,
                          borderRadius: 8,
                          cursor: 'pointer',
                          textAlign: 'left',
                          transition: 'all 0.15s',
                        }}
                        onMouseEnter={e => {
                          e.currentTarget.style.background = BG;
                          e.currentTarget.style.borderColor = TEAL;
                        }}
                        onMouseLeave={e => {
                          e.currentTarget.style.background = 'white';
                          e.currentTarget.style.borderColor = BORDER;
                        }}
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Chat Messages */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
                {chatMessages.map((msg, i) => (
                  <div
                    key={i}
                    style={{
                      marginBottom: 16,
                      display: 'flex',
                      justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    }}
                  >
                    <div
                      style={{
                        maxWidth: '80%',
                        padding: '12px 16px',
                        borderRadius: 12,
                        background: msg.role === 'user' ? TEAL : BG,
                        color: msg.role === 'user' ? 'white' : TEXT,
                        fontSize: '0.875rem',
                        lineHeight: 1.6,
                        whiteSpace: 'pre-line',
                      }}
                    >
                      {msg.content}
                    </div>
                  </div>
                ))}

                {isLoading && (
                  <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 16 }}>
                    <div
                      style={{
                        padding: '12px 16px',
                        borderRadius: 12,
                        background: BG,
                        color: '#6B7280',
                        fontSize: '0.875rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                      }}
                    >
                      <div
                        style={{
                          width: 6,
                          height: 6,
                          borderRadius: '50%',
                          background: TEAL,
                          animation: 'pulse 1.4s ease-in-out infinite',
                        }}
                      />
                      <div
                        style={{
                          width: 6,
                          height: 6,
                          borderRadius: '50%',
                          background: TEAL,
                          animation: 'pulse 1.4s ease-in-out 0.2s infinite',
                        }}
                      />
                      <div
                        style={{
                          width: 6,
                          height: 6,
                          borderRadius: '50%',
                          background: TEAL,
                          animation: 'pulse 1.4s ease-in-out 0.4s infinite',
                        }}
                      />
                      <span style={{ marginLeft: 8 }}>{loadingMessage}</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Chat Input */}
              <div style={{ padding: '16px 20px', borderTop: `1px solid ${BORDER}`, background: 'white' }}>
                <div style={{ display: 'flex', gap: 10 }}>
                  <input
                    type="text"
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && !isLoading) {
                        handleChatSubmit(chatInput);
                      }
                    }}
                    placeholder="Ask about this data..."
                    disabled={isLoading}
                    style={{
                      flex: 1,
                      padding: '12px 16px',
                      fontSize: '0.875rem',
                      border: `1px solid ${BORDER}`,
                      borderRadius: 8,
                      outline: 'none',
                      background: isLoading ? BG : 'white',
                    }}
                  />
                  <button
                    onClick={() => handleChatSubmit(chatInput)}
                    disabled={isLoading || !chatInput.trim()}
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: 8,
                      background: chatInput.trim() && !isLoading ? TEAL : '#E5E7EB',
                      border: 'none',
                      cursor: chatInput.trim() && !isLoading ? 'pointer' : 'not-allowed',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      transition: 'background 0.15s',
                    }}
                  >
                    <Send size={18} color={chatInput.trim() && !isLoading ? 'white' : '#9CA3AF'} />
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function FilterDropdown({ label, value, onChange, options }: any) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          width: '100%',
          height: 36,
          padding: '0 12px',
          fontSize: '0.8125rem',
          border: `1px solid ${BORDER}`,
          borderRadius: 6,
          color: TEXT,
          background: 'white',
          cursor: 'pointer',
          outline: 'none',
        }}
      >
        {options.map((opt: string) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </div>
  );
}

function ActionButton({ icon, label, onClick }: any) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '9px 16px',
        fontSize: '0.8125rem',
        fontWeight: 600,
        color: BLUE,
        background: 'white',
        border: `1px solid ${BORDER}`,
        borderRadius: 6,
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: 7,
        whiteSpace: 'nowrap',
      }}
    >
      {icon}
      {label}
    </button>
  );
}

function ChartCardCompanion({ title, subtitle, children }: any) {
  return (
    <div style={card}>
      <div style={{ padding: '18px 22px', borderBottom: `1px solid ${BORDER}` }}>
        <h3 style={{ fontSize: '1.0625rem', fontWeight: 600, color: TEXT }}>{title}</h3>
        <p style={{ fontSize: '0.875rem', color: '#6B7280', marginTop: 4 }}>{subtitle}</p>
      </div>
      <div style={{ padding: '26px 22px' }}>{children}</div>
    </div>
  );
}

function CompanyProfilePanel({ company, profile, companyData, onClose }: any) {
  const defaultProfile = {
    industry: 'Manufacturing',
    website: 'www.company.com',
    annualRevenue: '$1.5B',
    employees: '5,000+',
    marketPosition: 'Leading regional player',
    keyProducts: ['Product A', 'Product B', 'Product C'],
    currentSuppliers: ['Supplier A', 'Supplier B'],
    growthTrend: '+10% YoY',
    opportunitySummary: 'Strong potential for partnership. Currently evaluating new suppliers for expansion.',
  };

  const profileData = profile || defaultProfile;
  const standardDescription =
    'This company is an important player in its regional market with regular procurement demand across multiple polymer applications. It serves industrial and commercial sectors with steady annual purchasing volumes. The company has diversified sourcing behavior and strong future growth potential. Strategic engagement can create long-term supply opportunities.';

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        bottom: 0,
        width: '60%',
        maxWidth: 900,
        background: 'white',
        boxShadow: '-4px 0 20px rgba(0,0,0,0.15)',
        zIndex: 1000,
        overflowY: 'auto',
      }}
    >
      <div style={{ padding: '32px 40px', borderBottom: `1px solid ${BORDER}`, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 16 }}>
            <div
              style={{
                width: 80,
                height: 80,
                borderRadius: 16,
                background: 'linear-gradient(135deg, rgba(31,95,168,0.1) 0%, rgba(31,183,181,0.1) 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: `2px solid ${BORDER}`,
              }}
            >
              <Building2 size={40} color={BLUE} />
            </div>
            <div>
              <h2 style={{ fontSize: '1.75rem', fontWeight: 700, color: TEXT, marginBottom: 6 }}>{company}</h2>
              <p style={{ fontSize: '0.9375rem', color: '#6B7280', marginBottom: 4 }}>
                {companyData?.region || 'Global'} • {companyData?.country || 'Multiple Countries'}
              </p>
              <p style={{ fontSize: '0.875rem', color: '#6B7280' }}>{profileData.industry}</p>
            </div>
          </div>
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 8,
            borderRadius: 6,
          }}
        >
          <X size={24} color="#6B7280" />
        </button>
      </div>

      <div style={{ padding: '32px 40px' }}>
        {/* Company Description */}
        <div style={{ marginBottom: 32, padding: '20px 24px', background: BG, borderRadius: 12, border: `1px solid ${BORDER}` }}>
          <h3 style={{ fontSize: '1.0625rem', fontWeight: 600, color: TEXT, marginBottom: 12 }}>Company Overview</h3>
          <p style={{ fontSize: '0.9375rem', color: TEXT, lineHeight: 1.7 }}>{standardDescription}</p>
        </div>

        {/* Key Metrics Grid */}
        <div className="grid grid-cols-3 gap-5 mb-8">
          <InfoCard icon={<Globe size={18} color={TEAL} />} label="Website" value={profileData.website} />
          <InfoCard icon={<DollarSign size={18} color={GREEN} />} label="Annual Revenue" value={profileData.annualRevenue || 'N/A'} />
          <InfoCard icon={<Building2 size={18} color={BLUE} />} label="Employees" value={profileData.employees || 'N/A'} />
          <InfoCard icon={<TrendingUp size={18} color={GREEN} />} label="Growth Trend" value={companyData?.growthTrend || profileData.growthTrend} />
          <InfoCard icon={<DollarSign size={18} color={BLUE} />} label="Estimated Annual Demand" value={companyData ? `${companyData.annualDemand.toLocaleString()} MT` : 'N/A'} />
          <InfoCard icon={<Target size={18} color={RED} />} label="Opportunity Score" value={companyData ? `${companyData.fitScore}%` : 'N/A'} />
        </div>

        {/* Detailed Information Grid */}
        <div className="grid grid-cols-2 gap-6 mb-6">
          <SectionCard title="Main Products Purchased">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {companyData && (
                <span
                  style={{
                    padding: '8px 16px',
                    background: 'rgba(31,183,181,0.1)',
                    border: `1px solid rgba(31,183,181,0.3)`,
                    borderRadius: 20,
                    fontSize: '0.875rem',
                    color: TEAL,
                    fontWeight: 600,
                  }}
                >
                  {companyData.product}
                </span>
              )}
              {profileData.keyProducts?.slice(0, 3).map((product: string, i: number) => (
                <span
                  key={i}
                  style={{
                    padding: '8px 16px',
                    background: BG,
                    border: `1px solid ${BORDER}`,
                    borderRadius: 20,
                    fontSize: '0.875rem',
                    color: TEXT,
                  }}
                >
                  {product}
                </span>
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Application Segment">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {companyData && (
                <span
                  style={{
                    padding: '8px 16px',
                    background: 'rgba(31,95,168,0.1)',
                    border: `1px solid rgba(31,95,168,0.3)`,
                    borderRadius: 20,
                    fontSize: '0.875rem',
                    color: BLUE,
                    fontWeight: 600,
                  }}
                >
                  {companyData.application}
                </span>
              )}
            </div>
          </SectionCard>
        </div>

        <div className="grid grid-cols-2 gap-6 mb-6">
          <SectionCard title="Current Suppliers">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {companyData && (
                <span
                  style={{
                    padding: '8px 16px',
                    background: 'rgba(217,58,47,0.08)',
                    border: `1px solid rgba(217,58,47,0.2)`,
                    borderRadius: 20,
                    fontSize: '0.875rem',
                    color: RED,
                    fontWeight: 600,
                  }}
                >
                  {companyData.currentSupplier}
                </span>
              )}
              {profileData.currentSuppliers?.map((supplier: string, i: number) => (
                <span
                  key={i}
                  style={{
                    padding: '8px 16px',
                    background: 'rgba(31,95,168,0.08)',
                    border: `1px solid rgba(31,95,168,0.2)`,
                    borderRadius: 20,
                    fontSize: '0.875rem',
                    color: BLUE,
                    fontWeight: 600,
                  }}
                >
                  {supplier}
                </span>
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Pricing & Market Share">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 14px', background: BG, borderRadius: 8 }}>
                <span style={{ fontSize: '0.8125rem', color: '#6B7280', fontWeight: 600 }}>Avg Price Range:</span>
                <span style={{ fontSize: '0.875rem', color: TEXT, fontWeight: 600 }}>{companyData ? `$${companyData.price}/MT` : 'N/A'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 14px', background: BG, borderRadius: 8 }}>
                <span style={{ fontSize: '0.8125rem', color: '#6B7280', fontWeight: 600 }}>Competitor Share:</span>
                <span style={{ fontSize: '0.875rem', color: TEXT, fontWeight: 600 }}>{companyData ? `${companyData.competitorShare}%` : 'N/A'}</span>
              </div>
            </div>
          </SectionCard>
        </div>

        <div className="grid grid-cols-2 gap-6 mb-6">
          <SectionCard title="Suggested Grade Match">
            <div style={{ padding: '14px 18px', background: 'rgba(31,183,181,0.08)', border: `1px solid rgba(31,183,181,0.2)`, borderRadius: 10 }}>
              <div style={{ fontSize: '1.125rem', fontWeight: 700, color: TEAL, marginBottom: 4 }}>{companyData?.suggestedGrade || 'APX-Series'}</div>
              <div style={{ fontSize: '0.8125rem', color: '#6B7280' }}>Recommended Apcotex grade for optimal fit</div>
            </div>
          </SectionCard>

          <SectionCard title="Opportunity Status">
            <div
              style={{
                padding: '14px 18px',
                background: companyData?.entryPotential === 'High' ? 'rgba(16,185,129,0.08)' : 'rgba(245,158,11,0.08)',
                border: `1px solid ${companyData?.entryPotential === 'High' ? 'rgba(16,185,129,0.2)' : 'rgba(245,158,11,0.2)'}`,
                borderRadius: 10,
              }}
            >
              <div style={{ fontSize: '1.125rem', fontWeight: 700, color: companyData?.entryPotential === 'High' ? GREEN : YELLOW, marginBottom: 4 }}>
                {companyData?.entryPotential || 'Medium'} Priority
              </div>
              <div style={{ fontSize: '0.8125rem', color: '#6B7280' }}>Entry potential based on fit score analysis</div>
            </div>
          </SectionCard>
        </div>

        <SectionCard title="Strategic Opportunity Summary">
          <p style={{ fontSize: '0.9375rem', color: TEXT, lineHeight: 1.8 }}>{profileData.opportunitySummary || standardDescription}</p>
        </SectionCard>

        <div
          style={{
            marginTop: 28,
            padding: '24px 28px',
            background: 'linear-gradient(135deg, rgba(31,95,168,0.05) 0%, rgba(31,183,181,0.05) 100%)',
            border: `1px solid ${BORDER}`,
            borderRadius: 12,
          }}
        >
          <h4 style={{ fontSize: '1.0625rem', fontWeight: 600, color: TEXT, marginBottom: 14 }}>Recommended Next Steps</h4>
          <ul style={{ margin: 0, paddingLeft: 20, fontSize: '0.9375rem', color: TEXT, lineHeight: 2 }}>
            <li>Schedule discovery call with procurement team</li>
            <li>Prepare technical specifications for suggested grades</li>
            <li>Develop competitive pricing proposal</li>
            <li>Arrange product samples and testing timeline</li>
          </ul>
        </div>

        {companyData && (
          <div
            style={{
              marginTop: 24,
              padding: '18px 24px',
              background: '#F9FAFB',
              borderRadius: 10,
              border: `1px solid ${BORDER}`,
            }}
          >
            <div style={{ fontSize: '0.75rem', color: '#6B7280', fontWeight: 600, marginBottom: 8 }}>Contact Information</div>
            <div style={{ fontSize: '0.875rem', color: TEXT }}>procurement@{profileData.website}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function InfoCard({ icon, label, value }: any) {
  return (
    <div style={{ padding: '16px 18px', background: BG, borderRadius: 10, border: `1px solid ${BORDER}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        {icon}
        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#6B7280' }}>{label}</span>
      </div>
      <div style={{ fontSize: '1.0625rem', fontWeight: 700, color: TEXT }}>{value}</div>
    </div>
  );
}

function SectionCard({ title, children }: any) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, color: TEXT, marginBottom: 12 }}>{title}</h4>
      {children}
    </div>
  );
}

function GeographyEditorModal({ geography, onSave, onClose }: any) {
  const [editedGeography, setEditedGeography] = useState({ ...geography });
  const [newRegion, setNewRegion] = useState('');
  const [selectedRegionForCountry, setSelectedRegionForCountry] = useState('');
  const [newCountry, setNewCountry] = useState('');

  const addRegion = () => {
    if (newRegion && !editedGeography[newRegion]) {
      setEditedGeography({ ...editedGeography, [newRegion]: [] });
      setNewRegion('');
    }
  };

  const deleteRegion = (region: string) => {
    const updated = { ...editedGeography };
    delete updated[region];
    setEditedGeography(updated);
  };

  const addCountry = () => {
    if (selectedRegionForCountry && newCountry) {
      const updated = { ...editedGeography };
      if (!updated[selectedRegionForCountry].includes(newCountry)) {
        updated[selectedRegionForCountry] = [...updated[selectedRegionForCountry], newCountry];
        setEditedGeography(updated);
        setNewCountry('');
      }
    }
  };

  const deleteCountry = (region: string, country: string) => {
    const updated = { ...editedGeography };
    updated[region] = updated[region].filter((c: string) => c !== country);
    setEditedGeography(updated);
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: 20,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'white',
          borderRadius: 12,
          width: '100%',
          maxWidth: 900,
          maxHeight: '80vh',
          overflow: 'auto',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ padding: '22px 26px', borderBottom: `1px solid ${BORDER}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: TEXT }}>Edit Geography</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
            <X size={20} color="#6B7280" />
          </button>
        </div>

        <div style={{ padding: 26 }}>
          {/* Add Region */}
          <div style={{ marginBottom: 26 }}>
            <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: TEXT, marginBottom: 12 }}>Add New Region</h3>
            <div style={{ display: 'flex', gap: 12 }}>
              <input
                type="text"
                value={newRegion}
                onChange={e => setNewRegion(e.target.value)}
                placeholder="Enter region name"
                style={{
                  flex: 1,
                  padding: '10px 14px',
                  fontSize: '0.875rem',
                  border: `1px solid ${BORDER}`,
                  borderRadius: 6,
                  outline: 'none',
                }}
              />
              <button
                onClick={addRegion}
                style={{
                  padding: '10px 20px',
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  color: 'white',
                  background: TEAL,
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                <Plus size={16} />
                Add Region
              </button>
            </div>
          </div>

          {/* Add Country */}
          <div style={{ marginBottom: 26 }}>
            <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: TEXT, marginBottom: 12 }}>Add Country to Region</h3>
            <div style={{ display: 'flex', gap: 12 }}>
              <select
                value={selectedRegionForCountry}
                onChange={e => setSelectedRegionForCountry(e.target.value)}
                style={{
                  flex: 1,
                  padding: '10px 14px',
                  fontSize: '0.875rem',
                  border: `1px solid ${BORDER}`,
                  borderRadius: 6,
                  outline: 'none',
                }}
              >
                <option value="">Select region</option>
                {Object.keys(editedGeography).map(region => (
                  <option key={region} value={region}>{region}</option>
                ))}
              </select>
              <input
                type="text"
                value={newCountry}
                onChange={e => setNewCountry(e.target.value)}
                placeholder="Enter country name"
                style={{
                  flex: 1,
                  padding: '10px 14px',
                  fontSize: '0.875rem',
                  border: `1px solid ${BORDER}`,
                  borderRadius: 6,
                  outline: 'none',
                }}
              />
              <button
                onClick={addCountry}
                style={{
                  padding: '10px 20px',
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  color: 'white',
                  background: TEAL,
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                <Plus size={16} />
                Add Country
              </button>
            </div>
          </div>

          {/* Regions and Countries List */}
          <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: TEXT, marginBottom: 12 }}>Current Geography</h3>
          <div style={{ maxHeight: 400, overflowY: 'auto' }}>
            {Object.entries(editedGeography).map(([region, countries]) => (
              <div key={region} style={{ marginBottom: 18, padding: 16, background: BG, borderRadius: 8, border: `1px solid ${BORDER}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <h4 style={{ fontSize: '0.875rem', fontWeight: 600, color: BLUE }}>{region}</h4>
                  <button
                    onClick={() => deleteRegion(region)}
                    style={{
                      padding: '5px 11px',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      color: RED,
                      background: 'white',
                      border: `1px solid ${BORDER}`,
                      borderRadius: 6,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                    }}
                  >
                    <Trash2 size={12} />
                    Delete
                  </button>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {(countries as string[]).map(country => (
                    <div
                      key={country}
                      style={{
                        padding: '5px 11px',
                        background: 'white',
                        border: `1px solid ${BORDER}`,
                        borderRadius: 6,
                        fontSize: '0.75rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 7,
                      }}
                    >
                      <span>{country}</span>
                      <button
                        onClick={() => deleteCountry(region, country)}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: 0,
                          display: 'flex',
                          alignItems: 'center',
                        }}
                      >
                        <X size={12} color={RED} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ padding: '18px 26px', borderTop: `1px solid ${BORDER}`, display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
          <button
            onClick={onClose}
            style={{
              padding: '10px 20px',
              fontSize: '0.875rem',
              fontWeight: 600,
              color: TEXT,
              background: 'white',
              border: `1px solid ${BORDER}`,
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(editedGeography)}
            style={{
              padding: '10px 20px',
              fontSize: '0.875rem',
              fontWeight: 600,
              color: 'white',
              background: TEAL,
              border: 'none',
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
}
