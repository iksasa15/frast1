import { StrictMode, Component, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/readex-pro';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import '@fontsource/ibm-plex-mono/600.css';
import '@xyflow/react/dist/style.css';
import './styles/tokens.css';
import './i18n';
import './index.css';
import { initAppearance } from './lib/theme';
import App from './App';

initAppearance((localStorage.getItem('rootiq.lang') as 'ar' | 'en') || 'ar');

class ErrorBoundary extends Component<{ children: ReactNode }, { err: boolean }> {
  state = { err: false };
  static getDerivedStateFromError() {
    return { err: true };
  }
  componentDidCatch() {
    setTimeout(() => this.setState({ err: false }), 2000);
  }
  render() {
    if (this.state.err) {
      return (
        <div className="flex h-full items-center justify-center bg-noc-bg text-fg-2">
          Reconnecting…
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
