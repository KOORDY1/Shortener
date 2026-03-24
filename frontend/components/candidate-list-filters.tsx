type FilterValues = {
  status?: string;
  risk_level?: string;
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
          <span className="muted">Type</span>
          <select className="input" name="type" defaultValue={values.type ?? ""}>
            <option value="">전체</option>
            <option value="context_commentary">context_commentary</option>
          </select>
        </label>
        <label className="field inline">
          <span className="muted">Status</span>
          <select className="input" name="status" defaultValue={values.status ?? ""}>
            <option value="">전체</option>
            <option value="generated">generated</option>
            <option value="selected">selected</option>
            <option value="rejected">rejected</option>
            <option value="drafted">drafted</option>
          </select>
        </label>
        <label className="field inline">
          <span className="muted">Risk</span>
          <select className="input" name="risk_level" defaultValue={values.risk_level ?? ""}>
            <option value="">전체</option>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
        </label>
        <label className="field inline">
          <span className="muted">Min score</span>
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
          <span className="muted">Sort</span>
          <select className="input" name="sort_by" defaultValue={values.sort_by ?? "total_score"}>
            <option value="total_score">total_score</option>
            <option value="risk_score">risk_score</option>
            <option value="start_time">start_time</option>
          </select>
        </label>
        <label className="field inline">
          <span className="muted">Order</span>
          <select className="input" name="order" defaultValue={values.order ?? "desc"}>
            <option value="desc">desc</option>
            <option value="asc">asc</option>
          </select>
        </label>
        <button type="submit" className="button ghost">
          필터 적용
        </button>
      </div>
    </form>
  );
}
