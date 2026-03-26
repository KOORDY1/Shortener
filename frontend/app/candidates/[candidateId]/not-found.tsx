import Link from "next/link";
import { PageHeader } from "@/components/page-header";

export default function CandidateNotFoundPage() {
  return (
    <main className="page">
      <PageHeader
        title="후보를 찾을 수 없습니다"
        subtitle="재분석 후에는 예전 후보 ID가 더 이상 유효하지 않을 수 있습니다."
        backHref="/episodes"
      />
      <div className="panel">
        <p>
          이 후보는 삭제되었거나, 재분석 과정에서 새 후보 목록으로 교체되었을 가능성이 큽니다.
        </p>
        <div className="row">
          <Link href="/episodes" className="link-button primary">
            에피소드 목록으로
          </Link>
        </div>
      </div>
    </main>
  );
}
