(function () {
  function downloadBlob(blob, fileName) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 300);
  }

  async function exportPdf(apiFetch, { html, fileName }) {
    const response = await apiFetch("/api/export-report-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ html, fileName })
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || payload.detail || "PDF 生成失败");
    }
    const blob = await response.blob();
    downloadBlob(blob, `${fileName}.pdf`);
    return blob;
  }

  window.FinVueReportExport = {
    downloadBlob,
    exportPdf
  };
})();
