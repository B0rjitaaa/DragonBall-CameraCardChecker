import { useEffect, useState } from "react";

import Catalog from "./views/Catalog";
import Collection from "./views/Collection";
import History from "./views/History";
import Scanner from "./views/Scanner";
import { useNewVersion } from "./lib/updates";

const TABS = {
  scanner: { label: "Escáner", view: Scanner },
  catalog: { label: "Catálogo", view: Catalog },
  collection: { label: "Colección", view: Collection },
  history: { label: "Histórico", view: History },
} as const;

type TabKey = keyof typeof TABS;

// "Mi colección" vive en DragonBall-EnhancedAPI (mismo servidor, puerto 5173):
// allí se ve la colección escaneada con su ficha completa. La vista interna de
// colección sigue existiendo (#collection) pero ya no sale en el menú.
const NAV: TabKey[] = ["scanner", "catalog", "history"];
const COLLECTION_URL = `http://${window.location.hostname}:5173/coleccion`;

function currentTab(): TabKey {
  const hash = window.location.hash.slice(1);
  return hash in TABS ? (hash as TabKey) : "scanner";
}

export default function App() {
  const newVersion = useNewVersion();
  const [tab, setTab] = useState<TabKey>(currentTab);

  useEffect(() => {
    const onHash = () => setTab(currentTab());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const View = TABS[tab].view;
  return (
    <div className="app">
      {newVersion && (
        <div className="update-banner" role="status">
          Hay una versión nueva del escáner.
          <button onClick={() => window.location.reload()}>Recargar</button>
        </div>
      )}
      <header className="topbar">
        <h1>DBS Card Identifier</h1>
        <nav>
          {NAV.map((key) => (
            <a key={key} href={`#${key}`} className={key === tab ? "active" : ""}>
              {TABS[key].label}
            </a>
          ))}
          <a href={COLLECTION_URL} title="Abre Mi colección en DragonBall-EnhancedAPI">
            Mi colección ↗
          </a>
        </nav>
      </header>
      <main>
        <View />
      </main>
    </div>
  );
}
