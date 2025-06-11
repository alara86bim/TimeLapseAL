#!/usr/bin/env python3
import os
import json
import subprocess
import signal
import logging
from flask import Flask, request, render_template, jsonify, send_from_directory

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
            "width": 9152,
            "height": 6944
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

def start_timelapse():
    """Inicia el proceso de time-lapse"""
    global timelapse_process
    
    if timelapse_process and timelapse_process.poll() is None:
        logger.info("El proceso de time-lapse ya está en ejecución")
        return True
    
    try:
        timelapse_process = subprocess.Popen(
            ["python3", "timelapse.py", "--config", config_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        logger.info(f"Proceso de time-lapse iniciado con PID {timelapse_process.pid}")
        return True
    except Exception as e:
        logger.error(f"Error al iniciar el proceso de time-lapse: {e}")
        return False

def stop_timelapse():
    """Detiene el proceso de time-lapse"""
    global timelapse_process
    
    if not timelapse_process or timelapse_process.poll() is not None:
        logger.info("No hay proceso de time-lapse en ejecución")
        return True
    
    try:
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

@app.route('/')
def index():
    """Página principal"""
    config = load_config()
    return render_template('index.html', config=config)

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
        "pid": timelapse_process.pid if is_running else None
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True) 