import { useEffect, useState } from "react";

import Catalog from "./views/Catalog";
import Collection from "./views/Collection";
import History from "./views/History";
import Scanner from "./views/Scanner";

const TABS = {
  scanner: { label: "Escáner", view: Scanner },
  catalog: { label: "Catálogo", view: Catalog },
  collection: { label: "Colección", view: Collection },
  history: { label: "Histórico", view: History },
} as const;

type TabKey = keyof typeof TABS;

function currentTab(): TabKey {
  const hash = window.location.hash.slice(1);
  return hash in TABS ? (hash as TabKey) : "scanner";
}

export default function App() {
  const [tab, setTab] = useState<TabKey>(currentTab);

  useEffect(() => {
    const onHash = () => setTab(currentTab());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const View = TABS[tab].view;
  return (
    <div className="app">
      <header className="topbar">
        <h1>DBS Card Identifier</h1>
        <nav>
          {(Object.keys(TABS) as TabKey[]).map((key) => (
            <a key={key} href={`#${key}`} className={key === tab ? "active" : ""}>
              {TABS[key].label}
            </a>
          ))}
        </nav>
      </header>
      <main>
        <View />
      </main>
    </div>
  );
}
