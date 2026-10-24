import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, display, type RecordDetail, type Schema } from "../api";
import { Badge, ErrorBox } from "./ui";

export default function RecordDrawer({ base, recordId, schema, onClose }:
  { base: string; recordId: string; schema: Schema; onClose: () => void }) {
  const qc = useQueryClient();
  const rec = useQuery({ queryKey: ["record", recordId], queryFn: () => api.get<RecordDetail>(`${base}/records/${recordId}`) });
  const [edits, setEdits] = useState<Record<string, string>>({});
  useEffect(() => setEdits({}), [recordId]);
  const save = useMutation({
    mutationFn: (body: object) => api.patch<RecordDetail>(`${base}/records/${recordId}`, body),
    onSuccess: (r) => { qc.setQueryData(["record", recordId], r); qc.invalidateQueries({ queryKey: ["records"] }); setEdits({}); },
  });
  const r = rec.data;

  return (
    <div className="drawer" role="dialog" aria-label="Record details">
      <div className="drawer-head">
        <h2>Record {r && <Badge value={r.status} />}</h2>
        <button className="icon" onClick={onClose} aria-label="Close">✕</button>
      </div>
      {r && (
        <>
          {schema.spec.fields.map((f) => {
            const values = r.fields.filter((v) => v.field_name === f.name);
            const chosen = values.find((v) => v.selected);
            return (
              <div key={f.name} className="fv">
                <label>{f.label || f.name} <span className="muted small">{f.type}{f.required ? " · required" : ""}</span>
                  <input value={edits[f.name] ?? display(r.data[f.name])}
                         onChange={(e) => setEdits({ ...edits, [f.name]: e.target.value })} /></label>
                {chosen ? (
                  <p className="small muted">
                    {chosen.value_status} via {chosen.method}
                    {chosen.confidence != null && ` · ${Math.round(chosen.confidence * 100)}% confidence`}
                    {chosen.source_url && <> · <a href={chosen.source_url} target="_blank" rel="noreferrer noopener">source</a></>}
                    {chosen.evidence && <><br /><q>{chosen.evidence}</q></>}
                    {chosen.error && <><br /><span className="error">{chosen.error}</span></>}
                  </p>
                ) : <p className="small muted">not found on the crawled pages</p>}
                {values.filter((v) => !v.selected && v.value_status === "found").length > 0 && (
                  <details className="small"><summary>Other candidates</summary>
                    <ul>{values.filter((v) => !v.selected).map((v, i) => <li key={i}>{display(v.value)} <span className="muted">({v.method})</span></li>)}</ul>
                  </details>)}
              </div>
            );
          })}
          <ErrorBox error={save.error} />
          <div className="row">
            <button className="primary" disabled={!Object.keys(edits).length || save.isPending}
                    onClick={() => save.mutate({ data: edits })}>Save corrections</button>
            <button onClick={() => save.mutate({ excluded: !r.excluded })}>{r.excluded ? "Include in export" : "Exclude from export"}</button>
          </div>
          <p className="small muted">Sources: {r.source_urls.map((u) => <a key={u} href={u} target="_blank" rel="noreferrer noopener" className="url">{u} </a>)}</p>
        </>
      )}
    </div>
  );
}
