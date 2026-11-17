// Copia para static/dist os assets de terceiros usados pelo frontend (sem CDN).
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const copies = [
  ["node_modules/lucide/dist/umd/lucide.min.js", "static/dist/vendor/lucide.min.js"],
  [
    "node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2",
    "static/dist/fonts/inter-latin-wght-normal.woff2",
  ],
];

for (const [from, to] of copies) {
  const dest = path.join(root, to);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  if (dest.endsWith(".js")) {
    // Remove a referência ao sourcemap (não distribuído) para o collectstatic não falhar.
    const code = fs.readFileSync(path.join(root, from), "utf8").replace(/\/\/# sourceMappingURL=.*$/m, "");
    fs.writeFileSync(dest, code);
  } else {
    fs.copyFileSync(path.join(root, from), dest);
  }
  console.log(`copiado: ${to}`);
}
