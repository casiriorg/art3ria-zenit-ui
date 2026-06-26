# Spec: Resumen post-sesion

## 1. Motivacion

Al finalizar una sesion de grabacion, el investigador necesita saber rapidamente si
los datos se registraron correctamente antes de que el participante se retire. Sin un
resumen, debe abrir el CSV manualmente para verificar que hubo muestras IMU y que las
senales fisiologicas tienen valores razonables.

---

## 2. Comportamiento esperado

### 2.1 Cuando aparece

El modal de resumen se muestra automaticamente en dos casos:
- La sesion finaliza normalmente (el audio termina y concluye la cuenta regresiva post).
- El usuario presiona **ABORTAR** durante una sesion activa.

En ambos casos el resumen refleja los datos efectivamente grabados hasta ese momento.

### 2.2 Contenido del modal

```
┌──────────────────────────────────────────────────┐
│  Resumen de sesion                               │
├──────────────────────────────────────────────────┤
│  Participante       Juan Perez                   │
│  Audio              estimulo_01.wav              │
│  Duracion (grabacion)  45.2 s                    │
│  Muestras IMU       1356                         │
├──────────────────────────────────────────────────┤
│  Senal     Min        Prom       Max             │
│  PPG       62.100     78.420     95.200          │
│  GSR       0.021      0.043      0.071           │
├──────────────────────────────────────────────────┤
│              [  Aceptar  ]                       │
└──────────────────────────────────────────────────┘
```

- **Duracion (grabacion)**: tiempo entre la primera y la ultima fila con `estado == "record"`.
  No incluye las cuentas regresivas pre/post.
- **Muestras IMU**: filas con `estado == "record"` que contienen datos de quaternion (`qw`).
- **Tabla de senales**: aparece solo si se recibio al menos una senal durante la grabacion.
  Se muestra una fila por cada clave de senal (PPG, GSR, TEMP, etc.).
- El modal es de solo lectura; no modifica ningun dato.

### 2.3 Cierre del modal

| Accion | Resultado |
|--------|-----------|
| Tecla `Enter` | Cierra el modal |
| Tecla `Esc` | Cierra el modal |
| Clic en "Aceptar" | Cierra el modal |

Al cerrarlo, la app vuelve al estado normal (sin sesion activa) y el boton
**REPRODUCIR** queda disponible para una nueva sesion.

---

## 3. Datos calculados

Todos los calculos se realizan sobre las filas en memoria (`_rows`) antes de que el
buffer sea liberado. Solo se consideran filas con `estado == "record"`.

| Campo | Calculo |
|-------|---------|
| `duration_s` | `(timestamp[-1] - timestamp[0]).total_seconds()` sobre filas "record" |
| `imu_count` | Cantidad de filas "record" que contienen la clave `qw` |
| `signals[key].mean` | Promedio aritmetico de todos los valores de esa senal en filas "record" |
| `signals[key].min` | Valor minimo |
| `signals[key].max` | Valor maximo |
| `signals[key].count` | Cantidad de muestras de esa senal |

Claves excluidas del calculo de senales: `timestamp`, `participant_name`, `session_id`,
`audio_file`, `estado`, `qw`, `qx`, `qy`, `qz`.

---

## 4. Implementacion

### 4.1 Modulos afectados

| Archivo | Cambio |
|---------|--------|
| `logger.py` | Nuevo atributo `summary_queue`, nuevo metodo `_compute_summary()`, modificacion del handler STOP/ABORT en `run()` |
| `main.py` | Drenado de `logger.summary_queue` en el loop principal; llama a `ui.show_summary()` |
| `ui.py` | Nuevo metodo `show_summary()`, nuevo modo "summary" en `_handle_modal_event()` y `_draw_modal()`, nuevo metodo `_draw_summary_content()` |

### 4.2 Flujo de datos

```
[Audio thread] DONE/ABORTED
      |
      v
[main.py] logger.stop() / logger.abort()
      |
      v  (cmd_queue)
[CSVLogger thread] _compute_summary() -> summary_queue.put(summary)
                   _flush_to_disk()
                   _active = False
      |
      v  (cada frame, en el loop principal)
[main.py] logger.summary_queue.get_nowait() -> ui.show_summary(summary)
      |
      v
[AppUI] modal = {"mode": "summary", "data": summary}
      |
      v  (en render())
[AppUI._draw_summary_content()] dibuja el modal sobre el HUD
```

### 4.3 Consideraciones de concurrencia

- `_compute_summary()` se ejecuta **dentro del thread del logger**, sobre `self._rows`
  y `self._meta` que solo ese thread modifica. No requiere locks adicionales.
- `summary_queue` es una `queue.Queue` estandar; thread-safe por diseno.
- El loop principal drena `summary_queue` cada frame (no bloqueante, con `get_nowait()`).

---

## 5. Limitaciones conocidas

- Si la sesion se inicia y se aborta antes de que llegue cualquier dato del sensor,
  el resumen aparece con ceros/vacios (no es un error, refleja el estado real).
- La duracion se calcula a partir de los timestamps de los datos del sensor, no del
  reloj del sistema. Si el sensor envia datos con timestamps inconsistentes, la
  duracion puede ser incorrecta.
- El modal no muestra la ruta del CSV guardado (disponible en `summary["filepath"]`
  si se necesita en una futura iteracion).
