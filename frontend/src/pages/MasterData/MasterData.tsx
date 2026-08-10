import { useMemo, useState } from 'react';
import {
  MasterUploadCard,
  TemplateGenerationCard,
  ProgressTimeline,
  InfoCard,
  type UploadStatusState,
  type TemplateGenStatus,
} from '../../components/masterData';
import {
  MasterDataService,
  type MasterUploadResult,
  type TemplateGenerateResult,
} from '../../services/masterData.service';
import { AuditTrailService } from '../../services/auditTrail.service';
import type { TemplateGenerateMode } from '../../types';

type UploadSlice = {
  status: UploadStatusState;
  progress: number | null;
  message: string | null;
  lastUploaded: string | null;
  recordsImported: number | null;
  fileName: string | null;
};

const emptyUpload = (): UploadSlice => ({
  status: 'idle',
  progress: null,
  message: null,
  lastUploaded: null,
  recordsImported: null,
  fileName: null,
});

export function MasterData() {
  const [product, setProduct] = useState<UploadSlice>(emptyUpload);
  const [templateStatus, setTemplateStatus] = useState<TemplateGenStatus>('idle');
  const [templateMessage, setTemplateMessage] = useState<string | null>(null);
  const [templateMeta, setTemplateMeta] = useState<TemplateGenerateResult | null>(null);
  const [templateMode, setTemplateMode] = useState<TemplateGenerateMode>('generic');
  const [templateDistributorId, setTemplateDistributorId] = useState<number | null>(null);

  const productDone = product.status === 'success';
  const templateDone = templateStatus === 'ready';

  const timeline = useMemo(
    () => [
      {
        id: 'product',
        label: 'Upload Product Master',
        detail: productDone ? 'Completed' : product.status === 'uploading' ? 'In progress' : 'Pending',
        done: productDone,
        active: !productDone,
      },
      {
        id: 'template',
        label: 'Generate Template',
        detail: templateDone
          ? 'Template Ready'
          : templateStatus === 'generating'
            ? 'Generating'
            : 'Pending',
        done: templateDone,
        active: productDone && !templateDone,
      },
    ],
    [product.status, productDone, templateStatus, templateDone],
  );

  const runProductUpload = async (file: File) => {
    setProduct(prev => ({
      ...prev,
      status: 'uploading',
      progress: 0,
      message: null,
      fileName: file.name,
    }));

    setTemplateMeta(null);
    setTemplateStatus('idle');
    setTemplateMessage(null);

    try {
      const result: MasterUploadResult = await MasterDataService.uploadProductMaster(file, p => {
        setProduct(prev => ({ ...prev, progress: p }));
      });
      setProduct({
        status: 'success',
        progress: null,
        message: result.message,
        lastUploaded: result.uploaded_at,
        recordsImported: result.records_imported,
        fileName: result.file_name,
      });
    } catch (err) {
      setProduct(prev => ({
        ...prev,
        status: 'error',
        progress: null,
        message: err instanceof Error ? err.message : 'Upload failed',
      }));
    }
  };

  const handleGenerate = async () => {
    if (!productDone) return;
    if (templateMode === 'distributor' && !templateDistributorId) return;
    setTemplateStatus('generating');
    setTemplateMessage(null);
    try {
      const result = await MasterDataService.generateTemplate({
        mode: templateMode,
        ...(templateMode === 'distributor' && templateDistributorId
          ? { distributor_id: templateDistributorId }
          : {}),
      });
      setTemplateMeta(result);
      setTemplateStatus('ready');
      setTemplateMessage(result.warning || result.message);
    } catch (err) {
      setTemplateStatus('error');
      setTemplateMessage(err instanceof Error ? err.message : 'Template generation failed');
    }
  };

  const handleDownload = async () => {
    if (!templateMeta) return;
    try {
      await MasterDataService.downloadTemplate(undefined, templateMeta.file_name);
      void AuditTrailService.recordEvent({
        action: 'Template Downloaded',
        module: 'Master Data',
        description: `Downloaded distributor template ${templateMeta.file_name}`,
        status: 'Success',
        entity_type: 'template',
        report_name: templateMeta.file_name,
      });
    } catch (err) {
      setTemplateStatus('error');
      setTemplateMessage(err instanceof Error ? err.message : 'Template download failed');
      void AuditTrailService.recordEvent({
        action: 'Template Generation Failed',
        module: 'Master Data',
        description: err instanceof Error ? err.message : 'Template download failed',
        status: 'Failed',
        entity_type: 'template',
      });
    }
  };

  return (
    <div style={{ padding: '28px 32px', fontFamily: "'Inter', system-ui, sans-serif" }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: '#111827', margin: 0, marginBottom: 4 }}>
          Master Data Management
        </h1>
        <p style={{ fontSize: '0.875rem', color: '#6B7280', margin: 0 }}>
          Upload Product Master and generate the quarterly distributor sales template.
        </p>
      </div>

      <ProgressTimeline steps={timeline} />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: 20,
          marginBottom: 20,
          alignItems: 'stretch',
        }}
      >
        <MasterUploadCard
          title="Upload Product Master"
          description="Upload APCOTEX Product Master Excel file."
          helperText={
            <>
              Used to populate Segment and Product dropdowns. Products are linked by{' '}
              <strong>Industry Type Description → Product Code</strong>. Distributors enter Customer
              Name as free text and Reporting Quarter manually (e.g. Q1 2026).
            </>
          }
          status={product.status}
          progress={product.progress}
          message={product.message}
          lastUploaded={product.lastUploaded}
          recordsImported={product.recordsImported}
          fileName={product.fileName}
          onUpload={runProductUpload}
        />

        <TemplateGenerationCard
          status={templateStatus}
          message={templateMessage}
          templateVersion={templateMeta?.template_version ?? null}
          generatedAt={templateMeta?.generated_at ?? null}
          canGenerate={productDone}
          canDownload={templateDone && !!templateMeta}
          mode={templateMode}
          distributorId={templateDistributorId}
          fallbackGeneric={Boolean(templateMeta?.fallback_generic)}
          onModeChange={mode => {
            setTemplateMode(mode);
            if (mode === 'generic') setTemplateDistributorId(null);
            setTemplateStatus('idle');
            setTemplateMessage(null);
            setTemplateMeta(null);
          }}
          onDistributorChange={id => {
            setTemplateDistributorId(id);
            setTemplateStatus('idle');
            setTemplateMessage(null);
            setTemplateMeta(null);
          }}
          onGenerate={handleGenerate}
          onDownload={handleDownload}
        />
      </div>

      <InfoCard />
    </div>
  );
}
