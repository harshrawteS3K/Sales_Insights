import { useEffect, useState, type CSSProperties, type FormEvent } from 'react';
import { Navigate } from 'react-router';
import { Shuffle, Search } from 'lucide-react';
import { useLayoutContext } from '../../hooks/useLayoutContext';
import { StatusBanner } from '../../components/common/StatusBanner';
import {
  NormalizationService,
  type ProductMapping,
  type ProductMappingQuery,
} from '../../services/normalization.service';
import { ApiError } from '../../api';
import { isSuperAdminRole } from '../../utils/rbac';
import { BLUE, BORDER } from '../../constants/theme';

export const NORMALIZATION_COLUMNS = ['Distributor', 'Original Product', 'Normalized Product'] as const;

const PAGE_SIZE = 50;
const ENDPOINT = '/normalization/product-mappings';

function loadErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return 'Unable to load normalization mappings. Please check backend logs.';
  switch (err.status) {
    case 401:
      return 'Your session has expired or you are not signed in. Please sign in again.';
    case 403:
      return 'You do not have permission to access Normalization.';
    case 404:
      console.error(`Normalization endpoint not found: GET /api${ENDPOINT}`);
      return `Normalization endpoint not found (GET /api${ENDPOINT}). Restart the backend so it loads this route.`;
    default:
      if (err.status >= 500) return 'Unable to load normalization mappings. Please check backend logs.';
      return err.message || 'Unable to load normalization mappings.';
  }
}

const inputStyle: CSSProperties = {
  flex: 1,
  minWidth: 160,
  padding: '8px 12px',
  fontSize: '0.875rem',
  border: `1px solid ${BORDER}`,
  borderRadius: 8,
  outline: 'none',
};

const cellStyle: CSSProperties = {
  padding: '10px 14px',
  borderBottom: `1px solid ${BORDER}`,
  fontSize: '0.875rem',
  color: '#1F2937',
  textAlign: 'left',
};

export function NormalizationPage() {
  const { userRole } = useLayoutContext();
  const isSuperAdmin = isSuperAdminRole(userRole);

  const [rows, setRows] = useState<ProductMapping[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [filters, setFilters] = useState<ProductMappingQuery>({});
  const [draft, setDraft] = useState({ distributor: '', original_product: '', normalized_product: '' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isSuperAdmin) return;
    setLoading(true);
    setError(null);
    NormalizationService.listProductMappings({ ...filters, page, page_size: PAGE_SIZE })
      .then(res => {
        setRows(res.data);
        setTotal(res.meta.total);
        setTotalPages(res.meta.total_pages);
      })
      .catch((err: unknown) => {
        setRows([]);
        setTotal(0);
        setTotalPages(0);
        setError(loadErrorMessage(err));
      })
      .finally(() => setLoading(false));
  }, [isSuperAdmin, filters, page]);

  if (!isSuperAdmin) {
    return <Navigate to="/" replace />;
  }

  const applyFilters = (e: FormEvent) => {
    e.preventDefault();
    setPage(1);
    setFilters({
      distributor: draft.distributor.trim() || undefined,
      original_product: draft.original_product.trim() || undefined,
      normalized_product: draft.normalized_product.trim() || undefined,
    });
  };

  return (
    <div style={{ padding: '24px 28px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, marginBottom: 20 }}>
        <div
          style={{
            width: 42,
            height: 42,
            borderRadius: 10,
            background: 'rgba(31,95,168,0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Shuffle size={22} color={BLUE} />
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: BLUE }}>
            Normalization
          </h1>
          <p style={{ margin: '6px 0 0', color: '#6B7280', fontSize: '0.875rem', lineHeight: 1.5 }}>
            Distributor product names and the normalized product each one maps to.
          </p>
        </div>
      </div>

      <form onSubmit={applyFilters} style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
        <input
          style={inputStyle}
          placeholder="Distributor"
          value={draft.distributor}
          onChange={e => setDraft(d => ({ ...d, distributor: e.target.value }))}
        />
        <input
          style={inputStyle}
          placeholder="Original Product"
          value={draft.original_product}
          onChange={e => setDraft(d => ({ ...d, original_product: e.target.value }))}
        />
        <input
          style={inputStyle}
          placeholder="Normalized Product"
          value={draft.normalized_product}
          onChange={e => setDraft(d => ({ ...d, normalized_product: e.target.value }))}
        />
        <button
          type="submit"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 16px',
            border: 'none',
            borderRadius: 8,
            background: BLUE,
            color: 'white',
            fontSize: '0.875rem',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <Search size={15} /> Search
        </button>
      </form>

      {error && <StatusBanner error={error} style={{ marginBottom: 16 }} />}

      <div style={{ border: `1px solid ${BORDER}`, borderRadius: 12, background: 'white', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }} aria-label="Product normalization mappings">
          <thead>
            <tr style={{ background: '#F9FAFB' }}>
              {NORMALIZATION_COLUMNS.map(col => (
                <th key={col} style={{ ...cellStyle, fontWeight: 600, color: '#374151' }}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={NORMALIZATION_COLUMNS.length} style={cellStyle}>
                  <StatusBanner loading loadingText="Loading mappings…" />
                </td>
              </tr>
            ) : error ? (
              <tr>
                <td
                  colSpan={NORMALIZATION_COLUMNS.length}
                  style={{ ...cellStyle, textAlign: 'center', color: '#6B7280', padding: '32px 14px' }}
                >
                  Mappings could not be loaded.
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td
                  colSpan={NORMALIZATION_COLUMNS.length}
                  style={{ ...cellStyle, textAlign: 'center', color: '#6B7280', padding: '32px 14px' }}
                >
                  No product mappings yet.
                </td>
              </tr>
            ) : (
              rows.map(row => (
                <tr key={row.id}>
                  <td style={cellStyle}>{row.distributor_name || 'All Distributors'}</td>
                  <td style={cellStyle}>{row.original_product_name}</td>
                  <td style={{ ...cellStyle, fontWeight: 600 }}>{row.normalized_product_name}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {!loading && !error && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 14, fontSize: '0.875rem', color: '#6B7280' }}>
          {totalPages > 1 && (
            <button type="button" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
              Previous
            </button>
          )}
          <span>
            {totalPages > 1 ? `Page ${page} of ${totalPages} · ` : ''}
            {total} active mapping{total === 1 ? '' : 's'}
          </span>
          {totalPages > 1 && (
            <button type="button" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
              Next
            </button>
          )}
        </div>
      )}
    </div>
  );
}
