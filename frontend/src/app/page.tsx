"use client";

import { useState } from "react";
import FileUpload from "@/components/FileUpload";
import ExtractionForm from "@/components/ExtractionForm";
import ExtractionResult from "@/components/ExtractionResult";
import type { DocumentResponse, ExtractionResponse } from "@/lib/api";
import { FileText } from "lucide-react";

export default function HomePage() {
  const [document, setDocument] = useState<DocumentResponse | null>(null);
  const [extraction, setExtraction] = useState<ExtractionResponse | null>(null);

  return (
    <div className="space-y-8">
      {/* Hero section */}
      <div className="text-center">
        <h2 className="text-2xl font-bold text-gray-900">
          Extract Data from Documents
        </h2>
        <p className="mt-2 text-gray-500">
          Upload a document, choose what to extract, and get structured results
          in seconds.
        </p>
      </div>

      {/* Step 1: Upload */}
      <section>
        <div className="mb-3 flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary-100 text-xs font-bold text-primary-700">
            1
          </span>
          <h3 className="text-sm font-semibold text-gray-700">
            Upload your document
          </h3>
        </div>
        <FileUpload onUploaded={(doc) => { setDocument(doc); setExtraction(null); }} />

        {document && (
          <div className="mt-3 flex items-center gap-2 rounded-lg bg-green-50 px-4 py-2 text-sm text-green-700">
            <FileText className="h-4 w-4" />
            <span className="font-medium">{document.original_filename}</span>
            <span className="text-green-500">
              ({(document.file_size / 1024).toFixed(0)} KB)
            </span>
          </div>
        )}
      </section>

      {/* Step 2: Configure extraction */}
      {document && !extraction && (
        <section>
          <div className="mb-3 flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary-100 text-xs font-bold text-primary-700">
              2
            </span>
            <h3 className="text-sm font-semibold text-gray-700">
              Choose what to extract
            </h3>
          </div>
          <ExtractionForm
            document={document}
            onStarted={setExtraction}
          />
        </section>
      )}

      {/* Step 3: Results */}
      {extraction && (
        <section>
          <div className="mb-3 flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary-100 text-xs font-bold text-primary-700">
              3
            </span>
            <h3 className="text-sm font-semibold text-gray-700">
              Review results
            </h3>
          </div>
          <ExtractionResult extractionId={extraction.id} />
        </section>
      )}
    </div>
  );
}
