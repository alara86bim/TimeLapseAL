#!/usr/bin/env python3
import os
import time
import datetime
import json
import argparse
import logging
import traceback
from picamera2 import Picamera2

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("timelapse.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TimeLapse")

class TimeLapse:
    def __init__(self, config_file="config.json"):
        """Inicializa la aplicación de TimeLapse"""
        self.config_file = config_file
        self.config = self.load_config()
        self.camera = None
        
    def load_config(self):
        """Carga la configuración desde el archivo JSON"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
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
            }
        }
    
    def save_config(self):
        """Guarda la configuración actual en el archivo JSON"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
            logger.info("Configuración guardada correctamente")
        except Exception as e:
            logger.error(f"Error al guardar configuración: {e}")
    
    def initialize_camera(self):
        """Inicializa la cámara con la configuración adecuada"""
        try:
            logger.info("Inicializando cámara para time-lapse...")
            self.camera = Picamera2()
            
            # Configurar resolución
            width = self.config["resolution"]["width"]
            height = self.config["resolution"]["height"]
            logger.info(f"Configurando resolución: {width}x{height}")
            
            # Usar una configuración más compatible y estable
            try:
                config = self.camera.create_still_configuration(
                    main={"size": (width, height)}
                )
                self.camera.configure(config)
            except Exception as e:
                logger.error(f"Error al configurar resolución {width}x{height}: {e}")
                logger.info("Intentando con resolución predeterminada (1920x1080)")
                config = self.camera.create_still_configuration(
                    main={"size": (1920, 1080)}
                )
                self.camera.configure(config)
                
            self.camera.start()
            time.sleep(2)  # Dar tiempo a que la cámara se inicialice
            logger.info("Cámara inicializada correctamente")
            return True
        except Exception as e:
            logger.error(f"Error al inicializar la cámara: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def is_time_to_capture(self):
        """Verifica si es el momento adecuado para capturar según la configuración"""
        now = datetime.datetime.now()
        
        # Verificar día de la semana (0 = lunes, 6 = domingo en nuestra configuración)
        weekday = now.weekday()
        if weekday not in self.config["active_days"]:
            return False
        
        # Verificar hora del día
        current_time = now.strftime("%H:%M")
        if current_time < self.config["start_time"] or current_time > self.config["end_time"]:
            return False
            
        return True
    
    def capture_image(self):
        """Captura una imagen y la guarda en la carpeta correspondiente"""
        if not self.camera:
            if not self.initialize_camera():
                return False
        
        now = datetime.datetime.now()
        date_folder = now.strftime("%Y-%m-%d")
        timestamp = now.strftime("%H-%M-%S")
        
        # Crear carpeta base si no existe
        if not os.path.exists(self.config["base_folder"]):
            try:
                os.makedirs(self.config["base_folder"])
                logger.info(f"Creada carpeta base: {self.config['base_folder']}")
            except Exception as e:
                logger.error(f"Error al crear carpeta base: {e}")
                return False
        
        # Crear carpeta para el día actual si no existe
        day_folder = os.path.join(self.config["base_folder"], date_folder)
        if not os.path.exists(day_folder):
            try:
                os.makedirs(day_folder)
                logger.info(f"Creada carpeta del día: {day_folder}")
            except Exception as e:
                logger.error(f"Error al crear carpeta del día: {e}")
                return False
        
        # Nombre del archivo con timestamp
        filename = os.path.join(day_folder, f"img_{timestamp}.jpg")
        
        try:
            logger.info(f"Capturando imagen: {filename}")
            
            # Capturar con método más simple
            self.camera.capture_file(filename)
            
            # Verificar que el archivo existe y tiene tamaño
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                logger.info(f"Imagen capturada correctamente: {filename} ({os.path.getsize(filename)} bytes)")
                return True
            else:
                logger.error(f"Imagen no guardada o tamaño cero: {filename}")
                return False
        except Exception as e:
            logger.error(f"Error al capturar imagen: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def run(self):
        """Ejecuta el proceso de time-lapse según la configuración"""
        logger.info("Iniciando aplicación TimeLapse")
        
        try:
            if not self.initialize_camera():
                logger.error("No se pudo inicializar la cámara. Deteniendo aplicación.")
                return
            
            logger.info(f"Configuración: Inicio {self.config['start_time']}, "
                        f"Fin {self.config['end_time']}, "
                        f"Intervalo {self.config['interval_seconds']} segundos, "
                        f"Resolución {self.config['resolution']['width']}x{self.config['resolution']['height']}")
            
            # Capturar una imagen inicial para verificar que todo funciona
            logger.info("Capturando imagen de prueba inicial...")
            if not self.capture_image():
                logger.error("No se pudo capturar la imagen de prueba. Deteniendo aplicación.")
                return
            
            logger.info("Imagen de prueba capturada correctamente. Iniciando bucle principal.")
            
            while True:
                if self.is_time_to_capture():
                    logger.info("Capturando imagen programada...")
                    self.capture_image()
                else:
                    logger.info("No es momento de capturar según la configuración")
                
                # Esperar el intervalo configurado
                interval = self.config["interval_seconds"]
                logger.info(f"Esperando {interval} segundos para la siguiente captura")
                
                # Dividir la espera en intervalos más pequeños para responder mejor a Ctrl+C
                for _ in range(min(60, interval)):
                    time.sleep(1)
                    if interval <= 60:
                        break
                
                remaining = max(0, interval - 60)
                if remaining > 0:
                    time.sleep(remaining)
                
        except KeyboardInterrupt:
            logger.info("Aplicación detenida por el usuario")
        except Exception as e:
            logger.error(f"Error no esperado: {e}")
            logger.error(traceback.format_exc())
        finally:
            if self.camera:
                try:
                    self.camera.stop()
                    self.camera.close()
                except Exception as e:
                    logger.error(f"Error al cerrar la cámara: {e}")
            logger.info("Aplicación TimeLapse finalizada")

def main():
    parser = argparse.ArgumentParser(description="Aplicación de TimeLapse para Raspberry Pi")
    parser.add_argument("--config", default="config.json", help="Ruta al archivo de configuración")
    args = parser.parse_args()
    
    try:
        timelapse = TimeLapse(config_file=args.config)
        timelapse.run()
    except Exception as e:
        logger.error(f"Error al ejecutar la aplicación: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main() 