import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-gray-50 px-6 py-16">
      <div className="mx-auto max-w-2xl rounded-lg border bg-white p-8 shadow-sm">
        <h1 className="text-3xl font-bold text-gray-900">TeachOnce</h1>
        <p className="mt-3 text-gray-600">
          Upload one screen recording and generate a reusable automation workflow.
        </p>
        <div className="mt-8 flex gap-3">
          <Link
            href="/upload"
            className="inline-flex rounded-md bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700"
          >
            Upload Recording
          </Link>
          <Link
            href="/parseprompt"
            className="inline-flex rounded-md border border-gray-300 bg-white px-4 py-2 font-medium text-gray-700 hover:bg-gray-50"
          >
            Parse prompt
          </Link>
          <Link
            href="/greenhouse"
            className="inline-flex rounded-md border border-gray-300 bg-white px-4 py-2 font-medium text-gray-700 hover:bg-gray-50"
          >
            Greenhouse apply
          </Link>
        </div>
      </div>
    </main>
  );
}
