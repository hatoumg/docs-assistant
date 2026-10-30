import { notFound } from "next/navigation";

import { Browser } from "@/components/Browser";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function FolderPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ file?: string }>;
}) {
  const { id } = await params;
  if (!UUID.test(id)) notFound();
  const { file } = await searchParams;
  const fileId = file && /^\d{1,9}$/.test(file) ? Number(file) : null;
  return <Browser folderId={id} openFileId={fileId} />;
}
