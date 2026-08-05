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
  const [customer, setCustomer] = useState<UploadSlice>(emptyUpload);
  const [product, setProduct] = useState<UploadSlice>(emptyUpload);
  const [templateStatus, setTemplateStatus] = useState<TemplateGenStatus>('idle');
  const [templateMessage, setTemplateMessage] = useState<string | null>(null);
  const [templateMeta, setTemplateMeta] = useState<TemplateGenerateResult | null>(null);

  const customerDone = customer.status === 'success';
  const productDone = product.status === 'success';
  const templateDone = templateStatus === 'ready';

  const timeline = useMemo(
    () => [
      {
        id: 'customer',
        label: 'Upload Customer Master',
        detail: customerDone ? 'Completed' : customer.status === 'uploading' ? 'In progress' : 'Pending',
        done: customerDone,
        active: !customerDone && (customer.status === 'uploading' || (!customerDone && !productDone)),
      },
      {
        id: 'product',
        label: 'Upload Product Master',
        detail: productDone ? 'Completed' : product.status === 'uploading' ? 'In progress' : 'Pending',
        done: productDone,
        active: customerDone && !productDone,
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
        active: customerDone && productDone && !templateDone,
      },
    ],
    [customer.status, customerDone, product.status, productDone, templateStatus, templateDone],
  );

  const runUpload = async (
    kind: 'customer' | 'product',
    file: File,
  ) => {
    const setSlice = kind === 'customer' ? setCustomer : setProduct;
    const uploadFn =
      kind === 'customer'
        ? MasterDataService.uploadCustomerMaster
        : MasterDataService.uploadProductMaster;

    setSlice(prev => ({
      ...prev,
      status: 'uploading',
      progress: 0,
      message: null,
      fileName: file.name,
    }));

    // Reset template if masters change
    setTemplateMeta(null);
    setTemplateStatus('idle');
    setTemplateMessage(null);

    try {
      const result: MasterUploadResult = await uploadFn(file, p => {
        setSlice(prev => ({ ...prev, progress: p }));
      });
      setSlice({
        status: 'success',
        progress: null,
        message: result.message,
        lastUploaded: result.uploaded_at,
        recordsImported: result.records_imported,
        fileName: result.file_name,
      });
    } catch (err) {
      setSlice(prev => ({
        ...prev,
        status: 'error',
        progress: null,
        message: err instanceof Error ? err.message : 'Upload failed',
      }));
    }
  };

  const handleGenerate = async () => {
    if (!customerDone || !productDone) return;
    setTemplateStatus('generating');
    setTemplateMessage(null);
    try {
      const result = await MasterDataService.generateTemplate();
      setTemplateMeta(result);
      setTemplateStatus('ready');
      setTemplateMessage(result.message);
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
          Manage master datasets and generate official distributor templates.
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
          title="Upload Customer Master"
          description="Upload APCOTEX Customer Master Excel file."
          helperText={
            <>
              The <strong>CUSTOMER NAME</strong> column will be extracted and used to populate the Customer
              dropdown inside the distributor template.
            </>
          }
          status={customer.status}
          progress={customer.progress}
          message={customer.message}
          lastUploaded={customer.lastUploaded}
          recordsImported={customer.recordsImported}
          fileName={customer.fileName}
          onUpload={file => runUpload('customer', file)}
        />

        <MasterUploadCard
          title="Upload Product Master"
          description="Upload APCOTEX Product Master Excel file."
          helperText={
            <>
              The Product Master will be used to populate Product dropdowns inside the distributor template.
              Products are linked by <strong>Industry Type → Product Code</strong>.
            </>
          }
          status={product.status}
          progress={product.progress}
          message={product.message}
          lastUploaded={product.lastUploaded}
          recordsImported={product.recordsImported}
          fileName={product.fileName}
          onUpload={file => runUpload('product', file)}
        />

        <TemplateGenerationCard
          status={templateStatus}
          message={templateMessage}
          templateVersion={templateMeta?.template_version ?? null}
          generatedAt={templateMeta?.generated_at ?? null}
          canGenerate={customerDone && productDone}
          canDownload={templateDone && !!templateMeta}
          onGenerate={handleGenerate}
          onDownload={handleDownload}
        />
      </div>

      <InfoCard />
    </div>
  );
}
