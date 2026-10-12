import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type { Briefing, BriefingContent, CompanyDetail, Page } from "@/api/types";
import { PageBody, PageHeader } from "@/components/Layout";
import { ScoreChip, SeverityBadge } from "@/components/domain";
import { useToast } from "@/components/toast";
import { useUnsavedChanges } from "@/lib/useUnsavedChanges";
import { Button, Card, CardHeader, EmptyState, Input, Loading, Select, buttonClass } from "@/components/ui";
import { fmtDate } from "@/lib/utils";

type ListKey = "paginas" | "secoes" | "integracoes" | "conteudo_necessario";
const LISTS: { key: ListKey; title: string }[] = [
  { key: "paginas", title: "Páginas" },
  { key: "secoes", title: "Seções obrigatórias" },
  { key: "integracoes", title: "Integrações" },
  { key: "conteudo_necessario", title: "Conteúdo a pedir ao cliente" },
];

export default function BriefingPage() {
  const { id } = useParams();
  const client = useQueryClient();
  const toast = useToast();
  const company = useQuery({ queryKey: ["company", id], queryFn: () => api.get<CompanyDetail>(`companies/${id}`) });
  const list = useQuery({ queryKey: ["briefings", { empresa: id }], queryFn: () => api.get<Page<Briefing>>(`briefings?empresa=${id}`) });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const briefing = list.data?.results.find((b) => b.id === selectedId) ?? list.data?.results[0];
  const [content, setContent] = useState<BriefingContent | null>(null);

  useEffect(() => {
    setContent(briefing ? structuredClone(briefing.conteudo) : null);
  }, [briefing?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const create = useMutation({
    mutationFn: () => api.post<Briefing>("briefings", { company: Number(id) }),
    onSuccess: (b) => {
      client.invalidateQueries({ queryKey: ["briefings"] });
      setSelectedId(b.id);
      toast(`Briefing v${b.versao} gerado a partir dos achados confirmados.`);
    },
    onError: (e) => toast(e.message, "error"),
  });
  const save = useMutation({
    mutationFn: () => api.patch(`briefings/${briefing!.id}`, { conteudo: content! }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["briefings"] });
      toast("Briefing salvo.");
    },
    onError: (e) => toast(e.message, "error"),
  });
  const dirty = !!briefing && !!content && JSON.stringify(content) !== JSON.stringify(briefing.conteudo);
  useUnsavedChanges(dirty);

  const editList = (key: ListKey, fn: (items: string[]) => string[]) => setContent((c) => c && { ...c, [key]: fn(c[key]) });

  return (
    <>
      <PageHeader
        back={<Link to={`/leads/${id}`}>← {company.data?.nome ?? "Lead"}</Link>}
        title="Briefing do site novo"
        description="Cada falha apontada no diagnóstico vira um requisito para a equipe de desenvolvimento"
        actions={
          <>
            {list.data && list.data.results.length > 1 && (
              <Select aria-label="Versão" className="w-32" value={briefing?.id} onChange={(e) => setSelectedId(Number(e.target.value))}>
                {list.data.results.map((b) => (
                  <option key={b.id} value={b.id}>
                    v{b.versao} · {fmtDate(b.criado_em)}
                  </option>
                ))}
              </Select>
            )}
            {briefing && (
              <>
                <a href={`/api/briefings/${briefing.id}/pdf`} className={buttonClass({ variant: "outline" })}>
                  <Download className="size-4" aria-hidden /> PDF
                </a>
                <a href={`/api/briefings/${briefing.id}/markdown`} className={buttonClass({ variant: "outline" })}>
                  <Download className="size-4" aria-hidden /> Markdown
                </a>
              </>
            )}
            <Button variant={briefing ? "outline" : "primary"} onClick={() => create.mutate()} loading={create.isPending}>
              <Plus className="size-4" aria-hidden /> {briefing ? "Nova versão" : "Gerar briefing"}
            </Button>
            {briefing && (
              <Button onClick={() => save.mutate()} disabled={!dirty} loading={save.isPending}>
                Salvar
              </Button>
            )}
          </>
        }
      />
      <PageBody>
        {list.isLoading && <Loading />}
        {list.data?.results.length === 0 && (
          <Card>
            <EmptyState icon={FileText} title="Nenhum briefing ainda" description="O briefing junta os achados confirmados da última auditoria com o checklist mínimo da categoria (páginas, seções, integrações e metas de desempenho)." action={<Button onClick={() => create.mutate()} loading={create.isPending}>Gerar briefing</Button>} />
          </Card>
        )}
        {content && (
          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="lg:col-span-2">
              <CardHeader title={content.empresa.nome} description={`${content.empresa.categoria || "—"} · ${content.empresa.cidade || "—"} · site atual: ${content.empresa.site_atual || "sem site"}`} actions={<ScoreChip score={content.nota_atual} />} />
              {content.requisitos.length > 0 ? (
                <table className="w-full text-sm">
                  <thead className="border-b border-border text-left text-xs text-muted">
                    <tr>
                      <th className="px-4 py-2 font-medium">Severidade</th>
                      <th className="px-4 py-2 font-medium">Problema no site atual</th>
                      <th className="px-4 py-2 font-medium">Requisito no site novo</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {content.requisitos.map((r, i) => (
                      <tr key={r.achado_id}>
                        <td className="px-4 py-2 align-top">
                          <SeverityBadge severity={r.severidade} />
                        </td>
                        <td className="px-4 py-2 align-top">{r.problema}</td>
                        <td className="px-4 py-2 align-top">
                          <Input
                            aria-label={`Requisito para ${r.problema}`}
                            value={r.requisito}
                            onChange={(e) => setContent((c) => c && { ...c, requisitos: c.requisitos.map((x, j) => (j === i ? { ...x, requisito: e.target.value } : x)) })}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="px-4 py-4 text-sm text-muted">Sem auditoria concluída: briefing baseado só no checklist da categoria (site do zero).</p>
              )}
            </Card>

            {LISTS.map(({ key, title }) => (
              <EditableList key={key} title={title} items={content[key]} onChange={(fn) => editList(key, fn)} />
            ))}

            <Card className="lg:col-span-2">
              <CardHeader title="Metas de qualidade" description="Critérios de aceite do site entregue (reauditoria)" />
              <ul className="divide-y divide-border text-sm">
                {content.metas.map((m, i) => (
                  <li key={i} className="grid grid-cols-[1fr_1fr] gap-4 px-4 py-2">
                    <span>{m.meta}</span>
                    <span className="text-muted">{m.alvo}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        )}
      </PageBody>
    </>
  );
}

function EditableList({ title, items, onChange }: { title: string; items: string[]; onChange: (fn: (items: string[]) => string[]) => void }) {
  const [draft, setDraft] = useState("");
  return (
    <Card>
      <CardHeader title={title} />
      <ul className="divide-y divide-border text-sm">
        {items.map((item, i) => (
          <li key={i} className="group flex items-center justify-between gap-2 px-4 py-1.5">
            <span>{item}</span>
            <button className="rounded p-1 text-muted opacity-0 hover:text-bad focus:opacity-100 group-hover:opacity-100" aria-label={`Remover ${item}`} onClick={() => onChange((xs) => xs.filter((_, j) => j !== i))}>
              <Trash2 className="size-3.5" />
            </button>
          </li>
        ))}
      </ul>
      <form
        className="flex gap-2 border-t border-border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim()) onChange((xs) => [...xs, draft.trim()]);
          setDraft("");
        }}
      >
        <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Adicionar item" aria-label={`Adicionar em ${title}`} />
        <Button variant="outline" type="submit">
          Adicionar
        </Button>
      </form>
    </Card>
  );
}
