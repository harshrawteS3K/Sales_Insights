/**
 * Trigger a browser file download from an in-memory Blob.
 *
 * Important: do NOT revoke the object URL synchronously after click().
 * On many browsers (especially slower VPN / remote clients) the download
 * manager has not started reading the blob yet; immediate revoke cancels it.
 * Loopback/RDP often "works" because timing wins the race.
 */
export function triggerBrowserDownload(blob: Blob, fileName: string): void {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = fileName;
  anchor.rel = 'noopener';
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.setTimeout(() => {
    URL.revokeObjectURL(objectUrl);
  }, 60_000);
}

/** Prefer Content-Disposition filename when the header is CORS-exposed. */
export function filenameFromContentDisposition(
  disposition: string | null,
  fallback: string,
): string {
  if (!disposition) return fallback;
  const utf = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (utf?.[1]) {
    try {
      return decodeURIComponent(utf[1].trim());
    } catch {
      return utf[1].trim();
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  return plain?.[1]?.trim() || fallback;
}
