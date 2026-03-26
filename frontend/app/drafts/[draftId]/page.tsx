import { notFound } from "next/navigation";
import { VideoDraftLiveView } from "@/components/video-draft-live-view";
import { getVideoDraft } from "@/lib/api";

export default async function VideoDraftPage({
  params
}: {
  params: Promise<{ draftId: string }>;
}) {
  const { draftId } = await params;
  const draft = await getVideoDraft(draftId).catch(() => notFound());

  return <VideoDraftLiveView initialDraft={draft} />;
}
