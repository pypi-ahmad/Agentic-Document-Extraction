"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileText, Image as ImageIcon, Loader2 } from "lucide-react";
import { uploadDocument, type DocumentResponse } from "@/lib/api";

interface FileUploadProps {
  onUploaded: (doc: DocumentResponse) => void;
}

export default function FileUpload({ onUploaded }: FileUploadProps) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (!file) return;
      setError(null);
      setUploading(true);

      try {
        const doc = await uploadDocument(file);
        onUploaded(doc);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setUploading(false);
      }
    },
    [onUploaded],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "image/png": [".png"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/tiff": [".tiff", ".tif"],
    },
    maxFiles: 1,
    disabled: uploading,
  });

  return (
    <div>
      <div
        {...getRootProps()}
        className={`relative cursor-pointer rounded-xl border-2 border-dashed p-12 text-center transition-colors ${
          isDragActive
            ? "border-primary-500 bg-primary-50"
            : "border-gray-300 hover:border-primary-400 hover:bg-gray-50"
        } ${uploading ? "pointer-events-none opacity-60" : ""}`}
      >
        <input {...getInputProps()} />

        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-10 w-10 animate-spin text-primary-500" />
            <p className="text-sm text-gray-600">Uploading...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div className="flex gap-2">
              <Upload className="h-8 w-8 text-gray-400" />
            </div>
            <div>
              <p className="text-base font-medium text-gray-700">
                {isDragActive
                  ? "Drop your file here"
                  : "Drag & drop a document here"}
              </p>
              <p className="mt-1 text-sm text-gray-500">
                or click to browse &mdash; PDF, PNG, JPG/JPEG, TIFF/TIF supported
              </p>
            </div>
            <div className="flex gap-4 text-xs text-gray-400">
              <span className="flex items-center gap-1">
                <FileText className="h-3.5 w-3.5" /> PDF
              </span>
              <span className="flex items-center gap-1">
                <ImageIcon className="h-3.5 w-3.5" /> PNG / JPG/JPEG / TIFF/TIF
              </span>
            </div>
          </div>
        )}
      </div>

      {error && (
        <p className="mt-3 text-sm text-red-600">{error}</p>
      )}
    </div>
  );
}
