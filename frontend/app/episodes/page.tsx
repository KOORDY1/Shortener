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
        title="Episodes"
        subtitle="업로드된 에피소드 상태를 확인하고 분석 또는 후보 검토로 진입합니다."
        actions={
          <Link href="/episodes/new" className="link-button primary">
            New Upload
          </Link>
        }
      />
      <div className="panel soft">
        <div className="row">
          <span className="badge">Total {response.total}</span>
          {filters.status ? <span className="badge">status={filters.status}</span> : null}
          {filters.show_title ? <span className="badge">search={filters.show_title}</span> : null}
        </div>
      </div>
      <EpisodeTable episodes={response.items} />
    </main>
  );
}
