import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type { Faixa } from "@/api/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Faixas de nota do brief de design: sempre cor + rótulo. */
export function band(score: number | null | undefined): { faixa: Faixa; rotulo: string } {
  if (score === null || score === undefined) return { faixa: "nao_medido", rotulo: "Não medido" };
  if (score < 50) return { faixa: "ruim", rotulo: "Crítico" };
  if (score < 70) return { faixa: "fraco", rotulo: "Precisa melhorar" };
  if (score < 85) return { faixa: "regular", rotulo: "Regular" };
  return { faixa: "bom", rotulo: "Bom" };
}

export const bandText: Record<Faixa, string> = {
  ruim: "text-bad",
  fraco: "text-weak",
  regular: "text-ok",
  bom: "text-good",
  nao_medido: "text-muted",
};

export const bandBg: Record<Faixa, string> = {
  ruim: "bg-bad-soft text-bad",
  fraco: "bg-weak-soft text-weak",
  regular: "bg-ok-soft text-ok",
  bom: "bg-good-soft text-good",
  nao_medido: "bg-surface-2 text-muted",
};

export const bandStroke: Record<Faixa, string> = {
  ruim: "var(--bad)",
  fraco: "var(--weak)",
  regular: "#caa200",
  bom: "var(--good)",
  nao_medido: "var(--border)",
};

const dateFmt = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" });
const dateTimeFmt = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

export function fmtDate(value?: string | null) {
  return value ? dateFmt.format(new Date(value)) : "—";
}

export function fmtDateTime(value?: string | null) {
  return value ? dateTimeFmt.format(new Date(value)) : "—";
}

export function fmtSeconds(ms?: number | null) {
  return ms === null || ms === undefined ? "—" : `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}

export function fmtBytes(bytes?: number | null) {
  if (!bytes) return "—";
  if (bytes < 1_000) return `${bytes} B`;
  if (bytes < 1_000_000) return `${Math.round(bytes / 1000)} KB`;
  return `${(bytes / 1_000_000).toFixed(1).replace(".", ",")} MB`;
}

export function fmtMoney(value: number) {
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function fmtPhone(digits?: string) {
  if (!digits) return "";
  const d = digits.replace(/\D/g, "");
  if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return digits;
}
