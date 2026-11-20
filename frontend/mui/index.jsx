// Ponto de entrada: eleva o HTML do servidor a componentes MUI (spec 0012, ADR-0015). Roda síncrono, antes de app.js.
import { liftAll } from "./lift.jsx";
import { liftHeader, liftSidebar, mountConfirm } from "./shell.jsx";

function run() {
  mountConfirm();
  liftAll({ sidebar: liftSidebar, header: liftHeader });
  document.documentElement.setAttribute("data-mui-ready", "");
}

try {
  run();
} catch (error) {
  // Se algo falhar, o HTML do servidor (Tailwind) segue funcional.
  console.error("MUI: falha ao elevar a interface", error);
}
