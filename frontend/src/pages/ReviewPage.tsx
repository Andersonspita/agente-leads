import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, FileBarChart, Pencil, Plus, Trash2, Undo2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api } from "@/api/client";
import type { AuditDetail, Dimensao, Finding, Severidade } from "@/api/types";
import { PageHeader } from "@/components/Layout";
import { FindingItem, OriginBadge, ReviewBadge, ScreenshotAnnotated, SeverityBadge } from "@/components/domain";
import { useToast } from "@/components/toast";
import { useUnsavedChanges } from "@/lib/useUnsavedChanges";
import { Button, Card, Dialog, ErrorState, Field, Input, Loading, Select, Textarea, buttonClass } from "@/components/ui";
import { DIMENSIONS, SEVERITIES } from "@/lib/labels";
import { useAudit } from "./AuditPage";

const REVIEW_ORDER = { pendente: 0, confirmado: 1, descartado: 2 } as const;
type Draft = Pick<Finding, "titulo" | "severidade" | "impacto_negocio" | "melhoria_proposta" | "descricao">;

export default function ReviewPage() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const { data: audit, isLoading, error, refetch } = useAudit(id);
  const client = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [adding, setAdding] = useState(false);
  useUnsavedChanges(editing); // achado aberto em edição

  const findings = useMemo(
    () =>
      [...(audit?.findings ?? [])].sort(
        (a, b) => REVIEW_ORDER[a.status_revisao] - REVIEW_ORDER[b.status_revisao] || SEVERITIES[a.severidade].ordem - SEVERITIES[b.severidade].ordem || a.id - b.id,
      ),
    [audit],
  );
  const currentId = Number(params.get("achado")) || findings[0]?.id;
  const index = Math.max(0, findings.findIndex((f) => f.id === currentId));
  const current = findings[index];
  const select = useCallback((f?: Finding) => f && setParams({ achado: String(f.id) }, { replace: true }), [setParams]);

  const update = useMutation({
    mutationFn: ({ fid, body }: { fid: number; body: Partial<Finding> }) => api.patch<Finding>(`findings/${fid}`, body),
    onSuccess: (f) => {
      client.setQueryData<AuditDetail>(["audit", id], (old) => old && { ...old, findings: old.findings.map((x) => (x.id === f.id ? f : x)) });
      client.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e) => toast(e.message, "error"),
  });

  const review = useCallback(
    (status: Finding["status_revisao"]) => {
      if (!current) return;
      update.mutate({ fid: current.id, body: { status_revisao: status } });
      const next = findings.slice(index + 1).find((f) => f.status_revisao === "pendente") ?? findings[index + 1];
      if (next) select(next);
    },
    [current, findings, index, select, update],
  );

  const startEdit = useCallback(() => {
    if (!current) return;
    setDraft({ titulo: current.titulo, severidade: current.severidade, impacto_negocio: current.impacto_negocio, melhoria_proposta: current.melhoria_proposta, descricao: current.descricao });
    setEditing(true);
  }, [current]);

  useEffect(() => {
    setEditing(false);
  }, [currentId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (editing || adding || e.ctrlKey || e.metaKey || e.altKey || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)) return;
      const key = e.key.toLowerCase();
      if (key === "c") review("confirmado");
      else if (key === "d") review("descartado");
      else if (key === "e") {
        e.preventDefault();
        startEdit();
      } else if (key === "j") select(findings[Math.min(index + 1, findings.length - 1)]);
      else if (key === "k") select(findings[Math.max(index - 1, 0)]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing, adding, review, startEdit, select, findings, index]);

  if (isLoading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  const a = audit!;
  const pending = findings.filter((f) => f.status_revisao === "pendente").length;
  const artifact = current?.evidencia.artefato ? a.artifacts.find((x) => x.tipo === current.evidencia.artefato) : undefined;

  return (
    <div className="flex h-screen flex-col">
      <PageHeader
        back={<Link to={`/auditorias/${a.id}`}>← Auditoria de {a.dominio}</Link>}
        title="Revisão de achados"
        description={
          <span>
            {pending ? `${pending} pendente(s)` : "Tudo revisado"} · atalhos <kbd>C</kbd> confirma · <kbd>E</kbd> edita · <kbd>D</kbd> descarta · <kbd>J</kbd>/<kbd>K</kbd> navega
          </span>
        }
        actions={
          <>
            <Button variant="outline" onClick={() => setAdding(true)}>
              <Plus className="size-4" aria-hidden /> Achado manual
            </Button>
            <Link to={`/auditorias/${a.id}/relatorio`} className={buttonClass()} aria-disabled={pending > 0} onClick={(e) => pending > 0 && e.preventDefault()}
              title={pending ? "Revise os pendentes antes de gerar o relatório" : undefined}>
              <FileBarChart className="size-4" aria-hidden /> Preparar relatório
            </Link>
          </>
        }
      />
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(320px,0.9fr)_1.1fr]">
        <div className="min-h-0 space-y-2 overflow-y-auto border-r border-border p-4" role="listbox" aria-label="Achados">
          {findings.map((f) => (
            <div key={f.id} role="option" aria-selected={f.id === current?.id}>
              <FindingItem finding={f} selected={f.id === current?.id} onSelect={() => select(f)} />
            </div>
          ))}
        </div>

        <div className="min-h-0 overflow-y-auto p-4">
          {!current ? (
            <p className="text-sm text-muted">Nenhum achado nesta auditoria.</p>
          ) : (
            <Card className="space-y-4 p-5">
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={current.severidade} />
                <OriginBadge origin={current.origem} />
                <ReviewBadge status={current.status_revisao} />
                <span className="text-xs text-muted">
                  {DIMENSIONS[current.dimensao].nome}
                  {current.rule_id && ` · ${current.rule_id}`}
                  {current.editado_por_nome && ` · editado por ${current.editado_por_nome}`}
                </span>
              </div>

              {editing && draft ? (
                <div className="space-y-3">
                  <Field label="Título (como o cliente vai ler)" htmlFor="d-t">
                    <Input id="d-t" value={draft.titulo} onChange={(e) => setDraft({ ...draft, titulo: e.target.value })} autoFocus />
                  </Field>
                  <Field label="Severidade" htmlFor="d-s">
                    <Select id="d-s" value={draft.severidade} onChange={(e) => setDraft({ ...draft, severidade: e.target.value as Severidade })}>
                      {Object.entries(SEVERITIES).map(([k, v]) => (
                        <option key={k} value={k}>
                          {v.nome}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Impacto no negócio" htmlFor="d-i">
                    <Textarea id="d-i" value={draft.impacto_negocio} onChange={(e) => setDraft({ ...draft, impacto_negocio: e.target.value })} />
                  </Field>
                  <Field label="Melhoria no site novo" htmlFor="d-m">
                    <Textarea id="d-m" value={draft.melhoria_proposta} onChange={(e) => setDraft({ ...draft, melhoria_proposta: e.target.value })} />
                  </Field>
                  <Field label="Descrição técnica (interna)" htmlFor="d-d">
                    <Textarea id="d-d" value={draft.descricao} onChange={(e) => setDraft({ ...draft, descricao: e.target.value })} />
                  </Field>
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" onClick={() => setEditing(false)}>
                      Cancelar
                    </Button>
                    <Button
                      loading={update.isPending}
                      onClick={() => update.mutate({ fid: current.id, body: { ...draft, status_revisao: "confirmado" } }, { onSuccess: () => setEditing(false) })}
                    >
                      Salvar e confirmar
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  <h2 className="text-lg font-semibold leading-snug">{current.titulo}</h2>
                  <Section title="Impacto no negócio">{current.impacto_negocio}</Section>
                  <Section title="Melhoria no site novo">{current.melhoria_proposta}</Section>
                  {current.descricao && current.descricao !== current.titulo && <Section title="Descrição">{current.descricao}</Section>}
                  <div className="flex flex-wrap gap-2 border-t border-border pt-4">
                    <Button onClick={() => review("confirmado")} disabled={current.status_revisao === "confirmado"}>
                      <Check className="size-4" aria-hidden /> Confirmar <kbd className="ml-1 border-white/30 bg-white/10 text-inherit">C</kbd>
                    </Button>
                    <Button variant="outline" onClick={startEdit}>
                      <Pencil className="size-4" aria-hidden /> Editar <kbd className="ml-1">E</kbd>
                    </Button>
                    {current.status_revisao === "descartado" ? (
                      <Button variant="outline" onClick={() => review("pendente")}>
                        <Undo2 className="size-4" aria-hidden /> Restaurar
                      </Button>
                    ) : (
                      <Button variant="outline" className="text-bad" onClick={() => review("descartado")}>
                        <Trash2 className="size-4" aria-hidden /> Descartar <kbd className="ml-1">D</kbd>
                      </Button>
                    )}
                  </div>
                </>
              )}

              <div className="space-y-2 border-t border-border pt-4">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Evidência</h3>
                <Evidence finding={current} />
                {artifact && <ScreenshotAnnotated artifact={artifact} boxes={current.evidencia.caixas ?? []} alt={current.evidencia.legenda ?? "Captura do site"} maxHeight={560} />}
              </div>
            </Card>
          )}
        </div>
      </div>
      <AddFindingDialog open={adding} onClose={() => setAdding(false)} auditId={a.id} />
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h3>
      <p className="mt-1 whitespace-pre-wrap text-sm">{children}</p>
    </div>
  );
}

function Evidence({ finding }: { finding: Finding }) {
  const ev = finding.evidencia;
  if (!ev || !Object.keys(ev).length) return <p className="text-sm text-muted">Verificação automática no conteúdo das páginas rastreadas.</p>;
  if (ev.tipo === "metrica")
    return (
      <p className="text-sm">
        Medido: <strong>{String(ev.valor)}{ev.unidade ? ` ${ev.unidade}` : ""}</strong>
        {ev.referencia !== null && ev.referencia !== undefined && <span className="text-muted"> · recomendado: {String(ev.referencia)}{ev.unidade ? ` ${ev.unidade}` : ""}</span>}
        {typeof ev.fonte === "string" && <span className="text-muted"> · fonte: {ev.fonte}</span>}
      </p>
    );
  if (ev.tipo === "html") return <pre className="overflow-x-auto rounded-md bg-surface-2 p-3 text-xs">{ev.trecho}</pre>;
  if (ev.tipo === "captura") return ev.legenda ? <p className="text-sm text-muted">{ev.legenda}</p> : null;
  const { tipo: _tipo, ...rest } = ev;
  return <pre className="overflow-x-auto rounded-md bg-surface-2 p-3 text-xs">{JSON.stringify(rest, null, 2)}</pre>;
}

function AddFindingDialog({ open, onClose, auditId }: { open: boolean; onClose: () => void; auditId: number }) {
  const client = useQueryClient();
  const [form, setForm] = useState({ titulo: "", dimensao: "conteudo" as Dimensao, severidade: "media" as Severidade, impacto_negocio: "", melhoria_proposta: "" });
  const create = useMutation({
    mutationFn: () => api.post("findings", { ...form, audit: auditId }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["audit", String(auditId)] });
      setForm({ ...form, titulo: "", impacto_negocio: "", melhoria_proposta: "" });
      onClose();
    },
  });
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Adicionar achado manual"
      footer={
        <Button disabled={!form.titulo} loading={create.isPending} onClick={() => create.mutate()}>
          Adicionar
        </Button>
      }
    >
      <div className="space-y-3">
        <Field label="Título" htmlFor="m-t">
          <Input id="m-t" value={form.titulo} onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Dimensão" htmlFor="m-d">
            <Select id="m-d" value={form.dimensao} onChange={(e) => setForm({ ...form, dimensao: e.target.value as Dimensao })}>
              {Object.entries(DIMENSIONS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.nome}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Severidade" htmlFor="m-s">
            <Select id="m-s" value={form.severidade} onChange={(e) => setForm({ ...form, severidade: e.target.value as Severidade })}>
              {Object.entries(SEVERITIES).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.nome}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Impacto no negócio" htmlFor="m-i">
          <Textarea id="m-i" value={form.impacto_negocio} onChange={(e) => setForm({ ...form, impacto_negocio: e.target.value })} />
        </Field>
        <Field label="Melhoria no site novo" htmlFor="m-m">
          <Textarea id="m-m" value={form.melhoria_proposta} onChange={(e) => setForm({ ...form, melhoria_proposta: e.target.value })} />
        </Field>
        {create.error && <p className="text-sm text-bad">{create.error.message}</p>}
      </div>
    </Dialog>
  );
}
