import { PageHeader } from "@/components/page-header";
import { UploadForm } from "@/components/upload-form";

export default function NewEpisodePage() {
  return (
    <main className="page">
      <PageHeader
        title="New Episode Upload"
        subtitle="영상과 선택 자막을 등록해 분석 파이프라인의 시작점을 만듭니다."
        backHref="/episodes"
      />
      <UploadForm />
    </main>
  );
}
