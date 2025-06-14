#!/usr/bin/env python3
import os
import json
import subprocess
import signal
import logging
import time
import io
import threading
import base64
from flask import Flask, request, render_template, jsonify, send_from_directory, Response
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("webapp.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TimeLapseWeb")

app = Flask(__name__, template_folder='templates', static_folder='static')
config_file = "config.json"
timelapse_process = None
camera = None
camera_lock = threading.Lock()
preview_active = False
preview_thread = None
stop_preview_event = threading.Event()
latest_preview_image = None
timelapse_log_thread = None
stop_log_thread = threading.Event()

# Variables para el modo foto con intervalos
photo_timelapse_active = False
photo_timelapse_thread = None
stop_photo_timelapse = threading.Event()

# Constantes para resoluciones predefinidas
RESOLUTION_PRESETS = {
    "720p": {"width": 1280, "height": 720},
    "1080p": {"width": 1920, "height": 1080},
    "4K": {"width": 3840, "height": 2160},
    "max": {"width": 9152, "height": 6944}  # Máxima para Arducam 64MP
}

def load_config():
    """Carga la configuración desde el archivo JSON"""
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error al cargar configuración: {e}")

    # Configuración por defecto
    return {
        "start_time": "08:00",
        "end_time": "18:00",
        "active_days": [0, 1, 2, 3, 4, 5, 6],  # 0=Lunes, 6=Domingo
        "interval_seconds": 60,
        "base_folder": "timelapse_images",
        "resolution": {
            "width": 1920,
            "height": 1080
        },
        "preview_resolution": {
            "width": 640,
            "height": 480
        },
        "photo_timelapse": {
            "enabled": False,
            "interval_seconds": 30,
            "duration_minutes": 60,
            "prefix": "PHOTO_TL"
        }
    }

def save_config(config):
    """Guarda la configuración en el archivo JSON"""
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=4)
        logger.info("Configuración guardada correctamente")
        return True
    except Exception as e:
        logger.error(f"Error al guardar configuración: {e}")
        return False

def read_timelapse_output(process):
    """Lee la salida del proceso de time-lapse y la registra en el log"""
    while not stop_log_thread.is_set() and process and process.poll() is None:
        try:
            # Leer la salida estándar byte a byte
            stdout_bytes = b''
            while True:
                byte = process.stdout.read(1)
                if byte == b'' or byte == b'\n':
                    break
                stdout_bytes += byte
            
            if stdout_bytes:
                stdout_line = stdout_bytes.decode('utf-8', errors='replace').strip()
                if stdout_line:
                    logger.info(f"TimeLapse: {stdout_line}")
            
            # Leer la salida de error byte a byte
            stderr_bytes = b''
            while True:
                byte = process.stderr.read(1)
                if byte == b'' or byte == b'\n':
                    break
                stderr_bytes += byte
            
            if stderr_bytes:
                stderr_line = stderr_bytes.decode('utf-8', errors='replace').strip()
                if stderr_line:
                    logger.error(f"TimeLapse Error: {stderr_line}")
            
            # Si no hay salida, esperar un poco
            if not stdout_bytes and not stderr_bytes:
                time.sleep(0.1)
        except Exception as e:
            logger.error(f"Error al leer la salida del proceso: {e}")
            time.sleep(0.5)
    
    # Comprobar si el proceso terminó
    if process and process.poll() is not None:
        return_code = process.poll()
        logger.info(f"Proceso de time-lapse terminó con código: {return_code}")
        
        # Leer cualquier salida restante
        try:
            remaining_stdout = process.stdout.read()
            if remaining_stdout:
                remaining_stdout_str = remaining_stdout.decode('utf-8', errors='replace').strip()
                for line in remaining_stdout_str.split('\n'):
                    if line.strip():
                        logger.info(f"TimeLapse: {line}")
            
            remaining_stderr = process.stderr.read()
            if remaining_stderr:
                remaining_stderr_str = remaining_stderr.decode('utf-8', errors='replace').strip()
                for line in remaining_stderr_str.split('\n'):
                    if line.strip():
                        logger.error(f"TimeLapse Error: {line}")
        except Exception as e:
            logger.error(f"Error al leer la salida restante: {e}")

def start_timelapse():
    """Inicia el proceso de time-lapse"""
    global timelapse_process, timelapse_log_thread, stop_log_thread
    
    if timelapse_process and timelapse_process.poll() is None:
        logger.info("El proceso de time-lapse ya está en ejecución")
        return True
    
    try:
        # Detener el hilo de log anterior si existe
        stop_log_thread.set()
        if timelapse_log_thread and timelapse_log_thread.is_alive():
            timelapse_log_thread.join(timeout=2)
        
        # Reiniciar el flag para el nuevo hilo
        stop_log_thread.clear()
        
        # Iniciar el proceso con pipes para capturar la salida
        # No usamos buffering=1 para evitar advertencias
        timelapse_process = subprocess.Popen(
            ["python3", "timelapse.py", "--config", config_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,  # Sin buffering
            universal_newlines=False
        )
        
        logger.info(f"Proceso de time-lapse iniciado con PID {timelapse_process.pid}")
        
        # Iniciar hilo para leer la salida
        timelapse_log_thread = threading.Thread(target=read_timelapse_output, args=(timelapse_process,))
        timelapse_log_thread.daemon = True
        timelapse_log_thread.start()
        
        return True
    except Exception as e:
        logger.error(f"Error al iniciar el proceso de time-lapse: {e}")
        return False

def stop_timelapse():
    """Detiene el proceso de time-lapse"""
    global timelapse_process, stop_log_thread
    
    if not timelapse_process or timelapse_process.poll() is not None:
        logger.info("No hay proceso de time-lapse en ejecución")
        return True
    
    try:
        # Detener el hilo de lectura de logs
        stop_log_thread.set()
        
        # Enviar señal de interrupción
        timelapse_process.send_signal(signal.SIGINT)
        timelapse_process.wait(timeout=5)
        logger.info("Proceso de time-lapse detenido")
        timelapse_process = None
        return True
    except Exception as e:
        logger.error(f"Error al detener el proceso de time-lapse: {e}")
        try:
            timelapse_process.kill()
            logger.info("Proceso de time-lapse terminado forzosamente")
            timelapse_process = None
            return True
        except:
            return False

def initialize_camera(for_preview=True):
    """Inicializa la cámara con la configuración adecuada"""
    global camera

    # Si hay una instancia de cámara activa, cerrarla primero
    if camera:
        try:
            camera.stop()
            camera.close()
        except:
            pass
        camera = None

    try:
        logger.info("Inicializando cámara...")
        camera = Picamera2()
        config = load_config()
        
        if for_preview:
            # Usar una resolución más baja para la vista previa
            preview_width = config["preview_resolution"]["width"]
            preview_height = config["preview_resolution"]["height"]
            logger.info(f"Configurando vista previa: {preview_width}x{preview_height} a 60 FPS")
            
            # Configuración para vista previa con alto FPS
            try:
                preview_config = camera.create_video_configuration(
                    main={"size": (preview_width, preview_height), "format": "XRGB8888"},
                    controls={"FrameRate": 60.0, "NoiseReductionMode": 0}
                )
                camera.configure(preview_config)
            except Exception as e:
                logger.error(f"Error con resolución de vista previa {preview_width}x{preview_height}: {e}")
                # Usar una resolución más baja si falla
                preview_config = camera.create_video_configuration(
                    main={"size": (640, 480), "format": "XRGB8888"},
                    controls={"FrameRate": 60.0, "NoiseReductionMode": 0}
                )
                camera.configure(preview_config)
        else:
            # Usar la resolución configurada para captura
            width = config["resolution"]["width"]
            height = config["resolution"]["height"]
            logger.info(f"Configurando captura: {width}x{height}")
            
            try:
                still_config = camera.create_still_configuration(
                    main={"size": (width, height)}
                )
                camera.configure(still_config)
            except Exception as e:
                logger.error(f"Error con resolución de captura {width}x{height}: {e}")
                # Usar una resolución más baja si falla
                still_config = camera.create_still_configuration(
                    main={"size": (1920, 1080)}
                )
                camera.configure(still_config)
            
        camera.start()
        time.sleep(2)  # Dar tiempo a que la cámara se inicialice
        logger.info("Cámara inicializada correctamente")
        return True
    except Exception as e:
        logger.error(f"Error al inicializar la cámara: {e}")
        return False

def capture_preview_image():
    """Captura una imagen de vista previa"""
    global camera, latest_preview_image
    
    if not camera:
        if not initialize_camera(for_preview=True):
            return None
    
    try:
        output = io.BytesIO()
        camera.capture_file(output, format='jpeg')
        latest_preview_image = base64.b64encode(output.getvalue()).decode('utf-8')
        output.close()
        return latest_preview_image
    except Exception as e:
        logger.error(f"Error al capturar imagen de vista previa: {e}")
        return None

def generate_frames():
    """Genera frames para el streaming de video en tiempo real"""
    global camera, stop_preview_event
    
    with camera_lock:
        if not camera and not initialize_camera(for_preview=True):
            return
    
    try:
        while not stop_preview_event.is_set():
            output = io.BytesIO()
            with camera_lock:
                camera.capture_file(output, format='jpeg')
            frame = output.getvalue()
            output.close()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            
            # Control de velocidad de frames - reducir para permitir que la cámara capture a mayor velocidad
            time.sleep(0.01)  # Aproximadamente 100 FPS máximo (limitado por la cámara)
    except Exception as e:
        logger.error(f"Error en streaming de video: {e}")
    finally:
        if camera and not timelapse_process:
            with camera_lock:
                try:
                    camera.stop()
                    camera.close()
                    camera = None
                except:
                    pass

def preview_manager():
    """Gestiona el hilo de vista previa"""
    global preview_active, stop_preview_event, camera
    
    stop_preview_event.clear()
    preview_active = True
    
    try:
        # Inicializar la cámara si no está inicializada
        with camera_lock:
            if not camera:
                if not initialize_camera(for_preview=True):
                    logger.error("No se pudo inicializar la cámara para vista previa")
                    preview_active = False
                    return
        
        # Capturar imágenes mientras la vista previa esté activa
        while not stop_preview_event.is_set():
            with camera_lock:
                capture_preview_image()
            time.sleep(0.1)  # Actualizar más rápido (10 veces por segundo)
            
    except Exception as e:
        logger.error(f"Error en preview_manager: {e}")
    finally:
        # Limpiar recursos si no está en uso por timelapse
        if not timelapse_process:
            with camera_lock:
                if camera:
                    try:
                        camera.stop()
                        camera.close()
                        camera = None
                    except:
                        pass
        
        preview_active = False
        logger.info("Vista previa detenida")

@app.route('/')
def index():
    """Página principal"""
    config = load_config()
    return render_template('index.html', config=config, resolution_presets=RESOLUTION_PRESETS)

@app.route('/api/config', methods=['GET'])
def get_config():
    """Obtiene la configuración actual"""
    return jsonify(load_config())

@app.route('/api/config', methods=['POST'])
def update_config():
    """Actualiza la configuración"""
    try:
        config = request.json
        if save_config(config):
            return jsonify({"success": True, "message": "Configuración actualizada correctamente"})
        else:
            return jsonify({"success": False, "message": "Error al guardar la configuración"}), 500
    except Exception as e:
        logger.error(f"Error al actualizar configuración: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/resolution/presets', methods=['GET'])
def get_resolution_presets():
    """Obtiene las resoluciones predefinidas"""
    return jsonify(RESOLUTION_PRESETS)

@app.route('/api/start', methods=['POST'])
def api_start_timelapse():
    """Inicia el proceso de time-lapse"""
    if start_timelapse():
        return jsonify({"success": True, "message": "Time-lapse iniciado correctamente"})
    else:
        return jsonify({"success": False, "message": "Error al iniciar el time-lapse"}), 500

@app.route('/api/stop', methods=['POST'])
def api_stop_timelapse():
    """Detiene el proceso de time-lapse"""
    if stop_timelapse():
        return jsonify({"success": True, "message": "Time-lapse detenido correctamente"})
    else:
        return jsonify({"success": False, "message": "Error al detener el time-lapse"}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    """Obtiene el estado actual del time-lapse"""
    is_running = timelapse_process is not None and timelapse_process.poll() is None
    return jsonify({
        "running": is_running,
        "pid": timelapse_process.pid if is_running else None,
        "preview_active": preview_active
    })

@app.route('/images')
def images_list():
    """Lista todas las carpetas de imágenes disponibles"""
    config = load_config()
    base_folder = config["base_folder"]
    
    if not os.path.exists(base_folder):
        return jsonify({"folders": []})
    
    folders = [f for f in os.listdir(base_folder) 
               if os.path.isdir(os.path.join(base_folder, f))]
    folders.sort(reverse=True)  # Ordenar por fecha descendente
    
    return jsonify({"folders": folders})

@app.route('/images/<date>')
def images_by_date(date):
    """Lista todas las imágenes para una fecha específica"""
    config = load_config()
    date_folder = os.path.join(config["base_folder"], date)
    
    if not os.path.exists(date_folder):
        return jsonify({"images": []})
    
    images = [f for f in os.listdir(date_folder) 
              if f.endswith('.jpg')]
    images.sort()
    
    return jsonify({
        "date": date,
        "images": images,
        "count": len(images)
    })

@app.route('/images/<date>/<image>')
def get_image(date, image):
    """Devuelve una imagen específica"""
    config = load_config()
    date_folder = os.path.join(config["base_folder"], date)
    return send_from_directory(date_folder, image)

@app.route('/video_feed')
def video_feed():
    """Proporciona un feed de video en tiempo real"""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/preview/image', methods=['GET'])
def get_preview_image():
    """Devuelve la última imagen de vista previa como base64"""
    global latest_preview_image
    
    # Si no hay imagen de vista previa o la vista previa no está activa, capturar una nueva
    if not latest_preview_image or not preview_active:
        with camera_lock:
            if not preview_active:
                if not initialize_camera(for_preview=True):
                    return jsonify({"success": False, "message": "Error al inicializar la cámara"}), 500
            capture_preview_image()
    
    if latest_preview_image:
        return jsonify({"success": True, "image": latest_preview_image})
    else:
        return jsonify({"success": False, "message": "No se pudo obtener la imagen de vista previa"}), 500

@app.route('/api/preview/start', methods=['POST'])
def start_preview():
    """Inicia la vista previa en tiempo real"""
    global preview_thread, preview_active, stop_preview_event
    
    if preview_active:
        return jsonify({"success": True, "message": "Vista previa ya está activa"})
    
    # Detener la vista previa si está activa
    stop_preview_event.set()
    if preview_thread and preview_thread.is_alive():
        preview_thread.join(timeout=5)
    
    # Iniciar nuevo hilo de vista previa
    stop_preview_event.clear()
    preview_thread = threading.Thread(target=preview_manager)
    preview_thread.daemon = True
    preview_thread.start()
    
    # Esperar un momento para asegurarse de que la vista previa se inicie
    time.sleep(1)
    
    # Verificar si se inició correctamente
    if preview_active:
        return jsonify({"success": True, "message": "Vista previa iniciada correctamente"})
    else:
        return jsonify({"success": False, "message": "Error al iniciar vista previa"}), 500

@app.route('/api/preview/stop', methods=['POST'])
def stop_preview_route():
    """Detiene la vista previa en tiempo real"""
    global stop_preview_event
    
    stop_preview_event.set()
    
    return jsonify({"success": True, "message": "Vista previa detenida correctamente"})

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Obtiene los últimos logs de la aplicación"""
    num_lines = request.args.get('lines', default=50, type=int)
    
    try:
        # Leer logs del timelapse
        timelapse_logs = []
        if os.path.exists('timelapse.log'):
            with open('timelapse.log', 'r') as f:
                timelapse_logs = f.readlines()
                timelapse_logs = timelapse_logs[-num_lines:] if len(timelapse_logs) > num_lines else timelapse_logs
        
        # Leer logs de la webapp
        webapp_logs = []
        if os.path.exists('webapp.log'):
            with open('webapp.log', 'r') as f:
                webapp_logs = f.readlines()
                webapp_logs = webapp_logs[-num_lines:] if len(webapp_logs) > num_lines else webapp_logs
        
        return jsonify({
            "timelapse_logs": timelapse_logs,
            "webapp_logs": webapp_logs
        })
    except Exception as e:
        logger.error(f"Error al leer logs: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/photo/capture', methods=['POST'])
def capture_photo():
    """Captura una fotografía única de alta calidad"""
    # Detener vista previa temporalmente si está activa
    was_preview_active = preview_active
    if was_preview_active:
        stop_preview_route()
        time.sleep(1)  # Dar tiempo a que se libere la cámara
    
    # Capturar la foto
    result = capture_single_photo()
    
    # Reiniciar vista previa si estaba activa
    if was_preview_active:
        start_preview()
    
    return jsonify(result)

def capture_single_photo(prefix="PHOTO"):
    """Captura una foto única de alta calidad"""
    try:
        logger.info("Inicializando cámara para captura fotográfica única...")
        photo_camera = Picamera2()
        config = load_config()
        
        # Usar la resolución configurada para captura
        width = config["resolution"]["width"]
        height = config["resolution"]["height"]
        logger.info(f"Configurando captura fotográfica: {width}x{height}")
        
        # Configuración específica para fotografía de alta calidad
        still_config = photo_camera.create_still_configuration(
            main={"size": (width, height)}
        )
        photo_camera.configure(still_config)
        photo_camera.start()
        
        # Esperar para que la exposición automática se estabilice
        time.sleep(2)
        
        # Crear nombre de archivo
        now = datetime.datetime.now()
        date_folder = now.strftime("%Y-%m-%d")
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        
        # Asegurar que existe la carpeta
        base_folder = config["base_folder"]
        if not os.path.exists(base_folder):
            os.makedirs(base_folder)
        
        day_folder = os.path.join(base_folder, date_folder)
        if not os.path.exists(day_folder):
            os.makedirs(day_folder)
            
        # Contar imágenes existentes
        try:
            existing_images = [f for f in os.listdir(day_folder) if f.startswith(prefix)]
            image_count = len(existing_images) + 1
        except Exception as e:
            logger.error(f"Error al contar imágenes existentes: {e}")
            image_count = 1
            
        # Generar nombre de archivo
        filename = os.path.join(day_folder, f"{prefix}_{timestamp}_{image_count:03d}.jpg")
        
        # Capturar imagen con máxima calidad
        photo_camera.capture_file(filename)
        logger.info(f"Foto capturada: {filename}")
        
        # Cerrar la cámara
        photo_camera.stop()
        photo_camera.close()
        
        return {"success": True, "filename": filename, "path": f"/images/{date_folder}/{os.path.basename(filename)}"}
    except Exception as e:
        logger.error(f"Error al capturar foto: {e}")
        try:
            if 'photo_camera' in locals() and photo_camera:
                photo_camera.stop()
                photo_camera.close()
        except:
            pass
        return {"success": False, "error": str(e)}

def photo_timelapse_worker():
    """Función para capturar fotos a intervalos como un timelapse"""
    global photo_timelapse_active
    
    config = load_config()
    photo_config = config.get("photo_timelapse", {})
    interval = photo_config.get("interval_seconds", 30)
    duration = photo_config.get("duration_minutes", 60) * 60  # Convertir a segundos
    prefix = photo_config.get("prefix", "PHOTO_TL")
    
    logger.info(f"Iniciando timelapse fotográfico: intervalo {interval}s, duración {duration/60}min")
    
    start_time = time.time()
    next_capture = start_time
    
    while not stop_photo_timelapse.is_set():
        current_time = time.time()
        
        # Verificar si se ha completado la duración
        if duration > 0 and (current_time - start_time) > duration:
            logger.info(f"Timelapse fotográfico completado después de {duration/60} minutos")
            break
            
        # Capturar imagen cuando sea el momento
        if current_time >= next_capture:
            # Detener vista previa temporalmente si está activa
            was_preview_active = preview_active
            if was_preview_active:
                stop_preview_route()
                time.sleep(0.5)
            
            # Capturar foto
            result = capture_single_photo(prefix=prefix)
            
            # Reiniciar vista previa si estaba activa
            if was_preview_active:
                start_preview()
                
            if result["success"]:
                logger.info(f"Imagen de timelapse fotográfico capturada: {result['filename']}")
            else:
                logger.error(f"Error en timelapse fotográfico: {result.get('error', 'Error desconocido')}")
                
            # Programar próxima captura
            next_capture = time.time() + interval
        
        # Pequeña pausa para evitar uso excesivo de CPU
        time.sleep(0.1)
    
    photo_timelapse_active = False
    logger.info("Timelapse fotográfico detenido")
    
@app.route('/api/photo/timelapse/start', methods=['POST'])
def start_photo_timelapse():
    """Inicia la captura de fotos a intervalos"""
    global photo_timelapse_active, photo_timelapse_thread, stop_photo_timelapse
    
    if photo_timelapse_active:
        return jsonify({"success": False, "message": "El timelapse fotográfico ya está activo"})
    
    # Actualizar configuración si se proporcionan parámetros
    if request.json:
        config = load_config()
        if "interval_seconds" in request.json:
            config["photo_timelapse"]["interval_seconds"] = int(request.json["interval_seconds"])
        if "duration_minutes" in request.json:
            config["photo_timelapse"]["duration_minutes"] = int(request.json["duration_minutes"])
        if "prefix" in request.json:
            config["photo_timelapse"]["prefix"] = request.json["prefix"]
        config["photo_timelapse"]["enabled"] = True
        save_config(config)
    
    # Reiniciar el evento de parada
    stop_photo_timelapse.clear()
    
    # Iniciar el hilo de timelapse fotográfico
    photo_timelapse_thread = threading.Thread(target=photo_timelapse_worker)
    photo_timelapse_thread.daemon = True
    photo_timelapse_thread.start()
    
    photo_timelapse_active = True
    
    return jsonify({
        "success": True, 
        "message": "Timelapse fotográfico iniciado",
        "config": load_config()["photo_timelapse"]
    })

@app.route('/api/photo/timelapse/stop', methods=['POST'])
def api_stop_photo_timelapse():
    """Detiene la captura de fotos a intervalos"""
    global photo_timelapse_active, stop_photo_timelapse
    
    if not photo_timelapse_active:
        return jsonify({"success": False, "message": "El timelapse fotográfico no está activo"})
    
    # Señalizar al hilo que debe detenerse
    stop_photo_timelapse.set()
    
    # Esperar a que el hilo termine
    if photo_timelapse_thread and photo_timelapse_thread.is_alive():
        photo_timelapse_thread.join(timeout=2)
    
    # Actualizar configuración
    config = load_config()
    config["photo_timelapse"]["enabled"] = False
    save_config(config)
    
    return jsonify({"success": True, "message": "Timelapse fotográfico detenido"})

@app.route('/api/photo/timelapse/status', methods=['GET'])
def photo_timelapse_status():
    """Devuelve el estado actual del timelapse fotográfico"""
    config = load_config()
    
    return jsonify({
        "active": photo_timelapse_active,
        "config": config["photo_timelapse"]
    })

@app.route('/api/photo/timelapse/config', methods=['POST'])
def update_photo_timelapse_config():
    """Actualiza la configuración del timelapse fotográfico"""
    if not request.json:
        return jsonify({"success": False, "message": "No se proporcionaron datos de configuración"})
    
    config = load_config()
    
    # Actualizar configuración
    if "interval_seconds" in request.json:
        config["photo_timelapse"]["interval_seconds"] = int(request.json["interval_seconds"])
    if "duration_minutes" in request.json:
        config["photo_timelapse"]["duration_minutes"] = int(request.json["duration_minutes"])
    if "prefix" in request.json:
        config["photo_timelapse"]["prefix"] = request.json["prefix"]
    if "enabled" in request.json:
        config["photo_timelapse"]["enabled"] = bool(request.json["enabled"])
    
    if save_config(config):
        return jsonify({
            "success": True, 
            "message": "Configuración de timelapse fotográfico actualizada",
            "config": config["photo_timelapse"]
        })
    else:
        return jsonify({"success": False, "message": "Error al guardar la configuración"})

@app.teardown_appcontext
def shutdown_session(exception=None):
    """Limpia los recursos al cerrar la aplicación"""
    global camera, stop_preview_event, stop_log_thread, stop_photo_timelapse
    
    stop_preview_event.set()
    stop_log_thread.set()
    stop_photo_timelapse.set()
    
    with camera_lock:
        if camera:
            try:
                camera.stop()
                camera.close()
                camera = None
            except:
                pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True, threaded=True) 