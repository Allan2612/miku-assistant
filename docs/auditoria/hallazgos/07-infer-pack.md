# Fase 7 · Modelos RVC de terceros (`core/infer_pack/`)

Avance: `models.py` 1142/1142 · `modules.py` 522/522 · `attentions.py` 417/417 · `transforms.py` 193/193 · `commons.py` 164/164 · `__init__.py` 0/0 · **fase completa**

## Método

Se identificó el origen descargando los archivos del repositorio oficial [RVC-Project/Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) en varias versiones y comparándolos con `diff -w` y con el árbol sintáctico de Python (`ast.dump`), que ignora el formato:

| Archivo local | Versión original más cercana | Resultado |
|---|---|---|
| `modules.py` | `2.0.230618/infer_pack/modules.py` | idéntico |
| `attentions.py` | `2.0.230618/infer_pack/attentions.py` | idéntico |
| `transforms.py` | `2.0.230618/infer_pack/transforms.py` | mismo código; solo cambia el formato (110 líneas, sin cambio de AST) |
| `commons.py` | `2.0.230618/infer_pack/commons.py` | mismo código (2 líneas en blanco) |
| `models.py` | `2.0.230618/infer_pack/models.py` | 34 líneas distintas, leídas a mano (abajo) |
| `core/rmvpe.py` | `2.1.230814/lib/rmvpe.py` | las 8 capas de red (`BiGRU` … `DeepUnet`) idénticas; `E2E`, `MelSpectrogram` y `RMVPE` difieren y se leyeron a mano (H-042) |

**Las únicas diferencias de `models.py`** están en los cuatro métodos `infer` de los sintetizadores: el original recibe `max_len` y recorta la salida; la copia local recibe `rate` y, si se pasa, se queda con la parte final de la secuencia (`models.py:634-644`, `:750-760`, `:857-866`, `:963-972`). Es la variante de versiones posteriores de RVC, pensada para conversión en tiempo real. `rvc_worker.py` llama `infer` sin `rate`, así que se ejecuta la ruta completa. No introduce errores.

Conclusión: el código de terceros no tiene modificaciones locales peligrosas.

### H-043 · Falta la licencia MIT de RVC y la mitad de `models.py` no se usa

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/infer_pack/` (todo), `core/rmvpe.py`, `core/infer_pack/models.py`
- **Categoría:** mantenibilidad / licencia

**Qué pasa:**

- RVC se distribuye con licencia MIT ("Copyright (c) 2023 liujing04"), que exige conservar el aviso de copyright y la licencia en las copias. El repositorio no incluye ninguno de los dos ni indica de dónde vienen estos archivos. Ahora que el código está en GitHub (aunque sea privado), conviene corregirlo.
- Solo se usa `SynthesizerTrnMs768NSFsid` (`rvc_worker.py:36`). El resto de clases de `models.py` (`SynthesizerTrnMs256NSFsid`, las variantes `_nono`, `MultiPeriodDiscriminator`, `DiscriminatorS`/`DiscriminatorP`, etc.) son para otras versiones de modelo o para entrenamiento, y no se usan nunca.

**Propuesta:** añadir `core/infer_pack/LICENSE` con el texto MIT de RVC y una línea en el `README.md` con el origen y la versión (2.0.230618). Borrar las clases sin uso es opcional: mantener la copia idéntica al original facilita actualizarla.

### Notas para siguientes pasos

- Fase 10: `core/requirements.txt` no incluye `torch` ni `openwakeword`, que el código importa (`rvc_worker.py:33`, `rmvpe.py:1`, `wakeword.py:23`). Una instalación desde cero con `pip install -r requirements.txt` no funcionaría.
