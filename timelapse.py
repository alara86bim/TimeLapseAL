#!/usr/bin/env python3
import os
import time
import datetime
import json
import argparse
import logging
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
                "width": 9152,
                "height": 6944
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
            self.camera = Picamera2()
            
            # Configurar resolución máxima
            config = self.camera.create_still_configuration(
                main={"size": (self.config["resolution"]["width"], 
                               self.config["resolution"]["height"])}
            )
            self.camera.configure(config)
            self.camera.start()
            time.sleep(2)  # Dar tiempo a que la cámara se inicialice
            logger.info("Cámara inicializada correctamente")
            return True
        except Exception as e:
            logger.error(f"Error al inicializar la cámara: {e}")
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
            os.makedirs(self.config["base_folder"])
        
        # Crear carpeta para el día actual si no existe
        day_folder = os.path.join(self.config["base_folder"], date_folder)
        if not os.path.exists(day_folder):
            os.makedirs(day_folder)
        
        # Nombre del archivo con timestamp
        filename = os.path.join(day_folder, f"img_{timestamp}.jpg")
        
        try:
            self.camera.capture_file(filename)
            logger.info(f"Imagen capturada: {filename}")
            return True
        except Exception as e:
            logger.error(f"Error al capturar imagen: {e}")
            return False
    
    def run(self):
        """Ejecuta el proceso de time-lapse según la configuración"""
        logger.info("Iniciando aplicación TimeLapse")
        
        try:
            if not self.initialize_camera():
                return
            
            logger.info(f"Configuración: Inicio {self.config['start_time']}, "
                        f"Fin {self.config['end_time']}, "
                        f"Intervalo {self.config['interval_seconds']} segundos")
            
            while True:
                if self.is_time_to_capture():
                    self.capture_image()
                
                # Esperar el intervalo configurado
                time.sleep(self.config["interval_seconds"])
                
        except KeyboardInterrupt:
            logger.info("Aplicación detenida por el usuario")
        finally:
            if self.camera:
                self.camera.close()
            logger.info("Aplicación TimeLapse finalizada")

def main():
    parser = argparse.ArgumentParser(description="Aplicación de TimeLapse para Raspberry Pi")
    parser.add_argument("--config", default="config.json", help="Ruta al archivo de configuración")
    args = parser.parse_args()
    
    timelapse = TimeLapse(config_file=args.config)
    timelapse.run()

if __name__ == "__main__":
    main() 