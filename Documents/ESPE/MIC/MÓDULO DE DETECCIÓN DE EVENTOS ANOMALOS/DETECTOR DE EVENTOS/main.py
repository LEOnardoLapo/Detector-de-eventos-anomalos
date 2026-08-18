import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
import cv2
import numpy as np
from PIL import Image, ImageTk
import time
import os
import sys
import threading
from collections import deque
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import psutil
import json
import requests
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

class DashboardTesisV28_CommandCenterPro:
    def __init__(self, root):
        self.root = root
        self.root.title("SISTEMA DE DETECCIÓN DE EVENTOS ANÓMALOS -LAPO LEONARDO- ESPE")
        
        self.root.geometry("1540x950") 
        self.root.resizable(False, False)
        
        # --- PALETA DE COLORES ---
        self.bg_main = "#f0f2f5"     
        self.bg_panel = "#ffffff"    
        self.text_main = "#2c3e50"   
        self.text_sec = "#7f8c8d"    
        self.color_btn = "#0056b3"   
        self.color_danger = "#dc3545"
        self.color_success = "#28a745"
        self.color_info = "#17a2b8"  
        self.color_folder = "#6c757d" 
        self.color_card_bg = "#f8fafc" 
        
        self.root.configure(bg=self.bg_main)

        # --- PARÁMETROS DE TIEMPO ---
        self.SEGUNDOS_PRE = 2
        self.SEGUNDOS_POST = 3
        self.fps_actual = 30.0 
        
        self.VID_W = 576
        self.VID_H = 324
        
        self.K_MAG = 3.5  
        self.K_VAR = 3.5  
        
        # === PISOS MÍNIMOS ===
        self.PISO_MIN_MAG = 1.5
        self.PISO_MIN_VAR = 0.4
        
        self.VENTANA_ESTADISTICA = 60
        self.memoria_mag = deque(maxlen=self.VENTANA_ESTADISTICA)
        self.memoria_var = deque(maxlen=self.VENTANA_ESTADISTICA)
        
        self.buffer_circular = deque()
        self.MAX_FRAMES_BUFFER = 0
        self.FRAMES_POST_NECESARIOS = 0
        self.TOTAL_FRAMES_CLIP = 0
        
        self.grabando = False
        self.frames_grabados_post = 0
        self.frames_buffer_congelado = []
        self.video_writer = None
        self.frames_pre_usados = 0
        self.frames_post_pendientes = 0
        
        self.carpeta_salida = "Eventos_Extraidos"
        if not os.path.exists(self.carpeta_salida):
            os.makedirs(self.carpeta_salida)

        self.evidencias_sesion = 0
        self.evidencias_totales = len([f for f in os.listdir(self.carpeta_salida) if f.endswith('.mp4')])

        # --- VARIABLES PARA EL TEMPORIZADOR DE SESIÓN ---
        self.tiempo_inicio_sesion = None
        self.temporizador_activo = False
        self.id_temporizador = None

        # --- CONFIGURACIÓN GOOGLE DRIVE (REQUESTS DIRECTO) ---
        self.CLIENT_SECRET_FILE = 'client_secret.json'
        self.TOKEN_FILE = 'drive_token.json'
        self.GOOGLE_DRIVE_FOLDER_NAME = 'Eventos_Anómalos'
        self.GOOGLE_DRIVE_FOLDER_ID = None
        self.access_token = None
        self.inicializar_google_drive()

        # --- HISTÓRICOS ---
        self.historial_mag = []
        self.historial_var = []
        self.historial_umbral_mag = []
        self.historial_umbral_var = []
        self.frames_procesados = 0
        
        self.ANCHO_VENTANA_GRAFICA = 450  
        self.puntos_disparo_x = []
        self.puntos_disparo_y_mag = []
        self.puntos_disparo_y_var = []

        self.modo_manual = False  
        self.mouse_presionado = False
        self.mouse_ultimo_x = None
        self.mouse_ultimo_y = None

        self.cap = None
        self.prvs = None
        self.procesando = False
        self.proceso_actual = psutil.Process(os.getpid())
        
        # === INDICADOR DE TIPO DE VIDEO ===
        self.modo_video = None
        
        # === FLUJO ÓPTICO DISPERSO (Lucas-Kanade) ===
        self.puntos_previos = None
        self.lk_params = dict(winSize=(15, 15), maxLevel=2,
                               criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
        self.feature_params = dict(maxCorners=200, qualityLevel=0.3, minDistance=7, blockSize=7)
        self.contador_reinicio_puntos = 0

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TProgressbar", thickness=18, background=self.color_success, troughcolor="#e9ecef")

        self.construir_interfaz()

    # ============================================================================
    # MÉTODOS PARA EL TEMPORIZADOR DE SESIÓN
    # ============================================================================
    def iniciar_temporizador_sesion(self):
        if self.temporizador_activo:
            return
        self.tiempo_inicio_sesion = time.time()
        self.temporizador_activo = True
        self.actualizar_temporizador()

    def actualizar_temporizador(self):
        if not self.temporizador_activo:
            return
        tiempo_transcurrido = time.time() - self.tiempo_inicio_sesion
        horas = int(tiempo_transcurrido // 3600)
        minutos = int((tiempo_transcurrido % 3600) // 60)
        segundos = int(tiempo_transcurrido % 60)
        tiempo_str = f"{horas:02d}:{minutos:02d}:{segundos:02d}"
        self.lbl_tiempo_sesion.config(text=f"⏱ {tiempo_str}")
        self.id_temporizador = self.root.after(1000, self.actualizar_temporizador)

    def detener_temporizador_sesion(self):
        if self.id_temporizador:
            self.root.after_cancel(self.id_temporizador)
            self.id_temporizador = None
        self.temporizador_activo = False
        self.lbl_tiempo_sesion.config(text="⏱ 00:00:00")

    def reiniciar_temporizador_sesion(self):
        self.detener_temporizador_sesion()
        self.iniciar_temporizador_sesion()

    # ============================================================================
    # GOOGLE DRIVE CON REQUESTS DIRECTO
    # ============================================================================
    def inicializar_google_drive(self):
        try:
            if os.path.exists(self.TOKEN_FILE):
                with open(self.TOKEN_FILE, 'r') as f:
                    token_data = json.load(f)
                    self.access_token = token_data.get('access_token')
                    if time.time() > token_data.get('expires_at', 0):
                        print("[DRIVE] 🔄 Token expirado, refrescando...")
                        self.refrescar_token(token_data.get('refresh_token'))
                    else:
                        print("[DRIVE] ✓ Token cargado correctamente")
            if not self.access_token:
                self.autenticar_oauth()
            if self.access_token:
                self.GOOGLE_DRIVE_FOLDER_ID = self.buscar_o_crear_carpeta()
                if self.GOOGLE_DRIVE_FOLDER_ID:
                    print(f"[DRIVE] ✓ Carpeta lista: {self.GOOGLE_DRIVE_FOLDER_NAME}")
                    return True
            return False
        except Exception as e:
            print(f"[DRIVE] ❌ Error: {e}")
            return False

    def autenticar_oauth(self):
        try:
            if not os.path.exists(self.CLIENT_SECRET_FILE):
                print(f"[DRIVE] ⚠️ Archivo {self.CLIENT_SECRET_FILE} no encontrado")
                return
            with open(self.CLIENT_SECRET_FILE, 'r') as f:
                client_data = json.load(f)
            client_config = client_data.get('installed', client_data.get('web', {}))
            client_id = client_config['client_id']
            client_secret = client_config['client_secret']
            redirect_uri = 'http://localhost:8080'
            auth_url = 'https://accounts.google.com/o/oauth2/auth'
            params = {
                'client_id': client_id,
                'redirect_uri': redirect_uri,
                'response_type': 'code',
                'scope': 'https://www.googleapis.com/auth/drive.file',
                'access_type': 'offline',
                'prompt': 'consent'
            }
            auth_url_full = f"{auth_url}?{urllib.parse.urlencode(params)}"
            print("[DRIVE] 🌐 Abriendo navegador para autorización...")
            auth_code = None
            
            class AuthHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    nonlocal auth_code
                    query = urllib.parse.urlparse(self.path).query
                    params = urllib.parse.parse_qs(query)
                    if 'code' in params:
                        auth_code = params['code'][0]
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html; charset=utf-8')
                        self.end_headers()
                        self.wfile.write("""
                        <html>
                        <head><meta charset="utf-8"></head>
                        <body style="font-family:Arial;text-align:center;padding:50px;">
                        <h1 style="color:#28a745;">✅ Autorización Exitosa</h1>
                        <p>Ya puedes cerrar esta ventana y volver al Dashboard.</p>
                        </body>
                        </html>
                        """.encode('utf-8'))
                    else:
                        self.send_response(400)
                        self.end_headers()
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                def log_message(self, format, *args):
                    pass
            
            server = HTTPServer(('localhost', 8080), AuthHandler)
            webbrowser.open(auth_url_full)
            print("[DRIVE] ⏳ Esperando autorización en el navegador...")
            server.timeout = 120
            server.handle_request()
            if not auth_code:
                print("[DRIVE] ❌ No se recibió código de autorización")
                return
            print("[DRIVE] ✓ Código recibido, intercambiando por token...")
            token_response = requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'code': auth_code,
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'redirect_uri': redirect_uri,
                    'grant_type': 'authorization_code'
                }
            )
            if token_response.status_code == 200:
                token_data = token_response.json()
                self.access_token = token_data['access_token']
                token_data['expires_at'] = time.time() + token_data.get('expires_in', 3600)
                with open(self.TOKEN_FILE, 'w') as f:
                    json.dump(token_data, f)
                print("[DRIVE] ✅ Autenticación completada exitosamente")
            else:
                print(f"[DRIVE] ❌ Error al obtener token: {token_response.text}")
        except Exception as e:
            print(f"[DRIVE] ❌ Error en autenticación: {e}")

    def refrescar_token(self, refresh_token):
        try:
            with open(self.CLIENT_SECRET_FILE, 'r') as f:
                client_data = json.load(f)
            client_config = client_data.get('installed', client_data.get('web', {}))
            response = requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'client_id': client_config['client_id'],
                    'client_secret': client_config['client_secret'],
                    'refresh_token': refresh_token,
                    'grant_type': 'refresh_token'
                }
            )
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                token_data['refresh_token'] = refresh_token
                token_data['expires_at'] = time.time() + token_data.get('expires_in', 3600)
                with open(self.TOKEN_FILE, 'w') as f:
                    json.dump(token_data, f)
                print("[DRIVE] ✓ Token refrescado")
            else:
                print("[DRIVE] ❌ Error al refrescar token")
                self.access_token = None
        except Exception as e:
            print(f"[DRIVE] ❌ Error al refrescar: {e}")
            self.access_token = None

    def buscar_o_crear_carpeta(self):
        try:
            headers = {'Authorization': f'Bearer {self.access_token}'}
            query = f"name='{self.GOOGLE_DRIVE_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            response = requests.get(
                'https://www.googleapis.com/drive/v3/files',
                headers=headers,
                params={'q': query, 'fields': 'files(id, name)'}
            )
            if response.status_code == 200:
                files = response.json().get('files', [])
                if files:
                    folder_id = files[0]['id']
                    print(f"[DRIVE] ✓ Carpeta encontrada: {files[0]['name']} ({folder_id})")
                    return folder_id
            print(f"[DRIVE] 📁 Creando carpeta '{self.GOOGLE_DRIVE_FOLDER_NAME}'...")
            folder_metadata = {
                'name': self.GOOGLE_DRIVE_FOLDER_NAME,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            response = requests.post(
                'https://www.googleapis.com/drive/v3/files',
                headers=headers,
                json=folder_metadata
            )
            if response.status_code == 200:
                folder_id = response.json()['id']
                print(f"[DRIVE] ✅ Carpeta creada: {folder_id}")
                return folder_id
            else:
                print(f"[DRIVE] ❌ Error al crear carpeta: {response.text}")
                return None
        except Exception as e:
            print(f"[DRIVE] ❌ Error: {e}")
            return None

    def subir_a_google_drive_thread(self, ruta_archivo):
        try:
            if not self.access_token or not self.GOOGLE_DRIVE_FOLDER_ID:
                self.root.after(0, lambda: self.lbl_detalles_clip.config(
                    text="⚠️ Drive no configurado", fg="#e67e22"))
                return
            nombre_archivo = os.path.basename(ruta_archivo)
            print(f"\n[DRIVE] ⬆️ Subiendo: {nombre_archivo}")
            headers = {'Authorization': f'Bearer {self.access_token}'}
            metadata = {'name': nombre_archivo, 'parents': [self.GOOGLE_DRIVE_FOLDER_ID]}
            files = {
                'data': ('metadata', json.dumps(metadata), 'application/json'),
                'file': (nombre_archivo, open(ruta_archivo, 'rb'), 'video/mp4')
            }
            response = requests.post(
                'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart',
                headers=headers, files=files
            )
            if response.status_code == 200:
                file_info = response.json()
                self.root.after(0, lambda: self.lbl_detalles_clip.config(
                    text=f"✅ Drive: {file_info.get('name')}", fg=self.color_success))
            else:
                if response.status_code == 401:
                    self.refrescar_token_simple()
                    if self.access_token:
                        self.subir_a_google_drive_thread(ruta_archivo)
                        return
                self.root.after(0, lambda: self.lbl_detalles_clip.config(
                    text="❌ Error al subir a Drive", fg=self.color_danger))
        except Exception as e:
            print(f"[DRIVE] ❌ Error: {str(e)[:200]}")

    def refrescar_token_simple(self):
        try:
            if os.path.exists(self.TOKEN_FILE):
                with open(self.TOKEN_FILE, 'r') as f:
                    token_data = json.load(f)
                refresh_token = token_data.get('refresh_token')
                if refresh_token:
                    self.refrescar_token(refresh_token)
        except:
            pass

    # ============================================================================
    # INTERFAZ GRÁFICA
    # ============================================================================
    def construir_interfaz(self):
        self.panel_header = tk.Frame(self.root, bg=self.color_btn, pady=12)
        self.panel_header.pack(side=tk.TOP, fill=tk.X)
        tk.Label(self.panel_header, text="MÓDULO DE EXTRACCIÓN DE EVENTOS ANÓMALOS", 
                 bg=self.color_btn, fg="white", font=("Segoe UI", 14, "bold")).pack()

        self.panel_infraestructura = tk.Frame(self.root, bg=self.bg_main)
        self.panel_infraestructura.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=(5, 10))

        self.frame_hw = tk.LabelFrame(self.panel_infraestructura, text=" Telemetría de Recursos ", bg=self.bg_panel, fg=self.text_main, font=("Segoe UI", 10, "bold"), pady=6, padx=12, width=320)
        self.frame_hw.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.frame_hw.pack_propagate(False)
        
        self.lbl_ram = tk.Label(self.frame_hw, text="RAM Proceso: 0.0 MB", bg=self.bg_panel, fg=self.text_main, font=("Consolas", 10, "bold"))
        self.lbl_ram.pack(anchor="w")
        self.lbl_buffer_txt = tk.Label(self.frame_hw, text="Buffer RAM: [ INACTIVO ]", bg=self.bg_panel, fg=self.text_sec, font=("Consolas", 10, "bold"))
        self.lbl_buffer_txt.pack(anchor="w", pady=(2, 0))
        
        self.lbl_drive_status = tk.Label(self.frame_hw, text="Drive: [ ESPERANDO... ]", bg=self.bg_panel, fg=self.text_sec, font=("Consolas", 9))
        self.lbl_drive_status.pack(anchor="w", pady=(4, 0))
        
        if self.access_token:
            self.lbl_drive_status.config(text="Drive: [ CONECTADO ✓ ]", fg=self.color_success)

        self.panel_timeline = tk.LabelFrame(self.panel_infraestructura, text=" Gestión de Memoria y Extracción Automática ", bg=self.bg_panel, fg=self.text_main, font=("Segoe UI", 11, "bold"), pady=6, padx=15)
        self.panel_timeline.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.progress = ttk.Progressbar(self.panel_timeline, orient="horizontal", mode="determinate", maximum=150)
        self.progress.pack(fill=tk.X, padx=10, pady=2)
        
        self.lbl_detalles_clip = tk.Label(self.panel_timeline, text="Esperando inicialización...", bg=self.bg_panel, fg=self.text_sec, font=("Consolas", 11))
        self.lbl_detalles_clip.pack(pady=(2, 0))

        self.main_container = tk.Frame(self.root, bg=self.bg_main)
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        self.col_izq = tk.Frame(self.main_container, bg=self.bg_main, width=620)
        self.col_izq.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.col_izq.pack_propagate(False)

        self.col_der = tk.Frame(self.main_container, bg=self.bg_main)
        self.col_der.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.panel_videos = tk.Frame(self.col_izq, bg=self.bg_main)
        self.panel_videos.pack(fill=tk.BOTH, expand=True)
        
        img_negra = np.zeros((self.VID_H, self.VID_W, 3), dtype=np.uint8)
        self.img_placeholder = ImageTk.PhotoImage(Image.fromarray(img_negra))

        self.marco_orig = tk.LabelFrame(self.panel_videos, text=" Cámara Principal (RGB) ", bg=self.bg_panel, fg=self.text_main, font=("Segoe UI", 10, "bold"), pady=5)
        self.marco_orig.pack(fill=tk.X, pady=(0, 5))
        self.lbl_orig = tk.Label(self.marco_orig, bg="#000000", image=self.img_placeholder)
        self.lbl_orig.pack(pady=5)

        self.marco_flow = tk.LabelFrame(self.panel_videos, text=" Cinemática (Flujo Óptico Disperso LK) ", bg=self.bg_panel, fg=self.text_main, font=("Segoe UI", 10, "bold"), pady=5)
        self.marco_flow.pack(fill=tk.X, pady=4)
        self.lbl_flow = tk.Label(self.marco_flow, bg="#000000", image=self.img_placeholder)
        self.lbl_flow.pack(pady=5)

        self.panel_controles = tk.Frame(self.col_der, bg=self.bg_panel, bd=1, relief="ridge", pady=12, padx=12)
        self.panel_controles.pack(fill=tk.X, pady=(0, 10))
        self.panel_controles.columnconfigure(0, weight=1)
        self.panel_controles.columnconfigure(1, weight=1)
        self.panel_controles.columnconfigure(2, weight=1)

        self.frame_zona_botones = tk.Frame(self.panel_controles, bg=self.bg_panel)
        self.frame_zona_botones.grid(row=0, column=0, sticky="w")
        tk.Label(self.frame_zona_botones, text="COMANDOS", bg=self.bg_panel, fg=self.text_sec, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        
        self.frame_fila_unica = tk.Frame(self.frame_zona_botones, bg=self.bg_panel)
        self.frame_fila_unica.pack(fill=tk.X)
        tk.Button(self.frame_fila_unica, text="📁 Archivo", command=self.cargar_video, font=("Segoe UI", 9, "bold"), bg=self.color_btn, fg="white", relief="flat", width=9, pady=4).pack(side=tk.LEFT, padx=1)
        tk.Button(self.frame_fila_unica, text="📹 Cámara", command=self.iniciar_camara, font=("Segoe UI", 9, "bold"), bg=self.color_info, fg="white", relief="flat", width=9, pady=4).pack(side=tk.LEFT, padx=1)
        tk.Button(self.frame_fila_unica, text="⏹ Detener", command=self.detener, font=("Segoe UI", 9, "bold"), bg=self.color_danger, fg="white", relief="flat", width=9, pady=4).pack(side=tk.LEFT, padx=1)
        tk.Button(self.frame_fila_unica, text="📂 Carpeta", command=self.abrir_carpeta_evidencias, font=("Segoe UI", 9, "bold"), bg=self.color_folder, fg="white", relief="flat", width=9, pady=4).pack(side=tk.LEFT, padx=1)

        self.frame_info_sesion = tk.Frame(self.panel_controles, bg="#e9ecef", bd=1, relief="solid", padx=10, pady=6)
        self.frame_info_sesion.grid(row=0, column=1, sticky="nsew", padx=15)
        
        tk.Label(self.frame_info_sesion, text="INFORMACIÓN DE SESIÓN", bg="#e9ecef", fg=self.text_sec, font=("Segoe UI", 8, "bold")).pack(anchor="center")
        
        self.lbl_tipo_video = tk.Label(self.frame_info_sesion, text="📹 SIN FUENTE", bg="#e9ecef", fg=self.text_sec, font=("Segoe UI", 12, "bold"))
        self.lbl_tipo_video.pack(anchor="center", pady=(5, 2))
        
        self.lbl_tiempo_sesion = tk.Label(self.frame_info_sesion, text="⏱ 00:00:00", bg="#e9ecef", fg=self.color_btn, font=("Segoe UI", 14, "bold"))
        self.lbl_tiempo_sesion.pack(anchor="center", pady=(2, 0))

        self.card_evidencias = tk.Frame(self.panel_controles, bg=self.color_card_bg, bd=1, relief="solid", padx=15, pady=6)
        self.card_evidencias.grid(row=0, column=2, sticky="e")
        tk.Label(self.card_evidencias, text="CONTADOR DE EVENTOS", bg=self.color_card_bg, fg=self.text_sec, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.lbl_card_total = tk.Label(self.card_evidencias, text=f"Total: {self.evidencias_totales}", bg=self.color_card_bg, fg="#d35400", font=("Segoe UI", 11, "bold"))
        self.lbl_card_total.pack(anchor="w", pady=1)
        self.lbl_card_sesion = tk.Label(self.card_evidencias, text=f"Sesión: {self.evidencias_sesion}", bg=self.color_card_bg, fg=self.text_main, font=("Segoe UI", 10, "bold"))
        self.lbl_card_sesion.pack(anchor="w")

        self.panel_graficas = tk.LabelFrame(self.col_der, text=" Inspección Analítica de Ondas Cinemáticas ", bg=self.bg_panel, fg=self.text_main, font=("Segoe UI", 11, "bold"), pady=5, padx=5)
        self.panel_graficas.pack(fill=tk.BOTH, expand=True)
        
        self.frame_toolbar_custom = tk.Frame(self.panel_graficas, bg=self.bg_main, pady=4, padx=6, bd=1, relief="solid")
        self.frame_toolbar_custom.pack(fill=tk.X, side=tk.TOP, pady=(0, 5))
        
        tk.Button(self.frame_toolbar_custom, text="🏠 Restablecer", command=self.restablecer_vista, font=("Segoe UI", 9, "bold"), bg=self.color_folder, fg="white", relief="flat", padx=12).pack(side=tk.LEFT, padx=2)
        
        self.var_modo_grafica = tk.StringVar(value="ventana") 
        tk.Radiobutton(self.frame_toolbar_custom, text="Últimos 15s", variable=self.var_modo_grafica, value="ventana", bg=self.bg_main, fg=self.text_main, font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT, padx=5)
        tk.Radiobutton(self.frame_toolbar_custom, text="Historial", variable=self.var_modo_grafica, value="historico", bg=self.bg_main, fg=self.text_main, font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT, padx=5)

        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(4, 6.5))
        self.fig.patch.set_facecolor(self.bg_panel)
        self.fig.subplots_adjust(hspace=0.35, left=0.12, right=0.95, top=0.95, bottom=0.14)

        self.line_mag, = self.ax1.plot([], [], color='#007BFF', linewidth=1.8, label='Magnitud')
        self.line_umbral_mag, = self.ax1.plot([], [], color='#DC3545', linestyle='--', linewidth=1.5, label='Umbral')
        self.scatter_mag = self.ax1.scatter([], [], color='#e67e22', s=80, zorder=5)
        self.ax1.set_facecolor('#f8f9fa')
        self.ax1.tick_params(colors=self.text_main, labelsize=9)
        self.ax1.grid(color='#e0e0e0', linestyle='-', linewidth=0.5)
        self.ax1.legend(loc='upper left', fontsize=9)
        self.ax1.set_ylabel("Magnitud", color=self.text_main, fontsize=10, fontweight='bold')
        self.ax1.set_xlabel("Frames", color=self.text_main, fontsize=10, fontweight='bold')

        self.line_var, = self.ax2.plot([], [], color='#6f42c1', linewidth=1.8, label='Varianza')
        self.line_umbral_var, = self.ax2.plot([], [], color='#DC3545', linestyle='--', linewidth=1.5, label='Umbral')
        self.scatter_var = self.ax2.scatter([], [], color='#e67e22', s=80, zorder=5)
        self.ax2.set_facecolor('#f8f9fa')
        self.ax2.tick_params(colors=self.text_main, labelsize=9)
        self.ax2.grid(color='#e0e0e0', linestyle='-', linewidth=0.5)
        self.ax2.legend(loc='upper left', fontsize=9)
        self.ax2.set_ylabel("Varianza", color=self.text_main, fontsize=10, fontweight='bold')
        self.ax2.set_xlabel("Frames", color=self.text_main, fontsize=10, fontweight='bold')

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.panel_graficas)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.canvas.mpl_connect('scroll_event', self.evento_zoom_scroll)
        self.canvas.mpl_connect('button_press_event', self.evento_click_presionado)
        self.canvas.mpl_connect('button_release_event', self.evento_click_liberado)
        self.canvas.mpl_connect('motion_notify_event', self.evento_mouse_movimiento)

        self.toolbar_oculta = NavigationToolbar2Tk(self.canvas, self.root)
        self.toolbar_oculta.pack_forget()

    def actualizar_indicador_tipo_video(self):
        if self.modo_video == "EN VIVO":
            self.lbl_tipo_video.config(text="🔴 EN VIVO", fg=self.color_danger, bg="#f8d7da")
            self.frame_info_sesion.config(bg="#f8d7da")
        elif self.modo_video == "DIFERIDO":
            self.lbl_tipo_video.config(text="🎬 VIDEO DIFERIDO", fg=self.color_btn, bg="#d1ecf1")
            self.frame_info_sesion.config(bg="#d1ecf1")
        else:
            self.lbl_tipo_video.config(text="📹 SIN FUENTE", fg=self.text_sec, bg="#e9ecef")
            self.frame_info_sesion.config(bg="#e9ecef")

    def evento_zoom_scroll(self, event):
        if event.inaxes is None: return
        ax = event.inaxes
        scale = 1/1.25 if event.button == 'up' else 1.25
        xl, yl = ax.get_xlim(), ax.get_ylim()
        xr, yr = xl[1]-xl[0], yl[1]-yl[0]
        px = (event.xdata-xl[0])/xr
        py = (event.ydata-yl[0])/yr
        nx, ny = xr*scale, yr*scale
        ax.set_xlim([event.xdata-nx*px, event.xdata+nx*(1-px)])
        ax.set_ylim([max(0, event.ydata-ny*py), event.ydata+ny*(1-py)])
        self.modo_manual = True
        self.canvas.draw_idle()

    def evento_click_presionado(self, event):
        if event.inaxes and event.button == 1:
            self.modo_manual = True
            self.mouse_presionado = True
            self.mouse_ultimo_x = event.xdata
            self.mouse_ultimo_y = event.ydata

    def evento_click_liberado(self, event):
        self.mouse_presionado = False

    def evento_mouse_movimiento(self, event):
        if not self.mouse_presionado or not event.inaxes or event.xdata is None: return
        ax = event.inaxes
        ax.set_xlim([ax.get_xlim()[0]-(event.xdata-self.mouse_ultimo_x), ax.get_xlim()[1]-(event.xdata-self.mouse_ultimo_x)])
        ax.set_ylim([ax.get_ylim()[0]-(event.ydata-self.mouse_ultimo_y), ax.get_ylim()[1]-(event.ydata-self.mouse_ultimo_y)])
        self.mouse_ultimo_x, self.mouse_ultimo_y = event.xdata, event.ydata
        self.canvas.draw_idle()

    def restablecer_vista(self):
        self.modo_manual = False
        self.mouse_presionado = False
        self.toolbar_oculta.home()

    def abrir_carpeta_evidencias(self):
        try:
            ruta = os.path.abspath(self.carpeta_salida)
            if sys.platform == "win32": os.startfile(ruta)
            elif sys.platform == "darwin": __import__('subprocess').Popen(["open", ruta])
            else: __import__('subprocess').Popen(["xdg-open", ruta])
        except: pass

    def detener(self):
        self.procesando = False        
        if self.cap: self.cap.release()
        if self.video_writer: self.video_writer.release(); self.video_writer = None
        self.detener_temporizador_sesion()
        self.modo_video = None
        self.actualizar_indicador_tipo_video()
        self.lbl_buffer_txt.config(text="Buffer RAM: [ INACTIVO ]", fg=self.text_sec)
        self.grabando = False
        self.puntos_previos = None
        self.marco_orig.config(text=" Cámara Principal (RGB) ")
        self.marco_flow.config(text=" Cinemática (Flujo Óptico Disperso LK) ")

    def actualizar_ui_evidencias(self):
        self.lbl_card_total.config(text=f"Total: {self.evidencias_totales}")
        self.lbl_card_sesion.config(text=f"Sesión: {self.evidencias_sesion}")

    def limpiar_variables_inicio(self):
        self.historial_mag, self.historial_var = [], []
        self.historial_umbral_mag, self.historial_umbral_var = [], []
        self.memoria_mag.clear()
        self.memoria_var.clear()
        self.buffer_circular.clear()
        self.frames_buffer_congelado = []
        self.puntos_disparo_x, self.puntos_disparo_y_mag, self.puntos_disparo_y_var = [], [], []
        self.frames_procesados = 0
        self.grabando = False
        self.modo_manual = False
        self.evidencias_sesion = 0
        self.frames_pre_usados = 0
        self.frames_post_pendientes = 0
        self.puntos_previos = None
        self.contador_reinicio_puntos = 0
        self.actualizar_ui_evidencias()
        self.progress['value'] = 0
        self.lbl_buffer_txt.config(text="Buffer RAM: [ CALIBRANDO ]", fg=self.text_sec)

    def cargar_video(self):
        path = filedialog.askopenfilename()
        if path:
            self.modo_video = "DIFERIDO"
            self.actualizar_indicador_tipo_video()
            self.reiniciar_temporizador_sesion()
            self.limpiar_variables_inicio()
            self.cap = cv2.VideoCapture(path)
            self.iniciar_flujo()

    def iniciar_camara(self):
        self.modo_video = "EN VIVO"
        self.actualizar_indicador_tipo_video()
        self.reiniciar_temporizador_sesion()
        self.limpiar_variables_inicio()
        self.cap = cv2.VideoCapture(1) #camara
        if not self.cap.isOpened(): 
            self.lbl_tipo_video.config(text="❌ ERROR CÁMARA", fg=self.color_danger)
            return
        self.iniciar_flujo()

    def iniciar_flujo(self):
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps_actual = fps if fps and fps > 0 else 30.0
        self.MAX_FRAMES_BUFFER = int(self.fps_actual * self.SEGUNDOS_PRE)
        self.FRAMES_POST_NECESARIOS = int(self.fps_actual * self.SEGUNDOS_POST)
        self.TOTAL_FRAMES_CLIP = self.MAX_FRAMES_BUFFER + self.FRAMES_POST_NECESARIOS
        print(f"[CONFIG] FPS:{self.fps_actual:.1f} PRE:{self.MAX_FRAMES_BUFFER}f POST:{self.FRAMES_POST_NECESARIOS}f TOTAL:{self.TOTAL_FRAMES_CLIP}f=5.00s")
        self.buffer_circular = deque(maxlen=self.MAX_FRAMES_BUFFER)
        self.progress.configure(maximum=self.TOTAL_FRAMES_CLIP)
        ret, f = self.cap.read()
        if f is not None:
            tipo_video = self.modo_video if self.modo_video else "DESCONOCIDO"
            self.marco_orig.config(text=f" Cámara Principal (RGB) -- [ {tipo_video} | FPS: {self.fps_actual:.1f} ]")
            self.marco_flow.config(text=f" Cinemática (Flujo Óptico Disperso LK) -- [ {tipo_video} | FPS: {self.fps_actual:.1f} ]")
            f = cv2.resize(f, (self.VID_W, self.VID_H))
            self.prvs = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            self.hsv = np.zeros_like(f)
            self.hsv[..., 1] = 255
            self.procesando = True
            self.actualizar()

    def iniciar_extraccion(self, vm, vv):
        self.grabando = True
        self.frames_grabados_post = 0
        frames_en_buffer = len(self.buffer_circular)
        self.frames_pre_usados = min(frames_en_buffer, self.MAX_FRAMES_BUFFER)
        self.frames_post_pendientes = self.TOTAL_FRAMES_CLIP - self.frames_pre_usados
        self.frames_buffer_congelado = list(self.buffer_circular)[-self.frames_pre_usados:]
        print(f"[EXTRACCIÓN] PRE:{self.frames_pre_usados}f POST:{self.frames_post_pendientes}f TOTAL:{self.frames_pre_usados + self.frames_post_pendientes}f=5s")
        self.puntos_disparo_x.append(self.frames_procesados)
        self.puntos_disparo_y_mag.append(vm)
        self.puntos_disparo_y_var.append(vv)
        ts = time.strftime("%Y%m%d-%H%M%S")
        self.nombre_archivo_actual = f"{self.carpeta_salida}/Evento_Cinematico_5seg_{ts}.mp4"
        self.video_writer = cv2.VideoWriter(self.nombre_archivo_actual, cv2.VideoWriter_fourcc(*'mp4v'), self.fps_actual, (self.VID_W, self.VID_H))
        for f in self.frames_buffer_congelado:
            self.video_writer.write(f)
        self.progress['value'] = len(self.frames_buffer_congelado)

    def detener_extraccion(self):
        self.grabando = False
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            t = len(self.frames_buffer_congelado) + self.frames_grabados_post
            print(f"[EXTRACCIÓN] ✓ Clip:{t}f={t/self.fps_actual:.2f}s")
        self.frames_buffer_congelado = []
        self.evidencias_sesion += 1
        self.evidencias_totales += 1
        self.actualizar_ui_evidencias()
        self.lbl_detalles_clip.config(text="✓ Clip 5s. Subiendo a Drive...", fg=self.color_btn)
        threading.Thread(target=self.subir_a_google_drive_thread, args=(self.nombre_archivo_actual,), daemon=True).start()
        self.buffer_circular.clear()
        self.progress['value'] = 0

    def actualizar(self):
        if not self.procesando: return
        ret, frame = self.cap.read()
        if not ret:
            if self.grabando: self.detener_extraccion()
            self.lbl_tipo_video.config(text="● FIN DEL VIDEO", fg=self.text_sec)
            self.detener_temporizador_sesion()
            return

        frame_res = cv2.resize(frame, (self.VID_W, self.VID_H))
        next_f = cv2.cvtColor(frame_res, cv2.COLOR_BGR2GRAY)
        
        # === SIEMPRE guardar en buffer ===
        self.buffer_circular.append(frame_res.copy())
        
        # ===================================================================
        # === FLUJO ÓPTICO DISPERSO (Lucas-Kanade) - MUCHO MÁS RÁPIDO ===
        # ===================================================================
        
        # Reiniciar puntos cada 15 frames o si no hay puntos
        self.contador_reinicio_puntos += 1
        if self.puntos_previos is None or self.contador_reinicio_puntos >= 15:
            self.puntos_previos = cv2.goodFeaturesToTrack(next_f, mask=None, **self.feature_params)
            self.contador_reinicio_puntos = 0
        
        # Calcular flujo óptico solo en los puntos detectados
        if self.puntos_previos is not None and len(self.puntos_previos) > 0:
            puntos_nuevos, status, _ = cv2.calcOpticalFlowPyrLK(
                self.prvs, next_f, self.puntos_previos, None, **self.lk_params)
            
            if puntos_nuevos is not None:
                # Filtrar puntos válidos
                puntos_buenos_nuevos = puntos_nuevos[status == 1]
                puntos_buenos_viejos = self.puntos_previos[status == 1]
                
                if len(puntos_buenos_nuevos) > 10:
                    # Calcular vectores de movimiento
                    movimientos = puntos_buenos_nuevos - puntos_buenos_viejos
                    magnitudes = np.sqrt(movimientos[:, 0]**2 + movimientos[:, 1]**2)
                    angulos = np.arctan2(movimientos[:, 1], movimientos[:, 0])
                    
                    mp = np.mean(magnitudes)
                    vc = np.var(magnitudes)
                    
                    # Actualizar puntos para siguiente frame
                    self.puntos_previos = puntos_buenos_nuevos.reshape(-1, 1, 2)
                else:
                    mp, vc = 0.0, 0.0
                    self.puntos_previos = None
            else:
                mp, vc = 0.0, 0.0
                self.puntos_previos = None
        else:
            mp, vc = 0.0, 0.0
        
        # ===================================================================
        
        # === SIEMPRE actualizar estadísticas ===
        self.memoria_mag.append(mp)
        self.memoria_var.append(vc)
        
        if len(self.memoria_mag) > 30:
            um = np.mean(self.memoria_mag) + self.K_MAG * np.std(self.memoria_mag)
            uv = np.mean(self.memoria_var) + self.K_VAR * np.std(self.memoria_var)
            um = max(um, self.PISO_MIN_MAG)
            uv = max(uv, self.PISO_MIN_VAR)
        else:
            um, uv = 10.0, 30.0

        # === MODO GRABACIÓN ===
        if self.grabando:
            self.video_writer.write(frame_res)
            self.frames_grabados_post += 1
            p = len(self.frames_buffer_congelado) + self.frames_grabados_post
            self.progress['value'] = p
            self.lbl_detalles_clip.config(text=f"Ensamblando: {p}/{self.TOTAL_FRAMES_CLIP}f={p/self.fps_actual:.2f}s/5s", fg=self.color_danger)
            if self.frames_grabados_post >= self.frames_post_pendientes:
                self.detener_extraccion()
        
        # === MODO MONITOREO (DETECCIÓN SIEMPRE ACTIVA) ===
        else:
            n = len(self.buffer_circular)
            self.progress['value'] = n
            self.lbl_buffer_txt.config(text=f"Buffer: [{'LLENANDO' if n<self.MAX_FRAMES_BUFFER else 'ESTABLE'} {n}/{self.MAX_FRAMES_BUFFER}]", fg="#e67e22" if n<self.MAX_FRAMES_BUFFER else self.color_success)
            
            if len(self.memoria_mag) > 30 and (mp > um or vc > uv):
                self.iniciar_extraccion(mp, vc)

        # === ACTUALIZAR UI ===
        self.lbl_ram.config(text=f"RAM: {self.proceso_actual.memory_info().rss/(1024*1024):.1f} MB")
        self.frames_procesados += 1
        self.historial_mag.append(mp)
        self.historial_var.append(vc)
        self.historial_umbral_mag.append(um)
        self.historial_umbral_var.append(uv)
        
        xd = list(range(self.frames_procesados))
        self.line_mag.set_data(xd, self.historial_mag)
        self.line_umbral_mag.set_data(xd, self.historial_umbral_mag)
        self.line_var.set_data(xd, self.historial_var)
        self.line_umbral_var.set_data(xd, self.historial_umbral_var)
        if self.puntos_disparo_x:
            self.scatter_mag.set_offsets(np.c_[self.puntos_disparo_x, self.puntos_disparo_y_mag])
            self.scatter_var.set_offsets(np.c_[self.puntos_disparo_x, self.puntos_disparo_y_var])

        if not self.modo_manual:
            md = self.var_modo_grafica.get()
            li = self.frames_procesados-self.ANCHO_VENTANA_GRAFICA if md=="ventana" and self.frames_procesados>self.ANCHO_VENTANA_GRAFICA else 0
            ld = self.frames_procesados if md=="ventana" else max(10, self.frames_procesados)
            self.ax1.set_xlim(li, ld)
            self.ax2.set_xlim(li, ld)
            if self.frames_procesados>0:
                m1=max(max(self.historial_mag[li:ld] or [1]), max(self.historial_umbral_mag[li:ld] or [1]))*1.2+1
                m2=max(max(self.historial_var[li:ld] or [1]), max(self.historial_umbral_var[li:ld] or [1]))*1.2+1
                self.ax1.set_ylim(0,m1)
                self.ax2.set_ylim(0,m2)

        self.canvas.draw_idle()
        
        # Visualización del flujo disperso (puntos y líneas)
        vis_frame = frame_res.copy()
        if self.puntos_previos is not None and len(self.puntos_previos) > 0:
            for i, punto in enumerate(self.puntos_previos):
                x, y = punto.ravel()
                cv2.circle(vis_frame, (int(x), int(y)), 3, (0, 255, 0), -1)
        
        self.lbl_orig.img = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(frame_res, cv2.COLOR_BGR2RGB)))
        self.lbl_flow.img = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(vis_frame, cv2.COLOR_BGR2RGB)))
        self.lbl_orig.configure(image=self.lbl_orig.img)
        self.lbl_flow.configure(image=self.lbl_flow.img)
        self.prvs = next_f
        self.root.after(5, self.actualizar)

if __name__ == "__main__":
    root = tk.Tk()
    app = DashboardTesisV28_CommandCenterPro(root)
    root.mainloop()