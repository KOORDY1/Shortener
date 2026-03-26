import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { EpisodeTable } from "@/components/episode-table";
import { getEpisodes } from "@/lib/api";

export default async function EpisodesPage({
  searchParams
}: {
  searchParams: Promise<{ status?: string; show_title?: string }>;
}) {
  const filters = await searchParams;
  const response = await getEpisodes(filters);

  return (
    <main className="page">
      <PageHeader
        title="에피소드"
        subtitle="업로드된 에피소드 상태를 확인하고 분석 또는 후보 검토로 진입합니다."
        actions={
          <Link href="/episodes/new" className="link-button primary">
            새 업로드
          </Link>
        }
      />
      <div className="panel soft">
        <div className="row">
          <span className="badge">전체 {response.total}건</span>
          {filters.status ? <span className="badge">상태={filters.status}</span> : null}
          {filters.show_title ? <span className="badge">검색={filters.show_title}</span> : null}
        </div>
      </div>
      <EpisodeTable episodes={response.items} />
    </main>
  );
}
