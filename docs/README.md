# Documentación

| Documento | Contenido |
|---|---|
| [funciones.md](funciones.md) | Todo lo que puede hacer Miku, qué es local (0 peticiones) y cómo pedirlo |
| [architecture.md](architecture.md) | Procesos, stack, flujo de una petición, protocolo WebSocket y presupuesto de recursos |
| [roadmap.md](roadmap.md) | Fases del proyecto y su estado |
| [tools.md](tools.md) | Herramientas de control del PC y cuáles piden confirmación |
| [persona.md](persona.md) | Personalidad de Miku, emociones y frases fijas |
| [setup.md](setup.md) | Software, claves y recursos que hay que conseguir aparte |
| [auditoria/plan.md](auditoria/plan.md) | Plan de auditoría total del código |
| [auditoria/hallazgos/](auditoria/hallazgos/) | Hallazgos de la auditoría, por fase |

## Recursos descargados

Los archivos pesados viven en `downloads/` (no se suben a git, pesan ~1,8 GB):

| Carpeta | Contenido |
|---|---|
| `downloads/live2d/miku_official/` | Modelo Live2D oficial de Miku (zip y extraído) |
| `downloads/rvc/` | Modelo RVC `mikuindex.pth` + índice, y las voces `default`, `mellow` y `power` en `voces/` |
| `downloads/sdk/` | Cubism SDK for Web 5 |

Los modelos que usa la app en ejecución están en `models/` y `app/public/models/`, según [setup.md](setup.md).
