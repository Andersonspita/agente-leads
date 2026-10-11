import {
  Accessibility,
  FileText,
  Gauge,
  MousePointerClick,
  Scale,
  Search,
  ShieldCheck,
  Smartphone,
  type LucideIcon,
} from "lucide-react";

import type { Dimensao, LeadStatus, Severidade } from "@/api/types";

/** Um ícone por dimensão auditada (brief 4.2). */
export const DIMENSIONS: Record<Dimensao, { nome: string; icon: LucideIcon }> = {
  desempenho: { nome: "Desempenho", icon: Gauge },
  mobile: { nome: "Mobile", icon: Smartphone },
  seo: { nome: "SEO", icon: Search },
  acessibilidade: { nome: "Acessibilidade", icon: Accessibility },
  seguranca: { nome: "Segurança", icon: ShieldCheck },
  conteudo: { nome: "Conteúdo", icon: FileText },
  conversao: { nome: "Conversão", icon: MousePointerClick },
  conformidade: { nome: "LGPD", icon: Scale },
};

export const DIMENSION_ORDER = Object.keys(DIMENSIONS) as Dimensao[];

export const SEVERITIES: Record<Severidade, { nome: string; className: string; ordem: number }> = {
  critica: { nome: "Crítica", className: "bg-bad-soft text-bad", ordem: 0 },
  alta: { nome: "Alta", className: "bg-weak-soft text-weak", ordem: 1 },
  media: { nome: "Média", className: "bg-ok-soft text-ok", ordem: 2 },
  baixa: { nome: "Baixa", className: "bg-surface-2 text-muted", ordem: 3 },
};

export const LEAD_STATUS: Record<LeadStatus, { nome: string; className: string }> = {
  encontrado: { nome: "Encontrado", className: "bg-surface-2 text-fg" },
  sem_site: { nome: "Sem site", className: "bg-weak-soft text-weak" },
  auditado: { nome: "Auditado", className: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300" },
  relatorio_enviado: {
    nome: "Relatório enviado",
    className: "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-300",
  },
  em_negociacao: { nome: "Em negociação", className: "bg-ok-soft text-ok" },
  fechado: { nome: "Fechado", className: "bg-good-soft text-good" },
  perdido: { nome: "Perdido", className: "bg-bad-soft text-bad" },
  entregue: { nome: "Entregue", className: "bg-good-soft text-good" },
};

export const SOURCES: Record<string, string> = {
  places: "Google",
  osm: "OSM",
  cnpj: "CNPJ",
  web: "Web",
  manual: "Manual",
};

export const SITE_ORIGIN: Record<string, string> = {
  places: "Google Places",
  osm: "OpenStreetMap",
  email_cnpj: "domínio do e-mail no CNPJ",
  web: "busca web",
  manual: "cadastro manual",
};

export const STEP_STATUS: Record<string, string> = {
  pendente: "Pendente",
  executando: "Executando",
  ok: "Concluída",
  falhou: "Falhou",
  nao_medido: "Não medida",
};

export const UFS = [
  "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
  "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
];
