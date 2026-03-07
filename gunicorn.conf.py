# gunicorn.conf.py
import multiprocessing
import os

# Configuración básica
bind = "0.0.0.0:5000"  # Puerto donde escuchará
workers = 1  # SOLO 1 worker para ahorrar memoria
threads = 2  # 2 hilos por worker
worker_class = "sync"  # Worker síncrono (el más estable)
timeout = 120  # Tiempo máximo de espera (segundos)
graceful_timeout = 60  # Tiempo para apagado graceful
keepalive = 2  # Tiempo de conexión keep-alive

# Control de memoria y requests
max_requests = 100  # Reiniciar worker después de 100 requests
max_requests_jitter = 20  # Variación aleatoria para evitar reinicios sincronizados

# Logging
accesslog = "-"  # Log de acceso a stdout
errorlog = "-"   # Log de errores a stdout
loglevel = os.environ.get("LOG_LEVEL", "info")  # Nivel de log

# Prevención de memory leaks
preload_app = False  # No precargar la app (mejor para memoria)
reload = False  # No recargar automáticamente (solo desarrollo)

# Nombre del proceso
proc_name = "comidaiguala"

# Configuración adicional para Render
if os.environ.get("RENDER"):
    # En producción, usar más workers? (depende de tu memoria)
    # workers = 2  # Descomentar SOLO si tienes suficiente RAM
    pass

print("="*50)
print("🔧 GUNICORN CONFIGURATION")
print(f"workers: {workers}")
print(f"threads: {threads}")
print(f"timeout: {timeout}")
print(f"max_requests: {max_requests}")
print("="*50)