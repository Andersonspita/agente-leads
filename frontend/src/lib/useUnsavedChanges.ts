import { useEffect } from "react";
import { useBeforeUnload, useBlocker } from "react-router-dom";

const MESSAGE = "Há alterações não salvas. Sair mesmo assim?";

/** Avisa antes de sair da tela (link do painel, voltar, fechar ou recarregar a aba) com alterações não salvas. */
export function useUnsavedChanges(dirty: boolean) {
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm(MESSAGE)) blocker.proceed();
    else blocker.reset();
  }, [blocker]);
  useBeforeUnload((e) => {
    if (dirty) e.preventDefault(); // o navegador mostra o próprio aviso
  });
}
