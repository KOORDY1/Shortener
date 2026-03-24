import { notFound } from "next/navigation";
import { CandidateCard } from "@/components/candidate-card";
import { CandidateListFilters } from "@/components/candidate-list-filters";
import { PageHeader } from "@/components/page-header";
import { getEpisode, getEpisodeCandidates } from "@/lib/api";

export default async function EpisodeCandidatesPage({
  params,
  searchParams
}: {
  params: Promise<{ episodeId: string }>;
  searchParams: Promise<{
    status?: string;
    min_score?: string;
    risk_level?: string;
    type?: string;
    sort_by?: string;
    order?: string;
  }>;
}) {
  const { episodeId } = await params;
  const filters = await searchParams;

  try {
    const [episode, candidates] = await Promise.all([
      getEpisode(episodeId),
      getEpisodeCandidates(episodeId, filters)
    ]);

    return (
      <main className="page">
        <PageHeader
          title={`Candidates - ${episode.show_title}`}
          subtitle="후보 카드에서 바로 스크립트 생성, 선택, 거절을 처리합니다."
          backHref={`/episodes/${episodeId}`}
        />
        <CandidateListFilters episodeId={episodeId} values={filters} />
        <div className="panel soft">
          <div className="row">
            <span className="badge">Total {candidates.total}</span>
            {filters.type ? <span className="badge">type={filters.type}</span> : null}
            {filters.status ? <span className="badge">status={filters.status}</span> : null}
            {filters.risk_level ? <span className="badge">risk={filters.risk_level}</span> : null}
            {filters.min_score ? <span className="badge">min_score={filters.min_score}</span> : null}
            {filters.sort_by ? <span className="badge">sort={filters.sort_by}</span> : null}
            {filters.order ? <span className="badge">order={filters.order}</span> : null}
          </div>
        </div>
        <div className="card-list">
          {candidates.items.map((candidate) => (
            <CandidateCard key={candidate.id} candidate={candidate} />
          ))}
        </div>
      </main>
    );
  } catch {
    notFound();
  }
}
