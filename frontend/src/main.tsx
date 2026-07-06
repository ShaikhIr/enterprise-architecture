import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from '@app/App';

// PrimeReact CSS
import 'primereact/resources/themes/lara-light-blue/theme.css';
import 'primereact/resources/primereact.min.css';
import 'primeicons/primeicons.css';
import 'primeflex/primeflex.css';

// Emcure design system styles (tokens → base → overrides)
import '@assets/styles/tokens.css';
import '@assets/styles/base.css';
import '@assets/styles/theme-overrides.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
