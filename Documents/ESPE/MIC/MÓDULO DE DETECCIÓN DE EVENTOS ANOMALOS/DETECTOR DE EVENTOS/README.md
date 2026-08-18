================================================================================
  MÓDULO DE DETECCIÓN DE EVENTOS ANÓMALOS EN VIDEO URBANO (EDGE COMPUTING)
  Trabajo de Integración Curricular - Universidad de las Fuerzas Armadas ESPE
  Autor: Cesar Leonardo Lapo Chamba
  Director: Dr. Wilbert G. Aguilar
  Año: 2026
================================================================================

1. DESCRIPCIÓN DEL PROYECTO
---------------------------
Este software es un módulo de análisis cinemático en tiempo real diseñado para la
detección proactiva de eventos anómalos en secuencias de video urbano (en vivo o
diferido). 

Utiliza un enfoque de Flujo Óptico Disperso (Lucas-Kanade Piramidal con detección 
de esquinas de Shi-Tomasi) y modelos estadísticos adaptativos con pisos mínimos. 
Incluye una memoria temporal mediante búfer circular en RAM (anti-ceguera) que 
extrae automáticamente clips de 5 segundos (2 s pre-evento + 3 s post-evento) y 
los sincroniza de forma asíncrona con Google Drive a través de su API REST.

2. REQUISITOS DEL SISTEMA Y HARDWARE
-----------------------------------
- Sistema Operativo: Windows 10/11, macOS o Linux (Ubuntu 20.04+).
- Procesador: Intel Core i5/i7 o AMD Ryzen 5/7 (No requiere GPU dedicada).
- Memoria RAM: Mínimo 8 GB (Recomendado 16 GB DDR4/DDR5).
- Cámara web o conexión IP (Opcional, para monitoreo en vivo).
- Conexión a Internet (Para la sincronización inicial y subida a la nube).
- Entorno de Ejecución: Python versión 3.10 o superior.

3. ESTRUCTURA DEL PROYECTO
--------------------------
directorio_proyecto/
│
├── main.py                    # Script principal de la aplicación / Interfaz GUI
├── drive_service.py           # Módulo de autenticación y subida a Google Drive
├── requirements.txt           # Archivo de dependencias de Python
├── credentials.json           # Credenciales cliente OAuth 2.0 (Google Cloud)
├── drive_token.json           # Token de acceso generado automáticamente
├── Eventos_Extraidos/         # Carpeta local de almacenamiento de clips MP4
└── README.txt                 # Este manual de instrucciones

4. INSTALACIÓN Y CONFIGURACIÓN DEL ENTORNO
------------------------------------------
Paso 1: Clonar o descargar el repositorio
  Extraiga el archivo ZIP del proyecto en una carpeta local (ejemplo: C:\Tesis_Lapo_Detection).

Paso 2: Abrir una terminal de comandos
  En Windows, abra CMD o PowerShell en la carpeta del proyecto.

Paso 3: Crear y activar un entorno virtual (Recomendado)
  - En Windows:
      python -m venv venv
      .\venv\Scripts\activate
  - En Linux/macOS:
      python3 -m venv venv
      source venv/bin/activate

Paso 4: Instalación de dependencias
  Con el entorno virtual activo, ejecute el siguiente comando:
      pip install -r requirements.txt

  * Las librerías principales que se instalarán son:
    - opencv-python == 4.8.x
    - numpy == 1.24.x
    - matplotlib == 3.7.x
    - requests == 2.31.x
    - google-auth-oauthlib
    - google-api-python-client

5. CONFIGURACIÓN DE LA API DE GOOGLE DRIVE (NUBE)
-------------------------------------------------
Para habilitar la subida automática asíncrona a la nube:

1. Ingrese a Google Cloud Console (https://console.cloud.google.com/).
2. Cree un proyecto nuevo y habilite la API "Google Drive API".
3. Configure la pantalla de consentimiento OAuth (Tipo: Aplicación de Escritorio).
4. Cree una credencial de tipo "ID de cliente OAuth 2.0".
5. Descargue el archivo JSON generado, renómbrelo exactamente a "credentials.json"
   y colóquelo en la raíz de la carpeta del proyecto.
6. La primera vez que el programa intente subir un video, se abrirá una ventana 
   del navegador solicitando autorización. Otorgue los permisos. El sistema 
   guardará el token de acceso en "drive_token.json" para no volver a pedirlo.

6. INSTRUCCIONES DE EJECUCIÓN
-----------------------------
1. Asegúrese de tener activo el entorno virtual (`venv`).
2. Ejecute el script principal con el siguiente comando:
      python main.py

3. Uso de la Interfaz Gráfica (Tkinter):
   - Modo Archivo (Diferido): Haga clic en el botón "Archivo" y seleccione un
     video de prueba en formato MP4 o AVI.
   - Modo Cámara (En vivo): Conecte una cámara local o teléfono e ingrese el 
     índice de dispositivo (ej. 0 para cámara web integrada o URL de cámara IP).
   - Monitoreo en Tiempo Real: Observe la ventana gráfica con los gráficos de 
     Magnitud y Varianza cinemática ajustándose dinámicamente.
   - Detención: Presione el botón "Detener" o cierre la ventana principal para 
     liberar los recursos de video de forma segura.

7. SALIDA DEL SISTEMA Y EVIDENCIAS
----------------------------------
- Clips locales: Cada evento detectado se guardará en la carpeta `Eventos_Extraidos/`
  con el formato de nombre: `Evento_Cinematico_5seg_YYYYMMDD-HHMMSS.mp4`.
- Sincronización en la Nube: El sistema creará automáticamente la carpeta 
  `Eventos_Anómalos` en la raíz de su Google Drive y subirá el clip en segundo
  plano sin pausar la adquisición de video local.

8. CONTACTO Y SOPORTE
---------------------
Desarrollador: Cesar Leonardo Lapo Chamba
Correo institucional: cllapo@espe.edu.ec / cesar.lapo0@gmail.com
Universidad de las Fuerzas Armadas ESPE
Sangolquí - Ecuador, 2026.
================================================================================





