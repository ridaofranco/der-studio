# DER Studio

Herramienta personal para generar piezas de Instagram con el brand kit de DER.

- **Posteos e historias**: subís fotos del evento y/o un texto corto → te devuelve posts (4:5 y 1:1) e historias (9:16) listos.
- **Reels**: subís varios videos (y fotos, si querés) → te devuelve un reel 9:16 con transiciones, música genérica de fondo, título opcional y el logo de cierre.

## Cómo se usa (Windows)

1. Descomprimí `der-studio.zip` en una carpeta fija, por ejemplo `Documentos\der-studio`
   (clic derecho → *Extraer todo*; no lo abras desde adentro del zip).
2. Doble clic en **`iniciar.bat`**.
   - La primera vez instala todo solo (Python si no lo tenés, y lo demás). Tarda unos minutos.
   - Si Windows muestra "Windows protegió su PC", tocá *Más información* → *Ejecutar de todas formas*.
   - Te deja un acceso directo **DER Studio** en el escritorio.
3. Se abre el navegador con la app. Dejá abierta la ventana negra mientras la usás; para salir, cerrala.
4. Lo que generás se descarga desde la app y además queda guardado en la carpeta `salidas\`.

No necesita internet para usarse (solo la primera vez, para instalar), ni servidor: corre en tu compu.
Los reels usan el procesador de la PC; un reel de 30 segundos tarda aproximadamente 1 a 3 minutos en una notebook común.

## Actualizaciones

DER Studio se actualiza solo desde GitHub (`ridaofranco/der-studio`):
- cada vez que lo abrís busca la última versión y la instala antes de arrancar;
- si lo tenés abierto y sale una versión nueva, aparece un aviso arriba con el botón **Actualizar ahora**.

Las actualizaciones nunca tocan tus logos, tu música, tus tipografías cargadas ni las piezas de `salidas\`.

## Brand kit (carga única)

Los colores ya están configurados según el manual de marca:
`#ff5c00` naranja · `#333333` gris oscuro · `#f0f0f0` gris claro.

Desde la pestaña **Brand kit** de la app (o copiando los archivos a mano) cargá los archivos que están en el Drive:

| Qué | De dónde (Drive) | A dónde |
|---|---|---|
| Logos PNG | carpeta **LOGO SOMOS DER** (dejá los nombres originales, ej. `LOGO-DER-NARANJA-Y-GRIS-CLARO.png`) | `brand/logos/` |
| Netron (títulos) | `Netron.ttf` | `brand/fonts/` |
| Articulat CF (subtítulos) | `Articulat CF Font Family.zip` (sirve el .zip tal cual). ⚠️ La versión DEMO de Fontspring no trae tildes ni ñ: hace falta la licencia completa | `brand/fonts/` |
| Jost (cuerpo) | ya está incluida | — |
| Música propia (opcional) | temas libres de derechos .mp3/.wav | `brand/music/` |

Las tipografías con licencia no se suben a este repositorio (es público): se cargan en cada instalación desde **Brand kit → Tipografías**.

Mientras falten, la app usa reemplazos parecidos (Orbitron para títulos, Jost para subtítulos y un logotipo de texto) y lo avisa con un cartel arriba.

El logo se elige solo según el fondo: naranja + gris claro sobre fondos oscuros, naranja + gris oscuro sobre fondos claros.

## Logos

En **Brand kit → Logos** arrastrá todas las versiones juntas (naranja, gris claro, gris oscuro, logos de clientes…).
Cada una se puede ver sobre fondo claro u oscuro y eliminar.

Al generar (posteos, historias o reels) elegís el logo:
- **Automático**: la app elige la versión DER que contrasta con el fondo, según el nombre del archivo
  (`...NARANJA-Y-GRIS-CLARO` para fondos oscuros, `...NARANJA-Y-GRIS-OSCURO` para fondos claros).
- **Uno puntual**: se usa ese en todas las piezas.

## Editar una pieza

Tocá cualquier imagen generada y se abre el editor:
- **Mover**: arrastrar. **Agrandar o achicar**: desde las esquinas. Se pega sola al centro.
- **Textos**: doble clic para escribir. Tipografía (Netron / Articulat / Jost), tamaño, alineación y mayúsculas.
- **Resaltar palabras**: mientras escribís, seleccioná las palabras y tocá un color.
- **Colores**: solo los de la marca (naranja, gris oscuro, gris claro, blanco).
- **Logo**: cambiarlo por otra versión o agregar otro (por ejemplo, el del cliente).
- **Agregar**: texto, barra naranja, esquinero, grilla de puntos.
- Duplicar, traer al frente, enviar atrás, eliminar, opacidad.
- **Deshacer** / **Rehacer** (Ctrl+Z / Ctrl+Y). Flechas del teclado para mover de a 1 px (con Shift, de a 10).
- **Guardar** reemplaza la imagen y el .zip toma la versión editada. Se puede volver a editar cuantas veces quieras.

La foto de fondo no se mueve desde el editor; para cambiar el encuadre usá "Encuadre de la foto" al generar.

## Plantillas

| Plantilla | Uso |
|---|---|
| Foto a sangre | foto protagonista, texto sobre degradé gris oscuro |
| Foto enmarcada | fondo gris claro, foto con bloque naranja desplazado |
| Foto + banda naranja | foto arriba, texto en banda naranja |
| Collage | 2 a 4 fotos en grilla |
| Solo texto (gris / naranja) | anuncios, frases, avisos |
| Frase / cita | título = la frase, subtítulo = quién la dijo; comillas naranjas grandes |
| Dato / número grande | título = el número (`+40.000`), subtítulo = qué es, texto = contexto; foto opcional de fondo |
| Lista de puntos | título + un punto por renglón del texto (hasta 6), numerados |
| Antes / después | 2 fotos (la primera es ANTES) con etiquetas y línea naranja |
| Evento / agenda | subtítulo = fecha (`15 NOV`) en bloque naranja, título = evento, texto = lugar y hora; foto opcional |
| Foto con cinta | foto impresa con borde blanco, girada y pegada con cinta naranja; una pieza por foto |

- En el título, lo que pongas `*entre asteriscos*` va resaltado en naranja.
- Con varias fotos se arma un **carrusel en cualquier plantilla** (hasta 20 diapositivas): el texto va solo en la primera, salvo que marques "Texto en todas".
  - Collage: hasta 4 fotos por diapositiva. Antes / después: una diapositiva por par.
  - Frase, lista, dato, agenda y solo texto: la primera es la plantilla y después una diapositiva por foto, con el mismo estilo.
- En el editor, **Fondo** cambia el color liso de la pieza (marca u otro). Lo que quedaría del mismo color que el fondo pasa solo a un color de marca que contraste.
- Las historias respetan los márgenes que tapa la interfaz de Instagram.

## Reels

- Cada clip se recorta al tramo central (máx. de segundos configurable).
- Los videos horizontales se centran sobre el mismo video desenfocado.
- Las fotos entran con un zoom lento.
- Música: genérica sintetizada en el momento (enérgica, corporativa o suave; sin derechos de autor) o un tema propio de `brand/music/`.
- Cierre de 3 s con el logo, esquineros naranjas y `SOMOSDER.AR`.

## Trabajar en segundo plano

- Mientras **sube** los archivos, la app tiene que quedar abierta (la pantalla no se apaga sola). Si se corta o salís,
  al volver retoma desde la parte que faltaba.
- Una vez subidos, **podés salir de la app**: el servidor arma todo (también las piezas terminadas).
  Al volver, el resultado aparece solo; además queda en la pestaña **Recientes** (últimos 14 días).
- **Avisarme** (arriba): activa una notificación cuando termina cada reel, carrusel o lote de piezas.
  En iPhone funciona con DER Studio agregado a la pantalla de inicio (iOS 16.4 o más nuevo).

## Carrusel de fotos y videos

Pestaña **Carrusel**: subís fotos y videos en el orden en que van (hasta 20).
- Las fotos salen como piezas de marca con el estilo elegido (foto a sangre, enmarcada, banda o cinta) y se pueden editar.
- Los videos salen en 4:5 o 1:1, con el logo chico arriba y su audio original; los horizontales van sobre el mismo video desenfocado. Máximo de segundos configurable (Instagram admite hasta 60).
- **Descargar todo** baja un .zip numerado (`DER-carrusel-01`, `-02`…); **Compartir todo** lo manda directo desde el celular si el sistema lo permite.

### Editor de reels (estilo CapCut)

Debajo del reel, **Editar reel** abre el editor a pantalla completa:
- **Línea de tiempo** con la tira de cuadros de cada clip. Tocá un clip para elegirlo; arrastrá sus bordes blancos para recortar;
  mantenelo apretado y arrastralo para cambiarlo de lugar. Entre clip y clip, el cuadradito es la **transición** (16, con duración).
- Con un clip elegido: **Recortar, Dividir, Velocidad** (0,25x a 4x), **Volumen** (sonido original), **Encuadre** (llenar o
  ajustar con fondo desenfocado o de color, zoom y posición), **Filtros** (11), **Ajustes** (brillo, contraste, saturación,
  temperatura, viñeta), **Animación** (acercar, alejar, paneo, latido, sacudida), **Girar y espejar**, **Congelar** un cuadro,
  **Invertir** (hasta 6 s), **Duplicar, Mover, Borrar**.
- Sin clip elegido: **Agregar** más videos o fotos, **Formato** (9:16, 4:5, 1:1), **Música** (volumen, desde qué segundo,
  fundido, otra canción), **Voz en off** (grabada desde el celular o subida, baja la música al hablar), **Título**,
  **Logo y cierre**, **Filtro a todo**.
- **Texto**: títulos, subtítulos, etiquetas con caja, llamados a la acción o máquina de escribir, cada uno con su
  momento de entrada y salida, posición (se arrastra sobre el video), tamaño, tipografía, color, caja y animación
  (aparecer, subir, deslizar, golpe, máquina de escribir). Aparecen en una pista debajo de los clips: se mueven y estiran ahí.
- **Stickers**: logo (DER o de cliente), marco de esquineros, grilla de puntos, barra naranja, SOMOSDER.AR y flecha.
- **Al ritmo**: detecta el pulso de la música (la genérica o un tema propio) y ajusta los clips para que cada corte caiga
  en un golpe (cada 1, 2, 4 u 8 tiempos).
- **Deshacer / Rehacer** sin límite práctico. Los cambios se guardan solos en el celular aunque cierres la app.
- **Vista previa**: versión liviana en segundos para revisar. **Exportar**: versión final en alta (versión 1, 2, 3…);
  sigue en el servidor aunque salgas, y avisa al terminar. Los clips que no cambiaron se reutilizan.

Los archivos originales quedan en `salidas/<lote>/fuentes`, así que un reel se puede volver a editar mientras esté esa carpeta.

## Estructura

```
app.py              servidor web local
der/brand.py        brand kit (colores, tipografías, logos)
der/graphics.py     plantillas de posts e historias
der/reels.py        armado de reels con ffmpeg
der/music.py        música genérica
templates/          interfaz
brand/              fuentes, logos y música
```
