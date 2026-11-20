/** Cores semânticas via variáveis CSS (definidas em input.css): o modo escuro
 *  só troca os valores das variáveis, sem `dark:` espalhado pelos templates. */
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: ["./templates/**/*.html", "./apps/**/templates/**/*.html", "./static/js/**/*.js", "./frontend/**/*.{js,jsx}"],
  theme: {
    fontFamily: {
      sans: ['"Inter Variable"', "Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
    },
    // Cantos quase retos: identidade do projeto. `full` só para avatares e indicadores.
    borderRadius: { none: "0", sm: "1px", DEFAULT: "1px", md: "2px", lg: "3px", full: "9999px" },
    extend: {
      colors: {
        bg: token("bg"),
        surface: token("surface"),
        "surface-2": token("surface-2"),
        line: token("line"),
        fg: token("fg"),
        muted: token("muted"),
        accent: token("accent"),
        "accent-fg": token("accent-fg"),
        sidebar: token("sidebar"),
        ok: token("ok"),
        warn: token("warn"),
        danger: token("danger"),
      },
      boxShadow: {
        // Profundidade discreta: realce superior + borda inferior + sombra suave.
        card: "inset 0 1px 0 rgb(255 255 255 / var(--hl)), 0 1px 0 rgb(0 0 0 / 0.03), 0 1px 2px rgb(0 0 0 / 0.06), 0 6px 14px -8px rgb(0 0 0 / 0.14)",
        raised: "inset 0 1px 0 rgb(255 255 255 / 0.18), inset 0 -2px 0 rgb(0 0 0 / 0.18), 0 1px 2px rgb(0 0 0 / 0.2)",
      },
      fontSize: { xs: ["0.75rem", "1.1rem"], sm: ["0.8125rem", "1.25rem"] },
    },
  },
  plugins: [],
};
