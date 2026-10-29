import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import "@fontsource-variable/instrument-sans/wght.css";
import "@fontsource-variable/bricolage-grotesque/wght.css";
import "@fontsource/martian-mono/400.css";
import { SessionProvider } from "./session";
import { applyStoredTheme } from "./theme";
import App from "./App";
import "./styles.css";

applyStoredTheme();

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: (n, e: unknown) => n < 2 && (e as { status?: number })?.status !== 404 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SessionProvider>
          <App />
        </SessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
