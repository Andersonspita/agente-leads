export type Faixa = "ruim" | "fraco" | "regular" | "bom" | "nao_medido";
export type Severidade = "critica" | "alta" | "media" | "baixa";
export type Dimensao =
  | "desempenho"
  | "mobile"
  | "seo"
  | "acessibilidade"
  | "seguranca"
  | "conteudo"
  | "conversao"
  | "conformidade";
export type LeadStatus =
  | "encontrado"
  | "auditado"
  | "sem_site"
  | "relatorio_enviado"
  | "em_negociacao"
  | "fechado"
  | "perdido"
  | "entregue";

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Me {
  authenticated: boolean;
  verified?: boolean;
  require_2fa?: boolean;
  has_2fa?: boolean;
  setup_required?: boolean;
  otp_required?: boolean;
  user?: { id: number; email: string; nome: string; role: "admin" | "analista"; is_admin: boolean };
}

export interface Municipality {
  codigo_ibge: string;
  nome: string;
  uf: string;
}

export interface ChecklistItem {
  id: number;
  item: string;
  obrigatorio: boolean;
  tipo: "pagina" | "secao" | "integracao" | "meta";
}

export interface Category {
  id: number;
  nome: string;
  slug: string;
  termos_busca: string[];
  cnaes: string[];
  osm_tags: string[];
  ativo: boolean;
  pesos: Record<Dimensao, number>;
  checklist: ChecklistItem[];
}

export interface SiteSummary {
  id: number;
  url: string;
  dominio: string;
  https: boolean | null;
  online: boolean | null;
  auditavel: boolean;
}

export interface CompanyListItem {
  id: number;
  nome: string;
  bairro: string;
  telefone: string;
  whatsapp: string;
  nota_google: string | null;
  n_avaliacoes: number | null;
  status_lead: LeadStatus;
  status_lead_nome: string;
  municipio: string;
  categoria: string;
  site: SiteSummary | null;
  situacao_site: "sem_site" | "fora_do_ar" | "tem_site";
  nota_site: number | null;
  cnpj: string;
}

export interface Website extends SiteSummary {
  principal: boolean;
  status_http: number | null;
  url_final: string;
  ultimo_check: string | null;
  tecnologias: { nome: string; categoria: string; versao: string | null; desatualizado: boolean | null }[];
  origem: "" | "places" | "osm" | "email_cnpj" | "web" | "manual";
  ultima_auditoria: { id: number; status: string; nota_geral: number | null; concluido_em: string | null; faixa: Faixa; rotulo: string } | null;
}

export interface LeadNote {
  id: number;
  texto: string;
  autor_nome: string;
  criado_em: string;
}

export interface CompanyDetail extends CompanyListItem {
  endereco: string;
  google_place_id: string;
  redes_sociais: Record<string, string>;
  category: number | null;
  municipality: string | null;
  responsavel: number | null;
  responsavel_nome: string;
  websites: Website[];
  notes: LeadNote[];
  transicoes: { valor: LeadStatus; nome: string }[];
  criado_em: string;
  atualizado_em: string;
}

export interface Search {
  id: number;
  category: number | null;
  categoria: string;
  municipality: string;
  municipio: string;
  termo_livre: string;
  bairro: string;
  status: "na_fila" | "executando" | "concluida" | "falhou";
  total_encontrado: number;
  fontes: {
    places?: number;
    osm?: number;
    cnpj?: number;
    web?: number;
    sites_por_email?: number;
    erros?: string[];
    avisos?: string[];
    cache_de?: number;
  };
  erro: string;
  criado_por_nome: string;
  criado_em: string;
  concluido_em: string | null;
  descricao: string;
}

export interface SearchResult {
  id: number;
  fonte: "places" | "osm" | "cnpj" | "web" | "manual";
  posicao: number;
  company: CompanyListItem;
}

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Evidence {
  tipo?: "captura" | "metrica" | "html" | "tecnico";
  artefato?: string;
  caixas?: Box[];
  legenda?: string | null;
  valor?: number | string;
  referencia?: number | string | null;
  unidade?: string;
  trecho?: string;
  [key: string]: unknown;
}

export interface Finding {
  id: number;
  audit: number;
  dimensao: Dimensao;
  dimensao_nome: string;
  rule_id: string;
  origem: "regra" | "ia" | "manual";
  severidade: Severidade;
  titulo: string;
  descricao: string;
  impacto_negocio: string;
  melhoria_proposta: string;
  evidencia: Evidence;
  status_revisao: "pendente" | "confirmado" | "descartado";
  editado_por_nome: string;
  editado_em: string | null;
}

export interface Step {
  ordem: number;
  etapa: string;
  nome: string;
  status: "pendente" | "executando" | "ok" | "falhou" | "nao_medido";
  duracao_ms: number | null;
  erro: string;
  resultado: Record<string, unknown>;
}

export interface Artifact {
  id: number;
  tipo: string;
  url: string;
  tamanho: number;
  meta: { largura?: number; altura?: number };
}

export interface AuditListItem {
  id: number;
  empresa: string;
  company_id: number;
  dominio: string;
  status: "na_fila" | "executando" | "concluida" | "falhou";
  nota_geral: number | null;
  faixa: { faixa: Faixa; rotulo: string };
  criado_em: string;
  iniciado_em: string | null;
  concluido_em: string | null;
  progresso: { feitas: number; total: number; atual: string | null };
  pendentes: number;
  erro: string;
}

export interface DimensionScore {
  chave: Dimensao;
  nome: string;
  nota: number | null;
  peso: number | null;
  faixa: Faixa;
  rotulo: string;
  achados: number;
}

export interface AuditDetail extends AuditListItem {
  notas_dimensao: Record<Dimensao, number | null>;
  pesos_usados: Record<Dimensao, number>;
  metricas: {
    lcp_mobile_ms?: number | null;
    cls_mobile?: number | null;
    peso_bytes?: number | null;
    requisicoes?: number | null;
    lighthouse?: Record<string, Record<string, number>>;
    https?: boolean | null;
    cms?: string | null;
    paginas_rastreadas?: number;
    violacoes_acessibilidade?: Record<string, number> | null;
    manual?: boolean;
  };
  versao_regras: string;
  versao_prompt: string;
  steps: Step[];
  findings: Finding[];
  artifacts: Artifact[];
  dimensoes: DimensionScore[];
  website: { id: number; url: string; url_final: string; dominio: string; https: boolean | null; company_id: number; tecnologias: Website["tecnologias"] };
  reports: { id: number; criado_em: string; revogado: boolean; enviado_em: string | null }[];
}

export interface CompareRow {
  nome: string;
  nota: number | null;
  destaque: boolean;
  faixa: Faixa;
  rotulo: string;
  company_id?: number;
  dominio?: string;
  audit_id?: number;
}

export interface Comparison {
  linhas: CompareRow[];
  posicao: number | null;
  total: number;
  media_local: number | null;
  referencia: number;
  maior_nota: number | null;
}

export interface Report {
  id: number;
  audit: number;
  empresa: string;
  company_id: number;
  nota_geral: number | null;
  token: string;
  url_publica: string;
  expira_em: string;
  pdf_url: string | null;
  pdf_status: string;
  texto_abertura: string;
  resumo: string;
  concorrentes_ids: number[];
  exibir_nomes_concorrentes: boolean;
  achados_ids: number[];
  criado_em: string;
  enviado_em: string | null;
  revogado: boolean;
  disponivel: boolean;
  visualizacoes: number;
  ultima_visualizacao: string | null;
}

export interface BriefingContent {
  empresa: { nome: string; cidade: string; categoria: string; site_atual: string };
  nota_atual: number | null;
  paginas: string[];
  secoes: string[];
  integracoes: string[];
  requisitos: { achado_id: number; dimensao: string; severidade: Severidade; problema: string; requisito: string }[];
  metas: { meta: string; alvo: string }[];
  conteudo_necessario: string[];
}

export interface Briefing {
  id: number;
  company: number;
  empresa: string;
  audit: number | null;
  conteudo: BriefingContent;
  versao: number;
  criado_em: string;
}

export interface Dashboard {
  funil: { status: LeadStatus; nome: string; total: number }[];
  auditorias_em_andamento: { id: number; empresa: string; status: string; criado_em: string }[];
  semana: { auditorias: number; relatorios_enviados: number; relatorios_abertos: number; leads_novos: number };
  revisao_pendente: number;
  metas: { chave: string; nome: string; valor: string; meta: string; ok: boolean | null; amostra: string }[];
  custos: {
    gasto_mes: number;
    teto_mes: number;
    percentual: number;
    alerta: boolean;
    por_provedor: { provedor: string; total: number; chamadas: number }[];
  };
  atividade: { acao: string; entidade: string; entidade_id: string; usuario: string; quando: string }[];
}

export interface Capabilities {
  google_places: boolean;
  osm: boolean;
  email_cnpj: boolean;
  busca_web: boolean;
  ia: boolean;
  modelo_ia: string;
  navegador: boolean;
  axe: boolean;
  lighthouse: boolean;
  filas_celery: boolean;
  base_cnpj: boolean;
}

export interface Brand {
  nome_empresa: string;
  cor_primaria: string;
  logo: string | null;
  whatsapp: string;
  link_agenda: string;
  email_contato: string;
  site: string;
  exibir_nomes_concorrentes: boolean;
}

export interface UserRow {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  role: "admin" | "analista";
  is_active: boolean;
  has_2fa: boolean;
  last_login: string | null;
}

export interface RuleRow {
  id: number;
  codigo: string;
  dimensao: Dimensao;
  dimensao_nome: string;
  descricao: string;
  severidade_padrao: Severidade;
  ativo: boolean;
}

export interface PromptVersion {
  id: number;
  nome: string;
  texto: string;
  modelo: string;
  ativo: boolean;
  criado_em: string;
}

export interface SiteItem {
  titulo: string;
  descricao: string;
}

export interface SiteContent {
  empresa: string;
  categoria: string;
  cidade: string;
  uf: string;
  telefone: string;
  whatsapp: string;
  email: string;
  endereco: string;
  bairro: string;
  cep: string;
  horario: string;
  instagram: string;
  facebook: string;
  link_agendamento: string;
  agendamento: boolean;
  cor: string;
  cor_destaque: string;
  titulo_seo: string;
  descricao_seo: string;
  headline: string;
  subheadline: string;
  sobre: string;
  servicos: SiteItem[];
  diferenciais: SiteItem[];
  faq: { pergunta: string; resposta: string }[];
  problemas_resolvidos: string[];
  a_confirmar: string[];
  [key: string]: unknown;
}

export interface SiteAuditSummary {
  id: number;
  status: string;
  nota_geral: number | null;
  notas_dimensao: Partial<Record<Dimensao, number | null>>;
  concluido_em: string | null;
  achados: number;
  faixa: Faixa;
  rotulo: string;
}

export interface SiteProject {
  id: number;
  company: number;
  empresa: string;
  token: string;
  conteudo: SiteContent;
  gerado_por_ia: boolean;
  modelo_ia: string;
  ia_status: "" | "pendente" | "ok" | "falhou";
  preview_url: string;
  auditoria_original: SiteAuditSummary | null;
  auditoria_site_novo: SiteAuditSummary | null;
  criado_em: string;
  atualizado_em: string;
}
