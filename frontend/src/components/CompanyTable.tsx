import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Radar, Star, X } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import type { CompanyListItem } from "@/api/types";
import { ScoreChip, SiteStateIcon, StatusPill } from "@/components/domain";
import { useToast } from "@/components/toast";
import { Button, Checkbox } from "@/components/ui";
import { SOURCES } from "@/lib/labels";
import { fmtPhone } from "@/lib/utils";

const MAX_BATCH = 50;

/** Tabela de empresas com seleção por checkbox e barra de ações flutuante (brief 4.3). */
export function CompanyTable({ rows, sources }: { rows: CompanyListItem[]; sources?: Record<number, string> }) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const toast = useToast();
  const navigate = useNavigate();
  const client = useQueryClient();

  const auditable = rows.filter((r) => r.site && r.site.auditavel);
  const allChecked = selected.size > 0 && selected.size === rows.length;
  const toggle = (id: number, on: boolean) =>
    setSelected((s) => {
      const next = new Set(s);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const audit = useMutation({
    mutationFn: (ids: number[]) => api.post<{ audit_ids: number[]; total: number }>("audits", { company_ids: ids }),
    onSuccess: (r) => {
      toast(`${r.total} auditoria(s) na fila.`);
      setSelected(new Set());
      client.invalidateQueries({ queryKey: ["dashboard"] });
      if (r.audit_ids.length === 1) navigate(`/auditorias/${r.audit_ids[0]}`);
      else navigate("/auditorias?status=na_fila,executando");
    },
    onError: (e) => toast(e.message, "error"),
  });

  const selectedAuditable = rows.filter((r) => selected.has(r.id) && r.site?.auditavel).length;

  return (
    <div className="relative">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="w-10 px-4 py-2">
                <Checkbox
                  label="Selecionar todas"
                  checked={allChecked}
                  indeterminate={selected.size > 0 && !allChecked}
                  onChange={(on) => setSelected(on ? new Set(rows.map((r) => r.id)) : new Set())}
                />
              </th>
              <th className="px-2 py-2 font-medium">Empresa</th>
              <th className="px-2 py-2 font-medium">Bairro</th>
              <th className="px-2 py-2 font-medium">Site</th>
              <th className="px-2 py-2 font-medium">Nota Google</th>
              <th className="px-2 py-2 font-medium">Nota do site</th>
              <th className="px-2 py-2 font-medium">Status do lead</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((r) => (
              <tr key={r.id} className={selected.has(r.id) ? "bg-brand/5" : "hover:bg-surface-2"}>
                <td className="px-4 py-2">
                  <Checkbox label={`Selecionar ${r.nome}`} checked={selected.has(r.id)} onChange={(on) => toggle(r.id, on)} />
                </td>
                <td className="max-w-72 px-2 py-2">
                  <Link to={`/leads/${r.id}`} className="block truncate font-medium hover:text-brand">
                    {r.nome}
                  </Link>
                  <span className="text-xs text-muted">
                    {fmtPhone(r.telefone)}
                    {sources?.[r.id] && <span className="ml-1.5 rounded bg-surface-2 px-1">{SOURCES[sources[r.id]]}</span>}
                  </span>
                </td>
                <td className="px-2 py-2 text-muted">{r.bairro || "—"}</td>
                <td className="px-2 py-2">
                  <SiteStateIcon state={r.situacao_site} />
                  {r.site && (
                    <a href={r.site.url} target="_blank" rel="noreferrer" className="block max-w-48 truncate text-xs text-muted hover:text-brand">
                      {r.site.dominio}
                    </a>
                  )}
                </td>
                <td className="px-2 py-2">
                  {r.nota_google ? (
                    <span className="inline-flex items-center gap-1 tabular-nums">
                      <Star className="size-3.5 fill-amber-400 text-amber-400" aria-hidden />
                      {Number(r.nota_google).toFixed(1).replace(".", ",")}
                      <span className="text-xs text-muted">({r.n_avaliacoes})</span>
                    </span>
                  ) : (
                    <span className="text-muted">—</span>
                  )}
                </td>
                <td className="px-2 py-2">
                  <ScoreChip score={r.nota_site} />
                </td>
                <td className="px-2 py-2">
                  <StatusPill status={r.status_lead} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected.size > 0 && (
        <div className="sticky bottom-4 z-10 mx-4 mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-2.5 shadow-lg" role="toolbar" aria-label="Ações da seleção">
          <span className="text-sm">
            <strong>{selected.size}</strong> selecionada(s) · {selectedAuditable} com site auditável
            {selectedAuditable > MAX_BATCH && <span className="text-bad"> (máximo {MAX_BATCH} por lote)</span>}
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
              <X className="size-3.5" /> Limpar
            </Button>
            <Button size="sm" disabled={!selectedAuditable || selectedAuditable > MAX_BATCH} loading={audit.isPending} onClick={() => audit.mutate([...selected])}>
              <Radar className="size-3.5" aria-hidden /> Auditar selecionados
            </Button>
          </div>
        </div>
      )}
      {rows.length > 0 && auditable.length === 0 && (
        <p className="px-4 py-2 text-xs text-muted">Nenhuma empresa desta lista tem site auditável — são ótimos leads para um site do zero.</p>
      )}
    </div>
  );
}
