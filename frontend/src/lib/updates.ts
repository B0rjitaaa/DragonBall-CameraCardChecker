import { useEffect, useState } from "react";

const CHECK_MS = 60_000;

/** Script principal que carga una página (cambia de nombre con cada despliegue). */
function mainScript(html: string): string | null {
  return html.match(/src="(\/assets\/[^"]+\.js)"/)?.[1] ?? null;
}

/**
 * true cuando el servidor sirve una versión distinta de la que está abierta:
 * una sesión larga (modo ráfaga, archivador) no se entera sola de un despliegue.
 */
export function useNewVersion(): boolean {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    const current = document.querySelector<HTMLScriptElement>('script[type="module"][src*="/assets/"]')?.getAttribute("src");
    if (!current) return; // modo desarrollo
    const check = async () => {
      try {
        const html = await (await fetch("/", { cache: "no-store" })).text();
        const latest = mainScript(html);
        if (latest && latest !== current) setAvailable(true);
      } catch {
        /* sin conexión: se vuelve a intentar */
      }
    };
    const timer = window.setInterval(() => void check(), CHECK_MS);
    return () => window.clearInterval(timer);
  }, []);
  return available;
}
