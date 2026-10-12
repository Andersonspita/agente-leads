import { useQuery } from "@tanstack/react-query";
import { Download, SearchX } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { api, qs } from "@/api/client";
import type { Page, Search, SearchResult } from "@/api/types";
import { CompanyFilters, useFilters } from "@/components/CompanyFilters";
import { CompanyTable } from "@/components/CompanyTable";
import { PageBody, PageHeader } from "@/components/Layout";
import { Badge, Card, EmptyState, ErrorState, Loading, Pagination, Spinner, buttonClass } from "@/components/ui";
import { SEARCH_STATUS } from "./SearchesPage";

/** Depois da busca, os sites vindos do e-mail do CNPJ ainda são verificados por alguns minutos. */
function emailProbesPending(search?: Search) {
  if (!search?.fontes.sites_por_email || !search.concluido_em) return false;
  return Date.now() - new Date(search.concluido_em).getTime() < 3 * 60_000;
}

export default function SearchResultsPage() {
  const { id } = useParams();
  const filters = useFilters();
  const { values, page } = filters;
  const search = useQuery({
    queryKey: ["search", id],
    queryFn: () => api.get<Search>(`searches/${id}`),
    refetchInterval: (q) => (q.state.data && ["na_fila", "executando"].includes(q.state.data.status) ? 2500 : false),
  });
  const running = search.data && ["na_fila", "executando"].includes(search.data.status);
  const filterQs = qs({ ...values, page: undefined });
  const results = useQuery({
    queryKey: ["search-results", id, values],
    queryFn: () => api.get<Page<SearchResult>>(`searches/${id}/results${qs({ ...values, page })}`),
    refetchInterval: running || emailProbesPending(search.data) ? 3000 : false,
  });
  const s = search.data;
  const sources = Object.fromEntries((results.data?.results ?? []).map((r) => [r.company.id, r.fonte]));

  return (
    <>
      <PageHeader
        back={<Link to="/buscas">← Buscas</Link>}
        title={s ? s.descricao : "Resultados"}
        description={
          s && (
            <span className="inline-flex items-center gap-2">
              <Badge className={SEARCH_STATUS[s.status].className}>
                {running && <Spinner className="size-3" />} {SEARCH_STATUS[s.status].nome}
              </Badge>
              {s.total_encontrado} empresas
              {s.fontes.cache_de ? ` · reaproveitada do cache (busca #${s.fontes.cache_de})` : ""}
            </span>
          )
        }
        actions={
          <a href={`/api/searches/${id}/results${filterQs ? filterQs + "&" : "?"}formato=csv`} className={buttonClass({ variant: "outline" })}>
            <Download className="size-4" aria-hidden /> Exportar CSV
          </a>
        }
      />
      <PageBody>
        {s && [...(s.fontes.erros ?? []), ...(s.fontes.avisos ?? [])].length > 0 && (
          <div className="rounded-md border border-weak/30 bg-weak-soft px-4 py-2 text-xs text-weak">
            {[...(s.fontes.erros ?? []), ...(s.fontes.avisos ?? [])].map((e) => (
              <p key={e}>{e}</p>
            ))}
          </div>
        )}
        {!!s?.fontes.sites_por_email && (
          <p className="rounded-md bg-surface-2 px-4 py-2 text-xs text-muted">
            {s.fontes.sites_por_email} possível(is) site(s) encontrados pelo domínio do e-mail cadastrado na Receita estão sendo verificados em segundo plano. Os confirmados passam a aparecer como “Tem site”.
          </p>
        )}
        <Card>
          <CompanyFilters {...filters} />
          {results.isLoading && <Loading />}
          {results.error && <ErrorState error={results.error} onRetry={results.refetch} />}
          {results.data && results.data.results.length === 0 && (
            running ? <Loading label="Buscando empresas…" /> : <EmptyState icon={SearchX} title="Nenhuma empresa com estes filtros" description="Ajuste os filtros ou tente outra categoria/cidade." />
          )}
          {results.data && results.data.results.length > 0 && (
            <>
              <CompanyTable rows={results.data.results.map((r) => r.company)} sources={sources} />
              <Pagination page={page} count={results.data.count} onPage={(p) => filters.set("page", String(p))} />
            </>
          )}
        </Card>
      </PageBody>
    </>
  );
}
