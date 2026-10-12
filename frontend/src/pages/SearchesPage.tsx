import { useQuery } from "@tanstack/react-query";
import { Search as SearchIcon } from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type { Page, Search } from "@/api/types";
import { PageBody, PageHeader } from "@/components/Layout";
import { Badge, Card, EmptyState, ErrorState, Loading, Spinner, buttonClass } from "@/components/ui";
import { fmtDateTime } from "@/lib/utils";

export const SEARCH_STATUS: Record<Search["status"], { nome: string; className: string }> = {
  na_fila: { nome: "Na fila", className: "bg-surface-2 text-muted" },
  executando: { nome: "Buscando…", className: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300" },
  concluida: { nome: "Concluída", className: "bg-good-soft text-good" },
  falhou: { nome: "Falhou", className: "bg-bad-soft text-bad" },
};

export default function SearchesPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["searches"],
    queryFn: () => api.get<Page<Search>>("searches"),
    refetchInterval: (q) => (q.state.data?.results.some((s) => s.status === "executando" || s.status === "na_fila") ? 3000 : false),
  });

  return (
    <>
      <PageHeader
        title="Buscas"
        description="Histórico de prospecções por categoria e cidade"
        actions={
          <Link to="/buscas/nova" className={buttonClass()}>
            <SearchIcon className="size-4" aria-hidden /> Nova busca
          </Link>
        }
      />
      <PageBody>
        <Card>
          {isLoading && <Loading />}
          {error && <ErrorState error={error} onRetry={refetch} />}
          {data?.results.length === 0 && (
            <EmptyState
              icon={SearchIcon}
              title="Nenhuma busca ainda"
              description="Busque empresas por categoria + cidade para montar sua lista de prospecção."
              action={
                <Link to="/buscas/nova" className={buttonClass()}>Nova busca</Link>
              }
            />
          )}
          {!!data?.results.length && (
            <table className="w-full text-sm">
              <thead className="border-b border-border text-left text-xs text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Busca</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 text-right font-medium">Empresas</th>
                  <th className="px-4 py-2 font-medium">Fontes</th>
                  <th className="px-4 py-2 font-medium">Quando</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.results.map((s) => (
                  <tr key={s.id} className="hover:bg-surface-2">
                    <td className="px-4 py-2.5">
                      <Link to={`/buscas/${s.id}`} className="font-medium hover:text-brand">
                        {s.descricao}
                      </Link>
                      {s.bairro && <span className="text-muted"> · {s.bairro}</span>}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge className={SEARCH_STATUS[s.status].className}>
                        {s.status === "executando" && <Spinner className="size-3" />} {SEARCH_STATUS[s.status].nome}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{s.total_encontrado}</td>
                    <td className="px-4 py-2.5 text-xs text-muted">
                      {s.fontes.cache_de ? `cache da busca #${s.fontes.cache_de}` : [s.fontes.places && `Google ${s.fontes.places}`, s.fontes.osm && `OSM ${s.fontes.osm}`, s.fontes.cnpj && `CNPJ ${s.fontes.cnpj}`, s.fontes.web && `Web ${s.fontes.web}`, s.fontes.sites_por_email && `${s.fontes.sites_por_email} sites a verificar`].filter(Boolean).join(" · ") || "—"}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted">
                      {fmtDateTime(s.criado_em)} · {s.criado_por_nome}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </PageBody>
    </>
  );
}
