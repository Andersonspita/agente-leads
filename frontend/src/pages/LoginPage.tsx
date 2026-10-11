import { ShieldCheck } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { api } from "@/api/client";
import type { Me } from "@/api/types";
import { useAuth } from "@/auth";
import { Button, Field, Input } from "@/components/ui";

type Stage = "credentials" | "otp" | "setup";

export default function LoginPage() {
  const { me, setMe } = useAuth();
  const location = useLocation();
  const [stage, setStage] = useState<Stage>("credentials");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [qr, setQr] = useState<{ svg: string; uri: string } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Sessão aberta mas sem 2FA configurado: vai direto para a configuração.
  useEffect(() => {
    if (me?.authenticated && !me.verified && me.setup_required) setStage("setup");
  }, [me]);

  useEffect(() => {
    if (stage !== "setup" || qr) return;
    api
      .post<{ qr_svg: string; otpauth_uri: string }>("auth/2fa/setup")
      .then((r) => setQr({ svg: r.qr_svg, uri: r.otpauth_uri }))
      .catch((e) => setError(e.message));
  }, [stage, qr]);

  if (me?.authenticated && me.verified) {
    const from = (location.state as { from?: string } | null)?.from ?? "/";
    return <Navigate to={from} replace />;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (stage === "setup") {
        setMe(await api.post<Me>("auth/2fa/confirm", { otp }));
        return;
      }
      const res = await api.post<Me>("auth/login", { email, password, otp: stage === "otp" ? otp : "" });
      if (res.otp_required) {
        setStage("otp");
        return;
      }
      if (res.setup_required && !res.verified) {
        setMe(res);
        setStage("setup");
        return;
      }
      setMe(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha no login");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-5 rounded-xl border border-border bg-surface p-6 shadow-sm">
        <div className="flex items-center gap-2">
          <img src="/favicon.svg" alt="" className="size-8" />
          <div>
            <h1 className="text-lg font-semibold">Auditor de Sites</h1>
            <p className="text-xs text-muted">Acesso restrito à equipe</p>
          </div>
        </div>

        {stage === "credentials" && (
          <>
            <Field label="E-mail" htmlFor="email">
              <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
            </Field>
            <Field label="Senha" htmlFor="password">
              <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
          </>
        )}

        {stage === "otp" && (
          <Field label="Código do aplicativo autenticador" htmlFor="otp" hint="Abra o Google Authenticator, Authy ou similar e digite os 6 dígitos.">
            <Input id="otp" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" required value={otp} onChange={(e) => setOtp(e.target.value)} autoFocus />
          </Field>
        )}

        {stage === "setup" && (
          <div className="space-y-3">
            <div className="flex items-start gap-2 rounded-md bg-surface-2 p-3 text-xs">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden />
              <p>A autenticação em dois fatores é obrigatória. Escaneie o QR code com um aplicativo autenticador e digite o código gerado.</p>
            </div>
            {qr ? (
              <div className="mx-auto w-44 rounded-md bg-white p-2" dangerouslySetInnerHTML={{ __html: qr.svg }} aria-label="QR code para o aplicativo autenticador" />
            ) : (
              <p className="text-center text-xs text-muted">Gerando QR code…</p>
            )}
            <Field label="Código de 6 dígitos" htmlFor="otp-setup">
              <Input id="otp-setup" inputMode="numeric" autoComplete="one-time-code" required value={otp} onChange={(e) => setOtp(e.target.value)} />
            </Field>
          </div>
        )}

        {error && (
          <p role="alert" className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" loading={busy}>
          {stage === "credentials" ? "Entrar" : stage === "otp" ? "Verificar" : "Ativar 2FA e entrar"}
        </Button>
      </form>
    </div>
  );
}
