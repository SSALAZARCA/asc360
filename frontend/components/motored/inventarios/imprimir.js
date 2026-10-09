/**
 * Minimal print pages of the inventory counts (WU11): the pairs' QR and the
 * store's location labels. Labels print the scan text `UBI-<código>` in
 * large type; a real barcode needs a barcode library, which is not added.
 */
const ESTILO = 'body{font-family:system-ui,sans-serif;margin:24px;color:#1a1a18}'
  + 'h1{font-size:22px;margin:0 0 12px}.e{display:inline-block;width:45%;margin:0 2% 16px 0;'
  + 'padding:16px;border:1px dashed #5a5a5a;box-sizing:border-box;page-break-inside:avoid}'
  + '.c{font-family:monospace;font-size:28px;font-weight:700}.n{font-size:14px}';

function escapar(texto) {
  return String(texto ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function imprimirHtml(titulo, cuerpo) {
  const ventana = window.open('', '_blank');
  if (!ventana) return false;
  ventana.document.write(
    `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>${escapar(titulo)}</title>`
    + `<style>${ESTILO}</style></head><body>${cuerpo}</body></html>`,
  );
  ventana.document.close();
  ventana.focus();
  ventana.print();
  return true;
}

export function imprimirQr({ tienda, qrSrc, url }) {
  return imprimirHtml(`QR del conteo · ${tienda}`,
    `<h1>Conteo de inventario · ${escapar(tienda)}</h1>`
    + `<img src="${escapar(qrSrc)}" alt="QR" style="width:320px;height:320px">`
    + `<p class="n">Escanee el QR o abra: ${escapar(url || '')}</p>`
    + '<p class="n">Luego escriba el código que le da el líder.</p>');
}

export function imprimirEtiquetas({ tienda, ubicaciones }) {
  const activas = ubicaciones.filter((u) => u.activa);
  const etiquetas = activas.map((u) => (
    `<div class="e"><div class="c">UBI-${escapar(u.codigo)}</div><div class="n">${escapar(u.nombre)}</div></div>`
  )).join('');
  return imprimirHtml(`Etiquetas de ubicación · ${tienda}`,
    `<h1>Ubicaciones · ${escapar(tienda)}</h1>${etiquetas}`);
}
