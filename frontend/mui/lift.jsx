// Elevador: transforma elementos do HTML do servidor em componentes MUI preservando atributos, filhos e comportamento nativo.
import React, { useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import LinearProgress from "@mui/material/LinearProgress";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import SvgIcon from "@mui/material/SvgIcon";
import Table from "@mui/material/Table";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Visibility from "@mui/icons-material/VisibilityOutlined";
import VisibilityOff from "@mui/icons-material/VisibilityOffOutlined";
import { ICONS } from "./icons.js";
import { copyAttrs, iconSize, layoutClass, moveChildren, mount, mover } from "./core.jsx";

const once = (el, fn) => (node) => { if (node && !node.__lifted) { node.__lifted = true; fn(node); } };
const dataset = (el) => ({ ...el.dataset });

/* ---------- Ícones ---------- */
function LiftIcon({ el, Icon }) {
  const px = iconSize(el);
  return <Icon className={el.getAttribute("class") || ""} sx={{ fontSize: px, verticalAlign: "middle", flexShrink: 0 }} aria-hidden="true" />;
}

/* ---------- Botões ---------- */
function LiftButton({ el }) {
  const isLink = el.tagName === "A";
  // `disabled` pode mudar depois da montagem (ex.: o cadastro habilita "Criar conta" só com tudo válido):
  // observa o atributo no nó renderizado e reflete no estado do MUI (classe Mui-disabled, foco, cliques).
  const [disabled, setDisabled] = useState(el.disabled);
  const cls = el.classList;
  const variant = cls.contains("btn-primary") ? "contained" : cls.contains("btn-ghost") ? "text" : "outlined";
  const color = cls.contains("text-danger") ? "error" : cls.contains("btn-ghost") ? "inherit" : "primary";
  const small = /\b(py-1|px-2|text-xs)\b/.test(el.className);
  const iconOnly = el.textContent.trim() === "" && el.querySelector("[data-lucide]");
  const common = {
    className: layoutClass(el, /^(w-full|-ml-.*|p-\d.*)$/),
    ref: once(el, (node) => {
      copyAttrs(el, node, []);
      if (!isLink) {
        new MutationObserver(() => setDisabled(node.disabled)).observe(node, { attributes: true, attributeFilter: ["disabled"] });
      }
    }),
    disabled: isLink ? undefined : disabled,
  };
  if (iconOnly) {
    return (
      <IconButton {...common} size={small ? "small" : "medium"} color="inherit" component={isLink ? "a" : "button"} type={isLink ? undefined : el.type}>
        <span ref={mover(el)} style={{ display: "inline-flex" }} />
      </IconButton>
    );
  }
  return (
    <Button
      {...common}
      variant={variant}
      color={color}
      size={small ? "small" : "medium"}
      fullWidth={cls.contains("w-full")}
      href={isLink ? el.getAttribute("href") : undefined}
      type={isLink ? undefined : el.type}
    >
      <span ref={mover(el)} style={{ display: "inline-flex", alignItems: "center", gap: 8 }} />
    </Button>
  );
}

/* ---------- Campos ---------- */
function LiftField({ el }) {
  const tag = el.tagName;
  const isSelect = tag === "SELECT";
  const isArea = tag === "TEXTAREA";
  const { label, toggle } = useMemo(() => {
    const lbl = el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`) : null;
    if (lbl) lbl.style.display = "none"; // o rótulo passa a ser o do MUI
    const tgl = el.type === "password" ? el.__parent?.querySelector("[data-password-toggle]") : null;
    if (tgl) tgl.remove(); // o botão mostrar/ocultar passa a ser um IconButton MUI
    return { label: lbl, toggle: tgl };
  }, []);
  const [show, setShow] = useState(false);
  const rows = Number(el.getAttribute("rows")) || undefined;
  const wasFocused = el.hasAttribute("autofocus");

  return (
    <TextField
      size="small"
      fullWidth
      select={isSelect}
      multiline={isArea}
      rows={isArea ? rows : undefined}
      label={label ? label.textContent.trim() : undefined}
      type={isSelect || isArea ? undefined : show ? "text" : el.type}
      defaultValue={isSelect ? undefined : el.value}
      id={el.id || undefined}
      name={el.name || undefined}
      placeholder={el.placeholder || undefined}
      required={el.required}
      disabled={el.disabled}
      className={layoutClass(el, /^(w-full|block)$/)}
      slotProps={{
        inputLabel: { shrink: true },
        select: { native: true },
        input: toggle
          ? {
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton size="small" edge="end" aria-label={show ? "Ocultar senha" : "Mostrar senha"} aria-pressed={show} onClick={() => setShow((v) => !v)}>
                    {show ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                  </IconButton>
                </InputAdornment>
              ),
            }
          : undefined,
      }}
      inputRef={once(el, (node) => {
        copyAttrs(el, node, ["type", "value"]);
        if (isSelect) while (el.firstChild) node.appendChild(el.firstChild);
        if (wasFocused) node.focus();
      })}
    />
  );
}

function LiftCheckbox({ el }) {
  return (
    <Checkbox
      size="small"
      defaultChecked={el.checked}
      disabled={el.disabled}
      name={el.name || undefined}
      value={el.value}
      sx={{ p: 0.5 }}
      slotProps={{ input: { ref: once(el, (node) => copyAttrs(el, node, ["type", "value", "checked"])) } }}
    />
  );
}

/* ---------- Cartões, selos, tabelas, links ---------- */
function LiftPaper({ el }) {
  const Tag = el.tagName.toLowerCase();
  return (
    <Paper component={Tag} className={layoutClass(el)} ref={once(el, (node) => { copyAttrs(el, node, []); moveChildren(el, node); })} />
  );
}

function LiftChip({ el }) {
  const cls = el.classList;
  const color = cls.contains("badge-ok") ? "success" : cls.contains("badge-warn") ? "warning" : cls.contains("badge-danger") ? "error" : "default";
  return (
    <Chip
      component="span"
      size="small"
      variant="outlined"
      color={color}
      className={layoutClass(el, /^(inline-flex|flex|items-.*|gap-.*)$/)}
      label={<span ref={mover(el)} style={{ display: "inline-flex", alignItems: "center", gap: 6 }} />}
      ref={once(el, (node) => copyAttrs(el, node, []))}
    />
  );
}

function LiftTable({ el }) {
  return (
    <Table
      size="small"
      className={layoutClass(el)}
      sx={{ "& th": { fontWeight: 600, color: "text.secondary" }, "& td, & th": { borderBottom: "none", fontSize: "inherit", lineHeight: "inherit" } }}
      ref={once(el, (node) => { copyAttrs(el, node, []); moveChildren(el, node); })}
    />
  );
}

function LiftLink({ el }) {
  return (
    <Link underline="hover" component="a" className={layoutClass(el)} ref={once(el, (node) => { copyAttrs(el, node, []); moveChildren(el, node); })} />
  );
}

/* ---------- Alertas ---------- */
function LiftAlert({ el }) {
  const [open, setOpen] = useState(true);
  const cls = el.className;
  const severity = /border-l-danger|text-danger/.test(cls) ? "error" : /border-l-warn/.test(cls) ? "warning" : /border-l-ok/.test(cls) ? "success" : "info";
  const closable = !!el.querySelector("[data-dismiss]");
  const role = el.getAttribute("role") || (severity === "error" ? "alert" : undefined);
  if (!open) return null;
  return (
    <Alert
      severity={severity}
      role={role}
      variant="outlined"
      className={layoutClass(el, /^(flex|inline-flex|items-.*|justify-.*|gap-.*)$/)}
      onClose={closable ? () => setOpen(false) : undefined}
      sx={{ alignItems: "center", "& .MuiAlert-message": { py: 0.5, flex: 1 }, "& a": { textDecoration: "underline" } }}
    >
      <span ref={mover(el, (n) => !(n.nodeType === 1 && n.hasAttribute("data-dismiss")))} style={{ display: "contents" }} />
    </Alert>
  );
}

/* ---------- Componentes por data-mui ---------- */
function LiftAvatar({ el }) {
  const px = iconSize(el);
  const isImg = el.tagName === "IMG";
  const style = { background: el.style.background, width: px, height: px, fontSize: px / 2.6 };
  if (isImg) return <Avatar variant="rounded" src={el.getAttribute("src")} alt={el.getAttribute("alt") || ""} sx={style} slotProps={{ img: { referrerPolicy: "no-referrer" } }} />;
  return (
    <Avatar component="span" sx={{ ...style, fontWeight: 600, color: "#fff" }}>
      <span ref={mover(el)} style={{ display: "contents" }} />
    </Avatar>
  );
}

function LiftProgress({ el }) {
  return <LinearProgress variant="determinate" value={Number(el.dataset.value) || 0} className={layoutClass(el)} sx={{ height: 6, borderRadius: 3, flex: 1 }} />;
}

function LiftStepper({ el }) {
  const items = Array.from(el.querySelectorAll("li"));
  const labels = items.map((li) => li.querySelector("span:nth-of-type(2)")?.textContent.trim() || li.textContent.trim());
  const active = Math.max(0, items.findIndex((li) => li.querySelector("[aria-current]")));
  return (
    <Stepper activeStep={active} className={layoutClass(el)} sx={{ mb: 5, justifyContent: "center", width: "100%", maxWidth: 520 }} aria-label="Etapas">
      {labels.map((label) => (
        <Step key={label}>
          <StepLabel>{label}</StepLabel>
        </Step>
      ))}
    </Stepper>
  );
}

function LiftTile({ el }) {
  const d = dataset(el);
  const iconName = el.querySelector("[data-lucide]")?.getAttribute("data-lucide");
  const Icon = ICONS[iconName];
  const label = el.querySelector("[data-tile-label]")?.textContent.trim() || "";
  const hint = el.querySelector("[data-tile-hint]")?.textContent.trim() || "";
  const initial = el.querySelector("[data-tile-initial]")?.textContent.trim();
  const isLink = el.tagName === "A";
  const interactive = el.tagName === "BUTTON" || isLink;
  const disabled = el.disabled || el.getAttribute("aria-disabled") === "true";
  const bg = el.querySelector("[data-tile-initial]")?.style.background;
  const actionProps = {
    ref: once(el, (node) => copyAttrs(el, node, ["data-mui", "data-tile"])),
    component: isLink ? "a" : "button",
    type: isLink ? undefined : el.type,
    href: isLink ? el.getAttribute("href") : undefined,
    disabled,
  };

  if (d.tile === "avatar") {
    return (
      <ButtonBase {...actionProps} sx={{ flexDirection: "column", gap: 1.5, width: 144, p: 1, borderRadius: 2, "&:hover .tile-avatar": { transform: "scale(1.06)" } }}>
        <Avatar className="tile-avatar" sx={{ width: 112, height: 112, fontSize: 44, fontWeight: 600, color: "#fff", background: bg, bgcolor: initial ? undefined : "transparent", border: initial ? "none" : "2px dashed", borderColor: "text.secondary", transition: "transform .15s" }}>
          {initial || (Icon ? <Icon sx={{ fontSize: 44 }} /> : null)}
        </Avatar>
        <Typography fontWeight={500} sx={{ fontSize: 16 }}>{label}</Typography>
        {hint ? <Typography variant="caption" color="text.secondary" sx={{ mt: -1 }}>{hint}</Typography> : null}
      </ButtonBase>
    );
  }

  const body = (
    <>
      <Avatar sx={{ width: 56, height: 56, bgcolor: interactive && !disabled ? "primary.main" : "action.selected", color: interactive && !disabled ? "primary.contrastText" : "text.secondary" }}>
        {Icon ? <Icon sx={{ fontSize: 28 }} /> : null}
      </Avatar>
      <Typography fontWeight={600}>{label}</Typography>
      {d.soon ? <Chip size="small" label="Em breve" variant="outlined" /> : <Typography variant="caption" color="text.secondary" align="center">{hint}</Typography>}
    </>
  );
  const sx = { display: "flex", flexDirection: "column", alignItems: "center", gap: 1, p: 3, textAlign: "center", height: "100%" };
  return (
    <Card sx={{ height: "100%", opacity: disabled ? 0.6 : 1 }}>
      {interactive ? <CardActionArea {...actionProps} sx={sx}>{body}</CardActionArea> : <Box sx={sx}>{body}</Box>}
    </Card>
  );
}

/* ---------- Varredura ---------- */
const SELECTOR = [
  "[data-mui]", ".border-l-2", ".card", "table", ".btn", "input.input", "textarea.input", "select.input",
  'input[type="checkbox"]', ".badge", "a.text-accent", "i[data-lucide]",
].join(",");

function lift(el, shell) {
  if (!el.isConnected || el.__lifted) return;
  const kind = el.getAttribute("data-mui");
  if (kind && shell[kind]) { el.__lifted = true; return shell[kind](el); }
  const make = (Comp, props = {}) => { el.__lifted = true; return mount(el, <Comp el={el} {...props} />); };
  if (kind === "avatar") return make(LiftAvatar);
  if (kind === "progress") return make(LiftProgress);
  if (kind === "stepper") return make(LiftStepper);
  if (kind === "tile") return make(LiftTile);
  if (el.matches("i[data-lucide]")) {
    const Icon = ICONS[el.getAttribute("data-lucide")];
    return Icon ? make(LiftIcon, { Icon }) : undefined;
  }
  if (el.matches(".border-l-2")) return make(LiftAlert);
  if (el.matches("table")) return make(LiftTable);
  if (el.matches(".card")) return make(LiftPaper);
  if (el.matches(".btn")) return make(LiftButton);
  if (el.matches('input[type="checkbox"]')) return make(LiftCheckbox);
  if (el.matches("input.input, textarea.input, select.input")) return el.type === "file" ? undefined : make(LiftField);
  if (el.matches(".badge")) return make(LiftChip);
  if (el.matches("a.text-accent")) return make(LiftLink);
}

export function liftAll(shell) {
  document.querySelectorAll(SELECTOR).forEach((el) => lift(el, shell));
}
