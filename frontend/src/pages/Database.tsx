import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, display, type CatalogClaim, type CatalogCompany, type CatalogCompanyDetail, type Page } from "../api";
import { Badge, Card, Crumbs, ErrorBox, Pager, when } from "../components/ui";

export default function DatabasePage({ orgId }: { orgId: string }) {
  const base = `/orgs/${orgId}/catalog`;
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [region, setRegion] = useState("");
  const [technology, setTechnology] = useState("");
  const [field, setField] = useState("");
  const [value, setValue] = useState("");
  const [includeReview, setIncludeReview] = useState(false);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const limit = 50;
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset), include_review: String(includeReview) });
  if (q.trim()) params.set("q", q.trim());
  if (region.trim()) params.set("region", region.trim());
  if (technology.trim()) params.set("technology", technology.trim());
  if (field.trim()) params.set("field", field.trim());
  if (value.trim()) params.set("value", value.trim());

  const catalog = useQuery({
    queryKey: ["catalog", orgId, params.toString()],
    queryFn: () => api.get<Page<CatalogCompany>>(`${base}?${params}`),
  });
  const detail = useQuery({
    queryKey: ["catalog-company", orgId, selected],
    enabled: !!selected,
    queryFn: () => api.get<CatalogCompanyDetail>(`${base}/${selected}`),
  });
  const rebuild = useMutation({
    mutationFn: () => api.post<{ jobs_scanned: number; companies: number; claims: number }>(`${base}/rebuild`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["catalog", orgId] }); qc.invalidateQueries({ queryKey: ["catalog-company", orgId] }); },
  });
  const review = useMutation({
    mutationFn: ({ claimId, decision }: { claimId: string; decision: "verify" | "reject" | "reopen" }) =>
      api.post<CatalogClaim>(`${base}/claims/${claimId}/review`, { decision }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["catalog", orgId] }); qc.invalidateQueries({ queryKey: ["catalog-company", orgId, selected] }); },
  });
  const resetPage = () => setOffset(0);

  return (
    <div>
      <Crumbs items={[["Research", "/"], ["Company database", null]]} />
      <div className="page-head">
        <div>
          <h1>Company database</h1>
          <p>Facts accumulate across research runs. Verified claims keep their source, quote, and review history.</p>
        </div>
        <div className="page-actions">
          <button onClick={() => rebuild.mutate()} disabled={rebuild.isPending}>
            {rebuild.isPending ? "Importing…" : "Import past results"}
          </button>
        </div>
      </div>

      <ErrorBox error={catalog.error || detail.error || rebuild.error || review.error} />
      {rebuild.data && <p className="small muted" role="status">
        Checked {rebuild.data.jobs_scanned.toLocaleString()} prior runs; found {rebuild.data.claims.toLocaleString()} eligible claims.
      </p>}

      <Card title="Search the catalog">
        <div className="row wrap">
          <input aria-label="Company or any fact" placeholder="Company, website, or any fact" value={q}
            onChange={(e) => { setQ(e.target.value); resetPage(); }} />
          <input aria-label="Region" placeholder="Region or country" value={region}
            onChange={(e) => { setRegion(e.target.value); resetPage(); }} />
          <input aria-label="Software" placeholder="Software used" value={technology}
            onChange={(e) => { setTechnology(e.target.value); resetPage(); }} />
        </div>
        <div className="row wrap" style={{ marginTop: 10 }}>
          <input aria-label="Field label" placeholder="Any field label (e.g. phone)" value={field}
            onChange={(e) => { setField(e.target.value); resetPage(); }} />
          <input aria-label="Field value" placeholder="Field value" value={value}
            onChange={(e) => { setValue(e.target.value); resetPage(); }} />
          <label className="check"><input type="checkbox" checked={includeReview}
            onChange={(e) => { setIncludeReview(e.target.checked); resetPage(); }} /> Include claims awaiting review</label>
        </div>
        <p className="small muted" style={{ marginTop: 12 }}>
          Search shows verified facts by default. Software use enters as verified only with a Confirmed evidence verdict;
          first-party profile fields wait here until a person checks the source.
        </p>
      </Card>

      <div className="database-layout">
        <Card title={catalog.data ? `${catalog.data.total.toLocaleString()} companies` : "Companies"}>
          <div className="table-wrap"><table>
            <thead><tr><th>Company</th><th>Verified location / website</th><th>Verified</th><th>Review</th></tr></thead>
            <tbody>{catalog.data?.items.map((company) => (
              <tr key={company.id} className={selected === company.id ? "selected-row" : "clickable"}>
                <td><button className="link" onClick={() => setSelected(company.id)}>{company.name || company.domain}</button>
                  {company.domain && <div className="small mono muted">{company.domain}</div>}</td>
                <td className="small">
                  {company.location && <div>{company.location}</div>}
                  {company.website && <a href={company.website} target="_blank" rel="noreferrer noopener">{company.website}</a>}
                </td>
                <td><Badge value="verified" /> <span className="mono small">{company.verified_claims}</span></td>
                <td>{company.review_claims > 0 ? <Badge value="needs_review" /> : <span className="muted small">—</span>}
                  {company.review_claims > 0 && <span className="mono small"> {company.review_claims}</span>}</td>
              </tr>
            ))}</tbody>
          </table></div>
          {catalog.data && <Pager total={catalog.data.total} limit={limit} offset={offset} onChange={setOffset} />}
          {catalog.data?.total === 0 && <p className="empty">No companies match. Run research or import eligible results from earlier runs.</p>}
        </Card>

        {selected && <Card title={detail.data?.name || "Company facts"} actions={<button className="ghost" onClick={() => setSelected(null)}>Close</button>}>
          {detail.data?.website && <p className="small"><a href={detail.data.website} target="_blank" rel="noreferrer noopener">{detail.data.website}</a></p>}
          {detail.data && <p className="small muted">Last seen {when(detail.data.last_seen_at)}. Each fact retains its original value, source, retrieval date, and license details.</p>}
          <div className="claim-list">
            {detail.data?.claims.map((claim) => <ClaimCard key={claim.id} claim={claim}
              busy={review.isPending} onReview={(decision) => review.mutate({ claimId: claim.id, decision })} />)}
          </div>
          {detail.data?.claims.length === 0 && <p className="empty">No saved claims for this company.</p>}
        </Card>}
      </div>
    </div>
  );
}

function ClaimCard({ claim, busy, onReview }: {
  claim: CatalogClaim; busy: boolean; onReview: (decision: "verify" | "reject" | "reopen") => void;
}) {
  return (
    <article className="claim-card">
      <div className="claim-title">
        <div><strong>{claim.field_key.replace(/_/g, " ")}</strong><div>{display(claim.value)}</div></div>
        <Badge value={claim.verification_status} />
      </div>
      <div className="small muted">Source type: {claim.source_type || claim.verification_method}
        {claim.confidence != null && <> · stored score {Math.round(claim.confidence * 100)}%</>}
        {claim.source_date && <> · evidence date {claim.source_date}</>}
      </div>
      <div className="small muted">Origin: {claim.source_origin || "unspecified"}
        {claim.source_group && <> · independent-source group: {claim.source_group}</>}
        {claim.source_record_id && <> · record: {claim.source_record_id}</>}
        {claim.retrieved_at && <> · retrieved {when(claim.retrieved_at)}</>}
      </div>
      {claim.quote && <blockquote>{claim.quote}</blockquote>}
      {claim.source_license && <div className="small muted">License: {claim.source_license}</div>}
      {!claim.quote && <div className="small muted">No excerpt was saved; check the linked source before verifying.</div>}
      {claim.source_url && <a className="small url" href={claim.source_url} target="_blank" rel="noreferrer noopener">Open source</a>}
      {claim.verification_status === "needs_review" && <div className="claim-actions">
        <button className="primary" disabled={busy} onClick={() => onReview("verify")}>Verify this fact</button>
        <button className="danger" disabled={busy} onClick={() => onReview("reject")}>Reject</button>
      </div>}
      {claim.verification_status === "verified" && <div className="claim-actions">
        <button disabled={busy} onClick={() => onReview("reopen")}>Reopen for review</button>
        <button className="danger" disabled={busy} onClick={() => onReview("reject")}>Reject</button>
      </div>}
      {claim.verification_status === "rejected" && <div className="claim-actions">
        <button disabled={busy} onClick={() => onReview("reopen")}>Reopen for review</button>
      </div>}
      {claim.verification_status === "verified" && claim.verification_method === "user_review" &&
        <div className="small muted">Verified by a member on {when(claim.verified_at)}.</div>}
    </article>
  );
}
