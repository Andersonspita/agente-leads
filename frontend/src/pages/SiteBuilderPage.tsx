import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Download, ExternalLink, Loader2, Monitor, Plus, Radar, Smartphone, Sparkles, Trash2, Wand2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type { CompanyDetail, Page, SiteAuditSummary, SiteContent, SiteProject } from "@/api/types";
import { PageHeader } from "@/components/Layout";
import { ScoreGauge } from "@/components/domain";
import { useToast } from "@/components/toast";
import { useUnsavedChanges } from "@/lib/useUnsavedChanges";
import { Badge, Button, Card, CardHeader, Checkbox, EmptyState, Field, Input, Loading, Select, Tabs, Textarea, buttonClass } from "@/components/ui";
import { DIMENSIONS, DIMENSION_ORDER } from "@/lib/labels";
import { bandText, cn, fmtDateTime } from "@/lib/utils";

type Tab = "dados" | "textos" | "servicos" | "faq";
type ListKey = "servicos" | "diferenciais";

export default function SiteBuilderPage() {
  const { id } = useParams();
  const client = useQueryClient();
  const toast = useToast();
  const company = useQuery({ queryKey: ["company", id], queryFn: () => api.get<CompanyDetail>(`companies/${id}`) });
  const list = useQuery({
    queryKey: ["sites", id],
    queryFn: () => api.get<Page<SiteProject>>(`sites?empresa=${id}`),
    refetchInterval: (q) => {
      const p = q.state.data?.results[0];
      if (p?.ia_status === "pendente") return 5000;
      return p?.auditoria_site_novo && ["na_fila", "executando"].includes(p.auditoria_site_novo.status) ? 3000 : false;
    },
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const project = list.data?.results.find((p) => p.id === selectedId) ?? list.data?.results[0];
  const [draft, setDraft] = useState<SiteContent | null>(null);
  const [tab, setTab] = useState<Tab>("textos");
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [previewKey, setPreviewKey] = useState(0);

  useEffect(() => {
    setDraft(project ? structuredClone(project.conteudo) : null);
  }, [project?.id, project?.atualizado_em]); // eslint-disable-line react-hooks/exhaustive-deps

  const invalidate = () => client.invalidateQueries({ queryKey: ["sites", id] });
  const generate = useMutation({
    mutationFn: () => api.post<SiteProject>("sites", { company: Number(id) }),
    onSuccess: (p) => {
      invalidate();
      setSelectedId(p.id);
      toast(p.ia_status === "pendente" ? "Site gerado. A IA está escrevendo os textos em segundo plano." : "Site gerado com textos-base (IA não configurada). Revise os textos.");
    },
    onError: (e) => toast(e.message, "error"),
  });
  const save = useMutation({
    mutationFn: () => api.patch<SiteProject>(`sites/${project!.id}`, { conteudo: draft! }),
    onSuccess: () => {
      invalidate();
      setPreviewKey((k) => k + 1);
      toast("Site atualizado.");
    },
    onError: (e) => toast(e.message, "error"),
  });
  const audit = useMutation({
    mutationFn: () => api.post<{ audit_id: number }>(`sites/${project!.id}/audit`),
    onSuccess: () => {
      invalidate();
      toast("Auditoria do site novo na fila (cerca de 1 a 3 minutos).");
    },
    onError: (e) => toast(e.message, "error"),
  });

  const dirty = !!project && !!draft && JSON.stringify(draft) !== JSON.stringify(project.conteudo);
  useUnsavedChanges(dirty);
  const set = <K extends keyof SiteContent>(key: K, value: SiteContent[K]) => setDraft((d) => (d ? { ...d, [key]: value } : d));
  const setItem = (key: ListKey, i: number, field: "titulo" | "descricao", value: string) =>
    setDraft((d) => (d ? { ...d, [key]: d[key].map((it, j) => (j === i ? { ...it, [field]: value } : it)) } : d));

  if (company.isLoading || list.isLoading) return <Loading />;
  const c = company.data;
  const novo = project?.auditoria_site_novo;
  const auditing = !!novo && ["na_fila", "executando"].includes(novo.status);
  const writing = project?.ia_status === "pendente"; // edição travada: a IA vai substituir os textos
  const origem = project?.gerado_por_ia ? `textos por IA (${project.modelo_ia})`
    : writing ? "IA escrevendo os textos…" : project?.ia_status === "falhou" ? "textos-base (a IA não respondeu)" : "textos-base, sem IA";

  return (
    <div className="flex h-screen flex-col">
      <PageHeader
        back={<Link to={`/leads/${id}`}>← {c?.nome}</Link>}
        title="Site novo"
        description={project ? `Versão de ${fmtDateTime(project.atualizado_em)} · ${origem}` : "Gera um site completo que resolve as falhas do diagnóstico"}
        actions={
          project && (
            <>
              {list.data && list.data.results.length > 1 && (
                <Select aria-label="Versão" className="w-44" value={project.id} onChange={(e) => setSelectedId(Number(e.target.value))}>
                  {list.data.results.map((p) => (
                    <option key={p.id} value={p.id}>
                      {fmtDateTime(p.criado_em)}
                    </option>
                  ))}
                </Select>
              )}
              <Button variant="outline" onClick={() => generate.mutate()} loading={generate.isPending} title="Gera uma nova versão do zero">
                <Wand2 className="size-4" aria-hidden /> Gerar de novo
              </Button>
              <a href={`/api/sites/${project.id}/download`} className={buttonClass({ variant: "outline" })} aria-disabled={dirty}
                onClick={(e) => dirty && e.preventDefault()} title={dirty ? "Salve antes de baixar" : undefined}>
                <Download className="size-4" aria-hidden /> Baixar .zip
              </a>
              <Button onClick={() => save.mutate()} disabled={!dirty || writing} loading={save.isPending}>
                Salvar
              </Button>
            </>
          )
        }
      />

      {!project ? (
        <div className="p-6">
          <Card>
            <EmptyState
              icon={Sparkles}
              title="Nenhum site gerado ainda"
              description="O site novo é montado a partir do diagnóstico e do checklist da categoria: rápido, responsivo, acessível, com WhatsApp, mapa, dados para o Google e política de privacidade. Com a IA configurada, os textos são escritos para a empresa (leva cerca de 1 minuto)."
              action={
                <Button onClick={() => generate.mutate()} loading={generate.isPending}>
                  <Wand2 className="size-4" aria-hidden /> Gerar site novo
                </Button>
              }
            />
          </Card>
        </div>
      ) : (
        draft && (
          <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(380px,0.85fr)_1.15fr]">
            <div className="min-h-0 space-y-4 overflow-y-auto border-r border-border p-4">
              <Comparison original={project.auditoria_original} novo={novo} auditing={auditing} onAudit={() => audit.mutate()} loading={audit.isPending} dirty={dirty} />

              {draft.a_confirmar.length > 0 && (
                <Card className="border-weak/40">
                  <CardHeader title="Confirmar com o cliente" description="Itens que o sistema não sabe e não deve inventar" />
                  <ul className="space-y-1.5 p-4 text-sm">
                    {draft.a_confirmar.map((item) => (
                      <li key={item} className="flex items-start gap-2">
                        <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-weak" aria-hidden /> {item}
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              {writing && (
                <p role="status" className="flex items-center gap-2 rounded-md border border-dashed border-border px-3 py-2 text-sm text-muted">
                  <Loader2 className="size-4 animate-spin" aria-hidden /> A IA está escrevendo os textos (pode levar alguns minutos). A edição libera quando terminar.
                </p>
              )}

              <Card>
                <div className="px-4 pt-2">
                  <Tabs
                    value={tab}
                    onChange={setTab}
                    items={[
                      { value: "textos", label: "Textos" },
                      { value: "dados", label: "Dados e cores" },
                      { value: "servicos", label: "Serviços" },
                      { value: "faq", label: "Dúvidas" },
                    ]}
                  />
                </div>
                <fieldset disabled={writing} className="min-w-0 space-y-3 p-4 disabled:opacity-60">
                  {tab === "textos" && (
                    <>
                      <Field label="Título principal (H1)" htmlFor="s-h"><Input id="s-h" value={draft.headline} onChange={(e) => set("headline", e.target.value)} /></Field>
                      <Field label="Subtítulo" htmlFor="s-sub"><Textarea id="s-sub" rows={2} value={draft.subheadline} onChange={(e) => set("subheadline", e.target.value)} /></Field>
                      <Field label="Sobre a empresa" htmlFor="s-sobre" hint="Separe parágrafos com uma linha em branco"><Textarea id="s-sobre" rows={6} value={draft.sobre} onChange={(e) => set("sobre", e.target.value)} /></Field>
                      <Field label={`Título no Google (${draft.titulo_seo.length}/60)`} htmlFor="s-ts"><Input id="s-ts" value={draft.titulo_seo} onChange={(e) => set("titulo_seo", e.target.value)} /></Field>
                      <Field label={`Descrição no Google (${draft.descricao_seo.length}/155)`} htmlFor="s-ds"><Textarea id="s-ds" rows={2} value={draft.descricao_seo} onChange={(e) => set("descricao_seo", e.target.value)} /></Field>
                    </>
                  )}
                  {tab === "dados" && (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Text label="Nome da empresa" v={draft.empresa} on={(v) => set("empresa", v)} />
                      <Text label="Categoria" v={draft.categoria} on={(v) => set("categoria", v)} />
                      <Text label="Telefone (só dígitos, com DDD)" v={draft.telefone} on={(v) => set("telefone", v.replace(/\D/g, ""))} />
                      <Text label="WhatsApp (só dígitos, com DDD)" v={draft.whatsapp} on={(v) => set("whatsapp", v.replace(/\D/g, ""))} />
                      <Text label="E-mail" v={draft.email} on={(v) => set("email", v)} />
                      <Text label="Horário de atendimento" v={draft.horario} on={(v) => set("horario", v)} />
                      <Text label="Endereço" v={draft.endereco} on={(v) => set("endereco", v)} />
                      <Text label="Bairro" v={draft.bairro} on={(v) => set("bairro", v)} />
                      <Text label="CEP" v={draft.cep} on={(v) => set("cep", v.replace(/\D/g, ""))} />
                      <Text label="Link de agendamento online" v={draft.link_agendamento} on={(v) => set("link_agendamento", v)} />
                      <Text label="Instagram (URL)" v={draft.instagram} on={(v) => set("instagram", v)} />
                      <Text label="Facebook (URL)" v={draft.facebook} on={(v) => set("facebook", v)} />
                      <Color label="Cor principal" v={draft.cor} on={(v) => set("cor", v)} />
                      <Color label="Cor de destaque" v={draft.cor_destaque} on={(v) => set("cor_destaque", v)} />
                      <label className="flex items-center gap-2 text-sm sm:col-span-2">
                        <Checkbox label="Atendimento com agendamento" checked={!!draft.agendamento} onChange={(v) => set("agendamento", v)} /> Botão principal como “Agendar pelo WhatsApp”
                      </label>
                    </div>
                  )}
                  {tab === "servicos" && (
                    <>
                      <ItemList title="Serviços" items={draft.servicos} onChange={(i, f, v) => setItem("servicos", i, f, v)}
                        onAdd={() => set("servicos", [...draft.servicos, { titulo: "", descricao: "" }])}
                        onRemove={(i) => set("servicos", draft.servicos.filter((_, j) => j !== i))} />
                      <ItemList title="Diferenciais" items={draft.diferenciais} onChange={(i, f, v) => setItem("diferenciais", i, f, v)}
                        onAdd={() => set("diferenciais", [...draft.diferenciais, { titulo: "", descricao: "" }])}
                        onRemove={(i) => set("diferenciais", draft.diferenciais.filter((_, j) => j !== i))} />
                    </>
                  )}
                  {tab === "faq" && (
                    <div className="space-y-3">
                      {draft.faq.map((f, i) => (
                        <div key={i} className="space-y-2 rounded-md border border-border p-3">
                          <div className="flex gap-2">
                            <Input aria-label={`Pergunta ${i + 1}`} value={f.pergunta} onChange={(e) => set("faq", draft.faq.map((x, j) => (j === i ? { ...x, pergunta: e.target.value } : x)))} />
                            <Button variant="ghost" size="sm" aria-label="Remover pergunta" onClick={() => set("faq", draft.faq.filter((_, j) => j !== i))}><Trash2 className="size-3.5" /></Button>
                          </div>
                          <Textarea aria-label={`Resposta ${i + 1}`} rows={2} value={f.resposta} onChange={(e) => set("faq", draft.faq.map((x, j) => (j === i ? { ...x, resposta: e.target.value } : x)))} />
                        </div>
                      ))}
                      <Button variant="outline" size="sm" onClick={() => set("faq", [...draft.faq, { pergunta: "", resposta: "" }])}><Plus className="size-3.5" /> Pergunta</Button>
                    </div>
                  )}
                </fieldset>
              </Card>

              {draft.problemas_resolvidos.length > 0 && (
                <Card>
                  <CardHeader title="Problemas do site atual tratados" description="Do diagnóstico confirmado" />
                  <ul className="space-y-1.5 p-4 text-sm">
                    {draft.problemas_resolvidos.map((p) => (
                      <li key={p} className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-good" aria-hidden /> {p}</li>
                    ))}
                  </ul>
                </Card>
              )}
            </div>

            <div className="flex min-h-0 flex-col bg-surface-2">
              <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2 text-xs text-muted">
                <span>Prévia {dirty && <Badge className="ml-1 bg-weak-soft text-weak">alterações não salvas</Badge>}</span>
                <div className="flex items-center gap-1">
                  <Button size="sm" variant={device === "desktop" ? "secondary" : "ghost"} onClick={() => setDevice("desktop")} aria-pressed={device === "desktop"}><Monitor className="size-3.5" /> Computador</Button>
                  <Button size="sm" variant={device === "mobile" ? "secondary" : "ghost"} onClick={() => setDevice("mobile")} aria-pressed={device === "mobile"}><Smartphone className="size-3.5" /> Celular</Button>
                  <a href={project.preview_url} target="_blank" rel="noreferrer" className={buttonClass({ variant: "ghost", size: "sm" })}><ExternalLink className="size-3.5" /> Abrir</a>
                </div>
              </div>
              <div className="flex min-h-0 flex-1 justify-center overflow-auto p-4">
                <iframe
                  key={`${project.id}-${previewKey}-${project.atualizado_em}`}
                  title="Prévia do site novo"
                  src={`/s/${project.token}/`}
                  className={cn("h-full rounded-lg border border-border bg-white shadow-sm", device === "mobile" ? "w-[390px] max-w-full" : "w-full")}
                />
              </div>
            </div>
          </div>
        )
      )}
    </div>
  );
}

function Comparison({ original, novo, auditing, onAudit, loading, dirty }: { original: SiteAuditSummary | null; novo: SiteAuditSummary | null | undefined; auditing: boolean; onAudit: () => void; loading: boolean; dirty: boolean }) {
  const done = novo && novo.status === "concluida";
  const gain = done && original?.nota_geral != null && novo.nota_geral != null ? novo.nota_geral - original.nota_geral : null;
  return (
    <Card>
      <CardHeader
        title="Antes × depois"
        description="O site novo passa pelo mesmo motor de auditoria do site atual"
        actions={
          <Button size="sm" onClick={onAudit} loading={loading || auditing} disabled={dirty} title={dirty ? "Salve antes de auditar" : undefined}>
            <Radar className="size-3.5" aria-hidden /> {done ? "Auditar de novo" : "Auditar site novo"}
          </Button>
        }
      />
      <div className="grid grid-cols-2 gap-2 p-4">
        <Score label="Site atual" audit={original} empty="Sem site ou sem auditoria" />
        <Score label="Site novo" audit={novo ?? null} empty={auditing ? "Auditando…" : "Ainda não auditado"} />
      </div>
      {gain !== null && (
        <p className={cn("px-4 pb-3 text-center text-sm font-semibold", gain >= 30 ? "text-good" : "text-fg")}>
          {gain >= 0 ? `+${gain}` : gain} pontos {gain >= 30 && "· meta do PDF atingida (+30)"}
        </p>
      )}
      {done && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 border-t border-border px-4 py-3 text-xs sm:grid-cols-4">
          {DIMENSION_ORDER.map((d) => {
            const a = original?.notas_dimensao?.[d];
            const b = novo.notas_dimensao?.[d];
            return (
              <div key={d} className="flex justify-between gap-1">
                <span className="text-muted">{DIMENSIONS[d].nome}</span>
                <span className="tabular-nums">{a ?? "—"} → <strong>{b ?? "—"}</strong></span>
              </div>
            );
          })}
        </div>
      )}
      {done && (
        <p className="border-t border-border px-4 py-2 text-xs text-muted">
          Segurança (HTTPS e cabeçalhos) é definida na hospedagem e não é medida na prévia. <Link className="text-brand hover:underline" to={`/auditorias/${novo.id}`}>Ver auditoria completa</Link>
        </p>
      )}
    </Card>
  );
}

function Score({ label, audit, empty }: { label: string; audit: SiteAuditSummary | null; empty: string }) {
  return (
    <div className="flex flex-col items-center gap-1 text-center">
      <span className="text-xs font-medium text-muted">{label}</span>
      {audit && audit.status === "concluida" ? <ScoreGauge score={audit.nota_geral} size={96} label={label} /> : <p className={cn("py-8 text-xs", bandText.nao_medido)}>{empty}</p>}
    </div>
  );
}

function Text({ label, v, on }: { label: string; v: string; on: (v: string) => void }) {
  return <Field label={label}><Input value={v ?? ""} onChange={(e) => on(e.target.value)} aria-label={label} /></Field>;
}

function Color({ label, v, on }: { label: string; v: string; on: (v: string) => void }) {
  return (
    <Field label={label}>
      <div className="flex gap-2">
        <input type="color" value={v} onChange={(e) => on(e.target.value)} className="h-9 w-12 rounded border border-border" aria-label={label} />
        <Input value={v} onChange={(e) => on(e.target.value)} aria-label={`${label} (hex)`} />
      </div>
    </Field>
  );
}

function ItemList({ title, items, onChange, onAdd, onRemove }: { title: string; items: { titulo: string; descricao: string }[]; onChange: (i: number, f: "titulo" | "descricao", v: string) => void; onAdd: () => void; onRemove: (i: number) => void }): ReactNode {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h3>
      {items.map((it, i) => (
        <div key={i} className="space-y-2 rounded-md border border-border p-3">
          <div className="flex gap-2">
            <Input aria-label={`${title} ${i + 1}: título`} value={it.titulo} onChange={(e) => onChange(i, "titulo", e.target.value)} />
            <Button variant="ghost" size="sm" aria-label={`Remover ${it.titulo || "item"}`} onClick={() => onRemove(i)}><Trash2 className="size-3.5" /></Button>
          </div>
          <Textarea aria-label={`${title} ${i + 1}: descrição`} rows={2} value={it.descricao} onChange={(e) => onChange(i, "descricao", e.target.value)} />
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={onAdd}><Plus className="size-3.5" /> {title === "Serviços" ? "Serviço" : "Diferencial"}</Button>
    </div>
  );
}
