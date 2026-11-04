/** Where the browser loads the PDF reader's background worker from. (Its own file so tests can replace it.) */
export const pdfWorkerUrl = () => new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
