import { createTheme } from "@mui/material/styles";

const font = '"Inter Variable", Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';

const palettes = {
  light: {
    primary: { main: "#c2410c", contrastText: "#ffffff" },
    success: { main: "#15803d" },
    warning: { main: "#b45309" },
    error: { main: "#b91c1c" },
    background: { default: "#f4f3f0", paper: "#ffffff" },
    text: { primary: "#18181b", secondary: "#71717a" },
    divider: "#e2dfd9",
  },
  dark: {
    primary: { main: "#fb923c", contrastText: "#18181b" },
    success: { main: "#4ade80" },
    warning: { main: "#fbbf24" },
    error: { main: "#f87171" },
    background: { default: "#0e0e10", paper: "#18181b" },
    text: { primary: "#f4f4f5", secondary: "#a1a1aa" },
    divider: "#2d2d33",
  },
};

const cache = {};

/** Tema MUI (claro/escuro) com o laranja do Hub; mesmo conjunto de cores dos tokens do Tailwind. */
export function getTheme(mode) {
  if (cache[mode]) return cache[mode];
  const dark = mode === "dark";
  cache[mode] = createTheme({
    palette: { mode, ...palettes[mode] },
    breakpoints: { values: { xs: 0, sm: 640, md: 768, lg: 1024, xl: 1280 } }, // mesmos do Tailwind
    shape: { borderRadius: 6 },
    typography: { fontFamily: font, fontSize: 13, button: { textTransform: "none", fontWeight: 500 } },
    components: {
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: { root: { gap: 8, lineHeight: 1.25 } },
      },
      MuiPaper: { defaultProps: { variant: "outlined" }, styleOverrides: { root: { backgroundImage: "none" } } },
      MuiChip: { styleOverrides: { root: { fontWeight: 500 } } },
      MuiOutlinedInput: { styleOverrides: { root: { backgroundColor: dark ? "#1f1f23" : "#f9f8f6" } } },
      MuiTooltip: { defaultProps: { arrow: true } },
    },
  });
  return cache[mode];
}
