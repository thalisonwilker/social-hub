// Shell (menu lateral e barra superior) e diálogo de confirmação, lidos do HTML de fallback do servidor.
import React, { useEffect, useState } from "react";
import AppBar from "@mui/material/AppBar";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Toolbar from "@mui/material/Toolbar";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import Layers from "@mui/icons-material/Layers";
import Logout from "@mui/icons-material/Logout";
import Menu from "@mui/icons-material/Menu";
import UnfoldMore from "@mui/icons-material/UnfoldMore";
import { ICONS } from "./icons.js";
import { mount, mountFixed, useMode } from "./core.jsx";

const OPEN_EVENT = "mui:sidebar-toggle";
const RAIL = 64;
const WIDE = 256;

const gradient = (hue) => `linear-gradient(135deg,hsl(${hue} 80% 55%),hsl(${(Number(hue) + 50) % 360} 75% 38%))`;

/* ---------- Menu lateral ---------- */
function readLinks(container) {
  return Array.from(container.querySelectorAll("a.nav-link")).map((a) => ({
    href: a.getAttribute("href"),
    label: a.querySelector("span:not(.nav-tip)")?.textContent.trim() || "",
    icon: a.querySelector("[data-lucide]")?.getAttribute("data-lucide"),
    active: a.getAttribute("aria-current") === "page",
  }));
}

function NavList({ items, wide }) {
  return (
    <List disablePadding sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
      {items.map((item) => {
        const Icon = ICONS[item.icon];
        const button = (
          <ListItemButton
            component="a"
            href={item.href}
            selected={item.active}
            aria-current={item.active ? "page" : undefined}
            sx={{
              borderRadius: 1.5, minHeight: 44, justifyContent: wide ? "flex-start" : "center", px: wide ? 2 : 0, color: "#a1a1aa", position: "relative",
              "&:hover": { bgcolor: "rgba(255,255,255,.06)", color: "#fff" },
              "&.Mui-selected": { bgcolor: "rgba(255,255,255,.1)", color: "#fff", "&:hover": { bgcolor: "rgba(255,255,255,.12)" } },
              "&.Mui-selected::before": { content: '""', position: "absolute", left: -12, top: 8, bottom: 8, width: 3, bgcolor: "primary.main", borderRadius: 1 },
            }}
          >
            <ListItemIcon sx={{ color: "inherit", minWidth: 0, mr: wide ? 2 : 0, justifyContent: "center" }}>{Icon ? <Icon /> : null}</ListItemIcon>
            {wide ? <ListItemText primary={item.label} slotProps={{ primary: { fontSize: 14 } }} /> : null}
          </ListItemButton>
        );
        return wide ? <React.Fragment key={item.href}>{button}</React.Fragment> : (
          <Tooltip key={item.href} title={item.label} placement="right">{button}</Tooltip>
        );
      })}
    </List>
  );
}

function Sidebar({ brand, main, footer }) {
  const desktop = useMediaQuery("(min-width:1024px)", { noSsr: true });
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const toggle = (e) => setOpen(e.detail === undefined ? (v) => !v : !!e.detail);
    window.addEventListener(OPEN_EVENT, toggle);
    return () => window.removeEventListener(OPEN_EVENT, toggle);
  }, []);
  const wide = !desktop;
  const content = (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", px: 1.5, py: 2, bgcolor: "#161618" , color: "#fff" }}>
      <Box sx={{ mb: 3, display: "flex", alignItems: "center", justifyContent: wide ? "space-between" : "center" }}>
        <Box component="a" href={brand} aria-label="Social Hub" sx={{ display: "flex", alignItems: "center", gap: 1.5, color: "#fff", textDecoration: "none" }}>
          <Avatar variant="rounded" sx={{ bgcolor: "primary.main", color: "primary.contrastText", width: 36, height: 36 }}><Layers /></Avatar>
          {wide ? <Typography fontWeight={600} sx={{ fontSize: 16 }}>Social Hub</Typography> : null}
        </Box>
        {wide ? <IconButton size="small" onClick={() => setOpen(false)} aria-label="Fechar menu" sx={{ color: "#a1a1aa" }}><ICONS.x /></IconButton> : null}
      </Box>
      <Box sx={{ flex: 1 }}><NavList items={main} wide={wide} /></Box>
      <Divider sx={{ borderColor: "rgba(255,255,255,.1)", mb: 1.5 }} />
      <NavList items={footer} wide={wide} />
    </Box>
  );
  if (desktop) {
    return (
      <Drawer variant="permanent" slotProps={{ paper: { sx: { width: RAIL, border: "none", bgcolor: "#161618", overflow: "visible" } } }} sx={{ width: RAIL, "& .MuiDrawer-paper": { width: RAIL } }}>
        {content}
      </Drawer>
    );
  }
  return (
    <Drawer open={open} onClose={() => setOpen(false)} variant="temporary" ModalProps={{ keepMounted: true }} slotProps={{ paper: { sx: { width: WIDE, border: "none", bgcolor: "#161618" } } }}>
      {content}
    </Drawer>
  );
}

export function liftSidebar(el) {
  const main = readLinks(el.querySelector("nav") || el);
  const footerBox = Array.from(el.children).find((c) => c.tagName === "DIV" && c.querySelector("a.nav-link"));
  const footer = footerBox ? readLinks(footerBox) : [];
  const brand = el.querySelector('a[aria-label="Social Hub"]')?.getAttribute("href") || "/";
  document.getElementById("sidebar-backdrop")?.remove();
  el.setAttribute("data-mui-theme", "dark");
  mount(el, <Sidebar brand={brand} main={main} footer={footer} />);
}

/* ---------- Barra superior ---------- */
export function toggleTheme() {
  const root = document.documentElement;
  const next = root.classList.contains("dark") ? "light" : "dark";
  root.classList.toggle("dark", next === "dark");
  try { localStorage.setItem("theme", next); } catch (e) { /* armazenamento indisponível */ }
}

function Header({ title, profile, user, logout }) {
  const mode = useMode();
  const SunMoon = mode === "dark" ? ICONS.sun : ICONS.moon;
  return (
    <AppBar position="sticky" color="inherit" elevation={0} sx={{ top: 0, zIndex: 20, bgcolor: "background.paper", borderBottom: 1, borderColor: "divider", borderRadius: 0, border: "none", borderBottomStyle: "solid", borderBottomWidth: 1 }}>
      <Toolbar variant="dense" sx={{ minHeight: 56, gap: 1.5, px: { xs: 2, sm: 3, lg: 4 } }}>
        <IconButton edge="start" aria-label="Abrir menu" onClick={() => window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: true }))} sx={{ display: { lg: "none" } }}><Menu /></IconButton>
        <Typography component="h1" noWrap sx={{ fontSize: 16, fontWeight: 600, letterSpacing: "-0.01em" }}>{title}</Typography>
        <Box sx={{ ml: "auto", display: "flex", alignItems: "center", gap: { xs: 0.5, sm: 1 } }}>
          {profile ? (
            <Chip
              component="a"
              href={profile.href}
              clickable
              title="Trocar de perfil"
              variant="outlined"
              avatar={<Avatar sx={{ background: gradient(profile.hue), color: "#fff", fontWeight: 600 }}>{profile.initial}</Avatar>}
              label={<Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}><Box component="span" sx={{ display: { xs: "none", sm: "inline" }, maxWidth: 160 }} className="truncate">{profile.name}</Box><UnfoldMore sx={{ fontSize: 16, display: { xs: "none", sm: "block" } }} /></Box>}
            />
          ) : null}
          <IconButton data-theme-toggle aria-label="Alternar tema claro/escuro" title="Alternar tema" onClick={toggleTheme}><SunMoon /></IconButton>
          {user ? (
            <Chip
              component="a"
              href={user.href}
              clickable
              variant="outlined"
              avatar={<Avatar sx={{ bgcolor: "primary.main", color: "primary.contrastText", fontWeight: 600, textTransform: "uppercase" }}>{user.initial}</Avatar>}
              label={<Box component="span" sx={{ display: { xs: "none", sm: "inline" } }}>{user.name}</Box>}
              sx={{ "& .MuiChip-label": { px: { xs: 0, sm: 1.25 } } }}
            />
          ) : null}
          <form method="post" action={logout.action} style={{ display: "contents" }}>
            <input type="hidden" name="csrfmiddlewaretoken" value={logout.csrf} />
            <IconButton type="submit" aria-label="Sair" title="Sair"><Logout /></IconButton>
          </form>
        </Box>
      </Toolbar>
    </AppBar>
  );
}

export function liftHeader(el) {
  const chip = el.querySelector("[data-profile-chip]");
  const userLink = el.querySelector("[data-user-link]");
  const form = el.querySelector("form");
  mount(
    el,
    <Header
      title={el.querySelector("h1")?.textContent.trim() || "Social Hub"}
      profile={chip ? { href: chip.getAttribute("href"), hue: chip.dataset.hue, initial: chip.dataset.initial, name: chip.dataset.name } : null}
      user={userLink ? { href: userLink.getAttribute("href"), initial: userLink.dataset.initial, name: userLink.dataset.name } : null}
      logout={{ action: form?.getAttribute("action") || "/sair/", csrf: form?.querySelector('[name="csrfmiddlewaretoken"]')?.value || "" }}
    />,
  );
}

/* ---------- Diálogo de confirmação ---------- */
function Confirm() {
  const [state, setState] = useState(null);
  useEffect(() => {
    window.muiConfirm = (message) => new Promise((resolve) => setState({ message, resolve }));
    return () => { delete window.muiConfirm; };
  }, []);
  const close = (ok) => { state?.resolve(ok); setState(null); };
  return (
    <Dialog open={!!state} onClose={() => close(false)} maxWidth="xs" fullWidth aria-labelledby="mui-confirm-title">
      <DialogTitle id="mui-confirm-title">Confirmar ação</DialogTitle>
      <DialogContent><DialogContentText sx={{ color: "text.primary" }}>{state?.message}</DialogContentText></DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={() => close(false)} color="inherit">Cancelar</Button>
        <Button onClick={() => close(true)} variant="contained" autoFocus>Confirmar</Button>
      </DialogActions>
    </Dialog>
  );
}

export function mountConfirm() {
  mountFixed(<Confirm />);
}
