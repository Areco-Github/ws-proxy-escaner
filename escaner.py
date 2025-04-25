import socket
import sys
import time
import threading
import requests
import os
import json
import itertools
import shutil

config_path = "config.json"
cdn_host = ""
proxy_host = None
proxy_port = 0
encontrados = []
lock = threading.Lock()

# Animación global
def animacion(titulo, stop_event):
    for c in itertools.cycle(['|', '/', '-', '\\']):
        if stop_event.is_set():
            break
        sys.stdout.write(f"\r{titulo} {c}")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write("\r" + " " * shutil.get_terminal_size().columns + "\r")

# Recibir contenido completo del socket
def recibir_completo(sock):
    data = b""
    try:
        while True:
            parte = sock.recv(2048)
            if not parte:
                break
            data += parte
    except socket.timeout:
        pass
    return data.decode(errors="ignore")

# Detectar tipo de servidor
def detectar_servidor(headers):
    headers = headers.lower()
    if "cloudfront" in headers:
        return "CloudFront"
    elif "cloudflare" in headers:
        return "Cloudflare"
    elif "akamai" in headers:
        return "Akamai"
    elif "nginx" in headers:
        return "Nginx"
    elif "apache" in headers:
        return "Apache"
    elif "gws" in headers or "google" in headers:
        return "Google"
    elif "microsoft" in headers or "iis" in headers:
        return "Microsoft-IIS"
    else:
        return "Desconocido"

# Probar conexión a host
def probar_host(host, timeout, detectar_tipo=False):
    try:
        s = socket.socket()
        s.settimeout(timeout)

        if proxy_host:
            s.connect((proxy_host, proxy_port))
            s.sendall(f"OPTIONS / HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
            time.sleep(0.2)
            s.sendall(
                f"GET / HTTP/1.1\r\n"
                f"Host: {cdn_host}\r\n"
                f"Connection: Upgrade\r\n"
                f"Upgrade: websocket\r\n\r\n".encode()
            )
        else:
            s.connect((host, 80))
            s.sendall(
                f"GET / HTTP/1.1\r\n"
                f"Host: {cdn_host}\r\n"
                f"Connection: Upgrade\r\n"
                f"Upgrade: websocket\r\n\r\n".encode()
            )

        r = recibir_completo(s)
        s.close()

        if "101" in r:
            tipo = detectar_servidor(r) if detectar_tipo else ""
            with lock:
                encontrados.append(f"{host} {'| ' + tipo if tipo else ''}")
            print(f"[✔] {host} | WebSocket funcional (101) {'| ' + tipo if tipo else ''}")
        else:
            print(f"[✘] {host} | Sin 101 - {r.splitlines()[0] if 'HTTP/' in r else 'Sin status HTTP'}")

    except socket.timeout:
        print(f"[✘] {host} | Timeout")
    except Exception as e:
        print(f"[✘] {host} | Error: {str(e)}")

# Escaneo simple secuencial
def escaneo_simple(hosts, timeout, detectar_tipo=False):
    for host in hosts:
        probar_host(host, timeout, detectar_tipo)

# Escaneo multihilo
def escaneo_multihilo(hosts, timeout):
    hilos = []
    for host in hosts:
        t = threading.Thread(target=probar_host, args=(host, timeout))
        t.start()
        hilos.append(t)
    for h in hilos:
        h.join()

# Validar dominio
def dominio_valido(dominio):
    partes = dominio.strip().split(".")
    return len(partes) >= 2 and all(partes)

# Buscar subdominios en crt.sh
def buscar_subdominios():
    dominio = ""
    while True:
        dominio_input = input(f"Ingrese el dominio para buscar subdominios: ").strip()
        if not dominio_input and dominio:
            dominio_input = dominio
        if dominio_input == "0":
            print("🔙 Volviendo al menú...")
            return
        if not dominio_valido(dominio_input):
            print("❌ Dominio inválido. Asegúrate de ingresar un dominio como 'ejemplo.com'")
            continue
        dominio = dominio_input
        break

    print(f"🔍 Buscando subdominios de {dominio}...")
    stop_event = threading.Event()
    anim = threading.Thread(target=animacion, args=("Buscando", stop_event))
    anim.start()

    try:
        res = requests.get(f"https://crt.sh/?q=%25.{dominio}&output=json", timeout=20)
        datos = res.json()
        subs = set()
        for entry in datos:
            for sub in entry["name_value"].split("\n"):
                if sub.endswith(dominio):
                    subs.add(sub.strip())
        lista = sorted(subs)
        stop_event.set()
        anim.join()
        nombre = input("📁 Nombre del archivo para guardar subdominios (sin .txt): ").strip()
        if nombre:
            os.makedirs("subdominios", exist_ok=True)
            ruta = f"subdominios/{nombre}.txt"
            with open(ruta, "w") as f:
                for s in lista:
                    f.write(s + "\n")
            print(f"✅ Subdominios guardados en {ruta}")
        else:
            print("⚠️ No se especificó nombre de archivo. Subdominios no guardados.")
    except Exception as e:
        stop_event.set()
        anim.join()
        print(f"❌ Error al buscar subdominios: {e}")

# Cargar lista de hosts desde archivo
def cargar_hosts_desde_archivo():
    print("📂 Archivos disponibles en carpeta subdominios:")
    archivos = [f for f in os.listdir("subdominios") if f.endswith(".txt")]
    if not archivos:
        print("❌ No hay archivos en subdominios/. Primero genera algunos desde la opción 2.")
        return []
    for i, archivo in enumerate(archivos):
        print(f"{i + 1}. {archivo}")
    op = input("👉 Elige un archivo por número: ").strip()
    try:
        idx = int(op) - 1
        if 0 <= idx < len(archivos):
            ruta = os.path.join("subdominios", archivos[idx])
            with open(ruta) as f:
                return [line.strip() for line in f if line.strip()]
        else:
            print("❌ Índice fuera de rango.")
            return []
    except:
        print("❌ Entrada inválida.")
        return []

# Mostrar configuración actual
def mostrar_configuracion():
    print("\n⚙️  Configuración actual:")
    print(f"🔹 CDN Host: {cdn_host or 'No definido'}")
    print(f"🔹 Proxy Host: {proxy_host or 'Sin proxy'}")
    print(f"🔹 Proxy Puerto: {proxy_port if proxy_host else 'N/A'}")

# Selección de tipo de escaneo
def seleccion_tipo_escaneo(hosts):
    print("1. Rápido (Escaneo normal)")
    print("2. Multihilo (Recomendado, varios hosts a la vez)")
    print("3. Completo (Con mas detalles pero lento)")
    modo = input("👉 Tipo de escaneo: ").strip()
    global encontrados
    encontrados = []

    stop_event = threading.Event()
    anim = threading.Thread(target=animacion, args=("Escaneando", stop_event))
    anim.start()

    if modo == "1":
        escaneo_simple(hosts, 2)
    elif modo == "2":
        escaneo_multihilo(hosts, 2)
    elif modo == "3":
        escaneo_simple(hosts, 5, detectar_tipo=True)
    else:
        stop_event.set()
        anim.join()
        print("❌ Opción inválida.")
        return

    stop_event.set()
    anim.join()

    print(f"\n📋 Total: {len(encontrados)} WebSockets encontrados.")
    for h in encontrados:
        print(f" - {h}")

    while True:
        op = input("\n¿Guardar resultados? (1=Sí, 0=Volver): ").strip()
        if op == "1":
            nombre = input("📁 Nombre del archivo (sin .txt): ").strip()
            if nombre:
                os.makedirs("funcionales", exist_ok=True)
                ruta = f"funcionales/{nombre}.txt"
                with open(ruta, "w") as f:
                    for h in encontrados:
                        f.write(h + "\n")
                print(f"📦 Guardado en {ruta}")
            break
        elif op == "0":
            break

# Guardar configuración en archivo
def guardar_config():
    with open(config_path, "w") as f:
        json.dump({
            "cdn_host": cdn_host,
            "proxy_host": proxy_host,
            "proxy_port": proxy_port
        }, f)

# Cargar configuración desde archivo
def cargar_config():
    global cdn_host, proxy_host, proxy_port
    if os.path.isfile(config_path):
        with open(config_path, "r") as f:
            data = json.load(f)
            cdn_host = data.get("cdn_host", "")
            proxy_host = data.get("proxy_host")
            proxy_port = data.get("proxy_port", 80)

# Configurar entorno del escaneo
def configurar_entorno():
    global cdn_host, proxy_host, proxy_port
    cargar_config()

    while True:
        mostrar_configuracion()
        print("\nSeleccione una opción:")
        print("1. Continuar")
        print("2. Modificar configuración")
        print("0. Salir")
        op = input("👉 Opción: ").strip()

        if op == "0":
            print("👋 Cancelado por el usuario.")
            sys.exit()
        elif op == "1" and cdn_host:
            break
        elif op == "2":
            while True:
                mostrar_configuracion()
                print("\n🔧 Modificar configuración:")
                print("1. CDN Host")
                print("2. Proxy Host y Puerto")
                print("3. Solo Puerto Proxy")
                print("0. Volver")
                eleccion = input("👉 ¿Qué desea modificar?: ").strip()

                if eleccion == "0":
                    guardar_config()
                    break
                elif eleccion == "1":
                    nuevo = input("🔹 Introduzca su dominio CDN (0 para volver): ").strip()
                    if nuevo != "0":
                        cdn_host = nuevo
                elif eleccion == "2":
                    nuevo = input("🔹 Proxy host (vacío para desactivar): ").strip()
                    if nuevo:
                        proxy_host = nuevo
                        while True:
                            puerto = input("🔹 Puerto del proxy (1-65535): ").strip()
                            if not puerto:
                                print("❌ El puerto es obligatorio si se usa proxy.")
                                continue
                            try:
                                proxy_port = int(puerto)
                                if 1 <= proxy_port <= 65535:
                                    break
                                else:
                                    print("❌ El puerto debe estar entre 1 y 65535.")
                            except ValueError:
                                print("❌ Puerto inválido. Debe ser un número entero.")
                    else:
                        proxy_host = None
                        proxy_port = None
                elif eleccion == "3":
                    if proxy_host:
                        try:
                            puerto = input("🔹 Puerto del proxy: ").strip()
                            proxy_port = int(puerto)
                            if not (1 <= proxy_port <= 65535):
                                print("❌ El puerto debe estar entre 1 y 65535.")
                                proxy_port = None
                        except ValueError:
                            print("❌ Puerto inválido.")
                    else:
                        print("❗ Define un Proxy Host primero.")
                else:
                    print("❌ Opción inválida.")

# Menú principal
def menu():
    configurar_entorno()
    while True:
        print("\n💡 Menú")
        print("1. Iniciar escaneo de subdominios(usar con datos móviles sin saldo)")
        print("2. Buscar subdominios(necesita conexión a internet)")
        print("0. Salir")
        opcion = input("👉 Opción: ")

        if opcion == "1":
            print("\nSelecciona una opción para escanear subdominios:")
            print("1. Escanear desde una lista introducida por el usuario")
            print("2. Escanear desde los archivos en la carpeta de subdominios")
            subopcion = input("👉 Opción: ")

            if subopcion == "1":
                # Opción para ingresar una lista de subdominios
                print("\nIntroduce la lista de subdominios (cada uno en una nueva línea). Cuando termines, presiona 'Enter' para confirmar.")
                print("Ejemplo:\nappdev.claro.com.py\naprendeconclaro.claro.com.py\n...")
                print("Para terminar, simplemente presiona 'Enter' en una línea vacía.")
                
                # Leer múltiples líneas y separarlas
                subdominios = []
                while True:
                    subdominio = input("👉 Subdominio: ").strip()
                    if subdominio == "":
                        break  # Termina el input cuando se presiona 'Enter' en una línea vacía
                    subdominios.append(subdominio)

                if subdominios:
                    print(f"\nEscaneando {len(subdominios)} subdominios...")
                    seleccion_tipo_escaneo(subdominios)
                else:
                    print("❌ No se ingresaron subdominios.")
            
            elif subopcion == "2":
                # Opción para cargar subdominios desde archivos
                hosts = cargar_hosts_desde_archivo()
                if hosts:
                    seleccion_tipo_escaneo(hosts)
            else:
                print("❌ Opción no válida.")

        elif opcion == "2":
            buscar_subdominios()
        elif opcion == "0":
            print("🔴 Saliendo...")
            break
        else:
            print("❌ Opción no válida.")


if __name__ == "__main__":
    menu()

