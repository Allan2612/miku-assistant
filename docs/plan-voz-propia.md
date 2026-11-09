# Plan pendiente: una voz propia de Miku, en un solo paso

**Estado:** pendiente (9-nov). El usuario lo aprobó como idea, pero aún no autorizó las instalaciones que necesita (WSL y
las herramientas de Piper). **Condición del usuario:** solo se adopta si suena igual o mejor que la voz actual.

## Por qué

Hoy cada respuesta pasa por dos pasos:

1. **edge-tts:** Microsoft genera la frase con la voz Dalia. Necesita internet.
2. **RVC:** un proceso con PyTorch la convierte al timbre de Miku.

Lo que cuesta, según el log:

- **En esta PC (RTX 3050):** 1,7 s de voz por turno (mediana de 154 turnos; p90 2,8 s).
- **En la PC AMD, sin NVIDIA:** 4,2 s para una frase de 3,9 s. Al arrancar, la voz tarda 60 s la primera vez y unos
  15 s las siguientes.

Un modelo de voz de un solo paso, tipo Piper/VITS, convertiría el texto directamente en la voz de Miku. Sería más
rápido, funcionaría sin internet y dejaría de necesitar el proceso de RVC y la tarjeta gráfica para hablar.

## Lo que se puede esperar

- **Techo de calidad:** el modelo aprende de audios hechos con la voz actual, así que como mucho suena igual. A veces
  suena más limpio, porque desaparecen los fallos sueltos de RVC, pero no mejora la entonación.
- **Para sonar mejor:** harían falta grabaciones reales de Miku hablando español, y no existen. Los modelos de clonación
  modernos (XTTS, F5-TTS, Fish Speech) necesitan tarjeta gráfica y en la PC AMD irían más lentos que hoy: descartados.
- **Palabras en inglés** (títulos de canciones): es el punto más débil. Hay que incluirlas en los datos.
- **Derechos:** el timbre es el de Hatsune Miku (Crypton Future Media), igual que el modelo RVC actual. Es para uso
  personal; repartir un modelo de voz de Miku es más delicado que repartir la app.
- **PyTorch sigue haciendo falta:** lo usa el reentrenamiento de «Hey Miku», así que el instalador no se libra de él.

## Pasos

1. **Datos** (RTX 3050, unas horas):
   - generar unas 5.000 frases (5–10 h de audio) con la cadena actual, edge-tts + RVC, con los ajustes de `config.yaml`;
   - mezclar el estilo de Miku (respuestas cortas, preguntas, exclamaciones), números, horas, fechas y nombres en
     inglés;
   - repartir las peticiones a edge-tts en el tiempo: es un servicio gratuito y puede limitar.
2. **Entrenamiento** (de 1 a 3 días de tarjeta gráfica):
   - partir de un modelo de Piper que ya habla español (calidad *medium* o *high*) y ajustarlo con esos audios;
   - Piper entrena en Linux: usar WSL2;
   - entrenar solo cuando el usuario no juegue, y retomar desde el último punto guardado.
3. **Prueba a ciegas:** 20 frases que no estén en los datos, dichas por las dos voces, sin decirle al usuario cuál es
   cuál.
   - **Pasa** si elige la nueva o no nota la diferencia.
   - **No pasa** en cualquier otro caso: se descarta y Miku queda exactamente como está.
4. **Si pasa:** integrarla en `core/tts.py`.
   - El modelo es un `.onnx` de unos 60 MB; corre con `onnxruntime`, que ya está instalado por openWakeWord.
   - Hace falta una librería nueva que convierte el texto en sonidos (`piper-phonemize`, con espeak-ng).
   - La boca se mueve con el volumen del audio (`lipSyncFromAudio` en `app/src/live2d.ts`); los tiempos por palabra de
     edge-tts son solo un extra y se pueden quitar.
   - Medir la velocidad en las dos PCs antes de cambiar el instalador.

## Antes de empezar

- Pedir permiso para instalar WSL y Piper.
- Comprobar que la voz actual (RVC encendido) es la que el usuario quiere conservar: los datos la copian tal cual.
