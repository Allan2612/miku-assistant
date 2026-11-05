# Extensión de Miku para Opera GX

Le da a Miku las pestañas de Opera de verdad: cada pestaña abierta (número, título, dirección), los resultados de una
búsqueda que tengas delante (Google, YouTube, DuckDuckGo, Bing) y órdenes exactas por número de pestaña: abrir una web
(en pestaña nueva o en una dada), cerrar, activar, recargar, atrás y adelante.

Sin ella Miku sigue abriendo webs (`opera.exe <url>`), pero no ve ni maneja pestañas.

## Instalar

1. En Opera GX abre `opera://extensions`.
2. Activa **Modo de desarrollador** (arriba a la derecha).
3. **Cargar descomprimida** → elige esta carpeta (`browser-extension`).
4. Listo: con Miku en marcha, el log del backend dice `Opera extension connected.`

Tras cambiar un archivo de la carpeta, pulsa el botón de recargar de la extensión en `opera://extensions`.

## Cómo funciona

- `background.js` (service worker) se conecta a `ws://127.0.0.1:8765`, el servidor local de Miku, y le envía el estado
  de las pestañas cada vez que cambia (agrupado cada 400 ms). Si Miku no está en marcha, reintenta cada 3 s; si Opera duerme la extensión, la alarma la despierta cada 30 s.
- El backend la reconoce por su `Origin` (`chrome-extension://gfjpfiehfhmpcfidlgjgbgjkaehkkaaf`, fijo gracias a la
  `key` de `manifest.json`) y solo le acepta estado y respuestas: la extensión no puede hablar por Miku ni apagar nada.
- Cada petición a Gemini lleva ese estado, así que el modelo elige pestañas por número (`browser_tabs`,
  `open_url(tab_id=...)`) en vez de adivinar.

Permisos: `tabs` (títulos y direcciones), `scripting` y acceso a las páginas de resultados de Google, YouTube,
DuckDuckGo y Bing (para leer la lista de resultados), `alarms` (mantener la conexión). Nada sale de tu PC.
