import { createGlobalStyle } from 'styled-components';

// Токены тёмной темы ИИ-Юрист на основе палитры Plasma B2C
// Цвет акцента: #21A038 (зелёный)
// Фон: #0C0C0E (почти чёрный)

export const darkThemeTokens = {
  // Основные цвета фона
  '--color-bg': '#0C0C0E',
  '--color-bg-secondary': '#111113',
  '--color-surface': '#161618',
  '--color-surface-card': '#1C1C1E',
  '--color-surface-hover': '#222226',

  // Акцентный цвет (зелёный)
  '--color-primary': '#21A038',
  '--color-primary-hover': '#1D8F31',
  '--color-primary-active': '#197A2A',
  '--color-primary-muted': 'rgba(33, 160, 56, 0.16)',

  // Текст
  '--color-text': '#FFFFFF',
  '--color-text-secondary': 'rgba(255, 255, 255, 0.56)',
  '--color-text-tertiary': 'rgba(255, 255, 255, 0.32)',
  '--color-text-disabled': 'rgba(255, 255, 255, 0.20)',

  // Границы
  '--color-border': 'rgba(255, 255, 255, 0.10)',
  '--color-border-hover': 'rgba(255, 255, 255, 0.20)',

  // Состояния
  '--color-error': '#FF453A',
  '--color-error-muted': 'rgba(255, 69, 58, 0.16)',
  '--color-success': '#30D158',
  '--color-success-muted': 'rgba(48, 209, 88, 0.16)',
  '--color-warning': '#FFD60A',
  '--color-warning-muted': 'rgba(255, 214, 10, 0.16)',
  '--color-info': '#4A90E2',
  '--color-info-muted': 'rgba(74, 144, 226, 0.16)',

  // Тени
  '--shadow-card': '0 2px 12px rgba(0, 0, 0, 0.48)',
  '--shadow-elevated': '0 8px 32px rgba(0, 0, 0, 0.64)',

  // Радиусы
  '--radius-sm': '8px',
  '--radius-md': '12px',
  '--radius-lg': '16px',
  '--radius-xl': '24px',
  '--radius-full': '9999px',

  // Анимации
  '--transition-fast': '120ms ease',
  '--transition-normal': '200ms ease',
  '--transition-slow': '320ms ease',

  // Типографика
  '--font-family': '"Inter", "SF Pro Display", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  '--font-size-xs': '12px',
  '--font-size-sm': '14px',
  '--font-size-md': '16px',
  '--font-size-lg': '18px',
  '--font-size-xl': '22px',
  '--font-size-2xl': '28px',
  '--font-size-3xl': '36px',
  '--font-size-4xl': '48px',

  // Расстояния
  '--sidebar-width': '280px',
  '--header-height': '64px',
};

export const GlobalStyle = createGlobalStyle`
  *, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  :root {
    ${() =>
      Object.entries(darkThemeTokens)
        .map(([k, v]) => `${k}: ${v};`)
        .join('\n    ')}
  }

  html, body {
    font-family: var(--font-family);
    font-size: var(--font-size-md);
    background-color: var(--color-bg);
    color: var(--color-text);
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    min-height: 100vh;
  }

  #root {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  a {
    color: var(--color-primary);
    text-decoration: none;
    &:hover { text-decoration: underline; }
  }

  button {
    cursor: pointer;
    font-family: var(--font-family);
  }

  input, textarea, select {
    font-family: var(--font-family);
  }

  ::-webkit-scrollbar {
    width: 6px;
    height: 6px;
  }
  ::-webkit-scrollbar-track {
    background: var(--color-bg);
  }
  ::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.18);
    border-radius: 3px;
    &:hover { background: rgba(255, 255, 255, 0.28); }
  }

  ::selection {
    background: var(--color-primary-muted);
    color: var(--color-text);
  }
`;
