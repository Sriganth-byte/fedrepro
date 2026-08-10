import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import "./styles.css";

// Apply persisted theme before first render to prevent FOUC
try {
  const saved = localStorage.getItem("fedrepro-theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);
} catch {}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>
);

