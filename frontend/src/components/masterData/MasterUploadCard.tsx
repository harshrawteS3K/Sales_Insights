import { useRef, useState, type DragEvent, type ChangeEvent, type ReactNode } from 'react';
import { Upload, FileSpreadsheet } from 'lucide-react';
import { BLUE, TEAL, BORDER, TEXT_SECONDARY } from '../../constants/theme';
import { UploadStatus, type UploadStatusState } from './UploadStatus';

type Props = {
  title: string;
  description: string;
  helperText: ReactNode;
  accept?: string;
  status: UploadStatusState;
  progress?: number | null;
  message?: string | null;
  lastUploaded?: string | null;
  recordsImported?: number | null;
  fileName?: string | null;
  disabled?: boolean;
  onUpload: (file: File) => void;
};

export function MasterUploadCard({
  title,
  description,
  helperText,
  accept = '.xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  status,
  progress,
  message,
  lastUploaded,
  recordsImported,
  fileName,
  disabled,
  onUpload,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const busy = status === 'uploading' || disabled;

  const takeFile = (file: File | undefined | null) => {
    if (!file || busy) return;
    onUpload(file);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    takeFile(e.dataTransfer.files?.[0]);
  };

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    takeFile(file);
  };

  return (
    <div
      style={{
        background: 'white',
        border: `1px solid ${BORDER}`,
        borderRadius: 12,
        padding: '22px 22px 20px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        minHeight: 420,
      }}
    >
      <div>
        <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#111827' }}>{title}</h2>
        <p style={{ margin: '6px 0 0', fontSize: '0.8125rem', color: TEXT_SECONDARY, lineHeight: 1.5 }}>
          {description}
        </p>
      </div>

      <div
        style={{
          padding: '10px 12px',
          background: 'rgba(31,95,168,0.04)',
          border: '1px solid rgba(31,95,168,0.12)',
          borderRadius: 8,
          fontSize: '0.8125rem',
          color: '#374151',
          lineHeight: 1.5,
        }}
      >
        {helperText}
      </div>

      <div
        onDragOver={e => {
          e.preventDefault();
          if (!busy) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !busy && inputRef.current?.click()}
        style={{
          border: `1.5px dashed ${dragging ? TEAL : BORDER}`,
          background: dragging ? 'rgba(31,183,181,0.06)' : '#FAFBFC',
          borderRadius: 10,
          padding: '28px 16px',
          textAlign: 'center',
          cursor: busy ? 'not-allowed' : 'pointer',
          transition: 'border-color 0.15s, background 0.15s',
          opacity: busy ? 0.7 : 1,
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          style={{ display: 'none' }}
          disabled={busy}
          onChange={onChange}
        />
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 10,
            background: 'rgba(31,95,168,0.08)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: 10,
          }}
        >
          <FileSpreadsheet size={20} color={BLUE} />
        </div>
        <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#111827', marginBottom: 4 }}>
          Drag & drop Excel file here
        </div>
        <div style={{ fontSize: '0.75rem', color: TEXT_SECONDARY }}>
          Supported format: .xlsx
        </div>
      </div>

      <button
        type="button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          alignSelf: 'flex-start',
          padding: '9px 16px',
          background: busy ? '#9CA3AF' : BLUE,
          color: 'white',
          border: 'none',
          borderRadius: 8,
          fontSize: '0.8125rem',
          fontWeight: 600,
          cursor: busy ? 'not-allowed' : 'pointer',
        }}
      >
        <Upload size={15} />
        Upload File
      </button>

      <UploadStatus
        status={status}
        progress={progress}
        message={message}
        lastUploaded={lastUploaded}
        recordsImported={recordsImported}
        fileName={fileName}
      />
    </div>
  );
}
