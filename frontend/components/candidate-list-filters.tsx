type FilterValues = {
  status?: string;
  type?: string;
  min_score?: string;
  sort_by?: string;
  order?: string;
};

type Props = {
  episodeId: string;
  values: FilterValues;
};

export function CandidateListFilters({ episodeId, values }: Props) {
  return (
    <form action={`/episodes/${episodeId}/candidates`} method="get" className="panel soft filter-form">
      <div className="row wrap">
        <label className="field inline">
          <span className="muted">유형</span>
          <select className="input" name="type" defaultValue={values.type ?? ""}>
            <option value="">전체</option>
            <option value="context_commentary">맥락 해설</option>
          </select>
        </label>
        <label className="field inline">
          <span className="muted">상태</span>
          <select className="input" name="status" defaultValue={values.status ?? ""}>
            <option value="">전체</option>
            <option value="generated">생성됨</option>
            <option value="selected">선택됨</option>
            <option value="rejected">거절됨</option>
            <option value="drafted">초안</option>
          </select>
        </label>
        <label className="field inline">
          <span className="muted">최소 점수</span>
          <input
            className="input narrow"
            name="min_score"
            type="number"
            step="0.1"
            min="0"
            max="10"
            placeholder="예: 8"
            defaultValue={values.min_score ?? ""}
          />
        </label>
        <label className="field inline">
          <span className="muted">정렬 기준</span>
          <select className="input" name="sort_by" defaultValue={values.sort_by ?? "total_score"}>
            <option value="total_score">총점</option>
            <option value="start_time">시작 시각</option>
          </select>
        </label>
        <label className="field inline">
          <span className="muted">순서</span>
          <select className="input" name="order" defaultValue={values.order ?? "desc"}>
            <option value="desc">내림차순 (큰 값 먼저)</option>
            <option value="asc">오름차순 (작은 값 먼저)</option>
          </select>
        </label>
        <button type="submit" className="button ghost">
          필터 적용
        </button>
      </div>
    </form>
  );
}
