# Aplicación de Time-Lapse para Raspberry Pi

Esta aplicación permite configurar y controlar capturas time-lapse usando Raspberry Pi 5 con cámara Arducam 64MP Eyehawk.

## Características

- Configuración de hora de inicio y fin para las capturas
- Selección de días de la semana activos
- Configuración del intervalo entre capturas (en segundos)
- Organización automática de imágenes por día
- Interfaz web para configuración y visualización de imágenes
- Captura a máxima resolución (9152 x 6944 para Arducam 64MP)

## Requisitos

- Raspberry Pi 5
- Arducam 64MP Eyehawk o cámara compatible
- Python 3.7 o superior
- Librerías: picamera2, flask

## Instalación

1. Clona este repositorio en tu Raspberry Pi:

```bash
git clone https://github.com/tuusuario/timelapse-app.git
cd timelapse-app
```

2. Instala las dependencias necesarias:

```bash
pip3 install picamera2 flask
```

3. Asegúrate de que la cámara esté habilitada en tu Raspberry Pi:

```bash
sudo raspi-config
```

Navega a "Interfacing Options" > "Camera" y habilita la cámara.

## Uso

### Iniciar la interfaz web

```bash
python3 webapp.py
```

Esto iniciará la aplicación web en el puerto 8080. Puedes acceder a ella desde un navegador web:

```
http://dirección-ip-raspberry:8080
```

### Configuración

Desde la interfaz web puedes configurar:

- **Hora de Inicio y Fin**: Define el período diario durante el cual se tomarán imágenes
- **Días Activos**: Selecciona los días de la semana en que funcionará
- **Intervalo**: Tiempo entre capturas (en segundos)
- **Carpeta Base**: Donde se guardarán las imágenes (organizadas por fecha)
- **Resolución**: Ancho y alto de las imágenes (9152 x 6944 por defecto para la Arducam 64MP)

### Control Manual

Puedes iniciar y detener manualmente el proceso de time-lapse desde la interfaz web.

### Ejecución directa (sin interfaz web)

Si prefieres ejecutar el script directamente sin la interfaz web:

```bash
python3 timelapse.py
```

O con un archivo de configuración específico:

```bash
python3 timelapse.py --config mi_config.json
```

## Estructura de Archivos

- `timelapse.py`: Script principal para la captura de imágenes
- `webapp.py`: Servidor web para la interfaz de usuario
- `templates/`: Contiene las plantillas HTML
- `static/`: Archivos estáticos (CSS, JavaScript)
- `config.json`: Archivo de configuración (se crea automáticamente)
- `timelapse_images/`: Carpeta por defecto donde se guardan las imágenes (configurable)

## Automatizar inicio al arrancar

Para que la aplicación se inicie automáticamente al arrancar la Raspberry Pi:

1. Edita el archivo de crontab:

```bash
crontab -e
```

2. Añade la siguiente línea para iniciar la aplicación web:

```
@reboot cd /ruta/a/timelapse-app && python3 webapp.py &
```

## Resolución de problemas

### Error al acceder a la cámara

Si encuentras problemas al acceder a la cámara, verifica:

1. Que la cámara esté correctamente conectada
2. Que la cámara esté habilitada en la configuración (raspi-config)
3. Que los permisos sean correctos

### Error de permiso al guardar imágenes

Si hay errores al guardar imágenes, asegúrate de que el usuario tenga permisos de escritura en la carpeta de destino:

```bash
sudo chown -R pi:pi /ruta/a/carpeta/destino
```

## Licencia

Este proyecto está licenciado bajo la licencia MIT - ver el archivo LICENSE para más detalles. 